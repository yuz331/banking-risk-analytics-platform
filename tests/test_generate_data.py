"""Basic quality checks for the synthetic transaction generator."""
import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_data import create_dataset, write_csv


def load(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class GeneratorTests(unittest.TestCase):
    def test_failed_csv_write_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "records.csv"
            path.write_text("id\noriginal\n", encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                write_csv(path, ("id",), [{"id": "first"}, {"id": "second", "unexpected": "fails"}])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(folder.iterdir()), [path])

    def test_data_and_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = create_dataset(1000, 30, 50, 42, folder)
            customers = load(folder / "customers.csv")
            accounts = load(folder / "accounts.csv")
            transactions = load(folder / "transactions.csv")
            scenarios = load(folder / "injected_scenarios.csv")
            self.assertEqual(result["transactions"], 1000)
            self.assertEqual((len(customers), len(accounts), len(transactions)), (30, 50, 1000))
            self.assertEqual(len({t["transaction_id"] for t in transactions}), 1000)
            self.assertTrue(all(a["customer_id"] in {c["customer_id"] for c in customers} for a in accounts))
            self.assertTrue(all(t["account_id"] in {a["account_id"] for a in accounts} for t in transactions))
            ids = set(scenarios[0]["transaction_ids"].split("|"))
            self.assertEqual(len(ids), 5)
            seeded = [t for t in transactions if t["transaction_id"] in ids]
            self.assertEqual(len(seeded), 5)
            self.assertTrue(all(t["account_id"] == "A00001" and t["direction"] == "OUT" for t in seeded))
            times = [datetime.strptime(t["transaction_time"], "%Y-%m-%d %H:%M:%S") for t in seeded]
            self.assertEqual((max(times) - min(times)).total_seconds(), 2400)

    def test_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            create_dataset(100, 10, 15, 7, a)
            create_dataset(100, 10, 15, 7, b)
            self.assertEqual((a / "transactions.csv").read_bytes(), (b / "transactions.csv").read_bytes())

    def test_invalid_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_dataset(4, output_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
