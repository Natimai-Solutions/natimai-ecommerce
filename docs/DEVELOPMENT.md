# Development guide

This guide covers the **Docker-based development workflow**. `docker-compose.override.yml`
is applied automatically on top of `docker-compose.yml` when you run `docker compose up`,
enabling hot reload, source-mounted volumes and verbose logging.

> 🐍 **Prefer running the apps on your host** (native debuggers, faster reload)?
> See [Run the apps outside Docker](#run-the-apps-outside-docker) below.
> Working on **one part only** (API without Node, a frontend without Python)?
> See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
>
> 🚀 **Deployment & environment variables**: see [`DEPLOYMENT.md`](DEPLOYMENT.md)
> for the full list of environment variables and the first-deployment steps.

## Development features

### Hot reload
- **FastAPI auto-reload**: code changes are picked up automatically.
- **Volume mounts**: the source tree is mounted live into the container.
- **No rebuild needed**: edit and run, no container rebuild.

### Enhanced logging
- **DEBUG level**: more detailed logs for development.
- **PostgreSQL query logging**: all SQL statements are logged.
- **More tolerant healthchecks**: longer timeouts for debugging.

### Alembic migrations
- **Dedicated Alembic service**: a container configured for migrations.
- **Helper scripts**: PowerShell and Bash wrappers for common operations.
- **File generation**: migration files are written directly to your local filesystem.

## Usage

### Start the services

```bash
# Start all base services (API, worker, poller, db, redis…)
docker compose up -d

# Or start only selected services
docker compose up -d postgres redis api
```

### Apply migrations + seed initial data

The one-shot `migrate` service runs `alembic upgrade head` **and then** seeds the
reference data (`app/initial_data.py` — payment statuses, price groups, tax rates,
FX rates, the import corridor, RBAC groups, shipping statuses…):

```bash
docker compose run --rm migrate
```

Run this on first start and after pulling new migrations.

### Migrations via the helper scripts

#### PowerShell (Windows)
```powershell
.\scripts\alembic-dev.ps1 revision "Add new feature"   # generate a migration
.\scripts\alembic-dev.ps1 upgrade                       # apply migrations
.\scripts\alembic-dev.ps1 history                       # show history
.\scripts\alembic-dev.ps1 current                       # show current revision
```

#### Bash (Linux/Mac)
```bash
./scripts/alembic-dev.sh revision "Add new feature"   # generate a migration
./scripts/alembic-dev.sh upgrade                       # apply migrations
./scripts/alembic-dev.sh history                       # show history
```

### Manual migrations

Run Alembic directly inside the running `api` container (which is what the helper
scripts above wrap):

```bash
docker compose up -d api
docker compose exec api alembic revision --autogenerate -m "Migration description"
docker compose exec api alembic upgrade head
docker compose exec api alembic history
```

### Useful commands

```bash
docker compose logs -f api                         # live logs
docker compose restart api                         # restart a service after changes
docker compose exec api bash                       # shell into the API container
docker compose exec api pytest                     # run the tests
docker compose exec postgres psql -U postgres -d fastapi_ecommerce  # DB shell
```

## Volume layout

```
./backend/app            → /app/app            (source — hot reload)
./backend/alembic.ini    → /app/alembic.ini    (Alembic config)
./backend/pyproject.toml → /app/pyproject.toml (dependencies)
```

## Service configuration

### API (FastAPI)
- **Port**: 8000
- **Mode**: development with reload
- **Logs**: DEBUG level

### Database (PostgreSQL)
- **Port**: 5432 (exposed for external connections)
- **Logs**: all SQL queries
- **Data**: persisted in the `postgres_data` volume

### Redis
- **Port**: 6379 (exposed for external connections)
- **Persistence**: enabled (appendonly)
- **Data**: persisted in the `redis_data` volume

### ARQ worker
- **Logs**: DEBUG level
- **Restart**: disabled in development
- **Hot reload**: source mounted

### Outbox poller
- **Interval**: 5 seconds
- **Logs**: DEBUG level
- **Hot reload**: source mounted

## The `migrate` service

A one-shot service (`docker-compose.yml`) that applies migrations and seeds the
initial data, then exits — see [Apply migrations + seed initial data](#apply-migrations--seed-initial-data):

```bash
docker compose run --rm migrate
```

## Development workflow

1. **Start**: `docker compose up -d`
2. **Develop**: edit code → automatic hot reload
3. **Migrations**: `.\scripts\alembic-dev.ps1 revision "Description"`
4. **Tests**: `docker compose exec api pytest`
5. **Debug**: tail logs with `docker compose logs -f`

## Debugging

### Service access
- **API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Useful logs
```bash
docker compose logs -f api        # API logs (hot reload)
docker compose logs -f postgres   # database logs
docker compose logs -f            # all services
```

### Direct connections
```bash
docker compose exec api bash                                         # API container shell
docker compose exec postgres psql -U postgres -d fastapi_ecommerce   # PostgreSQL CLI
docker compose exec redis redis-cli                                  # Redis CLI
```

## Code conventions

- **Module layout**: HTTP routes in `app/api/routes/`; each domain is self-contained
  under `app/features/<domain>/` (`models/`, `crud/`, `services/`); outbox event
  handlers in `app/handlers/`; ARQ tasks in `app/tasks/`; cross-cutting code in
  `app/core/` and `app/outbox/`.
- **SQLModel per entity**: `XBase` (shared fields) → `X` (table) + `XCreate`,
  `XUpdate`, `XPublic`, and a list wrapper `XsPublic` = `{ data, count }`.
- **CRUD**: subclass `CrudBase[Model, Create, Update]` and export a singleton
  `crud_x`. `create_draft` / `update_draft` **flush only**; `create` / `update`
  **commit**. ⚠️ A `commit()` expires every ORM instance (async `expire_on_commit`)
  — reading an attribute afterwards raises `MissingGreenlet`. Capture the values you
  need into plain locals **before** committing (and before a loop that commits).
- **Providers (plugin pattern)**: an abstract base in `<feature>/providers/base.py`
  plus a registry / `get_provider(code)` in `providers/__init__.py`, keyed by a
  `code` string (payment providers, notification providers).
- **Routes stay thin**: delegate to CRUD/services; use the shared dependencies
  `SessionDep`, `RedisDep`, `CurrentUser`, `CurrentSuperUser`.

## Error handling

- Raise `AppError(code=..., status_code=..., message=..., details=...)` (from
  `app.core.errors`). A global handler renders a consistent JSON body
  `{"error": {"code", "message", "details"}}`.
- Codes are namespaced `domain.reason` (e.g. `payment.not_found`, `otp.invalid_code`,
  `signup.email_exists`).
- Map external/library exceptions to `AppError` at the route or service boundary so
  the client always gets the standard shape.

## Notification providers

Transactional emails (and Slack) go through a provider abstraction
(`app/features/notification/providers/`), selected by
`PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` (`mailgun` | `noop`); Mailgun config lives in
`MAILGUN_*` (see [`DEPLOYMENT.md`](DEPLOYMENT.md) §3.3). `noop` sends nothing (dev/test)
— switching provider is an env-var change, no code change. To add a provider,
implement `NotificationProvider.send()` and register it in `providers/__init__.py`.

### Email templates

Transactional email bodies live in `app/templates/email/<lang>/` (default language
`fr`), one template per event with three parts: `<name>.subject.txt`, `<name>.txt`
(plain text) and `<name>.html`. Render them with
`render_email(name, *, lang="fr", **context)` from
`app.features.notification.email_renderer`, which returns a `RenderedEmail(subject,
text, html)`. HTML parts are **auto-escaped** (`{{ value }}` is XSS-safe); text and
subject parts are not. Keep presentation logic (conditionals, labels) inside the
templates so it stays translatable. **Add a language**: copy the `fr/` folder to
`<lang>/` and translate; a missing template/part falls back to the default language.

## Important notes

1. **Hot reload** works only for Python files under `/app`.
2. **Permissions**: volumes are mounted read-only except for Alembic.
3. **Performance**: development mode is not optimized for production.
4. **Data**: volumes persist across restarts.
5. **Migration files** are generated directly on your local filesystem.

## Run the apps outside Docker

Run only the infrastructure in Docker and the apps on your host:

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
uv run arq app.core.arq_worker.WorkerSettings                              # ARQ worker
uv run python app/scripts/outbox_poller.py --mode continuous --interval 5  # outbox poller

# 4. Frontends (from the repo root)
pnpm install
pnpm dev:front    # storefront — Quasar dev server, http://localhost:9000
pnpm dev:admin    # admin      — next free port, http://localhost:9001 when the storefront runs
```

When running outside Docker, point the backend at the host-mapped services
(`POSTGRES_SERVER=localhost`, `REDIS_SERVER=localhost`); see
[`DEPLOYMENT.md`](DEPLOYMENT.md). To regenerate the frontends' API types after
a backend change: `pnpm gen:types` (no server needed).

## Docker Compose files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Base stack: PostgreSQL, Redis, ClamAV, API, ARQ worker, outbox poller, migrate, frontends. |
| `docker-compose.override.yml` | **Auto-applied in development** by `docker compose up` (no `-f`). `--reload`, source mounted for hot reload, dev dependencies, DEBUG logging, tolerant healthchecks. |
| `docker-compose.frontend-dev.yml` | **Frontend work without Python**: the Python services run from the GHCR image published from `main`, ClamAV is off. `make dev-front`. |
| `docker-compose.prod.yml` | Production overrides: `ENVIRONMENT=production`, no reload, restart policies, isolated DB network, resource limits, health checker. |
| `docker-compose.proxy.yml` | Caddy reverse proxy: Let's Encrypt TLS and subdomain routing (bare domain → storefront, `api.` → API, `admin.` → admin). |
| `docker-compose.images.yml` | Production from the images built by the Deploy workflow instead of building on the server. |
| `docker-compose.health.yml` | Dedicated outbox health checker. |

```bash
# Development (base + override, automatic)
docker compose up -d

# Frontend only (API from the published image)
docker compose -f docker-compose.yml -f docker-compose.frontend-dev.yml up -d --wait --no-build postgres redis api

# Production (compose files are layered explicitly; scripts/release/deploy.sh does this)
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml -f docker-compose.images.yml up -d
```

## Environment variables

The backend reads the repository-root `.env` (see [`.env.example`](../.env.example));
the two frontends read a build-time `VITE_API_URL` from their own `.env`. In
Docker, PostgreSQL and Redis are wired by the compose files; outside Docker you
set their connection details yourself.

The most important variables; [`DEPLOYMENT.md`](DEPLOYMENT.md) has the
**complete** list:

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (`openssl rand -base64 32`) |
| `ENVIRONMENT` | `local` \| `staging` \| `production` (controls cookie `Secure`, the safety guards, etc.) |
| `TERRITORY_PROFILE` / `SHOP_MODE` | `FR` or `PF`; `simple` hides suppliers, customs, exchange rates and multi-leg logistics |
| `DOMAIN` | Root domain (used by the Caddy proxy for subdomain routing) |
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins, JSON array |
| `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` | **Required**: bootstrap admin account |
| `POSTGRES_SERVER` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database connection (set in compose for Docker) |
| `REDIS_*` | Redis / ARQ broker connection |
| `CLAMAV_ENABLED` / `CLAMAV_HOST` / `CLAMAV_PORT` | Antivirus for uploads; `false` is only accepted in `local` |
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

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs on every
pull request (only the jobs whose files changed) and on every push to `main`
(everything):

- **backend**: `ruff` (lint + format), `mypy`, a single Alembic head, `pytest`
  **under coverage** against a throwaway PostgreSQL service. Coverage config
  lives in [`backend/pyproject.toml`](../backend/pyproject.toml); `fail_under`
  gates the build.
- **api-types**: the committed `shared/api-types/src/schema.ts` is regenerated
  from the application and compared.
- **frontend**: `lint` + `typecheck` for both apps, unit tests of the shared
  engine (`@app/utils`) via **vitest**, under coverage.
- **e2e**: the storefront and admin Playwright journeys against the compose stack.

```bash
# Backend (from backend/) — integration tests need a reachable test DB (TEST_DATABASE_URL)
uv run coverage run -m pytest && uv run coverage report

# Frontend — shared engine (from the repo root)
pnpm test:coverage
```
