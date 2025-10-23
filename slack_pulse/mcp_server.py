"""MCP server exposing Slack Pulse data tools."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .db import Database
from .service import SlackPulseService
from .slack_client import SlackClient

mcp = FastMCP("slack-pulse")

_settings = load_settings()
_database = Database(_settings.database_path)
_client = SlackClient(_settings.slack_bot_token)
_service = SlackPulseService(_settings, _database, _client)
_sync_lock = asyncio.Lock()


async def _sync_for_day(day_str: Optional[str] = None) -> None:
    day = (
        datetime.strptime(day_str, "%Y-%m-%d").date()
        if day_str
        else datetime.now(timezone.utc).date()
    )
    async with _sync_lock:
        await _service.sync_day(day)


def _ensure_date(day_str: Optional[str] = None):
    if not day_str:
        return datetime.now(timezone.utc).date()
    return datetime.strptime(day_str, "%Y-%m-%d").date()


@mcp.tool()
async def get_daily_checkins() -> dict:
    """Return today's check-ins."""

    day = datetime.now(timezone.utc).date()
    await _sync_for_day(day.isoformat())
    return {"date": day.isoformat(), "checkins": _service.get_daily_checkins(day)}


@mcp.tool()
async def get_absentees(date: Optional[str] = None) -> dict:
    """Return the list of users who did not submit a check-in for the date."""

    day = _ensure_date(date)
    await _sync_for_day(day.isoformat())
    return {"date": day.isoformat(), "absentees": _service.get_absentees(day)}


@mcp.tool()
async def get_user_checkin(user_id: str, date: Optional[str] = None) -> dict:
    """Return a specific user's check-in for the given date."""

    day = _ensure_date(date)
    await _sync_for_day(day.isoformat())
    checkin = _service.get_user_checkin(user_id, day)
    return {"date": day.isoformat(), "checkin": checkin}


@mcp.tool()
async def get_cumulative_report(period: str = "month") -> dict:
    """Return aggregate engagement metrics for the requested period."""

    today = datetime.now(timezone.utc).date()
    await _sync_for_day(today.isoformat())
    if period == "day":
        return _service.get_daily_summary(today)
    if period == "week":
        return _service.get_weekly_summary(today)
    if period == "month":
        return _service.get_monthly_summary(today)
    raise ValueError("period must be one of: day, week, month")


__all__ = [
    "mcp",
    "get_daily_checkins",
    "get_absentees",
    "get_user_checkin",
    "get_cumulative_report",
]
