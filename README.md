# Event Management App

Phase 1 scaffolding for the event management platform described in `project_spec.md`.

## Overview

This repository contains:

- A FastAPI backend
- A React + Vite frontend
- PostgreSQL and Redis via Docker Compose
- Celery worker scaffolding
- Alembic scaffolding
- A minimal pytest harness

## Prerequisites

- Docker
- Docker Compose

## Environment Files

Copy the example files before starting:

- Root backend/worker env: copy `.env.example` to `.env`
- Frontend env: copy `frontend/.env.example` to `frontend/.env`

## Start The Stack

```bash
docker compose up --build
```

Services exposed by default:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

## Run Backend Tests

```bash
docker compose run --rm backend pytest tests/ -v
```

## Seed Demo Data

Phase `14.5B` adds an idempotent demo/dev seed runner in `backend/seed.py`.

Run it with:

```bash
docker compose run --rm seed
```

The seed is additive and idempotent:

- it creates or updates the known seed records by stable business keys
- it does not wipe unrelated records
- it is safe to rerun when you want to refresh the demo dataset

All seeded staff accounts use this password:

```text
SeedDemo123!
```

Key seeded logins:

- `creator.admin@eventapp.local`
- `delegated.admin@eventapp.local`
- `ops.admin@eventapp.local`
- `events.staff@eventapp.local`
- `review.staff@eventapp.local`
- `selected.staff@eventapp.local`

Representative seeded registration IDs:

- `TEC-2026-RFD001` for completed refund history
- `TEC-2026-RRQ001` for active refund request history
- `WLT-2026-WTL001` for active waitlist promotion
- `VIPX-2026-EXC001` for capacity override / exception registration
- `VIPX-2026-CAN001` for preserved historical waitlist cancellation

## Project Notes

The project now includes:

- full backend business flows through Phase `14.5A`
- admin analytics and exports
- operational dead-letter handling for failed async email work
- a reusable demo seed dataset for local testing and UI work
