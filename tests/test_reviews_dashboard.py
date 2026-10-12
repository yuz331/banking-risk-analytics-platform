"""Review integrity, metric reconciliation and real Streamlit app flows."""

import csv
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dashboard_data import alert_queue, overview, queue_csv
from detect_risks import rule_registry
from generate_data import create_dataset
from load_database import load_dataset
from review_alerts import ReviewConflict, ensure_review_schema, review_history, save_review
from show_alerts import read_alerts

ROOT = Path(__file__).resolve().parents[1]
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


class DashboardFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        create_dataset(1000, output_dir=self.folder, include_r001=True, include_r003=True, include_r004=True)
        load_dataset(self.folder, self.db)
        for detect, _, _ in rule_registry().values():
            detect(self.db)
        self.alert = alert_queue(self.db)["rows"][0]["alert_id"]


class ReviewDataTests(DashboardFixture):
    def test_review_history_status_reopen_and_persistence(self):
        first = save_review(self.db, self.alert, "IN_REVIEW", "Matt", "Checking source evidence", None)
        second = save_review(self.db, self.alert, "NO_CONCERN", "Matt", "Pattern explained in this synthetic case", first)
        self.assertEqual(read_alerts(self.db, alert_id=self.alert)[0]["status"], "CLOSED")
        self.assertEqual([row["review_id"] for row in review_history(self.db, self.alert)], [second, first])
        third = save_review(self.db, self.alert, "IN_REVIEW", "Other analyst", "Reopened for another look", second)
        self.assertEqual(read_alerts(self.db, alert_id=self.alert)[0]["status"], "IN_REVIEW")
        self.assertEqual(review_history(self.db, self.alert)[0]["review_id"], third)
        self.assertFalse(load_dataset(self.folder, self.db)["imported"])
        for detect, _, _ in rule_registry().values():
            self.assertEqual(detect(self.db)["new_alerts"], 0)
        self.assertEqual(len(review_history(self.db, self.alert)), 3)

    def test_stale_form_and_duplicate_submission_rejected(self):
        saved = save_review(self.db, self.alert, "ESCALATE", "Reviewer", "Recommend additional simulated review", None)
        with self.assertRaises(ReviewConflict):
            save_review(self.db, self.alert, "NO_CONCERN", "Stale reviewer", "Outdated conclusion", None)
        self.assertEqual(review_history(self.db, self.alert)[0]["review_id"], saved)
        self.assertEqual(len(review_history(self.db, self.alert)), 1)

    def test_invalid_inputs_and_missing_alert(self):
        for outcome, alias, notes in (("INVALID", "Matt", "note"), ("IN_REVIEW", " ", "note"),
                                       ("NO_CONCERN", "Matt", " "), ("ESCALATE", "a" * 61, "note"),
                                       ("IN_REVIEW", "Matt", "n" * 2001)):
            with self.subTest(outcome=outcome, alias=alias[:4]), self.assertRaises(ValueError):
                save_review(self.db, self.alert, outcome, alias, notes, None)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            save_review(self.db, "missing", "IN_REVIEW", "Matt", "note", None)
        self.assertEqual(review_history(self.db, self.alert), [])

    def test_review_and_status_write_are_atomic(self):
        before = read_alerts(self.db, alert_id=self.alert)[0]["status"]
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""CREATE TRIGGER reject_status BEFORE UPDATE OF status ON alerts
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            save_review(self.db, self.alert, "NO_CONCERN", "Matt", "note", None)
        self.assertEqual(review_history(self.db, self.alert), [])
        self.assertEqual(read_alerts(self.db, alert_id=self.alert)[0]["status"], before)

    def test_summary_distribution_filters_pagination_and_export(self):
        data = overview(self.db)
        summary = data["summary"]
        self.assertEqual(summary["posted_transactions"], 1000)
        self.assertEqual(sum(row["transaction_count"] for row in data["daily"]), 1000)
        self.assertEqual(sum(row["inbound_cents"] for row in data["daily"]), summary["inbound_cents"])
        self.assertEqual(sum(row["outbound_cents"] for row in data["daily"]), summary["outbound_cents"])
        self.assertEqual(sum(row["alert_count"] for row in data["distribution"]), summary["alerts"])
        first = alert_queue(self.db, page_size=1)
        second = alert_queue(self.db, page=1, page_size=1)
        self.assertNotEqual(first["rows"][0]["alert_id"], second["rows"][0]["alert_id"])
        filtered = alert_queue(self.db, rule="R004", status="NEW", account="A00004")
        self.assertTrue(filtered["rows"])
        self.assertEqual(alert_queue(self.db, account="A00004' OR 1=1 --")["total"], 0)
        exported = list(csv.DictReader(io.StringIO(queue_csv(filtered["rows"]))))
        self.assertEqual(len(exported), len(filtered["rows"]))
        self.assertEqual(exported[0]["rule_id"], "R004")
        save_review(self.db, self.alert, "NO_CONCERN", "Matt", "Checked", None)
        after = overview(self.db)["summary"]
        self.assertEqual(after["closed_alerts"], 1)
        self.assertEqual(after["open_alerts"] + after["closed_alerts"], after["alerts"])

    def test_old_schema_upgrade_and_missing_database(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("DROP TABLE reviews")
        ensure_review_schema(self.db)
        self.assertEqual(review_history(self.db, self.alert), [])
        missing = self.folder / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            ensure_review_schema(missing)
        self.assertFalse(missing.exists())


@unittest.skipIf(AppTest is None, "Install requirements.txt to run Streamlit UI tests")
class StreamlitFlowTests(DashboardFixture):
    def app(self):
        with patch.dict(os.environ, {"BANKING_RISK_DB": str(self.db)}):
            return AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()

    def test_charts_filters_evidence_review_and_fresh_session(self):
        app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, "1,000")
        self.assertEqual(len(app.get("vega_lite_chart")), 2)
        self.assertGreaterEqual(len(app.dataframe), 2)
        app.selectbox(key="rule_filter").select("R004").run()
        app.text_input(key="account_filter").set_value("A00004").run()
        self.assertEqual(len(app.exception), 0)
        inspect = next(widget for widget in app.selectbox if widget.label == "Inspect alert")
        selected = inspect.value
        app.text_input(key=f"alias_{selected}").set_value("Matt")
        app.selectbox(key=f"outcome_{selected}").select("NO_CONCERN")
        app.text_area(key=f"notes_{selected}").set_value("Reviewed historical wires and destination change in this synthetic case")
        next(button for button in app.button if button.label == "Save review").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(read_alerts(self.db, alert_id=selected)[0]["status"], "CLOSED")
        self.assertEqual(len(review_history(self.db, selected)), 1)
        fresh = self.app()
        self.assertEqual(len(fresh.exception), 0)
        self.assertEqual(fresh.metric[3].value, "1")
        self.assertEqual(len(review_history(self.db, selected)), 1)

    def test_empty_filter_and_missing_database_states(self):
        app = self.app()
        app.text_input(key="account_filter").set_value("MISSING").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No alerts match" in item.value for item in app.info))
        app.text_input(key="db_path").set_value(str(self.folder / "absent.db")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.error)
        self.assertFalse((self.folder / "absent.db").exists())

    def test_stale_ui_review_cannot_overwrite_another_review(self):
        app = self.app()
        selected = next(widget for widget in app.selectbox if widget.label == "Inspect alert").value
        save_review(self.db, selected, "ESCALATE", "Other", "Another reviewer saved first", None)
        app.text_input(key=f"alias_{selected}").set_value("Stale")
        app.text_area(key=f"notes_{selected}").set_value("Old form should not overwrite current decision")
        next(button for button in app.button if button.label == "Save review").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Another review was saved" in item.value for item in app.error))
        self.assertEqual(len(review_history(self.db, selected)), 1)


if __name__ == "__main__":
    unittest.main()
