"""Configuration helpers for Slack Pulse."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Runtime configuration values loaded from environment variables."""

    slack_bot_token: str
    channel_id: str
    api_key: str
    database_path: Path
    team_roster_path: Path
    slack_oldest_ts: Optional[str] = None
    slack_latest_ts: Optional[str] = None


def load_settings(env_file: str | None = None) -> Settings:
    """Load settings from the environment, optionally from a specific file."""

    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    db_path = Path(os.getenv("DATABASE_PATH", "slack_pulse.db")).expanduser()
    roster_path = Path(
        os.getenv("TEAM_ROSTER_PATH", "team_roster.csv")
    ).expanduser()

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    channel_id = os.getenv("CHANNEL_ID")
    api_key = os.getenv("API_KEY")

    if not slack_token:
        raise RuntimeError("SLACK_BOT_TOKEN must be configured")
    if not channel_id:
        raise RuntimeError("CHANNEL_ID must be configured")
    if not api_key:
        raise RuntimeError("API_KEY must be configured")

    return Settings(
        slack_bot_token=slack_token,
        channel_id=channel_id,
        api_key=api_key,
        database_path=db_path,
        team_roster_path=roster_path,
        slack_oldest_ts=os.getenv("SLACK_OLDEST_TS"),
        slack_latest_ts=os.getenv("SLACK_LATEST_TS"),
    )


__all__ = ["Settings", "load_settings"]
