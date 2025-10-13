# Slack Check-in Analysis MCP

Slack Check-in Analysis MCP is a reference implementation of the check-in analytics platform described in the project brief. It exposes an HTTP API for retrieving channel messages from Slack and layers an AI-ready analysis agent on top of those messages to answer operational questions, rate check-in quality, and generate dashboards.

## Features

- **/api/checkins** endpoint that streams messages from a Slack channel into normalized JSON payloads.
- Intelligent **check-in quality classification** based on completeness, clarity, and specificity heuristics.
- **Agent endpoints** for natural-language-style queries and automated dashboard generation (daily, weekly, monthly).
- Modular service layer that can be extended with LLM integrations for richer reasoning workflows.

## Prerequisites

- Node.js 18+
- A Slack Workspace with a bot token that has the `conversations.history`, `users:read`, and `users:read.email` scopes.

## Getting Started

1. Install dependencies:

 ```bash
  npm install
  ```

2. Create an `.env` file with the following variables:

  ```bash
  SLACK_BOT_TOKEN=xoxb-...
  PORT=3000 # optional
  ```

3. Start the service:

  ```bash
  npm start
  ```

  The API will be available at `http://localhost:3000`.

## Turning the Service into a Slack App

The API expects a Slack Bot Token that can read messages from the target check-in channel.
Follow these steps to provision the token:

1. Visit <https://api.slack.com/apps> and click **Create New App → From scratch**.
2. Name the app (e.g., `Check-in MCP`) and choose the workspace that hosts your
   check-in channel.
3. In the app configuration sidebar, open **OAuth & Permissions** and add the
   following **Bot Token Scopes**:
   - `channels:history` *(or `conversations.history` if using the newer Conversations API)*
   - `channels:read`
   - `users:read`
   - `users:read.email`
4. Click **Install to Workspace** and authorize the app. Slack will generate a
   `Bot User OAuth Token` that begins with `xoxb-`. Copy this token into your
   `.env` file as `SLACK_BOT_TOKEN`.
5. Invite the bot user to the channel that contains daily check-ins, e.g.
   `/invite @check-in-mcp` inside Slack. Without this step, the token will not be
   able to read channel history.

Once these steps are complete you can call `GET /api/checkins` with the channel
ID (press `Ctrl+Shift+I` in Slack desktop → **Channels** → **Copy channel ID**) to
pull the raw dataset for MCP analysis.

> **Tip:** For production you may prefer to create a dedicated Slack workspace
> or user group so that MCP analysis stays scoped to the relevant cohort.

## Deploying the API

The service is a standard Express application that can run anywhere Node.js 18+
is available. Below is a reference deployment workflow using Render, but any
platform (Fly.io, Railway, AWS Elastic Beanstalk, Azure App Service, etc.) will
work with analogous settings.

1. Commit this repository to a Git provider (GitHub, GitLab, Bitbucket).
2. Create a new **Web Service** on <https://render.com> and connect the repo.
3. Configure the build and start commands:
   - Build command: `npm install`
   - Start command: `npm start`
4. Set the environment variables in Render → **Environment**:
   - `SLACK_BOT_TOKEN` with the bot token from the Slack app setup.
   - `PORT` (optional; Render will inject `PORT`, so you can omit this).
5. Deploy. Render will provision a public URL where the Express API is hosted.

### Securing the Deployment

- Restrict the `/api/checkins` endpoint with an API key or Slack signed secret
  middleware before exposing it broadly.
- Prefer storing environment variables in a secrets manager (Render Secrets,
  AWS SSM, etc.) rather than committing them to source control.
- Consider rate limiting and audit logging if you expect regular automated
  usage from your MCP agent.

### Connecting the MCP Agent

Once the API is live you can wire your MCP runtime to call the hosted endpoints:

1. Fetch channel history: `GET https://your-domain/api/checkins?channel_id=C123&start_date=...&end_date=...`.
2. Pass the response `results` array into the agent endpoints:
   - `POST /api/agent/query` for natural-language questions.
   - `POST /api/agent/report` for dashboards.
3. Cache results or persist them in your MCP to avoid re-querying Slack for the
   same window repeatedly.

For more detailed, step-by-step deployment examples (including Docker-based
setups and GitHub Actions automations), see [`docs/slack-app-deployment.md`](docs/slack-app-deployment.md).

## API Overview

### Health Check

`GET /health`

Returns `{ "status": "ok" }` to confirm the service is running.

### Retrieve Check-ins

`GET /api/checkins`

Query parameters:

| Name        | Required | Description                                  |
| ----------- | -------- | -------------------------------------------- |
| channel_id  | Yes      | Slack channel ID to read from.               |
| start_date  | Yes      | Start of the reporting window (YYYY-MM-DD).  |
| end_date    | Yes      | End of the reporting window (YYYY-MM-DD).    |

Example response:

```json
{
  "channel_id": "C123",
  "start_date": "2024-10-01",
  "end_date": "2024-10-07",
  "count": 5,
  "results": [
    {
      "message_id": "1727700160.12345",
      "user_id": "U123",
      "user_name": "Jane Smith",
      "timestamp": "2024-10-01T14:22:40.000Z",
      "message_content": "Yesterday I closed out...",
      "quality": "Strong"
    }
  ]
}
```

### Agent Query

`POST /api/agent/query`

Body fields:

- `question` (string, required): Natural language request.
- `checkins` (array, required): Check-in objects, e.g. the `results` array from `/api/checkins`.
- `roster` (array, optional): List of students expected to check in. Accepts strings or objects with `id`/`name`.

The agent currently handles attendance, blocker discovery, check-in quality lookups, and best-progress heuristics for the current ISO week.

### Agent Dashboard Generation

`POST /api/agent/report`

Body fields:

- `user` (object, required): `{ "id": "U123", "name": "Jane Smith" }`.
- `timeframe` (object, required):
  - `type`: `daily`, `weekly`, or `monthly`.
  - `date`, `start`, or `month`: Date anchors (YYYY-MM-DD) depending on the report type.
- `checkins` (array, required): Same structure as above.
- `roster` (array, optional).

The response includes summaries, average quality scores, blocker highlights, and consistency statistics.

## Extending the Agent

The agent class (`src/agent/checkinAgent.js`) is intentionally modular so you can plug it into an LLM orchestration framework. Feed it normalized check-in data and a roster, then:

- Use `answerQuestion()` for natural-language style prompts.
- Call `generateDashboard()` to build student-specific reports.
- Leverage helper methods (`summarizeDaily`, `summarizeWeek`, `extractBlockers`, etc.) within your MCP implementation.

## Development

- Run with live reload: `npm run dev`
- The repository ships with heuristics for check-in quality; adjust `src/utils/checkinQuality.js` to fine-tune scoring.

## Roadmap Ideas

- Persist check-ins to a database for historical analytics.
- Integrate with an LLM provider for richer natural language understanding.
- Build a Slack slash command that proxies requests to the MCP agent.

## License

MIT
