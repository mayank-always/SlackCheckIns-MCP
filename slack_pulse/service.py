"""Core orchestration logic for Slack Pulse."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import Settings
from .db import Database
from .models import CheckIn, User
from .quality import QualityResult, assess_quality
from .slack_client import SlackClient


class SlackPulseService:
    """High-level service that syncs Slack data and exposes query helpers."""

    def __init__(self, settings: Settings, database: Database, client: SlackClient) -> None:
        self.settings = settings
        self.database = database
        self.client = client

    # region Sync helpers
    async def sync_roster(self) -> None:
        roster_path = self.settings.team_roster_path
        if roster_path.exists():
            for user in load_roster_csv(roster_path):
                self.database.upsert_user(
                    {
                        "id": user.id,
                        "username": user.username,
                        "real_name": user.real_name,
                        "email": user.email,
                        "title": user.title,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )

        slack_users = await self.client.fetch_users()
        for member in slack_users:
            if member.get("deleted") or member.get("is_bot"):
                continue
            if member.get("id") == "USLACKBOT":
                continue
            profile = member.get("profile", {})
            user = User(
                id=member["id"],
                username=member.get("name") or member.get("id"),
                real_name=profile.get("real_name") or member.get("real_name") or member.get("name"),
                email=profile.get("email"),
                title=profile.get("title"),
            )
            self.database.upsert_user(
                {
                    "id": user.id,
                    "username": user.username,
                    "real_name": user.real_name,
                    "email": user.email,
                    "title": user.title,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

    async def sync_day(self, day: date) -> None:
        await self.sync_roster()
        oldest_ts, latest_ts = day_bounds(day)
        messages: List[Dict[str, Any]] = []
        async for message in self.client.fetch_channel_history(
            self.settings.channel_id,
            oldest=self.settings.slack_oldest_ts or oldest_ts,
            latest=self.settings.slack_latest_ts or latest_ts,
        ):
            ts = float(message.get("ts", 0))
            message_day = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            if message_day != day:
                continue
            messages.append(message)

        checkin_user_ids: set[str] = set()
        for message in messages:
            user_id = message.get("user")
            if not user_id:
                continue
            text = message.get("text", "").strip()
            if not text:
                continue

            quality: QualityResult = assess_quality(text)
            username = message.get("username") or message.get("user_profile", {}).get("name")
            if not username:
                # fallback to stored username
                record = self.database.get_checkin_for_user(user_id, day)
                username = record["username"] if record else user_id

            checkin = CheckIn(
                user_id=user_id,
                username=username,
                ts=float(message.get("ts", 0.0)),
                submitted_date=day,
                content=text,
                quality=quality.label,
            )
            self.database.record_checkin(
                {
                    "user_id": checkin.user_id,
                    "username": checkin.username,
                    "ts": checkin.ts,
                    "date": checkin.submitted_date.isoformat(),
                    "content": checkin.content,
                    "quality": checkin.quality,
                }
            )
            checkin_user_ids.add(user_id)

        roster_ids = {row["id"] for row in self.database.get_users()}
        missing = sorted(roster_ids - checkin_user_ids)
        self.database.clear_absentees(day)
        if missing:
            self.database.record_absentees(day, missing)

    async def sync_recent(self, days: int = 1) -> None:
        today = datetime.now(timezone.utc).date()
        for offset in range(days):
            await self.sync_day(today - timedelta(days=offset))

    # endregion

    # region Query helpers
    def get_daily_checkins(self, day: date) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.database.get_checkins_by_date(day)]

    def get_absentees(self, day: date) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.database.get_absentees(day)]

    def get_user_checkin(self, user_id: str, day: date) -> Optional[Dict[str, Any]]:
        row = self.database.get_checkin_for_user(user_id, day)
        return dict(row) if row else None

    def get_daily_summary(self, day: date) -> Dict[str, Any]:
        return self.database.get_daily_summary(day)

    def get_weekly_summary(self, day: date) -> Dict[str, Any]:
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=6)
        stats = self.database.get_weekly_stats(start, end)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "stats": stats,
        }

    def get_monthly_summary(self, day: date) -> Dict[str, Any]:
        start = day.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        end = next_month - timedelta(days=1)
        summary = self.database.get_monthly_trend(start, end)
        return summary

    # endregion


def load_roster_csv(path: Path) -> Iterable[User]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row.get("user_id"):
                continue
            yield User(
                id=row["user_id"],
                username=row.get("username", row["user_id"]),
                real_name=row.get("real_name", row["user_id"]),
                email=row.get("email") or None,
                title=row.get("title") or None,
            )


def day_bounds(day: date) -> tuple[str, str]:
    start_dt = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return f"{start_dt.timestamp():.6f}", f"{end_dt.timestamp():.6f}"


__all__ = ["SlackPulseService", "load_roster_csv", "day_bounds"]
