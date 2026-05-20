# Event Management App Backend

The Event Management App Backend is the server-side system for creating events, taking registrations, processing payments, managing refunds and waitlists, sending operational notifications, and exposing admin reporting. It is an API-first backend with role based access control, relational database persistence, asynchronous background processing, and a test-backed workflow model for event operations.  

For the detailed contributor-level breakdown of implementation decisions, request flow, schema evolution, and service behavior, see `docs/technical_implementation.md`.

## Current Scope

This repository currently implements:

- staff authentication with access and refresh tokens
- admin event creation, update, cancellation, and overflow-rule control
- public single and batch registration flows
- free and paid event handling
- payment initialization and webhook processing
- user and staff notifications
- registration lookup by `reg_id`
- paid waitlist promotion offers
- exception registration offers with audit history
- self-service cancellation and refund requests
- manual review and registration requeue flows
- admin analytics with CSV and PDF exports
- dead-letter tracking for terminal email task failures
- demo/dev seed data for local testing and walkthroughs

## Tech Stack

| Layer | Technology |
| --- | --- |
| API framework | FastAPI |
| Language/runtime | Python 3.11 |
| ORM and database access | SQLAlchemy async |
| Primary database | PostgreSQL 15 |
| Migrations | Alembic |
| Background jobs | Celery |
| Queue / broker / result backend | Redis |
| HTTP client integrations | httpx |
| Authentication | JWT via `python-jose` |
| Password hashing | bcrypt / passlib |
| Reporting | ReportLab (PDF), standard CSV utilities |
| Testing | pytest, pytest-asyncio, HTTPX ASGI client |
| Local container runtime | Docker Compose |

## Key Design Patterns

- Route handlers own the transaction boundary. Services mutate the session and return response artifacts; routes commit or roll back.
- Business rules live in service classes. Database querying and persistence stay in repository classes.
- Background work is queued after successful commits, so emails and async processing are not dispatched for rolled-back writes.
- Schema changes are additive and tracked through Alembic revisions.
- Seed data is idempotent and additive, so local environments can be repopulated without resetting the whole database.

These patterns are explained in more detail in `docs/technical_implementation.md`.

## Repository Layout

- `app/api/` - FastAPI route modules
- `app/services/` - business logic and orchestration
- `app/repositories/` - database access and query composition
- `app/models/` - SQLAlchemy models
- `app/workers/` - Celery tasks and schedules
- `app/schemas/` - request and response models
- `app/utils/` - export helpers
- `alembic/` - migration history
- `tests/` - backend test suite
- `seed.py` - demo/dev seed runner
- `docker-compose.yml` - backend-local runtime stack

## Local Setup

### 1. Prepare environment

```bash
cp .env.example .env
```

Review `.env` and update any values you need, especially:

- `JWT_SECRET`
- payment gateway credentials
- email provider credentials
- `APPLICATION_BASE_URL`

### 2. Start infrastructure

```bash
docker compose up -d db redis
```

### 3. Apply database migrations

```bash
docker compose run --rm migrate
```

### 4. Start the API and worker

```bash
docker compose up backend worker
```

### 5. Start the queue, database, database migrations, API, worker and app at once

```bash
docker compose up --build
```

### 6. Verify the service

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI spec: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

## Docker Services

This backend repository includes its own `docker-compose.yml` with:

- `db` - PostgreSQL database
- `redis` - Redis broker/backend
- `migrate` - one-shot Alembic migration runner
- `backend` - FastAPI application
- `worker` - Celery worker with beat enabled
- `seed` - one-shot seed runner

## Seed Data

This repository includes an idempotent seed dataset intended for local development, UI testing, demos, and backend verification.

Run it with:

```bash
docker compose run --rm seed
```

Shared seed password:

```text
SeedDemo123!
```

Seeded staff accounts:

- `creator.admin@eventapp.local`
- `delegated.admin@eventapp.local`
- `ops.admin@eventapp.local`
- `events.staff@eventapp.local`
- `review.staff@eventapp.local`
- `selected.staff@eventapp.local`

The seed populates realistic data across:

- events in multiple states
- single and batch registrations
- payments and payment retries
- refund requests
- waitlist and promotion records
- exception offers and audits
- manual review cases
- dead-letter failures
- notifications
- analytics-ready records

## Running Tests

Run the full backend suite:

```bash
docker compose run --rm --no-deps backend pytest tests/ -v
```

Run a focused module:

```bash
docker compose run --rm --no-deps backend pytest tests/test_registration.py -v
```

The test suite:

- applies Alembic migrations to the test database
- truncates tables between tests
- uses dependency overrides for the FastAPI app
- captures queued email and payment tasks in tests where needed

## Operational Notes

- Payment webhooks are normalized and then handed off to Celery-backed processing.
- Email sending can use provider failover and records terminal failures in the dead-letter store.
- Analytics and exports are synchronous API responses, not background export jobs.
- The worker runs both task execution and the periodic schedules for stale-payment and stale-offer expiry.

## Environment Reference

Use `.env.example` as the complete configuration reference. It includes:

- database URLs
- Redis URL
- JWT settings
- payment gateway settings
- callback and application URLs
- waitlist promotion expiry configuration
- email provider and failover settings

## Additional Documentation

- `docs/technical_implementation.md` - detailed implementation guide for contributors
