"""R003: single material receipt followed by one substantial outbound transfer."""

import json
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from time import perf_counter

from risk_storage import detection_database, save_alert

ELIGIBLE_SQL = """
SELECT * FROM transactions WHERE status = 'POSTED' AND (
    (direction = 'IN' AND transaction_type IN ('E_TRANSFER', 'WIRE', 'DIRECT_DEPOSIT', 'CASH_DEPOSIT'))
    OR (direction = 'OUT' AND transaction_type IN ('E_TRANSFER', 'WIRE'))
) ORDER BY account_id, transaction_time, transaction_id
"""


def validate_r003_parameters(minimum_inbound_cents, outbound_percentage, window_hours):
    for name, value in {"minimum_inbound_cents": minimum_inbound_cents,
                        "outbound_percentage": outbound_percentage, "window_hours": window_hours}.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"R003 {name} must be an integer >= 1")
    if minimum_inbound_cents > 9223372036854775807:
        raise ValueError("R003 minimum_inbound_cents must fit SQLite integer cents")
    if outbound_percentage > 100:
        raise ValueError("R003 outbound_percentage must be <= 100")
    if window_hours > 8760:
        raise ValueError("R003 window_hours must be <= 8760")


def find_rapid_pairs(rows, minimum_inbound_cents=500000, outbound_percentage=80, window_hours=24):
    """One account's SQL-filtered rows sorted by time and ID.

    Each outbound chooses the most recent unmatched qualifying receipt. Both
    records are used once. Window: 0 < elapsed <= window_hours. Same-time inbound
    records become candidates only after the timestamp batch's outbound scan.
    """
    validate_r003_parameters(minimum_inbound_cents, outbound_percentage, window_hours)
    available = deque()
    window = timedelta(hours=window_hours)
    for timestamp, batch_iter in groupby(rows, key=lambda row: row["transaction_time"]):
        when = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        while available and when - available[0][0] > window:
            available.popleft()
        batch = list(batch_iter)
        for outbound in batch:
            if outbound["direction"] != "OUT":
                continue
            for index in range(len(available) - 1, -1, -1):
                inbound_time, inbound = available[index]
                if 100 * outbound["amount_cents"] >= outbound_percentage * inbound["amount_cents"]:
                    del available[index]
                    yield {"inbound": inbound, "outbound": outbound,
                           "elapsed_seconds": int((when - inbound_time).total_seconds())}
                    break
        for inbound in batch:
            if inbound["direction"] == "IN" and inbound["amount_cents"] >= minimum_inbound_cents:
                available.append((when, inbound))


def detect_r003(db_path=Path("data/banking.db"), minimum_inbound_cents=500000,
                outbound_percentage=80, window_hours=24):
    parameters = {"minimum_inbound_cents": minimum_inbound_cents,
                  "outbound_percentage": outbound_percentage, "window_hours": window_hours}
    validate_r003_parameters(**parameters)
    parameters_json = json.dumps(parameters, sort_keys=True)
    started = perf_counter()
    receipts = outbound_count = matched = inserted = 0
    with detection_database(db_path) as connection:
        for account, account_rows in groupby(connection.execute(ELIGIBLE_SQL), key=lambda row: row["account_id"]):
            rows = list(account_rows)
            receipts += sum(row["direction"] == "IN" and row["amount_cents"] >= minimum_inbound_cents for row in rows)
            outbound_count += sum(row["direction"] == "OUT" for row in rows)
            for pair in find_rapid_pairs(rows, **parameters):
                matched += 1
                inbound, outbound = pair["inbound"], pair["outbound"]
                explanation = (f"Account {account}: posted receipt {inbound['transaction_id']} of CAD "
                               f"{Decimal(inbound['amount_cents']) / 100:.2f} was followed {pair['elapsed_seconds']} "
                               f"seconds later by outbound transfer {outbound['transaction_id']} of CAD "
                               f"{Decimal(outbound['amount_cents']) / 100:.2f}, at least {outbound_percentage}% "
                               f"of that receipt, within {window_hours} hours. Latest qualifying unmatched "
                               "receipt selected; each transaction paired once. This is a timing/amount pattern, not proof of fund tracing.")
                details = {"inbound_transaction_id": inbound["transaction_id"],
                           "outbound_transaction_id": outbound["transaction_id"],
                           "inbound_amount_cents": inbound["amount_cents"],
                           "outbound_amount_cents": outbound["amount_cents"],
                           "elapsed_seconds": pair["elapsed_seconds"]}
                inserted += save_alert(connection, "R003", "1", parameters_json, account,
                                       [inbound, outbound], inbound["transaction_time"], outbound["transaction_time"],
                                       2, 70, explanation, details)
    return {"rule_id": "R003", "parameters": parameters, "eligible_receipts": receipts,
            "eligible_outbound_transfers": outbound_count, "matched_events": matched,
            "unmatched_receipts": receipts - matched, "new_alerts": inserted,
            "existing_alerts": matched - inserted, "elapsed_seconds": round(perf_counter() - started, 6)}
