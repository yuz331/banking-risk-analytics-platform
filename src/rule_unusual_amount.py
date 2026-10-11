"""R001: exact historical-median comparisons with no future-data leakage."""

import json
from bisect import bisect_left, insort
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from time import perf_counter

from risk_storage import detection_database, save_alert

ELIGIBLE_SQL = """
SELECT * FROM transactions
WHERE status = 'POSTED' AND direction = 'OUT'
    AND transaction_type IN ('E_TRANSFER', 'WIRE')
ORDER BY account_id, transaction_time, transaction_id
"""


def validate_r001_parameters(min_history, lookback_days, multiplier, minimum_amount_cents):
    parameters = {"min_history": min_history, "lookback_days": lookback_days,
                  "multiplier": multiplier, "minimum_amount_cents": minimum_amount_cents}
    for name, value in parameters.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"R001 {name} must be an integer >= 1")
    if minimum_amount_cents > 9223372036854775807:
        raise ValueError("R001 minimum_amount_cents must fit SQLite integer cents")
    if lookback_days > 3650:
        raise ValueError("R001 lookback_days must be <= 3650")


def find_unusual_amounts(rows, min_history=5, lookback_days=30,
                        multiplier=4, minimum_amount_cents=200000):
    """Yield assessment records for one account, sorted by time and ID.

    History interval is [current_time - lookback, current_time). A timestamp
    batch is assessed before adding any batch members, so ties cannot leak.
    Median is stored as twice the number of cents for exact half-cent medians.
    """
    validate_r001_parameters(min_history, lookback_days, multiplier, minimum_amount_cents)
    history, amounts = deque(), []
    lookback = timedelta(days=lookback_days)
    for timestamp, batch_iter in groupby(rows, key=lambda row: row["transaction_time"]):
        current_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        cutoff = current_time - lookback
        while history and history[0][0] < cutoff:
            _, old = history.popleft()
            amounts.pop(bisect_left(amounts, old["amount_cents"]))
        batch = list(batch_iter)
        for row in batch:
            count = len(amounts)
            if count < min_history:
                yield {"trigger": row, "insufficient_history": True}
                continue
            middle = count // 2
            median_twice = (2 * amounts[middle] if count % 2 else amounts[middle - 1] + amounts[middle])
            if row["amount_cents"] > minimum_amount_cents and 2 * row["amount_cents"] > multiplier * median_twice:
                yield {"trigger": row, "insufficient_history": False, "median_twice_cents": median_twice,
                       "history": [old for _, old in history]}
        for row in batch:
            history.append((current_time, row))
            insort(amounts, row["amount_cents"])


def detect_r001(db_path=Path("data/banking.db"), min_history=5, lookback_days=30,
                multiplier=4, minimum_amount_cents=200000):
    parameters = {"min_history": min_history, "lookback_days": lookback_days,
                  "multiplier": multiplier, "minimum_amount_cents": minimum_amount_cents}
    validate_r001_parameters(**parameters)
    started = perf_counter()
    parameters_json = json.dumps(parameters, sort_keys=True)
    eligible = skipped = matched = inserted = 0
    with detection_database(db_path) as connection:
        for account, account_rows in groupby(connection.execute(ELIGIBLE_SQL), key=lambda row: row["account_id"]):
            rows = list(account_rows)
            eligible += len(rows)
            for event in find_unusual_amounts(rows, **parameters):
                if event["insufficient_history"]:
                    skipped += 1
                    continue
                matched += 1
                trigger, history = event["trigger"], event["history"]
                median_twice = event["median_twice_cents"]
                score = min(100, 60 + 10 * (2 * trigger["amount_cents"] // median_twice - multiplier))
                median_cad = Decimal(median_twice) / 200
                explanation = (f"Account {account}: transfer {trigger['transaction_id']} of CAD "
                               f"{Decimal(trigger['amount_cents']) / 100:.2f} exceeds both CAD "
                               f"{Decimal(minimum_amount_cents) / 100:.2f} and {multiplier}x the historical "
                               f"median CAD {median_cad:f}, based on {len(history)} posted outbound "
                               f"e-Transfer/wire transactions in the prior {lookback_days} days. "
                               "Current/same-timestamp transactions are excluded from the baseline.")
                details = {"trigger_transaction_id": trigger["transaction_id"], "history_count": len(history),
                           "median_twice_cents": median_twice,
                           "history_start_utc": history[0]["transaction_time"],
                           "history_end_utc": history[-1]["transaction_time"]}
                inserted += save_alert(connection, "R001", "1", parameters_json, account,
                                       history + [trigger], trigger["transaction_time"], trigger["transaction_time"],
                                       1, score, explanation, details)
    return {"rule_id": "R001", "parameters": parameters, "eligible_transactions": eligible,
            "skipped_insufficient_history": skipped, "matched_events": matched,
            "new_alerts": inserted, "existing_alerts": matched - inserted,
            "elapsed_seconds": round(perf_counter() - started, 6)}
