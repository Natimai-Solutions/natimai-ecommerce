# Natimai Ecommerce

[![CI](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)
[![Backend coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-backend.json)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)
[![Frontend coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/jburckel/9a9268773f32888a2eae4d1b9567efe0/raw/coverage-frontend.json)](https://github.com/Natimai-Solutions/natimai-ecommerce/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)

A full-stack e-commerce platform: a **FastAPI** API with async background
processing, a server-rendered **Quasar / Vue 3** storefront and a **Quasar**
back-office. It handles supplier catalogue synchronisation, automatic product
enrichment, multi-currency pricing, customs duties and complex margin
structures, with French Polynesia (XPF) as the reference implementation, and
a `SHOP_MODE=simple` profile for a shop that sells its own stock.

## Repository map

| Path | Role | Stack |
|---|---|---|
| [`backend/`](backend/README.md) | REST API, ARQ workers, outbox poller, Alembic migrations | Python 3.12+, FastAPI, SQLModel, PostgreSQL 16, Redis |
| [`frontend/`](frontend/README.md) | Public storefront (SSR) | Quasar 2, Vue 3, TypeScript, Pinia |
| [`admin-frontend/`](admin-frontend/README.md) | Back-office (SPA) | Quasar 2, Vue 3, TypeScript, Pinia |
| [`shared/`](shared/README.md) | API types generated from the OpenAPI schema, HTTP client, UI kit, utilities | TypeScript, pnpm workspace |
| [`e2e/`](e2e/README.md) | Storefront and admin journeys against the real stack | Playwright |
| `infra/`, `docker-compose*.yml` | Caddy reverse proxy, compose layers (dev, prod, images, frontend-only) | Docker Compose |
| [`docs/`](docs/) | [`DEVELOPMENT.md`](docs/DEVELOPMENT.md): day-to-day work · [`DEPLOYMENT.md`](docs/DEPLOYMENT.md): variables, first deployment, runbook · [`GUIDE_INTERFACE.md`](docs/GUIDE_INTERFACE.md): interface rules | |

Each folder's README explains how to run **that part alone**.
[`CONTRIBUTING.md`](CONTRIBUTING.md) walks through the three setups: API only
(no Node), a frontend only (no Python, the API runs from a published image),
or everything.

## Key features

- **Supplier catalogue synchronisation**: Ingram Micro pricing, availability and
  metadata pulled by ARQ tasks, with rate limiting, jittered retries honouring
  `Retry-After`, and a grace period before a vanished SKU is deactivated.
- **Product enrichment** from the [Icecat](https://icecat.us/) open catalogue:
  specifications, descriptions, images, standardised attributes.
- **Dynamic pricing**: sale price computed at runtime from cost, customs rate,
  margin and tax; FX rates fetched and cached for multi-currency suppliers.
- **Payments**: PayZen / Lyra cards (optional deferred capture) plus cheque,
  bank transfer and purchase order validated in the back office; full and
  partial refunds.
- **Invoicing**: gap-free legal numbering, PDF rendered from a frozen snapshot,
  credit notes on their own sequence; an issued invoice is never edited.
- **Server-authoritative checkout**: prices re-validated against the catalogue,
  fees read from the payment method, supplier stock re-checked before the
  reservation.
- **Full-text search** with a PostgreSQL GIN index across name, description,
  manufacturer and part number.

## Quick start (everything in Docker)

Prerequisites: Docker with Compose. For development on the host you will also
want Node 22+ with pnpm 10+ (frontends) and Python 3.12+ with
[uv](https://docs.astral.sh/uv/) (backend).

```bash
cp .env.example .env                                # backend / stack config
cp frontend/.env.example frontend/.env              # storefront (VITE_API_URL)
cp admin-frontend/.env.example admin-frontend/.env  # admin (VITE_API_URL)

docker compose up -d           # postgres, redis, clamav, api, workers, frontends
docker compose run --rm migrate  # alembic upgrade head + initial data
```

| Service | URL |
|---|---|
| API and OpenAPI docs | http://localhost:8000/docs |
| Storefront | http://localhost:3000 |
| Admin | http://localhost:3001 (log in with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`) |

`make help` lists the shortcuts (`make dev`, `make dev-front`, `make lint`,
`make test`, `make e2e`, `make seed-demo`…). Running the apps outside Docker,
the compose layers and the main environment variables are described in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md); the exhaustive variable
reference, first deployment and operations in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

> ⚠️ `SECRET_KEY`, `POSTGRES_PASSWORD`, `FIRST_SUPERUSER` and
> `FIRST_SUPERUSER_PASSWORD` ship with placeholder values for local work
> only. Outside `ENVIRONMENT=local` the backend **refuses to start** until
> they are set.

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
products (fixed price, warehouse stock) and, if you charge shipping, a
delivery mode under **Logistique → Modes de livraison** (flat fee, free above
an amount, in-store pickup). A classic shop gets its main warehouse at the
first start; without any delivery mode, delivery is free. Cheque and bank transfer work out
of the box; card payments need a PayZen account.

## Contributing and security

- [`CONTRIBUTING.md`](CONTRIBUTING.md): setups per area, checks CI runs,
  conventions, releases, and why this is one repository.
- [`SECURITY.md`](SECURITY.md): how to report a vulnerability privately.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- [`CHANGELOG.md`](CHANGELOG.md): releases are git tags `vX.Y.Z`.

## License

This project is licensed under the **GNU Affero General Public License v3.0 or later**
(`AGPL-3.0-or-later`), see [LICENSE](LICENSE). Copyright (C) 2026 Natimai Solutions.

> ⚠️ **Network use (AGPL §13):** if you run a modified version of this software
> as a network service, you must make its complete corresponding source code
> available to the users of that service.
