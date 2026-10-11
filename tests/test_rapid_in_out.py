"""R003 time/amount boundaries, one-to-one pairing and persistence checks."""

import csv
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_data import create_dataset
from load_database import SCHEMA, load_dataset
from rule_rapid_in_out import detect_r003, find_rapid_pairs
from show_alerts import read_alerts

ROOT = Path(__file__).resolve().parents[1]


def rows_for(entries):
    """Entries: seconds since a fixed UTC time, direction, integer cents."""
    rows = [{"transaction_id": f"T{i:05d}", "direction": direction, "amount_cents": amount,
             "transaction_time": (datetime(2026, 1, 1, 23) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")}
            for i, (seconds, direction, amount) in enumerate(entries)]
    return sorted(rows, key=lambda row: (row["transaction_time"], row["transaction_id"]))


class R003Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript(SCHEMA.read_text())
            connection.execute("INSERT INTO customers VALUES ('C1', 'PERSONAL', '2025-01-01')")
            connection.executemany("INSERT INTO accounts VALUES (?, 'C1', 'CHEQUING', '2025-01-01')", [("A1",), ("A2",)])

    def add(self, entries, account="A1", kind="WIRE", status="POSTED"):
        rows = rows_for(entries)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            offset = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            for i, row in enumerate(rows):
                row["transaction_id"] = f"T{offset + i:05d}"
                connection.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, 'CP1', 'CA', ?)",
                                   (row["transaction_id"], account, row["transaction_time"], row["amount_cents"], row["direction"], kind, status))
        return rows

    def test_exact_minimum_ratio_and_24_hour_boundary(self):
        rows = self.add([(0, "IN", 500000), (86400, "OUT", 400000)])
        result = detect_r003(self.db)
        self.assertEqual((result["eligible_receipts"], result["matched_events"], result["new_alerts"]), (1, 1, 1))
        alert = read_alerts(self.db, rule="R003", with_evidence=True)[0]
        self.assertEqual((alert["peak_count"], alert["evidence_count"], alert["score"], alert["priority"]), (2, 2, 70, "HIGH"))
        self.assertEqual(alert["details"]["elapsed_seconds"], 86400)
        self.assertEqual(alert["details"]["inbound_transaction_id"], rows[0]["transaction_id"])
        self.assertEqual([row["transaction_id"] for row in alert["transactions"]], [row["transaction_id"] for row in rows])

    def test_below_material_receipt_and_exact_integer_ratio(self):
        for inbound, outbound, expected in ((499999, 400000, 0), (500000, 399999, 0),
                                          (500001, 400000, 0), (500001, 400001, 1), (500000, 999999, 1)):
            with self.subTest(inbound=inbound, outbound=outbound):
                self.assertEqual(len(list(find_rapid_pairs(rows_for([(0, "IN", inbound), (3600, "OUT", outbound)])))), expected)

    def test_time_order_and_same_timestamp_exclusion(self):
        for delta, expected in ((-1, 0), (0, 0), (1, 1), (86400, 1), (86401, 0)):
            with self.subTest(delta=delta):
                rows = rows_for([(0, "IN", 500000), (delta, "OUT", 400000)])
                self.assertEqual(len(list(find_rapid_pairs(rows))), expected)

    def test_latest_qualifying_receipt_and_one_to_one_pairing(self):
        rows = rows_for([(0, "IN", 500000), (100, "IN", 1000000), (200, "OUT", 600000), (300, "OUT", 800000)])
        pairs = list(find_rapid_pairs(rows))
        self.assertEqual([(pair["inbound"]["transaction_id"], pair["outbound"]["transaction_id"]) for pair in pairs],
                         [("T00000", "T00002"), ("T00001", "T00003")])

    def test_same_time_receipts_use_deterministic_id_order(self):
        rows = rows_for([(0, "IN", 500000), (0, "IN", 500000), (100, "OUT", 400000), (100, "OUT", 400000)])
        pairs = list(find_rapid_pairs(rows))
        self.assertEqual([pair["inbound"]["transaction_id"] for pair in pairs], ["T00001", "T00000"])

    def test_receipt_not_reused_and_small_outflows_not_accumulated(self):
        rows = rows_for([(0, "IN", 500000), (100, "OUT", 250000), (200, "OUT", 250000)])
        self.assertEqual(list(find_rapid_pairs(rows)), [])
        rows = rows_for([(0, "IN", 500000), (100, "OUT", 250000), (200, "OUT", 250000),
                         (300, "OUT", 400000), (400, "OUT", 400000)])
        self.assertEqual(len(list(find_rapid_pairs(rows))), 1)

    def test_newer_valid_receipt_preferred_over_older(self):
        rows = rows_for([(0, "IN", 500000), (100, "IN", 500000), (200, "OUT", 400000)])
        pair = next(find_rapid_pairs(rows))
        self.assertEqual(pair["inbound"]["transaction_id"], "T00001")

    def test_status_and_type_exclusions(self):
        self.add([(0, "IN", 500000)], kind="DEBIT_PURCHASE")
        self.add([(100, "OUT", 400000)])
        self.add([(0, "IN", 500000)], status="PENDING")
        self.add([(0, "IN", 500000)], status="FAILED")
        self.add([(0, "IN", 500000)], status="REVERSED")
        self.assertEqual(detect_r003(self.db)["matched_events"], 0)
        self.add([(0, "IN", 500000)], kind="DIRECT_DEPOSIT")
        self.add([(50, "OUT", 400000)], kind="BILL_PAYMENT")
        self.assertEqual(detect_r003(self.db)["new_alerts"], 1)
        # Supported inbound cash deposits and e-Transfers also qualify.
        for kind in ("CASH_DEPOSIT", "E_TRANSFER"):
            self.add([(200, "IN", 500000)], kind=kind)
            self.add([(300, "OUT", 400000)], kind="E_TRANSFER")
        self.assertEqual(detect_r003(self.db)["matched_events"], 3)

    def test_accounts_are_not_pooled(self):
        self.add([(0, "IN", 500000)], account="A1")
        self.add([(100, "OUT", 400000)], account="A2")
        result = detect_r003(self.db)
        self.assertEqual((result["matched_events"], result["unmatched_receipts"]), (0, 1))

    def test_rerun_and_configuration_identity(self):
        self.add([(0, "IN", 1000000), (3600, "OUT", 850000)])
        detect_r003(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE alerts SET status='IN_REVIEW'")
        before = read_alerts(self.db, with_evidence=True)
        result = detect_r003(self.db)
        self.assertEqual((result["new_alerts"], result["existing_alerts"]), (0, 1))
        self.assertEqual(read_alerts(self.db, with_evidence=True), before)
        self.assertEqual(detect_r003(self.db, outbound_percentage=85)["new_alerts"], 1)
        self.assertEqual(detect_r003(self.db, outbound_percentage=86)["matched_events"], 0)

    def test_details_failure_rolls_back_pair(self):
        self.add([(0, "IN", 500000), (100, "OUT", 400000)])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""CREATE TRIGGER reject_details BEFORE INSERT ON alert_details
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            detect_r003(self.db)
        self.assertEqual(read_alerts(self.db), [])

    def test_invalid_parameters_and_cli_prevalidation(self):
        missing = self.folder / "missing.db"
        for parameters in ({"minimum_inbound_cents": True}, {"minimum_inbound_cents": 2**63},
                           {"outbound_percentage": 0}, {"outbound_percentage": 101},
                           {"window_hours": 1.5}, {"window_hours": 8761}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                detect_r003(missing, **parameters)
        self.assertFalse(missing.exists())
        # A valid earlier rule must not save anything before invalid R003 params fail.
        self.add([(i * 600, "OUT", 10000) for i in range(5)])
        result = subprocess.run([sys.executable, str(ROOT / "src/detect_risks.py"), "--db", str(self.db),
                                 "--rule", "all", "--outbound-percentage", "101"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Detection failed:", result.stderr)
        self.assertEqual(read_alerts(self.db), [])

    def test_seeded_pair_without_label_input_and_minimal_counts(self):
        folder = self.folder / "generated"
        create_dataset(1000, output_dir=folder, include_r001=True, include_r003=True)
        with (folder / "injected_scenarios.csv").open(newline="") as handle:
            label = next(row for row in csv.DictReader(handle) if row["rule_id"] == "R003")
        ids = label["transaction_ids"].split("|")
        (folder / "injected_scenarios.csv").unlink()
        db = folder / "banking.db"
        load_dataset(folder, db)
        detect_r003(db)
        alerts = read_alerts(db, account=label["account_id"], rule="R003", with_evidence=True, limit=1000)
        self.assertTrue(any({row["transaction_id"] for row in alert["transactions"]} == set(ids) for alert in alerts))
        for count, r001 in ((6, False), (12, True)):
            with self.assertRaises(ValueError):
                create_dataset(count, output_dir=self.folder / "invalid", include_r001=r001, include_r003=True)
        for count, r001 in ((7, False), (13, True)):
            minimal = self.folder / f"minimal{count}"
            create_dataset(count, 1, 1, 42, minimal, include_r001=r001, include_r003=True)
            load_dataset(minimal, minimal / "banking.db")
            self.assertEqual(detect_r003(minimal / "banking.db")["new_alerts"], 1)

    def test_pairing_matches_independent_candidate_oracle(self):
        rng = random.Random(42)
        for _ in range(100):
            entries = [(rng.randrange(200000), rng.choice(("IN", "OUT")), rng.randrange(1, 1500000)) for i in range(40)]
            rows = rows_for(entries)
            used, expected = set(), []
            for outbound in rows:
                if outbound["direction"] != "OUT":
                    continue
                when = datetime.strptime(outbound["transaction_time"], "%Y-%m-%d %H:%M:%S")
                candidates = [inbound for inbound in rows if inbound["direction"] == "IN"
                              and inbound["transaction_id"] not in used and inbound["amount_cents"] >= 500000
                              and timedelta(0) < when - datetime.strptime(inbound["transaction_time"], "%Y-%m-%d %H:%M:%S") <= timedelta(hours=24)
                              and 100 * outbound["amount_cents"] >= 80 * inbound["amount_cents"]]
                if candidates:
                    inbound = max(candidates, key=lambda row: (row["transaction_time"], row["transaction_id"]))
                    used.add(inbound["transaction_id"])
                    expected.append((inbound["transaction_id"], outbound["transaction_id"]))
            actual = [(pair["inbound"]["transaction_id"], pair["outbound"]["transaction_id"]) for pair in find_rapid_pairs(rows)]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
