"""Validate synthetic CSVs and atomically import one snapshot into SQLite."""

import argparse
import csv
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter

from generate_data import TRANSACTION_COLUMNS, TRANSACTION_TYPES

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "sql" / "schema.sql"
COLUMNS = {
    "customers": ("customer_id", "segment", "onboarding_date"),
    "accounts": ("account_id", "customer_id", "account_type", "opening_date"),
    "transactions": TRANSACTION_COLUMNS,
}
DB_COLUMNS = dict(COLUMNS, transactions=tuple(
    "amount_cents" if column == "amount_cad" else column
    for column in TRANSACTION_COLUMNS
))


class ValidationError(ValueError):
    """Invalid input; the database is not changed."""


def read_csv(path, columns):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != len(columns) or set(reader.fieldnames) != set(columns):
            raise ValidationError(f"{path.name}: expected columns {', '.join(columns)}")
        records = list(reader)
    if not records:
        raise ValidationError(f"{path.name}: at least one record is required")
    return records


def parse_date(value, with_time=False):
    pattern = "%Y-%m-%d %H:%M:%S" if with_time else "%Y-%m-%d"
    parsed = datetime.strptime(value, pattern)
    if parsed.strftime(pattern) != value:
        raise ValueError(f"expected {pattern}")
    return parsed


def to_cents(value):
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("amount_cad must be a decimal number") from error
    if not amount.is_finite() or amount <= 0 or amount > Decimal("92233720368547758.07"):
        raise ValueError("amount_cad must be positive, finite and fit SQLite integer cents")
    if amount.as_tuple().exponent < -2:
        raise ValueError("amount_cad must have at most two decimal places")
    return int(amount * 100)


def validate_dataset(data_dir):
    """Check shape, IDs, enums, dates, money and foreign keys before writing."""
    tables = {table: read_csv(Path(data_dir) / f"{table}.csv", columns)
              for table, columns in COLUMNS.items()}
    errors = []
    indexes = {}
    for table, records in tables.items():
        key = COLUMNS[table][0]
        index = {}
        for line, row in enumerate(records, 2):
            label = f"{table}.csv row {line}"
            if None in row or any(row.get(column) is None or not row[column].strip()
                                  for column in COLUMNS[table]):
                errors.append(f"{label}: missing/empty fields or extra values")
                continue
            if row[key] in index:
                errors.append(f"{label}: duplicate {key} {row[key]}")
            index[row[key]] = row
            try:
                if table == "customers":
                    if row["segment"] not in ("PERSONAL", "SMALL_BUSINESS"):
                        raise ValueError("invalid segment")
                    parse_date(row["onboarding_date"])
                elif table == "accounts":
                    if row["account_type"] not in ("CHEQUING", "SAVINGS"):
                        raise ValueError("invalid account_type")
                    parse_date(row["opening_date"])
                else:
                    parse_date(row["transaction_time"], with_time=True)
                    row["amount_cents"] = to_cents(row["amount_cad"])
                    if row["direction"] not in ("IN", "OUT"):
                        raise ValueError("invalid direction")
                    if row["transaction_type"] not in TRANSACTION_TYPES:
                        raise ValueError("invalid transaction_type")
                    if row["status"] not in ("POSTED", "PENDING", "FAILED", "REVERSED"):
                        raise ValueError("invalid status")
                    if not re.fullmatch(r"[A-Z]{2}", row["counterparty_country"]):
                        raise ValueError("country must be two uppercase letters")
            except ValueError as error:
                errors.append(f"{label}: {error}")
        indexes[table] = index

    for table, parent, foreign_key, date, parent_date in (
        ("accounts", "customers", "customer_id", "opening_date", "onboarding_date"),
        ("transactions", "accounts", "account_id", "transaction_time", "opening_date"),
    ):
        for line, row in enumerate(tables[table], 2):
            parent_row = indexes[parent].get(row.get(foreign_key))
            if parent_row is None:
                errors.append(f"{table}.csv row {line}: unknown {foreign_key} {row.get(foreign_key)}")
            elif row.get(date) and parent_row.get(parent_date) and row[date][:10] < parent_row[parent_date]:
                errors.append(f"{table}.csv row {line}: {date} precedes {parent_date}")
    if errors:
        details = "\n".join(errors[:20])
        raise ValidationError(f"Validation failed ({len(errors)} errors; first 20 shown):\n{details}")
    return {table: [tuple(row[column] for column in DB_COLUMNS[table]) for row in rows]
            for table, rows in tables.items()}


def load_dataset(data_dir=Path("data"), db_path=Path("data/banking.db")):
    """Import once; an identical re-run is a no-op, a changed snapshot is refused.

    Keep a changed dataset in a new DB path so future alerts/reviews remain safe.
    Validation occurs before opening the database; inserts share one transaction.
    """
    started = perf_counter()
    tables = validate_dataset(data_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute("BEGIN IMMEDIATE")
        existing = {table: connection.execute(f"SELECT {', '.join(DB_COLUMNS[table])} FROM {table}").fetchall()
                    for table in tables}
        if any(existing.values()):
            if any(sorted(existing[table]) != sorted(tables[table]) for table in tables):
                raise ValidationError("Database contains a different dataset. Use a new --db path; existing records were preserved.")
            imported = False
        else:
            for table, rows in tables.items():
                placeholders = ", ".join("?" for _ in DB_COLUMNS[table])
                connection.executemany(
                    f"INSERT INTO {table} ({', '.join(DB_COLUMNS[table])}) VALUES ({placeholders})", rows)
            imported = True
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValidationError("Database foreign key check failed")
    return dict({table: len(rows) for table, rows in tables.items()},
                imported=imported, elapsed_seconds=perf_counter() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--db", type=Path, default=Path("data/banking.db"))
    args = parser.parse_args()
    try:
        result = load_dataset(args.data_dir, args.db)
    except (ValueError, OSError, sqlite3.Error, csv.Error) as error:
        parser.exit(1, f"Import failed: {error}\n")
    action = "Imported" if result["imported"] else "Already loaded (unchanged)"
    print(f"{action}: {result['customers']} customers, {result['accounts']} accounts, "
          f"{result['transactions']} transactions into {args.db}")
    print(f"Validation + import: {result['elapsed_seconds']:.3f} seconds")


if __name__ == "__main__":
    main()
