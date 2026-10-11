"""Shared persistence for explainable alerts against an immutable snapshot."""

import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from load_database import SCHEMA


def priority_for_score(score):
    if score >= 70:
        return "HIGH"
    return "MEDIUM" if score >= 40 else "LOW"


@contextmanager
def detection_database(db_path):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as connection, connection:
        connection.row_factory = sqlite3.Row
        required = {"customers", "accounts", "transactions"}
        actual = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not required.issubset(actual):
            raise ValueError("Source tables are missing; run src/load_database.py first")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign-key integrity check failed")


def save_alert(connection, rule_id, rule_version, parameters_json, account_id,
               evidence, event_start, event_end, peak_count, score, explanation,
               details=None):
    identity = json.dumps([rule_id, rule_version, parameters_json, account_id,
                           [row["transaction_id"] for row in evidence]], separators=(",", ":"))
    alert_id = rule_id + "-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    cursor = connection.execute("""
        INSERT INTO alerts (
            alert_id, rule_id, rule_version, account_id, parameters_json,
            event_start_utc, event_end_utc, peak_count, evidence_count,
            score, priority, created_time_utc, status, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)
        ON CONFLICT(alert_id) DO NOTHING
    """, (alert_id, rule_id, rule_version, account_id, parameters_json,
          event_start, event_end, peak_count, len(evidence), score, priority_for_score(score),
          datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), explanation))
    if not cursor.rowcount:
        return False
    connection.executemany("INSERT INTO alert_transactions VALUES (?, ?)",
                           [(alert_id, row["transaction_id"]) for row in evidence])
    if details is not None:
        connection.execute("INSERT INTO alert_details VALUES (?, ?)",
                           (alert_id, json.dumps(details, sort_keys=True)))
    return True
