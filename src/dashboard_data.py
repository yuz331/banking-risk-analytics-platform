"""Consistent source-backed metrics and bounded alert-queue queries."""

import csv
import io
import sqlite3
from contextlib import closing, contextmanager
from decimal import Decimal
from pathlib import Path


@contextmanager
def readonly(db_path):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        yield connection


def overview(db_path):
    with readonly(db_path) as connection:
        summary = dict(connection.execute("""
            SELECT COUNT(*) AS all_transactions,
                COALESCE(SUM(CASE WHEN status='POSTED' THEN 1 ELSE 0 END),0) AS posted_transactions,
                MIN(transaction_time) AS first_time, MAX(transaction_time) AS last_time,
                COALESCE(SUM(CASE WHEN status='POSTED' AND direction='IN' THEN amount_cents ELSE 0 END),0) AS inbound_cents,
                COALESCE(SUM(CASE WHEN status='POSTED' AND direction='OUT' THEN amount_cents ELSE 0 END),0) AS outbound_cents
            FROM transactions
        """).fetchone())
        summary.update(dict(connection.execute("""
            SELECT COUNT(*) AS alerts,
                COALESCE(SUM(CASE WHEN status IN ('NEW','IN_REVIEW') THEN 1 ELSE 0 END),0) AS open_alerts,
                COALESCE(SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END),0) AS closed_alerts,
                MAX(created_time_utc) AS latest_detection_utc
            FROM alerts
        """).fetchone()))
        summary["review_records"] = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        daily = [dict(row) for row in connection.execute("""
            SELECT DATE(transaction_time) AS day_utc, COUNT(*) AS transaction_count,
                SUM(CASE WHEN direction='IN' THEN amount_cents ELSE 0 END) AS inbound_cents,
                SUM(CASE WHEN direction='OUT' THEN amount_cents ELSE 0 END) AS outbound_cents
            FROM transactions WHERE status='POSTED' GROUP BY DATE(transaction_time) ORDER BY day_utc
        """)]
        distribution = [dict(row) for row in connection.execute(
            "SELECT rule_id, status, COUNT(*) AS alert_count FROM alerts GROUP BY rule_id,status ORDER BY rule_id,status")]
        return {"summary": summary, "daily": daily, "distribution": distribution}


def alert_queue(db_path, rule=None, priority=None, status=None, account=None, page=0, page_size=25):
    if type(page) is not int or page < 0 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("Invalid queue pagination")
    predicates, values = [], []
    for column, value in (("rule_id", rule), ("priority", priority), ("status", status), ("account_id", account)):
        if value is not None:
            predicates.append(f"{column}=?")
            values.append(value)
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    with readonly(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM alerts" + where, values).fetchone()[0]
        rows = [dict(row) for row in connection.execute("""
            SELECT alert_id, rule_id, account_id, priority, score, status, event_start_utc, evidence_count
            FROM alerts
        """ + where + " ORDER BY score DESC,event_start_utc,alert_id LIMIT ? OFFSET ?",
            (*values, page_size, page * page_size))]
        return {"total": count, "rows": rows}


def queue_csv(rows):
    """Export exactly the visible page; defend text cells from spreadsheet formulas."""
    columns = ("alert_id", "rule_id", "account_id", "priority", "score", "status", "event_start_utc", "evidence_count")
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        safe = {column: row[column] for column in columns}
        for column, value in safe.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                safe[column] = "'" + value
        writer.writerow(safe)
    return handle.getvalue()


def cad(cents):
    return f"CAD {Decimal(cents) / 100:,.2f}"
