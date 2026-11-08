# Smart Health AI

A starter project for personal wellness insights using health data that the user explicitly chooses to provide.

## Current status

This repository contains the initial application scaffold. It does not yet connect to Xiaomi Mi Fitness, Health Connect, or Freddy, and it does not collect health data automatically.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Environment

Copy `.env.example` to `.env` if you later add integrations. Never commit API keys, passwords, tokens, or personal health data.

## Planned next steps

1. Define the health metrics and data source.
2. Add a secure, consent-based import/API integration.
3. Generate general wellness summaries with clear limitations.
4. Add an optional daily summary schedule.

## Important

This project is informational only and is not a medical device. It must not diagnose conditions or replace advice from a qualified healthcare professional.
