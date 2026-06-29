# Development guide

This guide covers the **Docker-based development workflow**. `docker-compose.override.yml`
is applied automatically on top of `docker-compose.yml` when you run `docker compose up`,
enabling hot reload, source-mounted volumes and verbose logging.

> 🐍 **Prefer running the apps on your host** (native debuggers, faster reload)?
> See the **"Run the apps outside Docker"** section of [`README.md`](README.md).
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

## Important notes

1. **Hot reload** works only for Python files under `/app`.
2. **Permissions**: volumes are mounted read-only except for Alembic.
3. **Performance**: development mode is not optimized for production.
4. **Data**: volumes persist across restarts.
5. **Migration files** are generated directly on your local filesystem.
