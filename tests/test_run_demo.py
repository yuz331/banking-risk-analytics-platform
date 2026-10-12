"""Demo preparation, non-destructive reuse and launcher failure handling."""

import csv
import io
import json
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_demo
from review_alerts import review_history, save_review


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.folder = self.parent / "demo with spaces"

    def prepare(self):
        return run_demo.prepare_demo(self.folder, transactions=1000)

    def database_dump(self, db):
        with closing(sqlite3.connect(db)) as connection:
            return list(connection.iterdump())

    def snapshot_bytes(self):
        return {name: (self.folder / name).read_bytes() for name in run_demo.SNAPSHOT_FILES}

    def test_fresh_preparation_saves_all_four_seeded_scenarios(self):
        result = self.prepare()
        self.assertFalse(result["reused"])
        self.assertTrue(result["snapshot"]["imported"])
        self.assertEqual(result["snapshot"]["transactions"], 1000)
        with (self.folder / "injected_scenarios.csv").open(newline="", encoding="utf-8") as handle:
            scenarios = list(csv.DictReader(handle))
        self.assertEqual({row["rule_id"] for row in scenarios}, {"R001", "R002", "R003", "R004"})
        with closing(sqlite3.connect(result["db_path"])) as connection:
            for scenario in scenarios:
                alerts = connection.execute("SELECT alert_id FROM alerts WHERE rule_id=? AND account_id=?",
                                            (scenario["rule_id"], scenario["account_id"])).fetchall()
                evidence = [set(row[0] for row in connection.execute(
                    "SELECT transaction_id FROM alert_transactions WHERE alert_id=?", alert)) for alert in alerts]
                self.assertTrue(any(set(scenario["transaction_ids"].split("|")).issubset(rows) for rows in evidence))
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(set(path.name for path in self.folder.iterdir()), set(run_demo.SNAPSHOT_FILES))

    def test_repeat_preserves_csvs_alerts_and_review_history(self):
        first = self.prepare()
        with closing(sqlite3.connect(first["db_path"])) as connection:
            alert = connection.execute("SELECT alert_id FROM alerts LIMIT 1").fetchone()[0]
        saved = save_review(first["db_path"], alert, "NO_CONCERN", "Demo reviewer", "Synthetic case explained", None)
        before_dump = self.database_dump(first["db_path"])
        before_files = self.snapshot_bytes()
        with patch("run_demo.create_dataset", side_effect=AssertionError("Reuse must not regenerate CSVs")):
            second = self.prepare()
        self.assertTrue(second["reused"])
        self.assertFalse(second["snapshot"]["imported"])
        self.assertTrue(all(rule["new_alerts"] == 0 for rule in second["rules"]))
        self.assertEqual(before_dump, self.database_dump(second["db_path"]))
        self.assertEqual(before_files, self.snapshot_bytes())
        self.assertEqual(review_history(second["db_path"], alert)[0]["review_id"], saved)

    def test_changed_settings_leave_every_existing_file_unchanged(self):
        self.prepare()
        before = self.snapshot_bytes()
        for count, seed in ((1000, 7), (2000, 42)):
            with self.subTest(count=count, seed=seed), self.assertRaisesRegex(run_demo.DemoError, "different settings"):
                run_demo.prepare_demo(self.folder, transactions=count, seed=seed)
            self.assertEqual(self.snapshot_bytes(), before)

    def test_unowned_or_empty_directory_and_file_are_preserved(self):
        for name in ("empty", "unrelated", "file"):
            target = self.parent / name
            if name == "file":
                target.write_text("keep me", encoding="utf-8")
            else:
                target.mkdir()
                if name == "unrelated":
                    (target / "notes.txt").write_text("keep me", encoding="utf-8")
            with self.subTest(name=name), self.assertRaisesRegex(run_demo.DemoError, "occupied or incomplete"):
                run_demo.prepare_demo(target, transactions=1000)
            if name == "file":
                self.assertEqual(target.read_text(), "keep me")
            else:
                self.assertEqual(sorted(path.name for path in target.iterdir()), [] if name == "empty" else ["notes.txt"])

    def test_incomplete_snapshot_and_invalid_settings_are_preserved(self):
        self.prepare()
        (self.folder / "injected_scenarios.csv").unlink()
        before_db = (self.folder / "banking.db").read_bytes()
        with self.assertRaisesRegex(run_demo.DemoError, "incomplete"):
            self.prepare()
        self.assertEqual((self.folder / "banking.db").read_bytes(), before_db)
        (self.folder / "injected_scenarios.csv").write_text("restored placeholder", encoding="utf-8")
        (self.folder / run_demo.SETTINGS_FILE).write_text("invalid json", encoding="utf-8")
        with self.assertRaisesRegex(run_demo.DemoError, "Cannot read demo settings"):
            self.prepare()
        self.assertEqual((self.folder / "banking.db").read_bytes(), before_db)

    def test_changed_csv_is_refused_without_changing_database(self):
        result = self.prepare()
        path = self.folder / "transactions.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        rows[0]["amount_cad"] = "123.45" if rows[0]["amount_cad"] != "123.45" else "124.45"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, columns)
            writer.writeheader()
            writer.writerows(rows)
        before = self.database_dump(result["db_path"])
        before_csv = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "different dataset"):
            self.prepare()
        self.assertEqual(self.database_dump(result["db_path"]), before)
        self.assertEqual(path.read_bytes(), before_csv)

    def test_empty_or_corrupt_database_is_not_silently_recreated(self):
        self.prepare()
        database = self.folder / "banking.db"
        for contents in (b"", b"not a SQLite database"):
            database.write_bytes(contents)
            before = self.snapshot_bytes()
            with self.subTest(contents=contents), self.assertRaises(run_demo.DemoError):
                self.prepare()
            self.assertEqual(self.snapshot_bytes(), before)

    def test_all_rule_configs_are_validated_before_any_preparation(self):
        config = json.loads((ROOT / "config" / "rules.json").read_text())
        config["R004"]["min_wire_history"] = "invalid"
        config_path = self.parent / "rules.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_demo.prepare_demo(self.folder, transactions=1000, config_path=config_path)
        self.assertFalse(self.folder.exists())
        self.assertEqual(list(self.parent.iterdir()), [config_path])

    def test_fresh_detector_failure_cleans_staging_and_lock(self):
        registry = run_demo.rule_registry()
        _, validator, keys = registry["R004"]
        registry["R004"] = (Mock(side_effect=sqlite3.OperationalError("test detection failure")), validator, keys)
        with patch("run_demo.rule_registry", return_value=registry), self.assertRaisesRegex(sqlite3.Error, "test detection failure"):
            self.prepare()
        self.assertFalse(self.folder.exists())
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertTrue(self.prepare()["db_path"].is_file())

    def test_concurrent_preparation_lock_is_respected(self):
        lock = self.parent / f"{self.folder.name}.demo-prepare.lock"
        lock.write_text("another preparation", encoding="utf-8")
        with self.assertRaisesRegex(run_demo.DemoError, "Preparation lock already exists"):
            self.prepare()
        self.assertFalse(self.folder.exists())
        self.assertEqual(lock.read_text(), "another preparation")

    def test_prepare_only_does_not_require_dashboard_dependencies_or_server(self):
        output = io.StringIO()
        with patch("run_demo.check_dependencies", side_effect=AssertionError), \
             patch("run_demo.launch_dashboard", side_effect=AssertionError), redirect_stdout(output):
            code = run_demo.main(["--prepare-only", "--transactions", "1000", "--demo-dir", str(self.folder)])
        self.assertEqual(code, 0)
        self.assertTrue((self.folder / "banking.db").is_file())
        for rule in ("R001", "R002", "R003", "R004"):
            self.assertIn(rule + ":", output.getvalue())

    def test_missing_dependencies_fail_before_creating_data(self):
        error = io.StringIO()
        with patch("run_demo.importlib.util.find_spec", return_value=None), redirect_stderr(error):
            code = run_demo.main(["--demo-dir", str(self.folder)])
        self.assertEqual(code, 1)
        self.assertIn("pip install", error.getvalue())
        self.assertFalse(self.folder.exists())

    def test_busy_or_invalid_port_fails_before_creating_data(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            occupied = listener.getsockname()[1]
            for port in (occupied, 0, 65536):
                with self.subTest(port=port), patch("run_demo.check_dependencies"), redirect_stderr(io.StringIO()):
                    code = run_demo.main(["--demo-dir", str(self.folder), "--port", str(port)])
                self.assertEqual(code, 1)
                self.assertFalse(self.folder.exists())

    def test_server_startup_failure_terminates_child_without_opening_browser(self):
        process = Mock()
        process.poll.return_value = None
        with patch("run_demo.check_port"), patch("run_demo.subprocess.Popen", return_value=process), \
             patch("run_demo.wait_for_server", side_effect=run_demo.DemoError("startup failed")), \
             patch("run_demo.webbrowser.open") as browser, self.assertRaisesRegex(run_demo.DemoError, "startup failed"):
            run_demo.launch_dashboard(self.folder / "banking.db")
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        browser.assert_not_called()

    def test_port_can_be_reused_immediately_after_a_server_connection_closes(self):
        with socket.create_server(("127.0.0.1", 0), backlog=1) as server:
            port = server.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port)) as client:
                accepted, _ = server.accept()
                with accepted:
                    accepted.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
        # The accepted server connection actively closed and may remain in TIME_WAIT.
        run_demo.check_port(port)

    def test_exited_server_is_reported_before_health_request(self):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch("run_demo.urllib.request.urlopen") as request, self.assertRaisesRegex(run_demo.DemoError, "exit code 1"):
            run_demo.wait_for_server(process, "http://127.0.0.1:8501")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
