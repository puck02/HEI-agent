"""Health log service module."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "hei_agent.db")


class HealthLogService:
    def __init__(self):
        self.db_path = os.path.abspath(DB_PATH)
        self._ensure_table()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        with self._get_conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS health_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    entry_date TEXT,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def get_logs(self, user_id: str, days: int = 7) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM health_logs
                   WHERE user_id = ?
                     AND entry_date >= date('now', ?)
                   ORDER BY entry_date DESC""",
                (user_id, f"-{days} days"),
            ).fetchall()
            return [dict(row) for row in rows]

    def log_health(self, user_id: str, data: dict) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO health_logs (user_id, entry_date, data)
                   VALUES (?, ?, ?)""",
                (
                    user_id,
                    data.get("entry_date"),
                    data.get("data"),
                ),
            )
            return cur.lastrowid
