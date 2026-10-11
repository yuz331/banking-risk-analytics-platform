"""R004 baseline, destination novelty, precise thresholds and persistence."""

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
from rule_cross_border import detect_r004, find_cross_border_events
from show_alerts import read_alerts

ROOT = Path(__file__).resolve().parents[1]


def records(amounts, countries=None):
    countries = countries or ["US"] * len(amounts)
    return [{"transaction_id": f"T{i:05d}", "amount_cents": amount, "counterparty_country": country,
             "transaction_time": (datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")}
            for i, (amount, country) in enumerate(zip(amounts, countries))]


def hits(rows, **parameters):
    return [event for event in find_cross_border_events(rows, **parameters) if not event["insufficient_history"]]


class R004Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "banking.db"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript(SCHEMA.read_text())
            connection.execute("INSERT INTO customers VALUES ('C1', 'PERSONAL', '2025-01-01')")
            connection.executemany("INSERT INTO accounts VALUES (?, 'C1', 'CHEQUING', '2025-01-01')", [("A1",), ("A2",)])

    def add(self, amounts, countries=None, account="A1", kind="WIRE", direction="OUT", status="POSTED", start_day=0):
        rows = records(amounts, countries)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            offset = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            for i, row in enumerate(rows):
                row["transaction_id"] = f"T{offset + i:05d}"
                row["transaction_time"] = (datetime(2026, 1, 1) + timedelta(days=start_day + i)).strftime("%Y-%m-%d %H:%M:%S")
                connection.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, 'CP1', ?, ?)",
                                   (row["transaction_id"], account, row["transaction_time"], row["amount_cents"],
                                    direction, kind, row["counterparty_country"], status))
        return rows

    def test_new_destination_persists_complete_history_and_reason(self):
        rows = self.add([100000] * 5 + [300000], ["US"] * 5 + ["JP"])
        result = detect_r004(self.db)
        self.assertEqual((result["matched_events"], result["new_alerts"]), (1, 1))
        alert = read_alerts(self.db, rule="R004", with_evidence=True)[0]
        self.assertEqual(alert["details"]["reasons"], ["NEW_DESTINATION"])
        self.assertEqual(alert["details"]["known_countries"], ["US"])
        self.assertEqual(alert["details"]["median_twice_cents"], 200000)
        self.assertEqual((alert["peak_count"], alert["evidence_count"], alert["score"], alert["priority"]), (1, 6, 60, "MEDIUM"))
        self.assertEqual([row["transaction_id"] for row in alert["transactions"]], [row["transaction_id"] for row in rows])

    def test_known_destination_and_strict_size_multiplier(self):
        for amount, expected in ((300000, 0), (400000, 0), (400001, 1)):
            with self.subTest(amount=amount):
                events = hits(records([100000] * 5 + [amount]))
                self.assertEqual(len(events), expected)
                if events:
                    self.assertEqual(events[0]["reasons"], ["UNUSUAL_AMOUNT"])

    def test_both_signals_form_one_high_priority_alert(self):
        self.add([100000] * 5 + [500000], ["US"] * 5 + ["JP"])
        self.assertEqual(detect_r004(self.db)["new_alerts"], 1)
        alert = read_alerts(self.db, rule="R004")[0]
        self.assertEqual(alert["details"]["reasons"], ["NEW_DESTINATION", "UNUSUAL_AMOUNT"])
        self.assertEqual((alert["score"], alert["priority"]), (80, "HIGH"))

    def test_amount_floor_and_domestic_candidate_exclusion(self):
        for amount, country, expected in ((200000, "JP", 0), (200001, "JP", 1), (9999999, "CA", 0)):
            with self.subTest(amount=amount, country=country):
                self.assertEqual(len(hits(records([100000] * 5 + [amount], ["US"] * 5 + [country]))), expected)

    def test_even_half_cent_median(self):
        baseline = [50000, 50000, 50001, 50001]
        self.assertEqual(hits(records(baseline + [200002]), min_wire_history=4), [])
        events = hits(records(baseline + [200003]), min_wire_history=4)
        self.assertEqual(events[0]["median_twice_cents"], 100001)

    def test_insufficient_history_and_domestic_baseline(self):
        self.add([100000] * 4 + [300000], ["US"] * 4 + ["JP"])
        result = detect_r004(self.db)
        self.assertEqual((result["matched_events"], result["skipped_insufficient_history"]), (0, 5))
        events = hits(records([100000] * 5 + [300000], ["CA"] * 5 + ["JP"]))
        self.assertEqual(events[0]["known_countries"], ["CA"])
        self.assertEqual(events[0]["reasons"], ["NEW_DESTINATION"])

    def test_same_timestamp_and_future_history_excluded(self):
        rows = records([100000] * 5 + [300000], ["US"] * 5 + ["JP"])
        ties = [dict(row, transaction_time=rows[-1]["transaction_time"]) for row in rows]
        self.assertEqual(hits(ties), [])
        # Future visits to JP and large amounts cannot change this earlier trigger.
        rows += [dict(records([9999999])[0], transaction_id="FUTURE", counterparty_country="JP", transaction_time="2026-02-01 00:00:00")]
        event = hits(rows)[0]
        self.assertEqual((event["trigger"]["transaction_id"], event["known_countries"], event["median_twice_cents"]),
                         ("T00005", ["US"], 200000))

    def test_exact_90_day_lower_boundary(self):
        rows = records([100000] * 5 + [300000], ["US"] * 5 + ["JP"])
        rows[-1]["transaction_time"] = "2026-04-01 00:00:00"
        self.assertEqual(len(hits(rows)), 1)
        rows[-1]["transaction_time"] = "2026-04-01 00:00:01"
        self.assertEqual(hits(rows), [])

    def test_country_remains_known_until_last_visit_expires(self):
        rows = records([100000] * 7 + [300000], ["US"] * 2 + ["GB"] * 5 + ["US"])
        rows[-1]["transaction_time"] = "2026-04-01 00:00:01"
        self.assertEqual(hits(rows), [])
        rows[-1]["transaction_time"] = "2026-04-02 00:00:01"
        event = hits(rows)[0]
        self.assertEqual(event["known_countries"], ["GB"])
        self.assertEqual(event["reasons"], ["NEW_DESTINATION"])

    def test_status_direction_and_type_history_filters(self):
        self.add([100000] * 4)
        for direction, kind, status in (("IN", "WIRE", "POSTED"), ("OUT", "E_TRANSFER", "POSTED"),
                                        ("OUT", "WIRE", "PENDING"), ("OUT", "WIRE", "FAILED"), ("OUT", "WIRE", "REVERSED")):
            self.add([100000], kind=kind, direction=direction, status=status)
        self.add([300000], ["JP"], start_day=6)
        self.assertEqual(detect_r004(self.db)["matched_events"], 0)
        self.add([100000], ["CA"], start_day=4)
        self.assertEqual(detect_r004(self.db)["new_alerts"], 1)

    def test_account_baselines_are_not_pooled(self):
        self.add([100000] * 5, account="A2")
        self.add([300000], ["JP"], account="A1", start_day=6)
        self.assertEqual(detect_r004(self.db)["matched_events"], 0)

    def test_repeat_and_changed_config_preserve_prior_result(self):
        self.add([100000] * 5 + [300000], ["US"] * 5 + ["JP"])
        detect_r004(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE alerts SET status='CLOSED'")
        before = read_alerts(self.db, with_evidence=True)
        self.assertEqual(detect_r004(self.db)["new_alerts"], 0)
        self.assertEqual(read_alerts(self.db, with_evidence=True), before)
        self.assertEqual(detect_r004(self.db, wire_multiplier=5)["new_alerts"], 1)
        self.assertEqual(len(read_alerts(self.db, rule="R004")), 2)

    def test_detail_failure_rolls_back_alert_and_evidence(self):
        self.add([100000] * 5 + [300000], ["US"] * 5 + ["JP"])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""CREATE TRIGGER reject_details BEFORE INSERT ON alert_details
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            detect_r004(self.db)
        self.assertEqual(read_alerts(self.db), [])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM alert_transactions").fetchone()[0], 0)

    def test_invalid_parameters_and_all_rule_prevalidation(self):
        missing = self.folder / "missing.db"
        for parameters in ({"min_wire_history": True}, {"wire_lookback_days": 3651}, {"wire_multiplier": 1.5},
                           {"minimum_cross_border_cents": 2**63}, {"minimum_cross_border_cents": 0}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                detect_r004(missing, **parameters)
        self.assertFalse(missing.exists())
        create_dataset(100, output_dir=self.folder / "all")
        db = self.folder / "all.db"
        load_dataset(self.folder / "all", db)
        result = subprocess.run([sys.executable, str(ROOT / "src/detect_risks.py"), "--db", str(db), "--rule", "all",
                                 "--wire-lookback-days", "0"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Detection failed:", result.stderr)
        self.assertEqual(read_alerts(db), [])

    def test_seeded_detection_without_labels_and_minimum_counts(self):
        folder = self.folder / "generated"
        create_dataset(1000, output_dir=folder, include_r001=True, include_r003=True, include_r004=True)
        with (folder / "injected_scenarios.csv").open(newline="") as handle:
            label = next(row for row in csv.DictReader(handle) if row["rule_id"] == "R004")
        ids = label["transaction_ids"].split("|")
        (folder / "injected_scenarios.csv").unlink()
        db = folder / "banking.db"
        load_dataset(folder, db)
        detect_r004(db)
        seeded = [alert for alert in read_alerts(db, rule="R004", account=label["account_id"], limit=1000, with_evidence=True)
                  if alert["details"]["trigger_transaction_id"] == ids[-1]][0]
        self.assertEqual({row["transaction_id"] for row in seeded["transactions"]}, set(ids))
        self.assertEqual(seeded["details"]["reasons"], ["NEW_DESTINATION"])
        for count, other_flags in ((11, False), (19, True)):
            minimal = self.folder / f"minimal{count}"
            with self.assertRaises(ValueError):
                create_dataset(count - 1, 1, 1, output_dir=minimal, include_r001=other_flags,
                               include_r003=other_flags, include_r004=True)
            create_dataset(count, 1, 1, output_dir=minimal, include_r001=other_flags,
                           include_r003=other_flags, include_r004=True)
            load_dataset(minimal, minimal / "banking.db")
            self.assertEqual(detect_r004(minimal / "banking.db")["new_alerts"], 1)

    def test_matches_independent_history_oracle(self):
        rng = random.Random(42)
        for _ in range(100):
            rows = sorted([{"transaction_id": str(i), "amount_cents": rng.randint(1, 1000000),
                            "counterparty_country": rng.choice(("CA", "US", "GB", "JP")),
                            "transaction_time": (datetime(2026, 1, 1) + timedelta(hours=rng.randrange(120))).strftime("%Y-%m-%d %H:%M:%S")}
                           for i in range(40)], key=lambda row: (row["transaction_time"], row["transaction_id"]))
            expected = []
            for row in rows:
                if row["counterparty_country"] == "CA" or row["amount_cents"] <= 200000:
                    continue
                when = datetime.strptime(row["transaction_time"], "%Y-%m-%d %H:%M:%S")
                history = [old for old in rows if when - timedelta(days=2) <= datetime.strptime(old["transaction_time"], "%Y-%m-%d %H:%M:%S") < when]
                if len(history) < 5:
                    continue
                amounts = sorted(old["amount_cents"] for old in history)
                n = len(amounts)
                median = 2 * amounts[n // 2] if n % 2 else amounts[n // 2 - 1] + amounts[n // 2]
                known = sorted({old["counterparty_country"] for old in history})
                reasons = (["NEW_DESTINATION"] if row["counterparty_country"] not in known else [])
                if 2 * row["amount_cents"] > 4 * median:
                    reasons.append("UNUSUAL_AMOUNT")
                if reasons:
                    expected.append((row["transaction_id"], median, known, reasons, [old["transaction_id"] for old in history]))
            actual = [(event["trigger"]["transaction_id"], event["median_twice_cents"], event["known_countries"],
                       event["reasons"], [old["transaction_id"] for old in event["history"]]) for event in hits(rows, wire_lookback_days=2)]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
