"""SQLite persistence for completed reviews."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from autoqc.models import Review


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            submission_path TEXT,
            action TEXT,
            payload TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def save_review(path: Path, review: Review) -> int:
    payload = review.to_dict()
    with connect(path) as connection:
        cursor = connection.execute(
            "INSERT INTO reviews (created_at, submission_path, action, payload) VALUES (?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                review.submission_path,
                review.recommended_action,
                json.dumps(payload),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_review(path: Path, review_id: int) -> dict | None:
    with connect(path) as connection:
        row = connection.execute("SELECT payload FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


def list_reviews(path: Path) -> list[dict]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT id, created_at, submission_path, action FROM reviews ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]
