# Development guide

This guide covers the **Docker-based development workflow**. `docker-compose.override.yml`
is applied automatically on top of `docker-compose.yml` when you run `docker compose up`,
enabling hot reload, source-mounted volumes and verbose logging.

> 🐍 **Prefer running the apps on your host** (native debuggers, faster reload)?
> See the **"Run the apps outside Docker"** section of [`README.md`](README.md).
>
> 🚀 **Deployment & environment variables**: see [`DEPLOYMENT.md`](DEPLOYMENT.md)
> for the full list of environment variables and the first-deployment steps.

## Working documentation

Internal working documents live in `backend/docs/development/`. Documents that still
have explicit open work:

- [CAHIER_DES_CHARGES_ROUTAGE_MULTI_FOURNISSEURS.md](backend/docs/development/CAHIER_DES_CHARGES_ROUTAGE_MULTI_FOURNISSEURS.md) (status: to implement)
- [PLAN_REFONTE_PAIEMENTS.md](backend/docs/development/PLAN_REFONTE_PAIEMENTS.md) ("Remaining" section, Stripe/PayPal phase unfinished)
- [PLAN_DEPLOIEMENT_PAR_PHASE.md](backend/docs/development/PLAN_DEPLOIEMENT_PAR_PHASE.md) (phased roadmap with deliverables)
- [PLAN_VERIFICATION_FONCTIONNEMENT.md](backend/docs/development/PLAN_VERIFICATION_FONCTIONNEMENT.md) (verification checklist with unchecked items)
- [CHECKLIST_PREPROD_ROLLBACK_E4.md](backend/docs/development/CHECKLIST_PREPROD_ROLLBACK_E4.md) (pre-prod / rollback checklist to complete)
- [TEST_COVERAGE_GAPS.md](backend/docs/development/TEST_COVERAGE_GAPS.md) (remaining test backlog)

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

```bash
# Start the Alembic service
docker compose --profile alembic run --rm alembic bash

# Inside the container:
alembic revision --autogenerate -m "Migration description"
alembic upgrade head
alembic history
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

## Docker Compose profiles

### `alembic` profile
A service configured for Alembic operations:
```bash
docker compose --profile alembic run --rm alembic [command]
```

### `migration` profile
A migration service for deployments:
```bash
docker compose --profile migration run --rm migrate
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

## Important notes

1. **Hot reload** works only for Python files under `/app`.
2. **Permissions**: volumes are mounted read-only except for Alembic.
3. **Performance**: development mode is not optimized for production.
4. **Data**: volumes persist across restarts.
5. **Migration files** are generated directly on your local filesystem.
