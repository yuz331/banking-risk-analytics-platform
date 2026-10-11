"""Run implemented risk rules against an immutable synthetic snapshot."""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path
from time import perf_counter

from risk_storage import detection_database, priority_for_score, save_alert

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


def load_parameters(path=ROOT / "config" / "rules.json", rule="R002"):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not set(config).issubset({"R001", "R002"}) or rule not in config:
        raise ValueError(f"Config must contain the requested {rule} and only implemented rules")
    parameters = config[rule]
    keys = ({"min_count", "window_minutes"} if rule == "R002" else
            {"min_history", "lookback_days", "multiplier", "minimum_amount_cents"})
    if not isinstance(parameters, dict) or set(parameters) != keys:
        raise ValueError(f"{rule} config requires exactly {', '.join(sorted(keys))}")
    if rule == "R002":
        validate_parameters(**parameters)
    else:
        from rule_unusual_amount import validate_r001_parameters
        validate_r001_parameters(**parameters)
    return parameters


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
    matched = inserted = eligible_count = 0
    with detection_database(db_path) as connection:
        for account_id, account_rows in groupby(connection.execute(ELIGIBLE_SQL), key=lambda row: row["account_id"]):
            rows = list(account_rows)
            eligible_count += len(rows)
            for event in find_events(rows, min_count, window_minutes):
                matched += 1
                evidence = event["rows"]
                score = min(100, 60 + 10 * (event["peak_count"] - min_count))
                explanation = (f"Account {account_id}: peak of {event['peak_count']} posted outbound "
                               f"e-Transfer/wire transactions within an inclusive {window_minutes}-minute "
                               f"rolling window (threshold {min_count}). Overlapping qualifying windows "
                               f"were grouped into one event with {len(evidence)} evidence transactions "
                               f"from {evidence[0]['transaction_time']} to {evidence[-1]['transaction_time']} UTC.")
                inserted += save_alert(connection, "R002", RULE_VERSION, parameters_json,
                                       account_id, evidence, evidence[0]["transaction_time"],
                                       evidence[-1]["transaction_time"], event["peak_count"], score, explanation)
    return {"rule_id": "R002", "parameters": json.loads(parameters_json),
            "eligible_transactions": eligible_count, "matched_events": matched,
            "new_alerts": inserted, "existing_alerts": matched - inserted,
            "elapsed_seconds": round(perf_counter() - started, 6)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/banking.db"))
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "rules.json")
    parser.add_argument("--rule", choices=("R001", "R002", "all"), default="R002")
    parser.add_argument("--min-count", type=int)
    parser.add_argument("--window-minutes", type=int)
    parser.add_argument("--min-history", type=int)
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--multiplier", type=int)
    parser.add_argument("--minimum-amount-cents", type=int)
    args = parser.parse_args()
    try:
        from rule_unusual_amount import detect_r001
        selected = ("R001", "R002") if args.rule == "all" else (args.rule,)
        allowed = {"min_count", "window_minutes"} if args.rule == "R002" else {
            "min_history", "lookback_days", "multiplier", "minimum_amount_cents"}
        if args.rule == "all":
            allowed |= {"min_count", "window_minutes"}
        overrides = {name: getattr(args, name) for name in (
            "min_count", "window_minutes", "min_history", "lookback_days", "multiplier", "minimum_amount_cents")
            if getattr(args, name) is not None}
        if not set(overrides).issubset(allowed):
            raise ValueError("An override applies to a rule that was not selected")
        configurations = {rule: load_parameters(args.config, rule) for rule in selected}
        for rule, parameters in configurations.items():
            parameters.update({key: value for key, value in overrides.items() if key in parameters})
            if rule == "R002":
                validate_parameters(**parameters)
            else:
                from rule_unusual_amount import validate_r001_parameters
                validate_r001_parameters(**parameters)
        results = [(detect_r002 if rule == "R002" else detect_r001)(args.db, **parameters)
                   for rule, parameters in configurations.items()]
        result = results if args.rule == "all" else results[0]
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Detection failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
