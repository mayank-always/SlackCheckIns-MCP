# Deploy on Replit: Set secrets and run 'uvicorn server:app --host=0.0.0.0 --port=8000'
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import sqlite3
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])
logger = logging.getLogger("slack_pulse")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
API_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "slack_pulse.db")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))

if not SLACK_BOT_TOKEN:
    logger.warning("SLACK_BOT_TOKEN is not set. Slack sync will be disabled until provided.")
if not CHANNEL_ID:
    logger.warning("CHANNEL_ID is not set. Slack sync will be disabled until provided.")
if not API_KEY:
    logger.warning("API_KEY is not set. API endpoints will reject requests without a key.")


class Database:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT,
                real_name TEXT,
                email TEXT,
                tz TEXT,
                is_bot INTEGER DEFAULT 0
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
                text TEXT NOT NULL,
                quality TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, ts)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS absentees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                UNIQUE(date, user_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def upsert_user(self, user: Dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO users (id, name, real_name, email, tz, is_bot)
            VALUES (:id, :name, :real_name, :email, :tz, :is_bot)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                real_name=excluded.real_name,
                email=excluded.email,
                tz=excluded.tz,
                is_bot=excluded.is_bot
            """,
            user,
        )
        self._conn.commit()

    def record_checkin(self, checkin: Dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO checkins (user_id, username, ts, text, quality, created_at)
            VALUES (:user_id, :username, :ts, :text, :quality, :created_at)
        """,
            {**checkin, "ts": float(checkin["ts"])},
        )
        self._conn.commit()

    def set_absentees(self, date_str: str, absentees: List[Dict[str, str]]) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM absentees WHERE date = ?", (date_str,))
        cursor.executemany(
            """
            INSERT OR IGNORE INTO absentees (date, user_id, username)
            VALUES (:date, :user_id, :username)
            """,
            [dict(date=date_str, user_id=a["user_id"], username=a["username"]) for a in absentees],
        )
        self._conn.commit()

    def get_daily_checkins(self, date: datetime) -> List[sqlite3.Row]:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return list(
            self._conn.execute(
                "SELECT * FROM checkins WHERE ts >= ? AND ts < ? ORDER BY ts ASC",
                (start.timestamp(), end.timestamp()),
            )
        )

    def get_absentees(self, date: datetime) -> List[sqlite3.Row]:
        date_str = date.strftime("%Y-%m-%d")
        return list(
            self._conn.execute(
                "SELECT * FROM absentees WHERE date = ? ORDER BY username ASC",
                (date_str,),
            )
        )

    def get_checkin(self, user_id: str, date: datetime) -> Optional[sqlite3.Row]:
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        cursor = self._conn.execute(
            """
            SELECT * FROM checkins
            WHERE user_id = ? AND ts >= ? AND ts < ?
            ORDER BY ts ASC
            LIMIT 1
            """,
            (user_id, start.timestamp(), end.timestamp()),
        )
        return cursor.fetchone()

    def get_summary_day(self, date: datetime) -> Dict[str, Any]:
        rows = self.get_daily_checkins(date)
        total = len(rows)
        good = sum(1 for r in rows if r["quality"] == "good")
        pct_good = (good / total * 100.0) if total else 0.0
        return {
            "date": date.strftime("%Y-%m-%d"),
            "total_checkins": total,
            "good_checkins": good,
            "percent_good": round(pct_good, 2),
        }

    def get_summary_week(self, date: datetime) -> List[Dict[str, Any]]:
        start = date - timedelta(days=6)
        rows = self._conn.execute(
            """
            SELECT user_id, username,
                COUNT(*) AS total,
                SUM(CASE WHEN quality = 'good' THEN 1 ELSE 0 END) AS good
            FROM checkins
            WHERE ts >= ? AND ts <= ?
            GROUP BY user_id, username
            ORDER BY username ASC
            """,
            (
                start.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(),
                date.timestamp(),
            ),
        )
        result = []
        for row in rows:
            total = row["total"]
            good = row["good"] or 0
            pct_good = (good / total * 100.0) if total else 0.0
            result.append(
                {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "total_checkins": total,
                    "good_checkins": good,
                    "percent_good": round(pct_good, 2),
                }
            )
        return result

    def get_summary_month(self, date: datetime) -> Dict[str, Any]:
        start = date - timedelta(days=29)
        rows = list(
            self._conn.execute(
                """
                SELECT DATE(datetime(ts, 'unixepoch')) AS day,
                       COUNT(*) AS total,
                       SUM(CASE WHEN quality = 'good' THEN 1 ELSE 0 END) AS good
                FROM checkins
                WHERE ts >= ? AND ts <= ?
                GROUP BY day
                ORDER BY day ASC
                """,
                (
                    start.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(),
                    date.timestamp(),
                ),
            )
        )
        total_checkins = sum(row["total"] for row in rows)
        good_checkins = sum(row["good"] or 0 for row in rows)
        pct_good = (good_checkins / total_checkins * 100.0) if total_checkins else 0.0
        trend = [
            {
                "date": row["day"],
                "total_checkins": row["total"],
                "good_checkins": row["good"] or 0,
            }
            for row in rows
        ]
        return {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": date.strftime("%Y-%m-%d"),
            "total_checkins": total_checkins,
            "good_checkins": good_checkins,
            "percent_good": round(pct_good, 2),
            "trend": trend,
        }

    def all_active_users(self) -> List[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM users WHERE is_bot = 0 ORDER BY real_name ASC"
            )
        )

    def set_sync_state(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def get_sync_state(self, key: str) -> Optional[str]:
        cursor = self._conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def quality_score(text: str) -> str:
    keywords = {"completed", "blocked", "planning", "done", "help", "stuck"}
    length_ok = len(text.strip()) > 50
    keyword_ok = any(k in text.lower() for k in keywords)
    structured_ok = any(
        line.strip().startswith(('-', '*', '1.', '•'))
        for line in text.splitlines()
        if line.strip()
    ) or any(marker in text.lower() for marker in ["yesterday:", "today:", "blockers:"])
    score = sum([length_ok, keyword_ok, structured_ok])
    return "good" if score >= 2 else "bad"


class SlackClient:
    BASE_URL = "https://slack.com/api"

    def __init__(self, token: Optional[str]) -> None:
        self.token = token
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=30.0))

    async def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Slack token not configured")
        headers = {"Authorization": f"Bearer {self.token}"}
        response = await self._client.request(method, f"{self.BASE_URL}/{path}", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error for {path}: {data.get('error')}")
        return data

    async def fetch_users(self) -> List[Dict[str, Any]]:
        users: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", "users.list", params)
            users.extend(data.get("members", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return users

    async def fetch_messages(self, channel: str, oldest: float, latest: float) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "channel": channel,
                "oldest": oldest,
                "latest": latest,
                "limit": 200,
                "inclusive": True,
            }
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", "conversations.history", params)
            messages.extend(data.get("messages", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return messages

    async def close(self) -> None:
        await self._client.aclose()


db = Database(DATABASE_URL)
slack_client = SlackClient(SLACK_BOT_TOKEN)

app = FastAPI(title="Slack Pulse API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp = FastMCP("slack-pulse")


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    if not API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API key is not configured")
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def start_of_day(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:  # noqa: TRY003
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Use YYYY-MM-DD.") from exc


async def sync_roster() -> Dict[str, Dict[str, Any]]:
    if not SLACK_BOT_TOKEN or not CHANNEL_ID:
        return {}
    users = await slack_client.fetch_users()
    roster: Dict[str, Dict[str, Any]] = {}
    for user in users:
        if user.get("deleted") or user.get("is_bot") or user.get("id") == "USLACKBOT":
            continue
        user_record = {
            "id": user["id"],
            "name": user.get("name"),
            "real_name": user.get("profile", {}).get("real_name") or user.get("real_name"),
            "email": user.get("profile", {}).get("email"),
            "tz": user.get("tz"),
            "is_bot": int(user.get("is_bot", False)),
        }
        roster[user["id"]] = user_record
        db.upsert_user(user_record)
    return roster


async def sync_checkins() -> None:
    if not SLACK_BOT_TOKEN or not CHANNEL_ID:
        logger.debug("Slack credentials missing; skipping sync")
        return

    logger.info("Starting Slack sync")
    now = now_utc()
    today = start_of_day(now)
    latest_state = db.get_sync_state("latest_ts")
    oldest = float(latest_state) if latest_state else float(today.timestamp())
    latest = float(now.timestamp())
    try:
        roster = await sync_roster()
        messages = await slack_client.fetch_messages(CHANNEL_ID, oldest=oldest, latest=latest)
        processed = 0
        for msg in messages:
            if msg.get("type") != "message" or "user" not in msg:
                continue
            user_id = msg.get("user")
            if user_id not in roster:
                continue
            ts = float(msg.get("ts", 0))
            if ts < today.timestamp():
                continue
            text = msg.get("text", "").strip()
            if not text:
                continue
            quality = quality_score(text)
            db.record_checkin(
                {
                    "user_id": user_id,
                    "username": roster[user_id].get("real_name") or roster[user_id].get("name"),
                    "ts": ts,
                    "text": text,
                    "quality": quality,
                    "created_at": now_utc().isoformat(),
                }
            )
            processed += 1
        db.set_sync_state("latest_ts", str(latest))
        # Determine absentees
        checkin_rows = db.get_daily_checkins(today)
        checkin_user_ids = {row["user_id"] for row in checkin_rows}
        absentees = []
        for user in roster.values():
            if user["id"] not in checkin_user_ids:
                absentees.append({"user_id": user["id"], "username": user.get("real_name") or user.get("name")})
        db.set_absentees(today.strftime("%Y-%m-%d"), absentees)
        logger.info("Slack sync complete: %s messages processed", processed)
    except Exception as exc:  # noqa: BLE001
        logger.error("Slack sync failed: %s", exc)


async def periodic_sync() -> None:
    while True:
        await sync_checkins()
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(periodic_sync())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await slack_client.close()


@app.get("/healthz")
async def healthcheck() -> Dict[str, str]:
    """Lightweight readiness probe for platform monitors."""

    return {"status": "ok"}


@app.get("/api/daily-checkins", dependencies=[Depends(require_api_key)])
async def api_daily_checkins() -> List[Dict[str, Any]]:
    today = start_of_day(now_utc())
    rows = db.get_daily_checkins(today)
    return [dict(row) for row in rows]


@app.get("/api/absentees", dependencies=[Depends(require_api_key)])
async def api_absentees(date: Optional[str] = None) -> List[Dict[str, Any]]:
    target_date = parse_date(date) if date else start_of_day(now_utc())
    rows = db.get_absentees(target_date)
    return [dict(row) for row in rows]


@app.get("/api/checkin", dependencies=[Depends(require_api_key)])
async def api_checkin(user: str, date: str) -> Dict[str, Any]:
    target_date = parse_date(date)
    row = db.get_checkin(user, target_date)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check-in not found")
    return dict(row)


@app.get("/api/summary/day", dependencies=[Depends(require_api_key)])
async def api_summary_day() -> Dict[str, Any]:
    return db.get_summary_day(start_of_day(now_utc()))


@app.get("/api/summary/week", dependencies=[Depends(require_api_key)])
async def api_summary_week() -> List[Dict[str, Any]]:
    return db.get_summary_week(now_utc())


@app.get("/api/summary/month", dependencies=[Depends(require_api_key)])
async def api_summary_month() -> Dict[str, Any]:
    return db.get_summary_month(now_utc())


@app.post("/api/refresh", dependencies=[Depends(require_api_key)])
async def api_refresh() -> Response:
    await sync_checkins()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@mcp.tool()
async def get_daily_checkins() -> List[Dict[str, Any]]:
    today = start_of_day(now_utc())
    return [dict(row) for row in db.get_daily_checkins(today)]


@mcp.tool()
async def get_absentees(date: Optional[str] = None) -> List[Dict[str, Any]]:
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:  # noqa: TRY003
            raise ValueError("Invalid date format. Use YYYY-MM-DD.") from exc
    else:
        target_date = start_of_day(now_utc())
    return [dict(row) for row in db.get_absentees(target_date)]


@mcp.tool()
async def get_user_checkin(user_id: str, date: str) -> Dict[str, Any]:
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:  # noqa: TRY003
        raise ValueError("Invalid date format. Use YYYY-MM-DD.") from exc
    row = db.get_checkin(user_id, target_date)
    if not row:
        raise ValueError("Check-in not found")
    return dict(row)


@mcp.tool()
async def get_cumulative_report(period: str = "month") -> Dict[str, Any]:
    period = period.lower()
    if period == "day":
        return db.get_summary_day(start_of_day(now_utc()))
    if period == "week":
        return {"period": "week", "entries": db.get_summary_week(now_utc())}
    if period == "month":
        return db.get_summary_month(now_utc())
    raise ValueError("Unsupported period. Choose from day, week, month.")


__all__ = ["app", "mcp"]
