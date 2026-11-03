# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are git tags
`vMAJOR.MINOR.PATCH` with a matching GitHub release. The **Deploy** workflow
takes a tag as its `ref`.

## [Unreleased]

### Added

- Admin → Logistique → **Modes de livraison**: a screen always shown, simple
  mode included (it does not depend on the "Trajets et lieux" module), where a
  shop sets what the customer picks at checkout and its price. A delivery mode
  is a translated mode (in-store pickup, home delivery, air freight, sea
  freight, or a custom code), a flat price, a free-shipping threshold and a
  coverage (everywhere or some zones); weight pricing, the internal name,
  origin and destination stay under folded sections. Origin defaults to the
  main warehouse and the destination is inferred. Each mode can be switched
  off without deleting it. A pickup place can be created from the dialog, and
  pickup at the main warehouse itself is accepted.
- "Trajets et lieux" uses the same dialog for delivery modes; its route
  dialog now only covers logistics legs (service level stays there).
- A classic shop (`SEED_FRENCH_POLYNESIA_LOGISTICS=false`) gets a main
  warehouse at start-up when none is flagged: a lone existing warehouse is
  flagged, none creates "Entrepôt principal" under the shop country, several
  leave the choice to the admin. The delivery modes screen also offers to
  create it.
- Several pickup points for one pickup mode: each pickup route (transport
  mode `pickup`) is its own offer at checkout, one per pickup place, and the
  customer picks theirs. The last-leg options list one entry per point,
  `GET /cart/me/checkout-quote` and `POST /cart/checkout` take the chosen
  `pickup_place_id` (omitted: the mode's best point, as before). Other modes
  keep one offer per mode. In the admin, creating a pickup mode accepts
  several places (one route per place); a place already offered for that
  mode cannot be picked again.
- Pickup modes take a pickup place; its postal address (new fields on physical
  places) is returned by the last-leg options endpoint (`pickup_place`) and
  shown to the customer at checkout under the delivery choice.
- Storefront: delivery modes without a customer label are shown with a
  translated label instead of their technical code.

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
- The back-office always reads back the tax settings and payment-provider
  switches it just saved: with several API workers, the one answering a page
  reload could still serve its settings snapshot for up to three seconds
  (the end-to-end suite caught it as a flaky test). Admin reads now bypass the
  snapshot; the storefront and checkout keep it.

## [0.0.1] - 2026-07-07

First tagged state of the platform: FastAPI API with ARQ workers and
transactional outbox, Quasar storefront (SSR) and back-office, supplier
synchronisation (Ingram Micro), Icecat enrichment, dynamic pricing with customs
and FX, PayZen and manual payments, legal invoicing, Docker Compose deployment
behind Caddy.

[Unreleased]: https://github.com/Natimai-Solutions/natimai-ecommerce/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/Natimai-Solutions/natimai-ecommerce/releases/tag/v0.0.1
