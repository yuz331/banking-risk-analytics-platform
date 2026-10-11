"""R004: destination novelty or unusual size versus prior outbound wire history."""

import json
from bisect import bisect_left, insort
from collections import Counter, deque
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from time import perf_counter

from risk_storage import detection_database, save_alert

ELIGIBLE_SQL = """
SELECT * FROM transactions
WHERE status = 'POSTED' AND direction = 'OUT' AND transaction_type = 'WIRE'
ORDER BY account_id, transaction_time, transaction_id
"""


def validate_r004_parameters(min_wire_history, wire_lookback_days,
                            wire_multiplier, minimum_cross_border_cents):
    for name, value in {"min_wire_history": min_wire_history,
                        "wire_lookback_days": wire_lookback_days,
                        "wire_multiplier": wire_multiplier,
                        "minimum_cross_border_cents": minimum_cross_border_cents}.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"R004 {name} must be an integer >= 1")
    if wire_lookback_days > 3650:
        raise ValueError("R004 wire_lookback_days must be <= 3650")
    if minimum_cross_border_cents > 9223372036854775807:
        raise ValueError("R004 minimum_cross_border_cents must fit SQLite integer cents")


def find_cross_border_events(rows, min_wire_history=5, wire_lookback_days=90,
                             wire_multiplier=4, minimum_cross_border_cents=200000):
    """One account's posted outbound wires, sorted by timestamp and ID.

    All destinations, including CA, contribute baseline history. Only non-CA
    wires can trigger. History interval [time-lookback, time) excludes the
    entire current timestamp batch and all future rows.
    """
    validate_r004_parameters(min_wire_history, wire_lookback_days,
                            wire_multiplier, minimum_cross_border_cents)
    history, amounts, countries = deque(), [], Counter()
    lookback = timedelta(days=wire_lookback_days)
    for timestamp, batch_iter in groupby(rows, key=lambda row: row["transaction_time"]):
        when = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        cutoff = when - lookback
        while history and history[0][0] < cutoff:
            _, old = history.popleft()
            amounts.pop(bisect_left(amounts, old["amount_cents"]))
            countries[old["counterparty_country"]] -= 1
            if not countries[old["counterparty_country"]]:
                del countries[old["counterparty_country"]]
        batch = list(batch_iter)
        for row in batch:
            if row["counterparty_country"] == "CA":
                continue
            count = len(amounts)
            if count < min_wire_history:
                yield {"trigger": row, "insufficient_history": True}
                continue
            if row["amount_cents"] <= minimum_cross_border_cents:
                continue
            middle = count // 2
            median_twice = 2 * amounts[middle] if count % 2 else amounts[middle - 1] + amounts[middle]
            reasons = []
            if row["counterparty_country"] not in countries:
                reasons.append("NEW_DESTINATION")
            if 2 * row["amount_cents"] > wire_multiplier * median_twice:
                reasons.append("UNUSUAL_AMOUNT")
            if reasons:
                yield {"trigger": row, "insufficient_history": False,
                       "history": [old for _, old in history], "median_twice_cents": median_twice,
                       "known_countries": sorted(countries), "reasons": reasons}
        for row in batch:
            history.append((when, row))
            insort(amounts, row["amount_cents"])
            countries[row["counterparty_country"]] += 1


def detect_r004(db_path=Path("data/banking.db"), min_wire_history=5,
                wire_lookback_days=90, wire_multiplier=4, minimum_cross_border_cents=200000):
    parameters = {"min_wire_history": min_wire_history, "wire_lookback_days": wire_lookback_days,
                  "wire_multiplier": wire_multiplier, "minimum_cross_border_cents": minimum_cross_border_cents}
    validate_r004_parameters(**parameters)
    parameters_json = json.dumps(parameters, sort_keys=True)
    started = perf_counter()
    wires = candidates = skipped = matched = inserted = 0
    with detection_database(db_path) as connection:
        for account, account_rows in groupby(connection.execute(ELIGIBLE_SQL), key=lambda row: row["account_id"]):
            rows = list(account_rows)
            wires += len(rows)
            candidates += sum(row["counterparty_country"] != "CA" for row in rows)
            for event in find_cross_border_events(rows, **parameters):
                if event["insufficient_history"]:
                    skipped += 1
                    continue
                matched += 1
                trigger, history = event["trigger"], event["history"]
                reasons = []
                if "NEW_DESTINATION" in event["reasons"]:
                    reasons.append(f"destination {trigger['counterparty_country']} is absent from the prior wire history")
                if "UNUSUAL_AMOUNT" in event["reasons"]:
                    reasons.append(f"amount exceeds {wire_multiplier}x the historical wire median CAD "
                                   f"{Decimal(event['median_twice_cents']) / 200:f}")
                explanation = (f"Account {account}: posted outbound cross-border wire {trigger['transaction_id']} "
                               f"of CAD {Decimal(trigger['amount_cents']) / 100:.2f} to {trigger['counterparty_country']} "
                               f"exceeds the CAD {Decimal(minimum_cross_border_cents) / 100:.2f} floor; "
                               + "; ".join(reasons) + f". Baseline: {len(history)} posted outbound wires in the "
                               f"prior {wire_lookback_days} days, including domestic wires. Current, same-time "
                               "and future transactions excluded; destination novelty is account-relative.")
                details = {"trigger_transaction_id": trigger["transaction_id"],
                           "trigger_country": trigger["counterparty_country"], "history_count": len(history),
                           "history_start_utc": history[0]["transaction_time"],
                           "history_end_utc": history[-1]["transaction_time"],
                           "median_twice_cents": event["median_twice_cents"],
                           "known_countries": event["known_countries"], "reasons": event["reasons"]}
                inserted += save_alert(connection, "R004", "1", parameters_json, account,
                                       history + [trigger], trigger["transaction_time"], trigger["transaction_time"],
                                       1, 60 if len(event["reasons"]) == 1 else 80, explanation, details)
    return {"rule_id": "R004", "parameters": parameters, "eligible_outbound_wires": wires,
            "cross_border_candidates": candidates, "skipped_insufficient_history": skipped,
            "matched_events": matched, "new_alerts": inserted, "existing_alerts": matched - inserted,
            "elapsed_seconds": round(perf_counter() - started, 6)}
