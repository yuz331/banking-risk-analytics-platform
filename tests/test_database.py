"""Acceptance checks for snapshot integrity and activity analytics."""

import csv
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze_data import run_analysis
from generate_data import create_dataset
from load_database import ValidationError, load_dataset, to_cents


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        create_dataset(1000, 30, 50, 42, self.folder)

    def edit(self, table, change):
        path = self.folder / f"{table}.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def test_import_and_repeat(self):
        result = load_dataset(self.folder, self.db)
        self.assertEqual((result["customers"], result["accounts"], result["transactions"]), (30, 50, 1000))
        self.assertTrue(result["imported"])
        self.assertFalse(load_dataset(self.folder, self.db)["imported"])
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1000)
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE transactions SET account_id = 'MISSING' WHERE transaction_id = 'T0000001'")

    def test_duplicate_rejected_before_creation(self):
        self.edit("transactions", lambda rows: rows.append(dict(rows[0])))
        with self.assertRaisesRegex(ValidationError, "duplicate transaction_id"):
            load_dataset(self.folder, self.db)
        self.assertFalse(self.db.exists())

    def test_orphan_account_and_transaction_rejected(self):
        self.edit("accounts", lambda rows: rows[0].update(customer_id="MISSING"))
        self.edit("transactions", lambda rows: rows[0].update(account_id="MISSING"))
        with self.assertRaises(ValidationError) as error:
            load_dataset(self.folder, self.db)
        self.assertIn("unknown customer_id", str(error.exception))
        self.assertIn("unknown account_id", str(error.exception))

    def test_invalid_transaction_fields_rejected(self):
        cases = (
            ("amount_cad", "NaN", "finite"),
            ("amount_cad", "-1.00", "positive"),
            ("amount_cad", "1.001", "decimal places"),
            ("transaction_time", "2026-02-30 00:00:00", "row 2"),
            ("transaction_time", "2020-01-01 00:00:00", "precedes"),
            ("direction", "OTHER", "invalid direction"),
            ("status", "UNKNOWN", "invalid status"),
            ("counterparty_country", "Canada", "two uppercase"),
        )
        for key, value, message in cases:
            with self.subTest(key=key, value=value):
                create_dataset(1000, 30, 50, 42, self.folder)
                self.edit("transactions", lambda rows: rows[0].update({key: value}))
                with self.assertRaisesRegex(ValidationError, message):
                    load_dataset(self.folder, self.db)
                self.assertFalse(self.db.exists())

    def test_bad_headers_and_missing_values_rejected(self):
        path = self.folder / "customers.csv"
        path.write_text("customer_id,segment\nC1,PERSONAL\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "expected columns"):
            load_dataset(self.folder, self.db)
        create_dataset(1000, 30, 50, 42, self.folder)
        self.edit("customers", lambda rows: rows[0].update(segment=""))
        with self.assertRaisesRegex(ValidationError, "empty fields"):
            load_dataset(self.folder, self.db)

    def test_changed_snapshot_preserves_database(self):
        load_dataset(self.folder, self.db)
        before = self.db.read_bytes()
        self.edit("transactions", lambda rows: rows[0].update(amount_cad="1.23"))
        with self.assertRaisesRegex(ValidationError, "different dataset"):
            load_dataset(self.folder, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_sql_totals_reconcile_and_pending_excluded(self):
        self.edit("transactions", lambda rows: rows[0].update(status="PENDING"))
        load_dataset(self.folder, self.db)
        results = run_analysis(self.db)
        overview = results["overview"][0]
        with (self.folder / "transactions.csv").open(newline="", encoding="utf-8") as handle:
            posted = [row for row in csv.DictReader(handle) if row["status"] == "POSTED"]
        self.assertEqual(overview["all_transactions"], 1000)
        self.assertEqual(overview["posted_transactions"], 999)
        for direction, key in (("IN", "inbound_cents"), ("OUT", "outbound_cents")):
            expected = sum(to_cents(row["amount_cad"]) for row in posted if row["direction"] == direction)
            self.assertEqual(overview[key], expected)
            self.assertEqual(sum(row[key] for row in results["daily_activity"]), expected)
        self.assertEqual(sum(row["transaction_count"] for row in results["type_distribution"]), 999)
        self.assertEqual(sum(row["total_cents"] for row in results["cross_border_activity"]),
                         sum(to_cents(row["amount_cad"]) for row in posted if row["counterparty_country"] != "CA"))
        self.assertTrue(all(row["amount_cents"] > 200000 and row["transaction_type"] in ("WIRE", "E_TRANSFER")
                            for row in results["large_outbound_transfers"]))
        self.assertLessEqual(len(results["top_outbound_accounts"]), 10)
        self.assertEqual(run_analysis(self.db, "overview")["overview"], results["overview"])

    def test_missing_database_analysis_does_not_create_file(self):
        with self.assertRaises(sqlite3.OperationalError):
            run_analysis(self.db)
        self.assertFalse(self.db.exists())

    def test_exact_money_conversion(self):
        self.assertEqual(to_cents("0.29"), 29)
        self.assertEqual(to_cents("92233720368547758.07"), 9223372036854775807)
        with self.assertRaises(ValueError):
            to_cents("92233720368547758.08")


if __name__ == "__main__":
    unittest.main()
