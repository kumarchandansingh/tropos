"""SQLite persistence adapter. Personal paths and text never belong in Git."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, updated TEXT NOT NULL)"
        )
        self.db.commit()

    def save(self, kind: str, record: dict) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
                (record["id"], kind, json.dumps(record), datetime.now(UTC).isoformat()),
            )
            self.db.commit()

    def get(self, kind: str, key: str) -> dict:
        with self.lock:
            row = self.db.execute(
                "SELECT payload FROM records WHERE id=? AND kind=?", (key, kind)
            ).fetchone()
        if not row:
            raise ValueError("Record not found.")
        return json.loads(row[0])

    def list(self, kind: str) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM records WHERE kind=? ORDER BY updated DESC", (kind,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
