"""HTTP client for interacting with Slack Web API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Dict, Optional

import httpx

SLACK_API_BASE = "https://slack.com/api"


class SlackApiError(RuntimeError):
    """Raised when Slack returns an error response."""

    def __init__(self, method: str, error: str) -> None:
        super().__init__(f"Slack API error for {method}: {error}")
        self.method = method
        self.error = error


class SlackClient:
    """Simple async wrapper around Slack Web API endpoints used by Slack Pulse."""

    def __init__(self, token: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=SLACK_API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_users(self) -> list[dict[str, Any]]:
        method = "users.list"
        response = await self._client.get(method)
        data = response.json()
        if not data.get("ok"):
            raise SlackApiError(method, data.get("error", "unknown_error"))
        return [member for member in data.get("members", []) if not member.get("deleted")]

    async def fetch_channel_history(
        self,
        channel_id: str,
        *,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        limit: int = 200,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield messages from `conversations.history` with pagination."""

        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"channel": channel_id, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            if oldest:
                params["oldest"] = oldest
            if latest:
                params["latest"] = latest

            response = await self._client.get("conversations.history", params=params)
            data = response.json()
            if not data.get("ok"):
                raise SlackApiError("conversations.history", data.get("error", "unknown_error"))

            messages = data.get("messages", [])
            for message in messages:
                if message.get("subtype") == "channel_join":
                    continue
                yield message

            if not data.get("has_more"):
                break
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            await asyncio.sleep(0.2)


__all__ = ["SlackClient", "SlackApiError"]
