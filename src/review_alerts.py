"""Persist local analyst decisions without overwriting earlier review history."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from load_database import SCHEMA
from risk_storage import detection_database

OUTCOMES = {"IN_REVIEW": "IN_REVIEW", "NO_CONCERN": "CLOSED", "ESCALATE": "CLOSED"}


class ReviewConflict(ValueError):
    """The review form was based on older saved history."""


def ensure_review_schema(db_path):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"transactions", "alerts", "alert_transactions"}.issubset(tables):
            raise ValueError("Load a banking snapshot and run detection before opening the dashboard")
        if "reviews" not in tables:
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))


def review_history(db_path, alert_id):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM reviews WHERE alert_id=? ORDER BY reviewed_time_utc DESC, rowid DESC", (alert_id,))]


def save_review(db_path, alert_id, outcome, reviewer_alias, notes, expected_review_id):
    if outcome not in OUTCOMES:
        raise ValueError("Select a valid review outcome")
    if not isinstance(reviewer_alias, str) or not 1 <= len(reviewer_alias.strip()) <= 60:
        raise ValueError("Reviewer alias must contain 1–60 characters")
    if not isinstance(notes, str) or not 1 <= len(notes.strip()) <= 2000:
        raise ValueError("Review notes must contain 1–2000 characters")
    review_id = str(uuid4())
    with detection_database(db_path) as connection:
        if not connection.execute("SELECT 1 FROM alerts WHERE alert_id=?", (alert_id,)).fetchone():
            raise ValueError("Alert no longer exists")
        latest = connection.execute(
            "SELECT review_id FROM reviews WHERE alert_id=? ORDER BY reviewed_time_utc DESC, rowid DESC LIMIT 1",
            (alert_id,)).fetchone()
        if (latest[0] if latest else None) != expected_review_id:
            raise ReviewConflict("Another review was saved. Refresh this alert and review the latest history before saving.")
        connection.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?)",
                           (review_id, alert_id, outcome, reviewer_alias.strip(), notes.strip(),
                            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")))
        connection.execute("UPDATE alerts SET status=? WHERE alert_id=?", (OUTCOMES[outcome], alert_id))
    return review_id
