"""Read persisted alerts and their source-transaction evidence."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def read_alerts(db_path, account=None, alert_id=None, priority=None, status=None,
                limit=10, with_evidence=False, rule=None):
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be an integer >= 1")
    predicates, values = [], []
    for column, value in (("account_id", account), ("alert_id", alert_id),
                          ("priority", priority), ("status", status), ("rule_id", rule)):
        if value is not None:
            predicates.append(f"{column} = ?")
            values.append(value)
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        result = [dict(row) for row in connection.execute(
            "SELECT * FROM alerts" + where + " ORDER BY score DESC, event_start_utc, alert_id LIMIT ?",
            (*values, limit))]
        for alert in result:
            alert["parameters"] = json.loads(alert.pop("parameters_json"))
            # Older Phase 3 databases may not yet have the additive details table.
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alert_details'").fetchone():
                details = connection.execute("SELECT details_json FROM alert_details WHERE alert_id=?", (alert["alert_id"],)).fetchone()
                if details:
                    alert["details"] = json.loads(details[0])
            if with_evidence:
                alert["transactions"] = [dict(row) for row in connection.execute("""
                    SELECT t.* FROM alert_transactions e
                    JOIN transactions t ON t.transaction_id = e.transaction_id
                    WHERE e.alert_id = ? ORDER BY t.transaction_time, t.transaction_id
                """, (alert["alert_id"],))]
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/banking.db"))
    parser.add_argument("--account")
    parser.add_argument("--alert-id")
    parser.add_argument("--priority", choices=("LOW", "MEDIUM", "HIGH"))
    parser.add_argument("--status", choices=("NEW", "IN_REVIEW", "CLOSED"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--with-evidence", action="store_true")
    parser.add_argument("--rule", choices=("R001", "R002"))
    args = parser.parse_args()
    try:
        result = read_alerts(args.db, args.account, args.alert_id, args.priority,
                             args.status, args.limit, args.with_evidence, args.rule)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Cannot read alerts: {error}\nRun src/detect_risks.py first.\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
