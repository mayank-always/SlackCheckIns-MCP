"""FastAPI application exposing the Slack Pulse REST API."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import Settings, load_settings
from .db import Database
from .service import SlackPulseService
from .slack_client import SlackClient


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    database = Database(settings.database_path)
    slack_client = SlackClient(settings.slack_bot_token)
    service = SlackPulseService(settings, database, slack_client)

    async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
        if x_api_key != settings.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    def date_dependency(value: Optional[str] = None) -> date:
        if not value:
            return datetime.now(timezone.utc).date()
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    app = FastAPI(title="Slack Pulse API", version="1.0.0")

    @app.on_event("startup")
    async def startup_event() -> None:  # pragma: no cover - io bound
        await service.sync_recent(1)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:  # pragma: no cover - io bound
        await slack_client.close()

    def get_service() -> SlackPulseService:
        return service

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/daily-checkins")
    async def get_daily_checkins(
        d: date = Depends(date_dependency),
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        return {"date": d.isoformat(), "checkins": svc.get_daily_checkins(d)}

    @app.get("/api/absentees")
    async def get_absentees(
        date_param: Optional[str] = None,
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        day = date_dependency(date_param)
        return {"date": day.isoformat(), "absentees": svc.get_absentees(day)}

    @app.get("/api/checkin")
    async def get_checkin(
        user: str,
        date_param: Optional[str] = None,
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        day = date_dependency(date_param)
        checkin = svc.get_user_checkin(user, day)
        if not checkin:
            raise HTTPException(status_code=404, detail="check-in not found")
        return {"date": day.isoformat(), "checkin": checkin}

    @app.get("/api/summary/day")
    async def get_day_summary(
        date_param: Optional[str] = None,
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        day = date_dependency(date_param)
        return svc.get_daily_summary(day)

    @app.get("/api/summary/week")
    async def get_week_summary(
        date_param: Optional[str] = None,
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        day = date_dependency(date_param)
        return svc.get_weekly_summary(day)

    @app.get("/api/summary/month")
    async def get_month_summary(
        date_param: Optional[str] = None,
        _: None = Depends(verify_api_key),
        svc: SlackPulseService = Depends(get_service),
    ) -> dict[str, object]:
        day = date_dependency(date_param)
        return svc.get_monthly_summary(day)

    return app


app = create_app()


__all__ = ["app", "create_app"]
