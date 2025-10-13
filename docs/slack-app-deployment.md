# Slack App Setup and Deployment Guide

This guide expands on the README and walks through turning the Slack Check-in
Analysis MCP into a production-ready Slack app and hosted API.

## 1. Create and Configure the Slack App

1. Log in to <https://api.slack.com/apps> and click **Create New App → From scratch**.
2. Name the app (e.g., `Check-in MCP`) and pick the target workspace.
3. Navigate to **Basic Information → App Credentials** and note the `Client ID`
   and `Client Secret` in case you need them for future OAuth flows.
4. Under **OAuth & Permissions**, add these **Bot Token Scopes**:
   - `channels:history` *(read channel messages)*
   - `channels:read` *(fetch channel list and metadata)*
   - `users:read` *(map user IDs to display names)*
   - `users:read.email` *(optional but helpful for roster matching)*
5. Scroll down and click **Install to Workspace**. Slack returns a `Bot User OAuth
   Token` (`xoxb-...`). Store it securely—this becomes your `SLACK_BOT_TOKEN`.
6. In Slack, invite the bot to each channel you plan to analyze (e.g.,
   `/invite @Check-in MCP`).

### Optional: Granular Bot Permissions

If your workspace is on the newer, granular permissions model, you can replace
`channels:*` scopes with their `conversations.*` equivalents. Ensure the bot has
access to the channel or it will return empty results.

## 2. Local Development Checklist

- Copy `.env.example` (if you create one) to `.env` and add `SLACK_BOT_TOKEN`.
- Run `npm install` and `npm start` to confirm `/health` and `/api/checkins`
  respond locally.
- Use Slack's web client to copy a channel ID (`Ctrl+Shift+I` → **Channels** →
  **Copy channel ID**) for testing.

## 3. Deploying with Docker (Any Container Platform)

1. Create a `Dockerfile` at the repository root (example below).
2. Build and push the image to your registry of choice.
3. Deploy to your container platform (AWS ECS/Fargate, Google Cloud Run,
   Azure Container Apps, Render, Fly.io, etc.).

```dockerfile
FROM node:18-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
CMD ["npm", "start"]
```

### Container Deployment Environment Variables

| Variable          | Required | Notes                                      |
| ----------------- | -------- | ------------------------------------------ |
| `SLACK_BOT_TOKEN` | Yes      | Bot token from Slack app installation.     |
| `PORT`            | No       | Only set if your platform requires a value |

Most platforms provide a `PORT` automatically. The Express app listens on
`process.env.PORT || 3000`, so no change is necessary.

## 4. Automating Deployments with GitHub Actions

A minimal workflow (`.github/workflows/deploy.yml`) could:

1. Install dependencies and run tests/lint.
2. Build the Docker image and push to GHCR or your registry.
3. Trigger your hosting platform (Render/Fly/Heroku) to deploy the new image.

```yaml
name: Deploy

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 18
      - run: npm install
      - run: npm test --if-present
      - run: npm run lint --if-present
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: ghcr.io/<org>/<app>:latest
      - name: Trigger Render deploy
        run: |
          curl -X POST \
            -H 'Authorization: Bearer ${{ secrets.RENDER_API_TOKEN }}' \
            -d '' \
            https://api.render.com/v1/services/<service-id>/deploys
```

Replace placeholder values (`<org>`, `<app>`, `<service-id>`) with your project
settings and inject tokens through repository secrets.

## 5. Wiring the MCP Agent

Once the API is deployed, integrate it with your MCP runtime:

1. Schedule periodic sync jobs to call `/api/checkins` for relevant date ranges.
2. Persist responses (e.g., S3, Supabase, Postgres) so you can query historical
   data without re-hitting Slack.
3. Expose MCP tools that proxy to `/api/agent/query` and `/api/agent/report`,
   passing in the cached check-in data and optional roster metadata.
4. Add rate limiting and retries—Slack APIs throttle burst requests.

## 6. Operational Considerations

- **Secrets management:** Use platform-specific secret stores (Render Secrets,
  AWS Secrets Manager, Doppler) rather than `.env` files in production.
- **Monitoring:** Enable log drains or attach APM tooling to detect failures in
  Slack API calls.
- **Error handling:** Slack tokens expire when the app is removed from a
  workspace. Implement alerts for repeated `401`/`403` responses.
- **Data retention:** Align check-in storage policies with your institution's
  privacy requirements. Consider encrypting stored messages at rest.

With these steps the Slack Check-in Analysis MCP becomes a deployable Slack app
that powers the `/api/checkins` endpoint and downstream AI analysis.
