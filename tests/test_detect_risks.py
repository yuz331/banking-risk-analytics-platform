"""R002 positive/negative, rolling-window and persistence acceptance tests."""

import csv
import json
import random
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from detect_risks import detect_r002, find_events, load_parameters, priority_for_score
from generate_data import create_dataset
from load_database import SCHEMA, load_dataset
from show_alerts import read_alerts


class R002Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        # Start with the old Phase 2 schema to also exercise additive upgrades.
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript(SCHEMA.read_text().split("-- Phase 3:")[0])
            connection.execute("INSERT INTO customers VALUES ('C1', 'PERSONAL', '2025-01-01')")
            connection.executemany("INSERT INTO accounts VALUES (?, 'C1', 'CHEQUING', '2025-01-01')",
                                   [("A1",), ("A2",)])

    def add(self, minutes, account="A1", direction="OUT", kind="E_TRANSFER", status="POSTED", start=None):
        start = start or datetime(2026, 1, 1, 0, 0)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            offset = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            ids = [f"T{offset + i:05d}" for i in range(len(minutes))]
            connection.executemany("INSERT INTO transactions VALUES (?, ?, ?, 12345, ?, ?, 'CP1', 'CA', ?)",
                                   [(txid, account, (start + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M:%S"),
                                     direction, kind, status) for txid, minute in zip(ids, minutes)])
        return ids

    def test_seeded_generator_scenario_detected_without_labels(self):
        folder = self.folder / "generated"
        create_dataset(1000, output_dir=folder)
        with (folder / "injected_scenarios.csv").open(newline="") as handle:
            labels = next(csv.DictReader(handle))
        expected = set(labels["transaction_ids"].split("|"))
        (folder / "injected_scenarios.csv").unlink()
        db = folder / "banking.db"
        load_dataset(folder, db)
        detect_r002(db)
        alerts = read_alerts(db, account="A00001", with_evidence=True)
        self.assertTrue(any(expected.issubset({row["transaction_id"] for row in alert["transactions"]}) for alert in alerts))

    def test_exact_60_minute_boundary_triggers(self):
        ids = self.add([0, 15, 30, 45, 60])
        result = detect_r002(self.db)
        self.assertEqual(result["new_alerts"], 1)
        alert = read_alerts(self.db, with_evidence=True)[0]
        self.assertEqual(alert["peak_count"], 5)
        self.assertEqual((alert["score"], alert["priority"], alert["status"]), (60, "MEDIUM", "NEW"))
        self.assertEqual([row["transaction_id"] for row in alert["transactions"]], ids)
        self.assertIn("inclusive 60-minute", alert["explanation"])
        outside = [dict(row) for row in alert["transactions"]]
        outside[-1]["transaction_time"] = "2026-01-01 01:00:01"
        self.assertEqual(list(find_events(outside)), [])

    def test_four_transfers_and_61_minute_span_do_not_trigger(self):
        self.add([0, 10, 20, 30], account="A1")
        self.add([0, 15, 30, 45, 61], account="A2")
        self.assertEqual(detect_r002(self.db)["matched_events"], 0)

    def test_status_direction_and_type_exclusions(self):
        self.add([0, 10, 20, 30])
        self.add([40], direction="IN")
        self.add([40], kind="DEBIT_PURCHASE")
        self.add([40], kind="BILL_PAYMENT")
        for status in ("PENDING", "FAILED", "REVERSED"):
            self.add([40], status=status)
        result = detect_r002(self.db)
        self.assertEqual((result["eligible_transactions"], result["matched_events"]), (4, 0))
        self.add([40], kind="WIRE")
        self.assertEqual(detect_r002(self.db)["new_alerts"], 1)

    def test_overlapping_windows_merge_and_score_increases(self):
        self.add([0, 10, 20, 30, 40, 50])
        self.assertEqual(detect_r002(self.db)["new_alerts"], 1)
        alert = read_alerts(self.db, with_evidence=True)[0]
        self.assertEqual((alert["evidence_count"], alert["peak_count"], alert["score"], alert["priority"]), (6, 6, 70, "HIGH"))
        self.assertEqual(len(alert["transactions"]), 6)

    def test_chain_can_span_more_than_one_window(self):
        self.add([0, 15, 30, 45, 60, 75, 90, 105, 120])
        self.assertEqual(detect_r002(self.db)["new_alerts"], 1)
        alert = read_alerts(self.db)[0]
        self.assertEqual((alert["evidence_count"], alert["peak_count"]), (9, 5))
        self.assertEqual(alert["event_end_utc"], "2026-01-01 02:00:00")

    def test_disjoint_bursts_and_accounts_are_separate(self):
        self.add([0, 10, 20, 30, 40, 200, 210, 220, 230, 240])
        self.add([0, 10, 20, 30, 40], account="A2")
        self.assertEqual(detect_r002(self.db)["new_alerts"], 3)
        self.assertEqual(len(read_alerts(self.db, account="A1")), 2)

    def test_midnight_and_identical_timestamps(self):
        self.add([0, 10, 20, 30, 40], start=datetime(2026, 1, 1, 23, 40))
        self.add([0, 0, 0, 0, 0], account="A2")
        self.assertEqual(detect_r002(self.db)["new_alerts"], 2)

    def test_rerun_preserves_ids_creation_status_and_evidence(self):
        self.add([0, 10, 20, 30, 40])
        detect_r002(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE alerts SET status = 'IN_REVIEW'")
        before = read_alerts(self.db, with_evidence=True)
        result = detect_r002(self.db)
        self.assertEqual((result["new_alerts"], result["existing_alerts"]), (0, 1))
        self.assertEqual(read_alerts(self.db, with_evidence=True), before)
        self.assertEqual(read_alerts(self.db, status="NEW"), [])
        self.assertEqual(len(read_alerts(self.db, priority="MEDIUM", status="IN_REVIEW")), 1)
        self.assertEqual(read_alerts(self.db, account="A1' OR 1=1 --"), [])

    def test_config_changes_create_distinct_results(self):
        self.add([0, 10, 20, 30, 40])
        detect_r002(self.db)
        self.assertEqual(detect_r002(self.db, min_count=4)["new_alerts"], 1)
        self.assertEqual(detect_r002(self.db, window_minutes=30)["matched_events"], 0)
        self.assertEqual(len(read_alerts(self.db)), 2)

    def test_evidence_write_failure_rolls_back_alert(self):
        self.add([0, 10, 20, 30, 40])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript(SCHEMA.read_text())
            connection.executescript("""CREATE TRIGGER reject_evidence BEFORE INSERT ON alert_transactions
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            detect_r002(self.db)
        self.assertEqual(read_alerts(self.db), [])

    def test_missing_db_and_invalid_parameters_fail_without_creation(self):
        missing = self.folder / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            detect_r002(missing)
        for values in ((1, 60), (5, 0), (True, 60), (5, 1.5)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                detect_r002(missing, *values)
        self.assertFalse(missing.exists())
        config = self.folder / "rules.json"
        config.write_text(json.dumps({"R002": {"min_count": 5, "window_minutes": 30}}))
        self.assertEqual(load_parameters(config), {"min_count": 5, "window_minutes": 30})
        config.write_text(json.dumps({"R002": {"min_count": True, "window_minutes": 30}}))
        with self.assertRaises(ValueError):
            load_parameters(config)

    def test_score_mapping_and_cap(self):
        self.assertEqual([priority_for_score(x) for x in (0, 39, 40, 69, 70, 100)],
                         ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH"])
        self.add([0] * 20)
        detect_r002(self.db)
        self.assertEqual(read_alerts(self.db)[0]["score"], 100)

    def test_windows_match_independent_brute_force_oracle(self):
        rng = random.Random(42)
        for _ in range(100):
            minutes = sorted(rng.randrange(200) for _ in range(40))
            rows = [{"transaction_time": (datetime(2026, 1, 1) + timedelta(minutes=value)).strftime("%Y-%m-%d %H:%M:%S"),
                     "transaction_id": str(i)} for i, value in enumerate(minutes)]
            threshold, window = rng.randint(2, 8), rng.randint(5, 60)
            expected = []
            for right, value in enumerate(minutes):
                hit = {i for i in range(right + 1) if value - minutes[i] <= window}
                if len(hit) < threshold:
                    continue
                if expected and hit & expected[-1][0]:
                    expected[-1] = (expected[-1][0] | hit, max(expected[-1][1], len(hit)))
                else:
                    expected.append((hit, len(hit)))
            actual = [({int(row["transaction_id"]) for row in event["rows"]}, event["peak_count"])
                      for event in find_events(rows, threshold, window)]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
