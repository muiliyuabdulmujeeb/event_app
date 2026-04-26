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

## Phase 1 Notes

This phase provides project scaffolding only. Feature implementation, migrations, authentication, and seed data behavior will be added in later phases.
