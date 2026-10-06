# API (backend)

FastAPI application, ARQ background workers and the outbox poller, with
Alembic migrations. Python 3.12+ managed by [`uv`](https://docs.astral.sh/uv/),
PostgreSQL 16, Redis 7. This folder is self-contained: its `pyproject.toml`,
`uv.lock` and `Dockerfile` are all the API needs. The frontends only depend on
it through the OpenAPI schema (`shared/api-types`, see below).

## Run it alone (no Node required)

From the repository root, Postgres and Redis in Docker, the API on your host:

```bash
cp .env.example .env                              # read as ../.env from here
docker compose up -d --wait postgres redis
cd backend
uv sync
uv run alembic upgrade head
uv run python app/initial_data.py                 # reference data + superuser
uv run uvicorn app.main:app --reload              # http://localhost:8000/docs

# optional, in other terminals
uv run arq app.core.arq_worker.WorkerSettings                               # ARQ worker
uv run python app/scripts/outbox_poller.py --mode continuous --interval 5   # outbox poller
```

Point the settings at the host-mapped services (`POSTGRES_SERVER=localhost`,
`REDIS_SERVER=localhost`). `CLAMAV_ENABLED=false` is accepted while
`ENVIRONMENT=local`; outside `local` the application refuses to start without
the antivirus.

Or everything in Docker with hot reload: `docker compose up -d api`
(`docker-compose.override.yml` mounts `app/` and installs the dev group).

### Docker image

`Dockerfile` builds a non-root image whose entrypoint takes a command:
`api`, `worker`, `poller`, `migrate`, `shell`, `test`, or `run <cmd>`.
The image is published on every push to `main` as
`ghcr.io/natimai-solutions/natimai-ecommerce/api:main` (and `sha-<commit>`),
so frontend contributors can run the API without Python
(`make dev-front`, see [`CONTRIBUTING.md`](../CONTRIBUTING.md)).

## Checks

```bash
uv run ruff check app && uv run ruff format --check app
uv run mypy app
uv run pytest                     # integration tests need TEST_DATABASE_URL, else skipped
uv run coverage run -m pytest && uv run coverage report
uv run alembic heads              # must print exactly one head
```

From the root, `make lint typecheck test-backend` runs the same.

## When you change the API contract

Routes and schemas are the contract with the frontends. After any change to a
route, a model or a response schema, from the repository root:

```bash
pnpm install   # once
pnpm gen:types # regenerates shared/api-types/src/schema.ts from app.openapi()
```

and commit the result. CI (`api-types` job) fails if the committed file no
longer matches the application. No server or database is needed: the schema is
produced by importing the app.

## Layout

```
app/
├── api/           # routers and endpoints (thin: delegate to CRUD/services)
├── core/          # settings, db, security, ARQ worker settings
├── features/      # one self-contained domain per folder: models/, crud/, services/
├── handlers/      # outbox event handlers (emails, status syncs…)
├── outbox/        # transactional outbox: poller, loader, health
├── services/      # cross-domain services
├── tasks/         # ARQ tasks (supplier sync, enrichment)
├── templates/     # transactional e-mail templates, per language
├── utils/         # helpers shared across features
├── demo/          # demo catalogue data (loaded by scripts/seed_demo.py)
├── scripts/       # entrypoint.sh, outbox_poller.py…
├── alembic/       # migrations
└── tests/
```

Code conventions (SQLModel per entity, `CrudBase`, `AppError`, providers,
notification templates) are in [`docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md).
Environment variables, first deployment and the operations runbook are in
[`docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).
