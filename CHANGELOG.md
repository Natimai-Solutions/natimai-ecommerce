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
- Admin → Trajets et lieux is split into three views (Trajets, Lieux, Zones de
  livraison) chosen with a segmented control and kept in the URL
  (`?view=zones`). Zones (country, region, island, municipality) are listed
  as a tree and have their own form (parent zone, postcodes); places
  (warehouse, shop, port, airport, supplier, address) keep the address,
  warehouse, customs and dropshipping fields. Place types and service levels
  are shown translated. The places table has five columns (code under the
  name, zone under the city, warehouse / customs / origin / dropshipping as
  tags) and fits without horizontal scrolling from 1024 px. The routes table
  has five columns (transport, service level and lead time under the name;
  free-shipping threshold under the tariff; the delivery mode or "final leg"
  as a tag) and fits from 1024 px too.
- Help panels: "Trajets et lieux" explains zones, places and routes (folded
  once closed, remembered per browser); "Modes de livraison" shows three setup
  examples (in-store pickup, flat fee, price by destination), open while no
  mode exists.
- Help panels on more admin screens, all built on one `HelpPanel` component
  (collapsible, numbered steps or icons, a closed panel stays closed per
  browser): the path of a parcel on Expéditions; the life of a grouped
  departure (open, close, ordered, transit, distributed) on Départs groupés;
  the three supply methods on Fournisseurs; "what the customer pays" (group
  price, promotion, discount code, gift card) shared by the four pricing
  screens; the path of a manual payment shared by Moyens de paiement and
  Validation des paiements. A shared panel marks the step of the current
  screen and folds on all its screens at once. The texts follow the code
  (pricing, checkout discount, shipping and departure services).
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

- A transfer, cash or cheque order (and a purchase order) reaches the shop as
  « Nouvelle commande à traiter » (support e-mail and Slack) with its order
  number and amount, instead of the raw `payment.awaiting_validation` /
  `payment.document_required` event. The admin payment e-mail never showed
  the amount (it read `amount`, the events carry `total_amount`): fixed.
- The PayZen IPN records its events in the shared provider journal
  (`payment_webhook_events`), like PayPal: one row per transaction status
  (`<trans_uuid>:<trans_status>`) with what was done with it (applied,
  duplicate, conflict, amount_mismatch, ignored). A replay of a recorded IPN
  is acknowledged without being looked at again.
- CI runs only the jobs whose files a pull request touches (`dorny/paths-filter`);
  everything still runs on `main`.
- `DEVELOPMENT.md` and `DEPLOYMENT.md` moved to `docs/`; the internal work plan
  moved to `docs/internal/`. The root `README.md` is now a map of the repository.
- Root `package.json` is named `natimai-ecommerce` and carries the repository
  metadata.

### Fixed

- Images: the Alpine / Debian security upgrade layer is rebuilt every day.
  The GitHub Actions layer cache kept serving an old `apk upgrade` layer as
  long as the base image did not change, so the admin image shipped
  libexpat 2.9.0 (CVE-2026-117610, CVE-2026-118370) while 2.10.0 was
  published, and Trivy failed. The three Dockerfiles take a
  `SECURITY_UPDATES_DATE` build argument (the UTC day) that `security.yml`,
  `deploy.yml` and `publish-api-image.yml` pass.
- Grouped departures: a draft or open departure is closed only through the
  assisted close (thresholds, live supplier stock, next recurring departure).
  `PATCH /admin/grouped-departures/{id}` with `status=closed` is refused
  (`grouped_departure.close_required`), the admin "next step" of an open
  departure runs the assisted close, and the edit form no longer offers
  "Clôturé" for it.
- Grouped departures: closing no longer unpublishes the departure, so its
  customers keep following it through `GET /grouped-departures/{id}` until it
  is distributed. The banner and the checkout still only pick open
  departures. Departures closed before this change stay unpublished until an
  admin publishes them again.
- Shipping: "Garder le groupage" on a lot's next leg now groups the next legs
  into a new consolidation on their common route (the finished legs stay in
  the old lot). Next legs on different routes continue individually, and the
  response says so.
- Payments: a purchase-order payment cannot be approved until an active,
  non-infected document is attached (`payment.document_missing`, 409).
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
