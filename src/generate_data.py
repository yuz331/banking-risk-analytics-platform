"""Create reproducible, entirely synthetic Canadian banking transactions.

Phase 1 of the Banking Transaction Monitoring & Risk Analytics Platform.
Python standard library only; no real customers or financial information.
"""

import argparse
import csv
import math
import random
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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def create_dataset(count=1000, customer_count=300, account_count=450,
                   seed=42, output_dir=Path("data")):
    """Write customers, accounts, transactions and seeded-scenario CSVs.

    One intentionally planted R002 scenario contains five outbound transfers
    from the same account over forty minutes. All other data are synthetic.
    """
    if count < 5 or customer_count < 1 or account_count < customer_count:
        raise ValueError("Require transactions >= 5 and accounts >= customers >= 1")

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
    for _ in range(count - 5):
        kind = rng.choices(TRANSACTION_TYPES, weights=TYPE_WEIGHTS)[0]
        direction = ("IN" if kind in ("DIRECT_DEPOSIT", "CASH_DEPOSIT")
                     else "OUT" if kind in ("BILL_PAYMENT", "DEBIT_PURCHASE", "ATM_WITHDRAWAL")
                     else rng.choice(["IN", "OUT"]))
        # Work in whole cents to avoid floating-point currency errors.
        amount_cents = round(rng.lognormvariate(math.log(MEDIAN_AMOUNTS[kind]), 0.8) * 100)
        amount_cents = max(100, min(amount_cents, 5_000_000))
        happened = START + timedelta(minutes=rng.randrange(DAYS * 24 * 60))
        country = rng.choices(["CA", "US", "GB", "JP"], weights=[50, 30, 12, 8])[0] if kind == "WIRE" else "CA"
        transactions.append({
            "account_id": f"A{rng.randint(1, account_count):05d}",
            "transaction_time": timestamp(happened),
            "amount_cad": f"{amount_cents / 100:.2f}",
            "direction": direction,
            "transaction_type": kind,
            "counterparty_id": f"CP{rng.randint(1, 1000):05d}",
            "counterparty_country": country,
            "status": "POSTED",
        })

    # A deliberately injected example for future R002 high-velocity detection.
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

    transactions.sort(key=lambda record: (record["transaction_time"], record["account_id"]))
    for number, record in enumerate(transactions, start=1):
        record["transaction_id"] = f"T{number:07d}"

    scenario_ids = [record["transaction_id"] for record in injected_transactions]

    write_csv(output_dir / "customers.csv", (
        "customer_id", "segment", "onboarding_date"), customers)
    write_csv(output_dir / "accounts.csv", (
        "account_id", "customer_id", "account_type", "opening_date"), accounts)
    write_csv(output_dir / "transactions.csv", TRANSACTION_COLUMNS, transactions)
    write_csv(output_dir / "injected_scenarios.csv", (
        "scenario_id", "rule_id", "account_id", "start_time_utc",
        "end_time_utc", "transaction_ids"), [{
            "scenario_id": "S001",
            "rule_id": "R002",
            "account_id": "A00001",
            "start_time_utc": timestamp(SEED_EVENT_START),
            "end_time_utc": timestamp(SEED_EVENT_START + timedelta(minutes=40)),
            "transaction_ids": "|".join(scenario_ids),
        }])

    return {"customers": len(customers), "accounts": len(accounts),
            "transactions": len(transactions), "scenario_transactions": len(scenario_ids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=1000)
    parser.add_argument("--customers", type=int, default=300)
    parser.add_argument("--accounts", type=int, default=450)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    try:
        result = create_dataset(args.transactions, args.customers, args.accounts,
                                args.seed, args.output_dir)
    except ValueError as error:
        parser.error(str(error))

    print(f"Created {result['customers']} customers, {result['accounts']} accounts, "
          f"{result['transactions']} transactions in {args.output_dir}/")
    print(f"Seeded R002 scenario: {result['scenario_transactions']} outbound transfers in 40 minutes")


if __name__ == "__main__":
    main()
