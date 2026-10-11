"""Create reproducible, entirely synthetic Canadian banking transactions.

Phase 1 of the Banking Transaction Monitoring & Risk Analytics Platform.
Python standard library only; no real customers or financial information.
"""

import argparse
import csv
import math
import os
import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

START = datetime(2026, 1, 1, 0, 0, 0)  # All timestamps in this prototype are UTC.
DAYS = 90
SEED_EVENT_START = datetime(2026, 2, 15, 10, 0, 0)

TRANSACTION_TYPES = (
    "E_TRANSFER", "BILL_PAYMENT", "DIRECT_DEPOSIT", "DEBIT_PURCHASE",
    "WIRE", "CASH_DEPOSIT", "ATM_WITHDRAWAL",
)
TYPE_WEIGHTS = (30, 18, 12, 23, 5, 5, 7)
MEDIAN_AMOUNTS = {
    "E_TRANSFER": 220, "BILL_PAYMENT": 125, "DIRECT_DEPOSIT": 2200,
    "DEBIT_PURCHASE": 55, "WIRE": 1500, "CASH_DEPOSIT": 450,
    "ATM_WITHDRAWAL": 100,
}
TRANSACTION_COLUMNS = (
    "transaction_id", "account_id", "transaction_time", "amount_cad",
    "direction", "transaction_type", "counterparty_id",
    "counterparty_country", "status",
)


