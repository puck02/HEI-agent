"""Medication service module."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "hei_agent.db")


class MedicationService:
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
                """CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    name TEXT,
                    dosage TEXT,
                    frequency TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def get_all(self, user_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM medications WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add(self, user_id: str, data: dict) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO medications (user_id, name, dosage, frequency, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data.get("name"),
                    data.get("dosage"),
                    data.get("frequency"),
                    data.get("notes"),
                ),
            )
            return cur.lastrowid

    def update(self, med_id: int, data: dict) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                """UPDATE medications
                   SET name = ?, dosage = ?, frequency = ?, notes = ?
                   WHERE id = ?""",
                (
                    data.get("name"),
                    data.get("dosage"),
                    data.get("frequency"),
                    data.get("notes"),
                    med_id,
                ),
            )
            return cur.rowcount > 0

    def remove(self, med_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM medications WHERE id = ?", (med_id,))
            return cur.rowcount > 0
