# Event Management App

This repository contains the full Event Management application:

- a FastAPI backend
- a React + Vite frontend
- PostgreSQL and Redis for local infrastructure
- Celery workers for background processing
- seed data for demos and UI walkthroughs

## Current Scope

The combined backend and frontend currently support:

- staff authentication with access and refresh tokens
- public event discovery and event detail
- single and batch registration
- payment initialization and callback guidance pages
- registration lookup and self-service actions
- staff registration operations, check-in, reverse check-in, and unread notifications
- admin event management
- admin staff management
- admin registrations analytics table
- admin refunds and notification dispatch
- admin analytics summary with CSV and PDF exports

## Repository Layout

- `backend/` - FastAPI app, Alembic, Celery worker, tests, and backend-local Docker Compose
- `frontend/` - React app, Vite config, route pages, and shared client utilities
- `docker-compose.yml` - root full-stack local container workflow
- [backend/README.md](./backend/README.md) - backend setup, services, tests, and seed details
- [frontend/README.md](./frontend/README.md) - frontend setup, routes, auth behavior, and known frontend limitations

## Local Environment Files

Create the env files before running services:

- copy `.env.example` to `.env` for the root full-stack compose flow
- copy `backend/.env.example` to `backend/.env` for backend-only compose work
- copy `frontend/.env.example` to `frontend/.env` for local frontend development

Minimum frontend requirement:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Local Run Options

### Option 1. Full-stack root Docker Compose

From the repository root:

```bash
docker compose up --build
```

Default services:

- frontend: [http://localhost:3000](http://localhost:3000)
- backend API: [http://localhost:8000](http://localhost:8000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

This root compose file includes:

- `backend`
- `worker`
- `frontend`
- `db`
- `redis`
- `seed`

### Option 2. Backend compose plus frontend dev server

Backend infrastructure and API:

```bash
cd backend
docker compose up -d db redis
docker compose run --rm migrate
docker compose up backend worker
```

Frontend dev server:

```bash
cd frontend
npm ci
npm run dev
```

Default local URLs for this split workflow:

- frontend dev server: [http://localhost:5173](http://localhost:5173)
- backend API: [http://localhost:8000](http://localhost:8000)

## Seed Demo Data

The backend includes an idempotent seed runner for demos, walkthroughs, and UI validation.

From the backend directory:

```bash
docker compose run --rm seed
```

Shared seeded staff password:

```text
SeedDemo123!
```

Representative seeded logins:

- `creator.admin@eventapp.local`
- `delegated.admin@eventapp.local`
- `ops.admin@eventapp.local`
- `events.staff@eventapp.local`
- `review.staff@eventapp.local`
- `selected.staff@eventapp.local`

See [backend/README.md](./backend/README.md) for the fuller seeded data breakdown.

## Frontend Notes

The frontend validates its env config at startup and shows an in-app error screen if `VITE_API_BASE_URL` is missing or invalid.

If data loads through backend `/docs` but the browser app shows connection errors, check:

1. frontend `.env`
2. backend CORS configuration
3. that the backend API is reachable at the exact `VITE_API_BASE_URL`

## Testing and Verification

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

Backend:

```bash
cd backend
docker compose run --rm --no-deps backend pytest tests/ -v
```

## Additional Documentation

- [backend/README.md](./backend/README.md)
- [frontend/README.md](./frontend/README.md)
