# FastAPI Ecommerce

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
