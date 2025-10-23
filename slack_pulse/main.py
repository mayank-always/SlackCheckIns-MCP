"""Entrypoint for running the Slack Pulse API via `python -m slack_pulse.main`."""

from __future__ import annotations

import os

import uvicorn

from .api import create_app
from .config import load_settings


def run() -> None:
    env_file = os.getenv("SLACK_PULSE_ENV")
    settings = load_settings(env_file)
    app = create_app(settings)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":  # pragma: no cover
    run()