def timestamp(value):
    """SQLite-friendly UTC timestamp, without a timezone suffix."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def write_csv(path, columns, records):
    """Replace one CSV only after its full write succeeds."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8",
                                         dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_dataset(count=1000, customer_count=300, account_count=450,
                   seed=42, output_dir=Path("data"), include_r001=False, include_r003=False,
                   include_r004=False):
    """Write customers, accounts, transactions and seeded-scenario CSVs.

    One intentionally planted R002 scenario contains five outbound transfers
    from the same account over forty minutes. include_r001 optionally reserves
    six records for five CAD 100 historical transfers and a CAD 5,000 trigger.
    include_r003 optionally reserves a CAD 10,000 receipt and CAD 8,500 transfer.
    include_r004 reserves five US-destination CAD 1,000 wires and one new
    JP-destination CAD 3,000 wire. Amounts remain CAD; no FX conversion is used.
    All data are synthetic. Default output is unchanged by the optional seed.
    """
    if count < 5 or customer_count < 1 or account_count < customer_count:
        raise ValueError("Require transactions >= 5 and accounts >= customers >= 1")
    reserved = 5 + (6 if include_r001 else 0) + (2 if include_r003 else 0) + (6 if include_r004 else 0)
    if count < reserved:
        raise ValueError(f"Selected seeded scenarios require transactions >= {reserved}")

    rng = random.Random(seed)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    customers = []
    for number in range(1, customer_count + 1):
        onboarded = datetime(2022, 1, 1) + timedelta(days=rng.randrange(1100))
        customers.append({
            "customer_id": f"C{number:05d}",
            "segment": rng.choices(["PERSONAL", "SMALL_BUSINESS"], weights=[85, 15])[0],
            "onboarding_date": onboarded.strftime("%Y-%m-%d"),
        })

    accounts = []
    for number in range(1, account_count + 1):
        # First give each customer one account; additional accounts are random.
        customer_number = number if number <= customer_count else rng.randint(1, customer_count)
        accounts.append({
            "account_id": f"A{number:05d}",
            "customer_id": f"C{customer_number:05d}",
            "account_type": rng.choice(["CHEQUING", "SAVINGS"]),
            "opening_date": "2025-07-01",
        })

    transactions = []
    r001_account = "A00002" if account_count >= 2 else "A00001"
    r001_start = START + timedelta(hours=12)
    r001_trigger_time = r001_start + timedelta(days=5)
    r003_account = f"A{min(3, account_count):05d}"
    r003_start = datetime(2026, 3, 10, 9, 0)
    r003_end = r003_start + timedelta(hours=6)
    r004_account = f"A{min(4, account_count):05d}"
    r004_start = START + timedelta(days=10, hours=12)
    r004_trigger_time = r004_start + timedelta(days=5)
    for _ in range(count - reserved):
        kind = rng.choices(TRANSACTION_TYPES, weights=TYPE_WEIGHTS)[0]
        direction = ("IN" if kind in ("DIRECT_DEPOSIT", "CASH_DEPOSIT")
                     else "OUT" if kind in ("BILL_PAYMENT", "DEBIT_PURCHASE", "ATM_WITHDRAWAL")
                     else rng.choice(["IN", "OUT"]))
        # Work in whole cents to avoid floating-point currency errors.
        amount_cents = round(rng.lognormvariate(math.log(MEDIAN_AMOUNTS[kind]), 0.8) * 100)
        amount_cents = max(100, min(amount_cents, 5_000_000))
        happened = START + timedelta(minutes=rng.randrange(DAYS * 24 * 60))
        country = rng.choices(["CA", "US", "GB", "JP"], weights=[50, 30, 12, 8])[0] if kind == "WIRE" else "CA"
        account_id = f"A{rng.randint(1, account_count):05d}"
        # Keep the optional seed's first five-transfer baseline exact. Random
        # eligible transfers on this account through the trigger become inbound.
        if include_r001 and account_id == r001_account and happened <= r001_trigger_time and kind in ("E_TRANSFER", "WIRE"):
            direction = "IN"
        if include_r003 and account_id == r003_account and r003_start - timedelta(hours=24) <= happened <= r003_end:
            # Isolate the demonstration pair from competing receipts/transfers.
            kind, direction, country = "BILL_PAYMENT", "OUT", "CA"
        if include_r004 and account_id == r004_account and happened <= r004_trigger_time and kind == "WIRE":
            # Keep the optional account's initial outbound wire baseline exact.
            direction = "IN"
        transactions.append({
            "account_id": account_id,
            "transaction_time": timestamp(happened),
            "amount_cad": f"{amount_cents / 100:.2f}",
            "direction": direction,
            "transaction_type": kind,
            "counterparty_id": f"CP{rng.randint(1, 1000):05d}",
            "counterparty_country": country,
            "status": "POSTED",
        })

    # A deliberately injected example for R002 high-velocity detection.
    injected_transactions = []
    for minute in (0, 10, 20, 30, 40):
        scenario_tx = {
            "account_id": "A00001",
            "transaction_time": timestamp(SEED_EVENT_START + timedelta(minutes=minute)),
            "amount_cad": f"{rng.randint(90000, 130000) / 100:.2f}",
            "direction": "OUT",
            "transaction_type": "E_TRANSFER",
            "counterparty_id": f"CP{2001 + minute:05d}",
            "counterparty_country": "CA",
            "status": "POSTED",
        }
        injected_transactions.append(scenario_tx)
        transactions.append(scenario_tx)

    r001_transactions = []
    if include_r001:
        # Five CAD 100 transfers on separate days, then one CAD 5,000 transfer.
        for day in range(6):
            record = {
                "account_id": r001_account,
                "transaction_time": timestamp(r001_start + timedelta(days=day)),
                "amount_cad": "100.00" if day < 5 else "5000.00",
                "direction": "OUT", "transaction_type": "E_TRANSFER",
                "counterparty_id": f"CP{3001 + day:05d}",
                "counterparty_country": "CA", "status": "POSTED",
            }
            r001_transactions.append(record)
            transactions.append(record)

    r003_transactions = []
    if include_r003:
        for happened, direction, amount in ((r003_start, "IN", "10000.00"), (r003_end, "OUT", "8500.00")):
            record = {
                "account_id": r003_account, "transaction_time": timestamp(happened),
                "amount_cad": amount, "direction": direction, "transaction_type": "WIRE",
                "counterparty_id": "CP04001" if direction == "IN" else "CP04002",
                "counterparty_country": "CA", "status": "POSTED",
            }
            r003_transactions.append(record)
            transactions.append(record)

    r004_transactions = []
    if include_r004:
        for day in range(6):
            record = {
                "account_id": r004_account,
                "transaction_time": timestamp(r004_start + timedelta(days=day)),
                "amount_cad": "1000.00" if day < 5 else "3000.00",
                "direction": "OUT", "transaction_type": "WIRE",
                "counterparty_id": f"CP{5001 + day:05d}",
                "counterparty_country": "US" if day < 5 else "JP", "status": "POSTED",
            }
            r004_transactions.append(record)
            transactions.append(record)

    transactions.sort(key=lambda record: (record["transaction_time"], record["account_id"]))
    for number, record in enumerate(transactions, start=1):
        record["transaction_id"] = f"T{number:07d}"

    scenario_ids = [record["transaction_id"] for record in injected_transactions]
    scenarios = [{
        "scenario_id": "S001", "rule_id": "R002", "account_id": "A00001",
        "start_time_utc": timestamp(SEED_EVENT_START),
        "end_time_utc": timestamp(SEED_EVENT_START + timedelta(minutes=40)),
        "transaction_ids": "|".join(scenario_ids),
    }]
    if include_r001:
        scenarios.append({
            "scenario_id": "S002", "rule_id": "R001", "account_id": r001_account,
            "start_time_utc": timestamp(r001_start), "end_time_utc": timestamp(r001_trigger_time),
            "transaction_ids": "|".join(record["transaction_id"] for record in r001_transactions),
        })
    if include_r003:
        scenarios.append({
            "scenario_id": "S003", "rule_id": "R003", "account_id": r003_account,
            "start_time_utc": timestamp(r003_start), "end_time_utc": timestamp(r003_end),
            "transaction_ids": "|".join(record["transaction_id"] for record in r003_transactions),
        })
    if include_r004:
        scenarios.append({
            "scenario_id": "S004", "rule_id": "R004", "account_id": r004_account,
            "start_time_utc": timestamp(r004_start), "end_time_utc": timestamp(r004_trigger_time),
            "transaction_ids": "|".join(record["transaction_id"] for record in r004_transactions),
        })

    write_csv(output_dir / "customers.csv", (
        "customer_id", "segment", "onboarding_date"), customers)
    write_csv(output_dir / "accounts.csv", (
        "account_id", "customer_id", "account_type", "opening_date"), accounts)
    write_csv(output_dir / "transactions.csv", TRANSACTION_COLUMNS, transactions)
    write_csv(output_dir / "injected_scenarios.csv", (
        "scenario_id", "rule_id", "account_id", "start_time_utc",
        "end_time_utc", "transaction_ids"), scenarios)

    return {"customers": len(customers), "accounts": len(accounts),
            "transactions": len(transactions), "scenario_transactions": len(scenario_ids),
            "r001_scenario_transactions": len(r001_transactions),
            "r003_scenario_transactions": len(r003_transactions),
            "r004_scenario_transactions": len(r004_transactions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=1000)
    parser.add_argument("--customers", type=int, default=300)
    parser.add_argument("--accounts", type=int, default=450)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--include-r001", action="store_true", help="Include five historical transfers and an unusual-amount trigger")
    parser.add_argument("--include-r003", action="store_true", help="Include a material receipt and rapid outbound transfer")
    parser.add_argument("--include-r004", action="store_true", help="Include historical wires and a new-destination trigger")
    args = parser.parse_args()

    try:
        result = create_dataset(args.transactions, args.customers, args.accounts,
                                args.seed, args.output_dir, args.include_r001, args.include_r003, args.include_r004)
    except ValueError as error:
        parser.error(str(error))

    print(f"Created {result['customers']} customers, {result['accounts']} accounts, "
          f"{result['transactions']} transactions in {args.output_dir}/")
    print(f"Seeded R002 scenario: {result['scenario_transactions']} outbound transfers in 40 minutes")
    if args.include_r001:
        print("Seeded R001 scenario: five CAD 100 historical transfers, then a CAD 5,000 transfer")
    if args.include_r003:
        print("Seeded R003 scenario: CAD 10,000 receipt, then CAD 8,500 transfer six hours later")
    if args.include_r004:
        print("Seeded R004 scenario: five CAD 1,000 wires to US, then a CAD 3,000 wire to JP")


if __name__ == "__main__":
    main()
