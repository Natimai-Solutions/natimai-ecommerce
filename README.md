# FastAPI Ecommerce

[![CI](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)
[![Backend coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-backend.json)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)
[![Frontend coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-frontend.json)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)

A full-stack e-commerce platform built with FastAPI, featuring async background processing, supplier catalog synchronization, and automatic product enrichment. Designed to handle multi-currency pricing, customs duties, and complex margin structures — with French Polynesia (XPF) as a reference implementation.

## Tech Stack

### Backend
- **FastAPI** — async REST API
- **SQLModel / SQLAlchemy** — async PostgreSQL ORM
- **Alembic** — database migrations
- **ARQ** — async background task queue (Redis-backed)
- **uv** — Python dependency management

### Frontend (public storefront)
- **Quasar 2 / Vue 3** — SSR
- **Pinia** — state management
- **TypeScript**

### Admin Frontend
- **Quasar 2 / Vue 3** — SPA
- **Pinia** — state management
- **TypeScript**

### Infrastructure
- **PostgreSQL 16** — primary database
- **Redis** — ARQ broker and cache
- **ClamAV** — antivirus scanning for file uploads
- **Docker / Docker Compose** — development and deployment

## Key Features

### Supplier Catalog Synchronization
Product catalogs are synchronized automatically from supplier APIs (e.g. Ingram Micro) via ARQ background tasks. Each sync run fetches pricing, availability, and product metadata, then updates the local catalog incrementally. Configurable filters allow restricting sync to specific categories, minimum quantities, and minimum prices. Outbound calls are rate-limited and retried with jittered backoff that honours `Retry-After`; a SKU the supplier stops returning is recorded first and only deactivated once the gap outlives a grace period, so a transient outage cannot empty the catalog.

### Product Enrichment via Icecat
Once synced, products are enriched asynchronously with detailed technical specifications, marketing descriptions, high-resolution images, and standardized attribute data pulled from the [Icecat](https://icecat.us/) open catalog. Enrichment runs as a separate ARQ task and is tracked per-product with a `last_enrichment_sync` timestamp.

### Dynamic Pricing
Sale prices are computed at runtime from cost + customs rate + margin + tax, avoiding price list maintenance. FX rates are fetched and cached so multi-currency supplier prices (USD, EUR…) are always converted to the local currency at checkout.

### Payments
Card payments via PayZen / Lyra (with optional deferred capture — authorise at checkout, debit at shipment) plus manual methods (cheque, bank transfer, purchase order) validated in the back office, with full and partial refunds.

### Invoicing
Invoices are issued on payment capture with a gap-free legal numbering sequence, rendered to PDF from a frozen snapshot, and e-mailed to the customer. A refund produces a credit note on its own sequence, referencing the original invoice — an issued invoice is never edited.

### Server-authoritative checkout
The order total is decided by the backend: line prices are re-validated against the catalog before billing (a drift stops the checkout rather than silently charging a different amount), payment fees are read from the selected payment method, and supplier stock is re-checked against the supplier itself before the reservation.

### Full-Text Search
PostgreSQL GIN index on `to_tsvector` enables fast full-text product search across name, description, manufacturer, and part number fields.

## Project Structure

```
.
├── backend/
│   └── app/
│       ├── api/           # Routes and endpoints
│       ├── features/      # Domain modules (products, orders, cart, pricing…)
│       ├── handlers/      # Outbox event handlers (emails, status syncs…)
│       ├── tasks/         # ARQ background tasks (supplier sync, enrichment)
│       └── alembic/       # Database migrations
├── frontend/              # Public storefront (Quasar SSR)
├── admin-frontend/        # Back-office (Quasar SPA)
├── shared/
│   ├── api-types/         # Types auto-generated from OpenAPI schema
│   ├── api-client/        # Shared axios client with token refresh
│   └── utils/             # Shared utilities (currency formatting, pricing…)
├── infra/                 # Caddy (reverse proxy)
├── docker-compose*.yml    # See "Docker Compose files" below
├── DEVELOPMENT.md         # Local development guide
└── DEPLOYMENT.md          # Deployment & environment variables reference
```

## Simple shop in ten minutes

The platform started as an import business in French Polynesia, but a shop
that sells its own stock from one warehouse and ships directly needs none of
that machinery. Two settings in `.env` shape the deployment:

```bash
TERRITORY_PROFILE=FR   # or PF — currency, tax rates, country and starter data
SHOP_MODE=simple       # hides suppliers, customs, exchange rates and multi-leg logistics
```

Then `docker compose up -d && docker compose run --rm migrate`, log into the
admin, fill the legal identity under **Système → Paramètres**, create your
products (fixed price, warehouse stock) and, if you charge shipping, one
carrier and one route under **Logistique**. Cheque and bank transfer work out
of the box; card payments need a PayZen account.

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 22+ and pnpm 10+
- Python 3.12+ and [uv](https://docs.astral.sh/uv/) (only needed for the non-Docker backend workflow)

### Configuration

Copy the example env files and fill in the values (the real `.env` files are gitignored):

```bash
cp .env.example .env                              # backend / stack config
cp frontend/.env.example frontend/.env            # storefront (VITE_API_URL)
cp admin-frontend/.env.example admin-frontend/.env # admin (VITE_API_URL)
```

See [Environment Variables](#environment-variables) below, and [`DEPLOYMENT.md`](DEPLOYMENT.md) for the exhaustive reference.

### Option A — Everything in Docker (recommended)

In development, `docker compose up` automatically merges `docker-compose.yml` with `docker-compose.override.yml` (hot reload, source-mounted volumes, DEBUG logs):

```bash
docker compose up -d                 # full stack (api, worker, poller, db, redis, clamav, frontends)
docker compose up -d postgres redis  # or just selected services
docker compose logs -f api
```

Apply database migrations **and seed the initial data** (one-shot `migrate` service —
runs `alembic upgrade head` then `app/initial_data.py`):

```bash
docker compose run --rm migrate
```

### Option B — Run the apps outside Docker

Run only the infrastructure in Docker and the apps on your host (faster iteration, native debuggers):

```bash
# 1. Infrastructure only
docker compose up -d postgres redis clamav

# 2. Backend API (from backend/)
cd backend
uv sync
uv run alembic upgrade head
uv run python app/initial_data.py      # seed reference data (first run)
uv run uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)

# 3. Background workers (separate terminals, from backend/)
uv run arq app.core.arq_worker.WorkerSettings                       # ARQ worker
uv run python app/scripts/outbox_poller.py --mode continuous --interval 5  # outbox poller

# 4. Frontends (from the repo root)
pnpm install
pnpm dev:front    # storefront — Quasar dev server, default http://localhost:9000
pnpm dev:admin    # admin      — next free Quasar port (e.g. http://localhost:9001)
```

> When running outside Docker, point the backend at the host-mapped services
> (`POSTGRES_SERVER=localhost`, `REDIS_*=localhost`) — see [`DEPLOYMENT.md`](DEPLOYMENT.md).

### Regenerate API types

```bash
pnpm gen:types   # backend must be running
```

## Docker Compose files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Base stack: PostgreSQL, Redis, ClamAV, API, ARQ worker, outbox poller, frontends. Defines the `alembic` / `migration` profiles. |
| `docker-compose.override.yml` | **Auto-applied in development** by `docker compose up`. Enables `--reload`, mounts the source for hot reload, DEBUG logging, tolerant healthchecks. |
| `docker-compose.prod.yml` | Production overrides: `ENVIRONMENT=production`, no reload, restart policies, isolated DB network. |
| `docker-compose.proxy.yml` | Caddy reverse proxy — Let's Encrypt TLS + subdomain routing (bare domain → storefront, `api.` → API, `admin.` → admin). |
| `docker-compose.health.yml` | Dedicated outbox health-checker (recommended in production). |

```bash
# Development (base + override, automatic)
docker compose up -d

# Production (compose files are layered explicitly)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml up -d
```

## Environment Variables

The backend reads configuration from the repository-root `.env` (see [`.env.example`](.env.example)); the two frontends read a build-time `VITE_API_URL` from their own `.env`. In Docker, PostgreSQL and Redis are wired by the compose files; outside Docker you set their connection details yourself.

The most important variables — see [`.env.example`](.env.example) and [`DEPLOYMENT.md`](DEPLOYMENT.md) for the **complete** list:

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (`openssl rand -base64 32`) |
| `ENVIRONMENT` | `local` \| `staging` \| `production` (controls cookie `Secure`, etc.) |
| `DOMAIN` | Root domain (used by the Caddy proxy for subdomain routing) |
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins, JSON array |
| `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` | **Required** — bootstrap admin account (email + password). Must be set in your `.env`. |
| `POSTGRES_SERVER` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database connection (set in compose for Docker) |
| `REDIS_*` | Redis / ARQ broker connection |
| `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` | `mailgun` \| `noop` |
| `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` / `MAILGUN_FROM_EMAIL` | Transactional email (when provider is `mailgun`) |
| `PAYZEN_SITE_ID` / `PAYZEN_API_PASSWORD_TEST` / `PAYZEN_API_PASSWORD_PROD` / `PAYZEN_PUBLIC_KEY_*` | PayZen / Lyra card payments |
| `PAYZEN_MODE` | `TEST` \| `PRODUCTION` |
| `PAYZEN_MANUAL_VALIDATION` | `true` → authorise card at checkout, capture later (deferred debit) |
| `INGRAM_CLIENT_ID` / `INGRAM_CLIENT_SECRET` / `INGRAM_CUSTOMER_NUMBER` | Ingram Micro supplier API |
| `INGRAM_ENVIRONMENT` | `sandbox` \| `production` |
| `INGRAM_ORDER_CREATION_ENABLED` | Auto-create supplier purchase orders on payment capture |
| `ICECAT_USERNAME` / `ICECAT_API_KEY` | Icecat product enrichment |
| `STOCK_RESERVATION_TTL_HOURS` | Release stock held by orders that never reached a payment outcome (0 disables) |
| `SUPPLIER_DELISTING_GRACE_HOURS` | Grace period before deactivating a SKU the supplier stopped returning |
| `CHECKOUT_SUPPLIER_AVAILABILITY_CHECK` | Re-check supplier stock at checkout instead of trusting the last sync |
| `VITE_API_URL` (frontends) | Backend origin; the client appends `/api/v1` |

> ⚠️ **Required secrets are enforced.** `SECRET_KEY`, `POSTGRES_PASSWORD`,
> `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` ship with placeholder defaults
> for local development only. If they are left at their placeholder value, the
> backend **refuses to start** when `ENVIRONMENT` is not `local` (and warns in
> `local`). Set real values in your `.env` before any staging/production deploy.

## Tests & coverage

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push to `main` and on every PR:

- **Backend**: `ruff` (lint + format) + `mypy` + `pytest` **under coverage**, against a throwaway PostgreSQL service. Coverage config (`source = app`, exclusions) lives in [`backend/pyproject.toml`](backend/pyproject.toml) (`[tool.coverage.*]`); `fail_under` gates the build (65 %).
- **Frontend**: `lint` + `typecheck` for both apps + **unit tests of the shared engine** (`@app/utils`: currency / pricing / date) via **vitest**, under coverage.

Coverage reports (`coverage.xml` / `coverage.json` / the vitest summary) are uploaded as CI artifacts.

### Run locally

```bash
# Backend (from backend/) — integration tests need a reachable test DB,
# otherwise they are skipped. See DEVELOPMENT.md.
uv run coverage run -m pytest && uv run coverage report

# Frontend — shared engine (from the repo root)
pnpm test:coverage
```

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`) — see [LICENSE](LICENSE).

Copyright (C) 2026 Natimai Solutions.

> ⚠️ **Network use (AGPL §13):** if you run a modified version of this software as a network service, you must make its complete corresponding source code available to the users of that service.
