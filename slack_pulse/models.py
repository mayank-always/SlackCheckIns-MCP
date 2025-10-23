"""Dataclasses representing Slack Pulse domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class User:
    id: str
    username: str
    real_name: str
    email: str | None = None
    title: str | None = None


@dataclass(slots=True)
class CheckIn:
    user_id: str
    username: str
    ts: float
    submitted_date: date
    content: str
    quality: str


@dataclass(slots=True)
class Absentee:
    user_id: str
    submitted_date: date


__all__ = ["User", "CheckIn", "Absentee"]
