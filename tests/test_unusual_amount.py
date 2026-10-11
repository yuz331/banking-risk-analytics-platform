"""R001 acceptance checks for exact thresholds and historical evidence."""

import csv
import random
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_data import create_dataset
from load_database import SCHEMA, load_dataset
from rule_unusual_amount import detect_r001, find_unusual_amounts
from show_alerts import read_alerts


def records(cents, start=None):
    start = start or datetime(2026, 1, 1)
    return [{"transaction_id": f"T{i:05d}", "amount_cents": amount,
             "transaction_time": (start + timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")}
            for i, amount in enumerate(cents)]


def hits(rows, **parameters):
    return [event for event in find_unusual_amounts(rows, **parameters) if not event["insufficient_history"]]


class R001Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript(SCHEMA.read_text())
            connection.execute("INSERT INTO customers VALUES ('C1', 'PERSONAL', '2025-01-01')")
            connection.executemany("INSERT INTO accounts VALUES (?, 'C1', 'CHEQUING', '2025-01-01')", [("A1",), ("A2",)])

    def add(self, cents, account="A1", direction="OUT", status="POSTED", kind="E_TRANSFER", start=None):
        rows = records(cents, start)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            offset = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            for i, row in enumerate(rows):
                row["transaction_id"] = f"T{offset + i:05d}"
                connection.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, 'CP1', 'CA', ?)",
                                   (row["transaction_id"], account, row["transaction_time"], row["amount_cents"], direction, kind, status))
        return rows

    def test_positive_baseline_and_persisted_evidence(self):
        rows = self.add([10000] * 5 + [500000])
        result = detect_r001(self.db)
        self.assertEqual((result["new_alerts"], result["skipped_insufficient_history"]), (1, 5))
        alert = read_alerts(self.db, with_evidence=True, rule="R001")[0]
        self.assertEqual(alert["details"]["median_twice_cents"], 20000)
        self.assertEqual(alert["details"]["history_count"], 5)
        self.assertEqual(alert["details"]["trigger_transaction_id"], rows[-1]["transaction_id"])
        self.assertEqual((alert["peak_count"], alert["evidence_count"], alert["score"], alert["priority"]), (1, 6, 100, "HIGH"))
        self.assertEqual(alert["event_start_utc"], rows[-1]["transaction_time"])
        self.assertEqual([row["transaction_id"] for row in alert["transactions"]], [row["transaction_id"] for row in rows])
        self.assertIn("median CAD 100", alert["explanation"])

    def test_strict_amount_and_multiple_boundaries(self):
        for baseline, amount, expected in ((50000, 200000, 0), (50000, 200001, 1),
                                          (100000, 400000, 0), (100000, 400001, 1),
                                          (10000, 199999, 0)):
            with self.subTest(baseline=baseline, amount=amount):
                self.assertEqual(len(hits(records([baseline] * 5 + [amount]))), expected)

    def test_even_half_cent_median_is_exact(self):
        baseline = [50000, 50000, 50001, 50001]
        self.assertEqual(hits(records(baseline + [200002]), min_history=4), [])
        result = hits(records(baseline + [200003]), min_history=4)
        self.assertEqual(result[0]["median_twice_cents"], 100001)

    def test_insufficient_history_is_skipped(self):
        self.add([10000] * 4 + [9999999])
        result = detect_r001(self.db)
        self.assertEqual((result["matched_events"], result["skipped_insufficient_history"]), (0, 5))

    def test_same_timestamp_and_future_rows_do_not_leak(self):
        rows = records([10000] * 5 + [500000] + [9999999] * 6)
        # Five baseline records at the trigger's timestamp must not count.
        ties = [dict(row, transaction_time=rows[5]["transaction_time"]) for row in rows[:6]]
        self.assertEqual(hits(ties), [])
        event = hits(rows)[0]
        self.assertEqual(event["trigger"]["transaction_id"], "T00005")
        self.assertEqual(event["median_twice_cents"], 20000)
        self.assertEqual([row["transaction_id"] for row in event["history"]], [f"T{i:05d}" for i in range(5)])

    def test_lookback_lower_boundary_included_then_expires(self):
        rows = records([10000] * 5 + [500000])
        rows[-1]["transaction_time"] = "2026-01-31 00:00:00"
        self.assertEqual(len(hits(rows)), 1)
        rows[-1]["transaction_time"] = "2026-01-31 00:00:01"
        self.assertEqual(hits(rows), [])

    def test_history_filters_and_account_separation(self):
        self.add([10000] * 4)
        for direction, kind, status in (("IN", "E_TRANSFER", "POSTED"), ("OUT", "BILL_PAYMENT", "POSTED"),
                                        ("OUT", "E_TRANSFER", "PENDING"), ("OUT", "WIRE", "FAILED"),
                                        ("OUT", "WIRE", "REVERSED")):
            self.add([10000], direction=direction, kind=kind, status=status)
        self.add([500000], start=datetime(2026, 1, 6))
        self.add([10000] * 4 + [500000], account="A2")
        self.assertEqual(detect_r001(self.db)["matched_events"], 0)
        # Mixed outbound wire history is eligible once a fifth prior row exists.
        self.add([10000], kind="WIRE", start=datetime(2026, 1, 5))
        self.assertEqual(detect_r001(self.db)["new_alerts"], 1)

    def test_rerun_and_changed_config_preserve_prior_result(self):
        self.add([10000] * 5 + [500000])
        detect_r001(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE alerts SET status='CLOSED'")
        before = read_alerts(self.db, with_evidence=True)
        self.assertEqual(detect_r001(self.db)["new_alerts"], 0)
        self.assertEqual(read_alerts(self.db, with_evidence=True), before)
        self.assertEqual(detect_r001(self.db, multiplier=5)["new_alerts"], 1)
        self.assertEqual(len(read_alerts(self.db, rule="R001")), 2)
        self.assertEqual(read_alerts(self.db, rule="R002"), [])

    def test_details_failure_rolls_back_alert_and_evidence(self):
        self.add([10000] * 5 + [500000])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""CREATE TRIGGER reject_details BEFORE INSERT ON alert_details
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            detect_r001(self.db)
        self.assertEqual(read_alerts(self.db), [])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM alert_transactions").fetchone()[0], 0)

    def test_invalid_parameters_fail_before_opening_database(self):
        missing = self.folder / "missing.db"
        for parameters in ({"min_history": 0}, {"lookback_days": -1}, {"multiplier": 1.5},
                           {"minimum_amount_cents": True}, {"minimum_amount_cents": 2**63}, {"lookback_days": 3651}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                detect_r001(missing, **parameters)
        self.assertFalse(missing.exists())

    def test_seeded_r001_without_label_file(self):
        folder = self.folder / "generated"
        create_dataset(1000, output_dir=folder, include_r001=True)
        with (folder / "injected_scenarios.csv").open(newline="") as handle:
            label = next(row for row in csv.DictReader(handle) if row["rule_id"] == "R001")
        ids = label["transaction_ids"].split("|")
        (folder / "injected_scenarios.csv").unlink()
        db = folder / "banking.db"
        load_dataset(folder, db)
        detect_r001(db)
        seeded = [alert for alert in read_alerts(db, rule="R001", account=label["account_id"], with_evidence=True)
                  if alert["details"]["trigger_transaction_id"] == ids[-1]][0]
        self.assertEqual({row["transaction_id"] for row in seeded["transactions"]}, set(ids))
        self.assertEqual(seeded["details"]["median_twice_cents"], 20000)

    def test_optional_seed_minimum_counts_and_reproducibility(self):
        with self.assertRaises(ValueError):
            create_dataset(10, output_dir=self.folder / "invalid", include_r001=True)
        a, b = self.folder / "a", self.folder / "b"
        create_dataset(11, 1, 1, 42, a, include_r001=True)
        create_dataset(11, 1, 1, 42, b, include_r001=True)
        self.assertEqual((a / "transactions.csv").read_bytes(), (b / "transactions.csv").read_bytes())
        db = a / "banking.db"
        load_dataset(a, db)
        self.assertEqual(detect_r001(db)["new_alerts"], 1)

    def test_median_and_history_match_independent_oracle(self):
        rng = random.Random(42)
        for _ in range(50):
            rows = sorted([{"transaction_id": str(i), "amount_cents": rng.randint(1, 1000000),
                            "transaction_time": (datetime(2026, 1, 1) + timedelta(hours=rng.randrange(120))).strftime("%Y-%m-%d %H:%M:%S")}
                           for i in range(40)], key=lambda row: (row["transaction_time"], row["transaction_id"]))
            expected = []
            for row in rows:
                when = datetime.strptime(row["transaction_time"], "%Y-%m-%d %H:%M:%S")
                history = [old for old in rows if when - timedelta(days=2) <= datetime.strptime(old["transaction_time"], "%Y-%m-%d %H:%M:%S") < when]
                if len(history) < 5:
                    continue
                amounts = sorted(old["amount_cents"] for old in history)
                n = len(amounts)
                median = 2 * amounts[n // 2] if n % 2 else amounts[n // 2 - 1] + amounts[n // 2]
                if row["amount_cents"] > 200000 and 2 * row["amount_cents"] > 4 * median:
                    expected.append((row["transaction_id"], median, [old["transaction_id"] for old in history]))
            actual = [(event["trigger"]["transaction_id"], event["median_twice_cents"],
                       [old["transaction_id"] for old in event["history"]]) for event in hits(rows, lookback_days=2)]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
