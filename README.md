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
Product catalogs are synchronized automatically from supplier APIs (e.g. Ingram Micro) via ARQ background tasks. Each sync run fetches pricing, availability, and product metadata, then updates the local catalog incrementally. Configurable filters allow restricting sync to specific categories, minimum quantities, and minimum prices.

### Product Enrichment via Icecat
Once synced, products are enriched asynchronously with detailed technical specifications, marketing descriptions, high-resolution images, and standardized attribute data pulled from the [Icecat](https://icecat.us/) open catalog. Enrichment runs as a separate ARQ task and is tracked per-product with a `last_enrichment_sync` timestamp.

### Dynamic Pricing
Sale prices are computed at runtime from cost + customs rate + margin + tax, avoiding price list maintenance. FX rates are fetched and cached so multi-currency supplier prices (USD, EUR…) are always converted to the local currency at checkout.

### Full-Text Search
PostgreSQL GIN index on `to_tsvector` enables fast full-text product search across name, description, manufacturer, and part number fields.

## Project Structure

```
.
├── backend/
│   └── app/
│       ├── api/           # Routes and endpoints
│       ├── features/      # Domain modules (products, orders, cart, pricing…)
│       ├── tasks/         # ARQ background tasks (supplier sync, enrichment)
│       └── alembic/       # Database migrations
├── frontend/              # Public storefront (Quasar SSR)
├── admin-frontend/        # Back-office (Quasar SPA)
├── shared/
│   ├── api-types/         # Types auto-generated from OpenAPI schema
│   ├── api-client/        # Shared axios client with token refresh
│   └── utils/             # Shared utilities (currency formatting, pricing…)
└── docker-compose.yml
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 22+
- pnpm 10+
- Python 3.12+ (or uv)

### Backend

```bash
docker compose up -d postgres redis clamav
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### Frontend

```bash
pnpm install
pnpm dev:front    # storefront at http://localhost:9000
pnpm dev:admin    # admin at http://localhost:9001
```

### Regenerate API types

```bash
# Backend must be running
pnpm gen:types
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT secret key |
| `DATABASE_URL` | PostgreSQL connection URL |
| `REDIS_URL` | Redis URL (ARQ broker) |
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins (e.g. `["http://localhost:9000"]`) |
| `INGRAM_CLIENT_ID` | Ingram Micro API client ID |
| `INGRAM_CLIENT_SECRET` | Ingram Micro API client secret |
| `ICECAT_USERNAME` | Icecat account username |
| `ICECAT_API_KEY` | Icecat API key |

## Tests & coverage

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push to `main` and on every PR:

- **Backend**: `ruff` (lint + format) + `mypy` + `pytest` **under coverage** (`coverage run -m pytest`). The coverage config (`source = app`, exclusions) lives in [`backend/pyproject.toml`](backend/pyproject.toml) (section `[tool.coverage.*]`); uncomment `fail_under` to gate the build.
- **Frontend**: `lint` + `typecheck` for both apps (storefront + admin) + **unit tests of the shared engine** (`@app/utils`: currency / pricing / date) via **vitest**, under coverage.

### Run locally

```bash
# Backend (from backend/)
uv run coverage run -m pytest && uv run coverage report

# Frontend — shared engine (from the repo root)
pnpm test:coverage          # report + coverage/coverage-summary.json
```

### Coverage badges (gist)

The badges at the top of this README rely on a **gist** read by shields.io, updated by CI on every push to `main` (via `schneegans/dynamic-badges-action`). This is **optional**: without configuration the badge steps are skipped and CI stays green.

**Enable**: the gist (`9a9268773f32888a2eae4d1b9567efe0`) is already wired into CI and the badges. What remains:
1. Seed the **public gist** with two files `coverage-backend.json` and `coverage-frontend.json` (initial content `{}`).
2. Add a **PAT** (scope `gist`) as the repository **secret** `GIST_SECRET` (Settings → Secrets and variables → Actions → Secrets).

On the next push to `main`, CI publishes the percentages into the gist and the badges render.

> ℹ️ A gist is tied to an **account**, not a repository — the setup is independent of forks.

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`) — see [LICENSE](LICENSE).

Copyright (C) 2026 Natimai Solutions.

> ⚠️ **Network use (AGPL §13):** if you run a modified version of this software as a network service, you must make its complete corresponding source code available to the users of that service.
