FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY slack_pulse ./slack_pulse
COPY team_roster.csv ./team_roster.csv
COPY .env.example ./

EXPOSE 8000

CMD ["uvicorn", "slack_pulse.api:app", "--host", "0.0.0.0", "--port", "8000"]
