# Slack Pulse API

Slack Pulse API is a combined FastAPI + MCP service that ingests daily check-ins
from a Slack channel, classifies the quality of each update, tracks absentees,
and exposes the results through secured REST endpoints and MCP tools for AI
agents.

## Key Features

- **Slack ingestion** via `conversations.history` with pagination and roster
  hydration through `users.list`.
- **Quality scoring** using heuristics for length, keywords, and structure.
- **SQLite persistence** for users, check-ins, absentees, and summary rollups.
- **FastAPI endpoints** protected with an `X-API-Key` header.
- **MCP tools** (`slack-pulse`) for copilots that need programmatic access to the
data.
- **Replit-ready** configuration for one-click deployment.

## Environment Variables

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot token with `channels:history`, `channels:read`, `users:read`. |
| `CHANNEL_ID` | Slack channel ID to monitor (e.g., `C1234567890`). |
| `API_KEY` | Shared secret for REST API access (`X-API-Key` header). |
| `DATABASE_URL` | Optional path to SQLite file (default `slack_pulse.db`). |
| `SYNC_INTERVAL_SECONDS` | Optional polling cadence (default 300 seconds). |

A `.env.example` file is included. When running locally, copy it to `.env` or
export the variables manually.

## Slack App Setup

1. Visit <https://api.slack.com/apps> and create a new app **from scratch**.
2. In **OAuth & Permissions**, add the bot scopes `channels:history`,
   `channels:read`, and `users:read`.
3. Install the app to your workspace and copy the **Bot User OAuth Token**.
4. Invite the bot to the target channel (e.g., `/invite @Slack Pulse`).
5. Capture the channel ID (Right click channel → **Copy channel ID**).

## One-Click Deployment on Replit

1. Click **Create Repl → Import from GitHub** and point to this repository.
2. Replit detects `replit.nix` and provisions Python 3.11 automatically.
3. In the Replit left sidebar, open **Secrets** and add:
   - `SLACK_BOT_TOKEN`
   - `CHANNEL_ID`
   - `API_KEY`
   - (optional) `DATABASE_URL`, `SYNC_INTERVAL_SECONDS`
4. Press **Run**. The `.replit` profile installs `requirements.txt` and launches
   `uvicorn server:app --host=0.0.0.0 --port=8000`.
5. Once bootstrapped, click the **Open in new tab** button to view the service.
6. Validate the deployment:
   - `GET https://<your-repl>.repl.co/healthz`
   - `GET https://<your-repl>.repl.co/api/daily-checkins` with header
     `X-API-Key: <API_KEY>`

The background task automatically syncs Slack every `SYNC_INTERVAL_SECONDS`
seconds. You can force a refresh with `POST /api/refresh`.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host=0.0.0.0 --port=8000
```

## REST API Overview

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Service readiness probe. |
| `GET` | `/api/daily-checkins` | Today’s check-ins. |
| `GET` | `/api/absentees?date=YYYY-MM-DD` | Absentees for a date (default today). |
| `GET` | `/api/checkin?user=<id>&date=YYYY-MM-DD` | Specific user’s entry. |
| `GET` | `/api/summary/day` | Daily totals and % good. |
| `GET` | `/api/summary/week` | Weekly per-user engagement stats. |
| `GET` | `/api/summary/month` | 30-day aggregate with trend series. |
| `POST` | `/api/refresh` | Triggers an immediate Slack sync. |

All `/api/*` routes require the `X-API-Key` header.

## MCP Usage

The MCP server is defined in `server.py` using `FastMCP("slack-pulse")` and
exposes the following tools:

- `get_daily_checkins()`
- `get_absentees(date: str | None)`
- `get_user_checkin(user_id: str, date: str)`
- `get_cumulative_report(period: str)`

Launch it with the `mcp` CLI:

```bash
mcp server server:mcp
```

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "slack-pulse": {
      "command": "python",
      "args": [
        "-m",
        "mcp",
        "server",
        "server:mcp"
      ],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "CHANNEL_ID": "${CHANNEL_ID}",
        "API_KEY": "${API_KEY}",
        "DATABASE_URL": "${DATABASE_URL:-slack_pulse.db}",
        "SYNC_INTERVAL_SECONDS": "${SYNC_INTERVAL_SECONDS:-300}"
      }
    }
  }
}
```

## Data Model

SQLite tables are created automatically on startup:

- `users` – Slack roster metadata.
- `checkins` – Individual check-in records with quality score.
- `absentees` – Users missing a check-in for a specific date.
- `sync_state` – Tracks incremental sync progress.

## Testing

Run a syntax check across the project:

```bash
python -m compileall server.py
```

For integration testing, configure Slack credentials and exercise the REST
endpoints or MCP tools.
