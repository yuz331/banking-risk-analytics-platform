"""Detect R002 high-velocity transfer events in an immutable synthetic snapshot."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from time import perf_counter

from load_database import SCHEMA

ROOT = Path(__file__).resolve().parents[1]
RULE_VERSION = "1"
ELIGIBLE_SQL = """
SELECT * FROM transactions
WHERE status = 'POSTED' AND direction = 'OUT'
    AND transaction_type IN ('E_TRANSFER', 'WIRE')
ORDER BY account_id, transaction_time, transaction_id
"""


def validate_parameters(min_count, window_minutes):
    if type(min_count) is not int or min_count < 2:
        raise ValueError("R002 min_count must be an integer >= 2")
    if type(window_minutes) is not int or window_minutes < 1:
        raise ValueError("R002 window_minutes must be an integer >= 1")


def load_parameters(path=ROOT / "config" / "rules.json"):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"R002"}:
        raise ValueError("Config must contain only the implemented R002 rule")
    parameters = config["R002"]
    if not isinstance(parameters, dict) or set(parameters) != {"min_count", "window_minutes"}:
        raise ValueError("R002 config requires exactly min_count and window_minutes")
    validate_parameters(**parameters)
    return parameters


def priority_for_score(score):
    if score >= 70:
        return "HIGH"
    return "MEDIUM" if score >= 40 else "LOW"


def find_events(rows, min_count=5, window_minutes=60):
    """Find rolling hits, merging windows sharing at least one transaction.

    Input: one account's eligible rows ordered by UTC timestamp and ID.
    Evidence is the union of qualifying windows; an event may span >60 minutes.
    Each event still has a qualifying rolling window with at least min_count rows.
    """
    validate_parameters(min_count, window_minutes)
    times = [datetime.strptime(row["transaction_time"], "%Y-%m-%d %H:%M:%S") for row in rows]
    window = timedelta(minutes=window_minutes)
    left = 0
    event = None
    for right, current in enumerate(times):
        while current - times[left] > window:
            left += 1
        count = right - left + 1
        if count < min_count:
            continue
        if event is None or left > event["right"]:
            if event:
                yield {"rows": rows[event["left"]:event["right"] + 1], "peak_count": event["peak_count"]}
            event = {"left": left, "right": right, "peak_count": count}
        else:
            event["right"] = right
            event["peak_count"] = max(event["peak_count"], count)
    if event:
        yield {"rows": rows[event["left"]:event["right"] + 1], "peak_count": event["peak_count"]}


def detect_r002(db_path=Path("data/banking.db"), min_count=5, window_minutes=60):
    validate_parameters(min_count, window_minutes)
    started = perf_counter()
    parameters_json = json.dumps({"min_count": min_count, "window_minutes": window_minutes}, sort_keys=True)
    created_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    matched = inserted = eligible_count = 0
    # mode=rw refuses a missing file rather than silently creating an empty DB.
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as connection, connection:
        connection.row_factory = sqlite3.Row
        required = {"customers", "accounts", "transactions"}
        actual = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not required.issubset(actual):
            raise ValueError("Source tables are missing; run src/load_database.py first")
        # Additive schema creation upgrades Phase 2 DBs without replacing records.
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute("BEGIN IMMEDIATE")
        for account_id, account_rows in groupby(connection.execute(ELIGIBLE_SQL), key=lambda row: row["account_id"]):
            rows = list(account_rows)
            eligible_count += len(rows)
            for event in find_events(rows, min_count, window_minutes):
                matched += 1
                evidence = event["rows"]
                identity = json.dumps(["R002", RULE_VERSION, parameters_json, account_id,
                                       [row["transaction_id"] for row in evidence]], separators=(",", ":"))
                alert_id = "R002-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
                score = min(100, 60 + 10 * (event["peak_count"] - min_count))
                explanation = (f"Account {account_id}: peak of {event['peak_count']} posted outbound "
                               f"e-Transfer/wire transactions within an inclusive {window_minutes}-minute "
                               f"rolling window (threshold {min_count}). Overlapping qualifying windows "
                               f"were grouped into one event with {len(evidence)} evidence transactions "
                               f"from {evidence[0]['transaction_time']} to {evidence[-1]['transaction_time']} UTC.")
                cursor = connection.execute("""
                    INSERT INTO alerts (
                        alert_id, rule_id, rule_version, account_id, parameters_json,
                        event_start_utc, event_end_utc, peak_count, evidence_count,
                        score, priority, created_time_utc, status, explanation
                    ) VALUES (?, 'R002', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)
                    ON CONFLICT(alert_id) DO NOTHING
                """, (alert_id, RULE_VERSION, account_id, parameters_json,
                      evidence[0]["transaction_time"], evidence[-1]["transaction_time"],
                      event["peak_count"], len(evidence), score, priority_for_score(score), created_time, explanation))
                if cursor.rowcount:
                    inserted += 1
                    connection.executemany("INSERT INTO alert_transactions VALUES (?, ?)",
                                           [(alert_id, row["transaction_id"]) for row in evidence])
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign-key integrity check failed")
    return {"rule_id": "R002", "parameters": json.loads(parameters_json),
            "eligible_transactions": eligible_count, "matched_events": matched,
            "new_alerts": inserted, "existing_alerts": matched - inserted,
            "elapsed_seconds": round(perf_counter() - started, 6)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/banking.db"))
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "rules.json")
    parser.add_argument("--min-count", type=int)
    parser.add_argument("--window-minutes", type=int)
    args = parser.parse_args()
    try:
        parameters = load_parameters(args.config)
        for name in ("min_count", "window_minutes"):
            if getattr(args, name) is not None:
                parameters[name] = getattr(args, name)
        result = detect_r002(args.db, **parameters)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Detection failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
