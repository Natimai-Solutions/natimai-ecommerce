# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are git tags
`vMAJOR.MINOR.PATCH` with a matching GitHub release. The **Deploy** workflow
takes a tag as its `ref`.

## [Unreleased]

### Added

- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull
  request templates, `CODEOWNERS`: the repository is ready to be worked on one
  part at a time.
- The API image is published on every push to `main`
  (`ghcr.io/natimai-solutions/natimai-ecommerce/api:main`,
  `.github/workflows/publish-api-image.yml`).
- `docker-compose.frontend-dev.yml` and `make dev-front`: work on the
  storefront or the admin without installing Python; the API runs from the
  published image, ClamAV stays off.
- `shared/README.md`; `backend/README.md` now explains how to run the API alone.

### Changed

- CI runs only the jobs whose files a pull request touches (`dorny/paths-filter`);
  everything still runs on `main`.
- `DEVELOPMENT.md` and `DEPLOYMENT.md` moved to `docs/`; the internal work plan
  moved to `docs/internal/`. The root `README.md` is now a map of the repository.
- Root `package.json` is named `natimai-ecommerce` and carries the repository
  metadata.

### Fixed

- The Security workflow, red on `main` since its creation: `trivy-action`
  pinned to an existing tag (`v0.36.0`), gitleaks run from its released binary
  (the GitHub action requires a paid licence for organisations), and two
  `pnpm audit` advisories closed with `pnpm.overrides` (`proxy-addr`,
  `source-map-js`). The three images now pass Trivy: Debian and Alpine
  security updates applied at build time, pip removed from the API image,
  npm and corepack removed from the storefront image.

## [0.0.1] - 2026-07-07

First tagged state of the platform: FastAPI API with ARQ workers and
transactional outbox, Quasar storefront (SSR) and back-office, supplier
synchronisation (Ingram Micro), Icecat enrichment, dynamic pricing with customs
and FX, PayZen and manual payments, legal invoicing, Docker Compose deployment
behind Caddy.

[Unreleased]: https://github.com/Natimai-Solutions/natimai-ecommerce/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/Natimai-Solutions/natimai-ecommerce/releases/tag/v0.0.1
