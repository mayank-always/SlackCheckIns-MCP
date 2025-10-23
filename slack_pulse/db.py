"""SQLite persistence layer for Slack Pulse."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, List

Connection = sqlite3.Connection
Row = sqlite3.Row


class Database:
    """Lightweight wrapper around SQLite operations."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT,
                    real_name TEXT,
                    email TEXT,
                    title TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    ts REAL NOT NULL,
                    date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, date),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS absentees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, date),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            conn.commit()

    # region Users
    def upsert_user(self, user: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, real_name, email, title, updated_at)
                VALUES (:id, :username, :real_name, :email, :title, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    real_name=excluded.real_name,
                    email=excluded.email,
                    title=excluded.title,
                    updated_at=excluded.updated_at
                """,
                user,
            )
            conn.commit()

    def get_users(self) -> List[Row]:
        with self.connect() as conn:
            cursor = conn.execute("SELECT * FROM users ORDER BY real_name")
            return cursor.fetchall()

    # endregion

    # region Check-ins
    def record_checkin(self, record: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO checkins (user_id, username, ts, date, content, quality)
                VALUES (:user_id, :username, :ts, :date, :content, :quality)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    ts=excluded.ts,
                    content=excluded.content,
                    quality=excluded.quality,
                    username=excluded.username
                """,
                record,
            )
            conn.commit()

    def get_checkins_by_date(self, day: date) -> List[Row]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM checkins WHERE date = ? ORDER BY ts",
                (day.isoformat(),),
            )
            return cursor.fetchall()

    def get_checkin_for_user(self, user_id: str, day: date) -> Optional[Row]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM checkins WHERE user_id = ? AND date = ?",
                (user_id, day.isoformat()),
            )
            return cursor.fetchone()

    def get_daily_summary(self, day: date) -> Dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN quality = 'good' THEN 1 ELSE 0 END) as good
                FROM checkins
                WHERE date = ?
                """,
                (day.isoformat(),),
            )
            row = cursor.fetchone()
            total = row["total"] if row else 0
            good = row["good"] if row and row["good"] is not None else 0
            percent_good = (good / total) * 100 if total else 0
            return {
                "date": day.isoformat(),
                "total_checkins": total,
                "good_checkins": good,
                "good_percentage": round(percent_good, 2),
            }

    def get_weekly_stats(self, start_day: date, end_day: date) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT u.id as user_id,
                       u.real_name,
                       COUNT(c.id) as total,
                       SUM(CASE WHEN c.quality = 'good' THEN 1 ELSE 0 END) as good
                FROM users u
                LEFT JOIN checkins c
                  ON u.id = c.user_id
                 AND c.date BETWEEN ? AND ?
                GROUP BY u.id, u.real_name
                ORDER BY u.real_name
                """,
                (start_day.isoformat(), end_day.isoformat()),
            )
            results: List[Dict[str, Any]] = []
            for row in cursor.fetchall():
                total = row["total"] or 0
                good = row["good"] or 0
                percent_good = (good / total) * 100 if total else 0
                results.append(
                    {
                        "user_id": row["user_id"],
                        "name": row["real_name"],
                        "checkins": total,
                        "good_checkins": good,
                        "good_percentage": round(percent_good, 2),
                    }
                )
            return results

    def get_monthly_trend(self, start_day: date, end_day: date) -> Dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT date,
                       COUNT(*) as total,
                       SUM(CASE WHEN quality = 'good' THEN 1 ELSE 0 END) as good
                FROM checkins
                WHERE date BETWEEN ? AND ?
                GROUP BY date
                ORDER BY date
                """,
                (start_day.isoformat(), end_day.isoformat()),
            )
            total_checkins = 0
            total_good = 0
            trend: List[Dict[str, Any]] = []
            for row in cursor.fetchall():
                day_total = row["total"] or 0
                day_good = row["good"] or 0
                total_checkins += day_total
                total_good += day_good
                percent_good = (day_good / day_total) * 100 if day_total else 0
                trend.append(
                    {
                        "date": row["date"],
                        "total": day_total,
                        "good_checkins": day_good,
                        "good_percentage": round(percent_good, 2),
                    }
                )
            avg_quality = (total_good / total_checkins) * 100 if total_checkins else 0
            return {
                "start": start_day.isoformat(),
                "end": end_day.isoformat(),
                "total_checkins": total_checkins,
                "avg_good_percentage": round(avg_quality, 2),
                "trend": trend,
            }

    # endregion

    # region Absentees
    def record_absentees(self, day: date, user_ids: Iterable[str]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO absentees (user_id, date)
                VALUES (?, ?)
                ON CONFLICT(user_id, date) DO NOTHING
                """,
                [(user_id, day.isoformat()) for user_id in user_ids],
            )
            conn.commit()

    def clear_absentees(self, day: date) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM absentees WHERE date = ?", (day.isoformat(),))
            conn.commit()

    def get_absentees(self, day: date) -> List[Row]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT a.date, u.id as user_id, u.real_name, u.username
                FROM absentees a
                JOIN users u ON u.id = a.user_id
                WHERE a.date = ?
                ORDER BY u.real_name
                """,
                (day.isoformat(),),
            )
            return cursor.fetchall()

    # endregion


__all__ = ["Database"]
