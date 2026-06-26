# FastAPI Ecommerce

[![CI](https://github.com/jburckel/fastapi-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/jburckel/fastapi-ecommerce/actions/workflows/ci.yml)
[![Couverture backend](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-backend.json)](https://github.com/jburckel/fastapi-ecommerce/actions/workflows/ci.yml)
[![Couverture frontend](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-frontend.json)](https://github.com/jburckel/fastapi-ecommerce/actions/workflows/ci.yml)

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

## Tests & couverture

La CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) s'exécute à chaque push sur `main` et sur chaque PR :

- **Backend** : `ruff` (lint + format) + `mypy` + `pytest` **sous couverture** (`coverage run -m pytest`). La config de couverture (`source = app`, exclusions) est dans [`backend/pyproject.toml`](backend/pyproject.toml) (section `[tool.coverage.*]`) ; décommenter `fail_under` pour gater le build.
- **Frontend** : `lint` + `typecheck` des deux apps (storefront + admin) + **tests unitaires du moteur partagé** (`@app/utils` : currency / pricing / date) via **vitest**, sous couverture.

### Lancer en local

```bash
# Backend (depuis backend/)
uv run coverage run -m pytest && uv run coverage report

# Frontend — moteur partagé (depuis la racine)
pnpm test:coverage          # rapport + coverage/coverage-summary.json
```

### Badges de couverture (gist)

Les badges en tête de ce README s'appuient sur un **gist** lu par shields.io, mis à jour par la CI à chaque push sur `main` (via `schneegans/dynamic-badges-action`). Le dispositif est **optionnel** : sans configuration, les étapes de badge sont ignorées et la CI reste verte.

**Activer** : le gist (`9a9268773f32888a2eae4d1b9567efe0`) est déjà câblé dans la CI et les badges. Il reste à :
1. Garnir le **gist public** avec deux fichiers `coverage-backend.json` et `coverage-frontend.json` (contenu initial `{}`).
2. Ajouter un **PAT** (scope `gist`) en **secret** de dépôt `GIST_SECRET` (Settings → Secrets and variables → Actions → Secrets).

Au prochain push sur `main`, la CI publie les pourcentages dans le gist et les badges s'affichent.

> ℹ️ Un gist est rattaché à un **compte**, pas à un dépôt : le dispositif est indépendant du fork.
