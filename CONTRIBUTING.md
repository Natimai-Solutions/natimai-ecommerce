# Contributing

Thanks for your interest. This repository holds the whole platform (API,
storefront, back-office, shared packages) **on purpose**: a backend route and
the admin screen that uses it ship in one pull request, the end-to-end suite
tests the real stack, and a deployment is one commit. But you do not have to
install or understand everything to contribute to one part. This page tells
you how to work on **just the piece you care about**.

## Map of the repository

| Path | What it is | Works on its own? |
|---|---|---|
| [`backend/`](backend/README.md) | FastAPI API, ARQ workers, Alembic migrations (Python, `uv`) | Yes: `uv sync` + Postgres/Redis, or its own `Dockerfile` |
| [`frontend/`](frontend/README.md) | Public storefront, Quasar 2 / Vue 3, server-side rendered | Needs `shared/*` and a running API (an image is enough) |
| [`admin-frontend/`](admin-frontend/README.md) | Back-office, Quasar 2 / Vue 3 SPA | Same as the storefront |
| [`shared/`](shared/README.md) | `@app/api-types` (generated from the API's OpenAPI schema), `@app/api-client`, `@app/ui`, `@app/utils` | Consumed by both frontends through the pnpm workspace |
| [`e2e/`](e2e/README.md) | Playwright journeys against the full stack | Needs the stack (`make dev`) |
| `infra/`, `docker-compose*.yml`, `scripts/` | Caddy, compose layers, release and backup scripts | — |
| [`docs/`](docs/) | [`DEVELOPMENT.md`](docs/DEVELOPMENT.md) (day-to-day), [`DEPLOYMENT.md`](docs/DEPLOYMENT.md) (operations) | — |

## Pick your setup

All commands run from the repository root. `make help` lists every target.

### I only want to work on the API

You need Python 3.12+ with [`uv`](https://docs.astral.sh/uv/) and Docker for
Postgres and Redis. No Node, no pnpm.

```bash
cp .env.example .env                   # defaults are fine locally
docker compose up -d --wait postgres redis
cd backend
uv sync
uv run alembic upgrade head && uv run python app/initial_data.py
uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
uv run pytest                          # TEST_DATABASE_URL for the integration tests
```

Details, conventions and the worker/poller commands: [`backend/README.md`](backend/README.md)
and [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

If you change a route or a schema, the frontends' types must follow:
run `pnpm gen:types` (needs `pnpm install` once) and commit
`shared/api-types/src/schema.ts`. CI fails otherwise. If you cannot install
Node, say so in the PR and a maintainer will regenerate it.

### I only want to work on the storefront or the admin

You need Node 22+ with pnpm 10+ and Docker. **No Python**: the API runs from
the image published from `main` on every push
(`ghcr.io/natimai-solutions/natimai-ecommerce/api:main`).

```bash
cp .env.example .env
pnpm install
make dev-front        # postgres, redis, api (GHCR image), migrations, workers
pnpm dev:front        # storefront  → http://localhost:9000
pnpm dev:admin        # admin       → http://localhost:9001 (next free port after the storefront)
```

Log into the admin with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` from
your `.env`. `make seed-demo` fills a demo catalogue. `make stop` tears the
stack down.

`make dev-front` layers [`docker-compose.frontend-dev.yml`](docker-compose.frontend-dev.yml)
on the base compose file: ClamAV is off, and the API image is pulled instead of
built. If the GHCR package is private, `docker login ghcr.io` first with a
token that has `read:packages`. If your branch also changes the API, use the
full stack (`make dev`) while you do.

### I want everything

```bash
make setup   # uv sync + pnpm install
make dev     # full stack in Docker (hot reload for the API)
make migrate
```

See [`README.md`](README.md) and [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Before you push

| Check | Command | CI job |
|---|---|---|
| Lint | `make lint` (ruff, eslint) | backend, frontend |
| Types | `make typecheck` (mypy strict, vue-tsc) | backend, frontend |
| Unit / integration tests | `make test` | backend, frontend |
| API types in sync | `make check-types` | api-types |
| End-to-end | `make e2e` (stack running) | e2e |

`uvx pre-commit install` runs the formatters and gitleaks on each commit with
the repository's own tools ([`.pre-commit-config.yaml`](.pre-commit-config.yaml)).

CI only runs the jobs whose files your pull request touches: a storefront-only
PR skips pytest and the end-to-end suite. Skipped jobs count as passed. On
`main` everything always runs.

## Conventions that CI enforces

- **One Alembic head.** Two branches that each add a migration produce two
  heads and the deployment refuses to run. Rebase and merge the revisions.
- **Generated API types are committed**, never edited by hand
  (`shared/api-types/src/schema.ts`).
- **Lockfiles are frozen**: `uv sync --locked`, `pnpm install --frozen-lockfile`.
  Update them with the tool, commit the result.
- **Every user-facing string goes through i18n**, in both `fr.ts` and `en.ts`.
- **Elements used by end-to-end tests carry a `data-testid`**; labels may
  change, identifiers do not.
- **Secrets never land in the repository**: `.env` is ignored, `.env.example`
  documents every variable, gitleaks runs in CI.

Backend conventions (module layout, CRUD, error shape) are in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md); interface rules shared by both apps
(colours, theme, breakpoints, formats, the design skill and what overrides it)
are in [`docs/GUIDE_INTERFACE.md`](docs/GUIDE_INTERFACE.md); the admin screen
charter is in its README.

## Pull requests

- Branch from `main`, keep one topic per PR, and describe **what and why** in
  the description (the template asks the right questions).
- Commit messages and code comments are in French or English; both are fine.
  Say what the change does and why, not how.
- A PR that changes behaviour, configuration or an operational step updates
  the matching documentation in the same PR (`.env.example`, `docs/`, the
  app's README).
- A maintainer reviews every PR; [`.github/CODEOWNERS`](.github/CODEOWNERS)
  is where additional reviewers per folder are declared.

## Issues

Use the templates: bug report, feature request. Security problems go through
private reporting, never a public issue: [`SECURITY.md`](SECURITY.md).

## Releases

- Versions are git tags `vMAJOR.MINOR.PATCH` with a matching GitHub release
  and an entry in [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog).
- The **Deploy** workflow takes a tag as its `ref`; deployments should target
  tags, not arbitrary commits (`docs/DEPLOYMENT.md`).
- The API image on GHCR is tagged `main` and `sha-<commit>` by
  `publish-api-image.yml`; deployment images are tagged `<env>-<sha>`.

## Why one repository, and when that could change

Keeping everything together is what lets a single maintainer ship a feature
that spans the API and a frontend in one reviewed, tested, deployable change.
The seams are already clean: `backend/` is self-contained, the frontends
depend on the API only through the generated `@app/api-types`.

Splitting would make sense if one of these happens:

- someone builds an alternative frontend against the API and needs the API
  contract as a published, versioned package (`@natimai/api-types` on npm);
- a part of the project gains its own contributors and release cadence.

Nothing is lost by waiting: `git filter-repo` or `git subtree split` extracts
a folder with its full history. Until then, the folder READMEs and the
per-area CI are what make the pieces independent.

## License

By contributing you agree that your contributions are licensed under the
[GNU AGPL v3.0 or later](LICENSE), like the rest of the project.
