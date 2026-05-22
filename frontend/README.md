# Event Management Frontend

The Event Management Frontend is the client application for browsing events, registering attendees, handling self-service registration follow-up, and running the operational staff and admin workflows exposed by the Event Management backend. It is a route-driven React application with typed API integration, centralized validation, server-state management, role-aware session handling, and a shared UI layer for public, staff, and admin experiences.

This frontend can be run and verified on its own as long as it can reach a hosted backend through `VITE_API_BASE_URL`.

## Current Scope

This frontend currently implements:

- public event browsing and event detail
- single and batch registration flows
- registration lookup
- self-service cancellation and refund-request submission
- payment callback guidance pages
- pending-payment recovery for eligible single registrations
- staff login
- staff registration search
- staff check-in and reverse check-in
- unread staff notifications
- admin dashboard
- admin event management
- admin staff management
- admin registrations analytics table
- admin refund review
- admin notification dispatch
- admin analytics summary with CSV and PDF export actions

## Tech Stack

| Layer | Technology |
| --- | --- |
| Framework | React 18 |
| Build tool | Vite 6 |
| Language | TypeScript 5 |
| Routing | React Router 6 |
| Server state | TanStack Query 5 |
| Forms | React Hook Form 7 |
| Validation | Zod 3 |
| HTTP client | Axios 1 |
| Styling | Shared CSS in `src/styles.css` |

## Key Design Patterns

- App startup validates environment configuration before bootstrapping the main app. Invalid or missing frontend env now renders a readable recovery screen instead of a blank page.
- HTTP behavior is centralized through a shared Axios client in `src/api/http.ts`.
- Backend errors are normalized centrally in `src/lib/apiError.ts` before they reach pages and forms.
- Shared query keys live in `src/lib/queryKeys.ts` so React Query usage stays consistent.
- Forms use `react-hook-form` and practical `zod` validation instead of ad hoc local form state.
- Critical backend responses are runtime-validated with `zod` before the UI consumes them.
- Mutations that affect registration state, refunds, check-in, and admin workflows stay server-confirmed only. The frontend does not use optimistic UI for those operations.
- Backend timestamps are treated as authoritative UTC input and formatted through shared date utilities instead of component-level timezone math.
- Public, auth, staff, and admin areas are separated through route guards, layouts, and route-level pages rather than one large app shell.

## Repository Layout

- `src/api/` - API modules grouped by backend domain
- `src/components/` - reusable UI primitives and shared screens
- `src/config/` - runtime configuration helpers
- `src/layouts/` - public, auth, staff, and admin layout shells
- `src/lib/` - shared client utilities such as query keys, sessions, dates, and error normalization
- `src/pages/` - route-level screens
- `src/routes/` - route map and guard wrappers
- `src/types/` - shared TypeScript types and Zod schemas
- `src/styles.css` - shared application styling
- `vite.config.ts` - Vite build configuration
- `Dockerfile` - production container build for the frontend app
- `nginx.conf` - SPA routing support for containerized frontend serving

## Local Setup

### 1. Prepare the frontend environment

Create `frontend/.env` before starting the app.

```bash
cp .env.example .env
```

Required variable:

- `VITE_API_BASE_URL`

Example:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### 2. Install dependencies

```bash
npm ci
```

### 3. Start the development server

```bash
npm run dev
```

Default local frontend URL:

- [http://localhost:5173](http://localhost:5173)

## Runtime And Build

### Production build

```bash
npm run build
```

### Preview the production build

```bash
npm run preview
```

Default preview URL:

- [http://localhost:4173](http://localhost:4173)

### Container runtime

The frontend repository includes:

- `Dockerfile` for the production image build
- `nginx.conf` for SPA route fallback and static file serving

The root repository `docker-compose.yml` can also run the frontend together with backend infrastructure when you want the full stack locally.

## Verification

Run the frontend verification steps from `frontend/`:

```bash
npm run typecheck
npm run build
```

Current verification model:

- TypeScript correctness is enforced through `npm run typecheck`
- production bundling is verified through `npm run build`
- there is not yet a dedicated frontend test suite in this repository

## Backend Integration Requirements

This frontend expects a reachable backend at `VITE_API_BASE_URL`.

For local development that usually means:

- backend API at [http://localhost:8000](http://localhost:8000)
- CORS configured to allow the frontend origin, such as:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

If backend API calls work in `/docs` but fail in the browser app, check:

1. the value of `VITE_API_BASE_URL`
2. backend CORS configuration
3. whether the backend is reachable from the browser at that exact origin

## Route Overview

### Public

- `/events`
- `/events/:eventId`
- `/events/:eventId/register`
- `/events/:eventId/register/batch`
- `/registrations/lookup`
- `/payment/success`
- `/payment/failure`

### Auth

- `/staff/login`
- `/admin/login`

### Staff

- `/staff`
- `/staff/registrations`
- `/staff/notifications`

### Admin

- `/admin`
- `/admin/events`
- `/admin/events/new`
- `/admin/events/:eventId/edit`
- `/admin/staff`
- `/admin/staff/:staffId`
- `/admin/registrations`
- `/admin/refunds`
- `/admin/notifications`
- `/admin/analytics`

## Operational Notes

- Staff and admin sign-in use backend JWT login and refresh endpoints.
- The frontend stores the access token, refresh token, and role in local storage because the current backend contract does not expose a `me` endpoint.
- On `401`, the frontend attempts one refresh cycle before clearing the session and redirecting to login.
- The payment callback pages are informational only. Final registration and payment truth still comes from backend processing and registration lookup.
- Pending single-registration payments can request a fresh payment link from registration lookup when the backend still allows it.
- Admin notifications are dispatch-only in the current UI because the backend has send behavior but not admin notification history retrieval.
- Public lookup currently reflects the backend’s unseen-notifications model rather than a full notification timeline.

## Environment Reference

Use `.env.example` as the source of truth for frontend runtime configuration.

At the moment the only required frontend env variable is:

- `VITE_API_BASE_URL` - the full backend base URL the frontend should call

The frontend startup layer validates this variable before the main app is imported.

## Known Limitations

These are backend-contract limitations the frontend already works around:

- no `GET /auth/me`, so the frontend relies on the persisted login payload for role and session context
- no admin notification history endpoint, so admin notifications remain dispatch-only
- no public notification history endpoint, so registration lookup shows only unseen notifications
- no public payment verification endpoint for callback pages, so payment success and failure pages cannot independently confirm final state
- no refund detail endpoint, so admin refund review is list-based with inline actions
- no batch payment re-initialization endpoint, so payment-link recovery is limited to eligible single registrations

## Additional Documentation

- [../README.md](../README.md) - repository-level overview and local run options
- [../backend/README.md](../backend/README.md) - backend setup, services, and seed details