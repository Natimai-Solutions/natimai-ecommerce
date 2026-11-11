# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are git tags
`vMAJOR.MINOR.PATCH` with a matching GitHub release. The **Deploy** workflow
takes a tag as its `ref`.

## [Unreleased]

### Added

- `docs/internal/AUDIT_2026-11.md`: security, functional and UI/UX audit of
  the stack before opening (findings verified against the code, with file,
  scenario and fix). The pre-opening fixes it calls for are tracked in
  `docs/internal/PLAN_DE_TRAVAIL.md`.

- `docs/GUIDE_INTERFACE.md`: the interface rules shared by the storefront and
  the admin, on the model of natimai-paie, and the design skill they override
  (`design-taste-frontend`, frozen copy under `.claude/skills/`, recorded in
  `skills-lock.json`; `.gitignore` now keeps `.claude/skills/`).
- Admin home → « Mise en route »: a start-up checklist computed from the data
  (`GET /admin/setup-checklist`): seller legal identity, shop e-mail for
  alerts, an active payment method, an online catalogue, products hidden for
  a missing customs rate or weight, and two zeros to confirm (transport
  insurance rate, clearance places without a fee per declaration). Each line
  links to the screen that settles it; the section disappears once every
  point is done. The settings screen opens a category from `?category=`.
- Integrity chain of the accounting documents: each invoice and credit note
  stores the SHA-256 of the previous document of its series and fiscal year
  and of its own frozen content (`previous_hash`, `chain_hash`, migration
  `f6a7b8c9d0e1`). `GET /admin/invoices/integrity` recomputes every chain and
  names the documents changed, deleted or inserted after issuance; Admin →
  Factures → « Vérifier l'intégrité » shows the result. Documents issued
  before the chain are sealed, in number order, by the next issuance of their
  series and year.
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

- Front: a Vitest design guard (`shared/ui/src/design-guard.test.ts`) over
  both apps and `shared/ui` refuses Material colours, `bg-white`, colours picked
  from `$q.dark`, hard-coded colours and `!important` outside the token files,
  and breakpoints off Quasar's scale. Status screens return a `StatusTag` tone
  (`orderStatusTone`, `quoteStatusTone`…) instead of a Material colour
  translated by `toneOf`, which is gone; 20 of the 28 `!important` are removed
  (more specific selectors, or the `--q-*` variable Quasar reads), the 8 left
  are justified in `tokens.scss`. New tokens: `--n-paper` (QR code background,
  white in both themes), `--n-shadow-up`.
- Front: one source for the Quasar Sass variables and the theme preference
  (`shared/ui`); each app keeps its own storage (cookie for the SSR
  storefront, localStorage for the admin). Radius and spacing tokens
  (`--n-radius*`, `--n-space-*`, Quasar's spacing scale) replace 83 hard-coded
  radii, pixel-identical.
- Front: breakpoints on Quasar's scale only (600 / 1024 / 1440 px). Phone
  tweaks moved from 767 to 599 px, so a portrait tablet (600–767 px) gets the
  wider layout (3-column product grid, side-by-side banners); the product grid
  and product page switch to 3 columns / the narrower buy column under
  1440 px instead of 1280; the storefront footer stays stacked up to 1023 px;
  the admin product form stacks under 1024 px. The admin order detail and
  settings navigation follow the width left by the side menu (container
  queries) instead of a screen width.
- Admin: the 20 form fields that had no label (placeholder only, or nothing
  in a table cell) now have one for screen readers: the four list searches,
  and the table inputs of margins, reception, deposits, price groups, product
  origin, quote lines and category pairs (column label and row, e.g.
  « Acompte (%) — Professionnels »). The SKU allowlist gets a visible label.
- Admin: the « modifications non enregistrées » guard now covers the form
  dialogs of Codes promo, Cartes cadeaux, Transporteurs, Taux de TVA, Douanes,
  Utilisateurs, Fournisseurs (supplier form, SKU allowlist), Trajets et lieux
  (place, route), Modes de livraison (delivery mode, new pickup place) and
  Départs groupés (departure, purchase order, reminder). Escape, a backdrop
  click, Cancel or leaving the screen asks before dropping typed edits.
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

### Removed

- Generic CRUD routes no frontend calls: analytics (products, sales, users),
  partners, stock movements (`/inventory/stock-movements`) and user
  notifications (`/notification/users/…`). Their models and tables stay: stock
  movements are still written by checkout and the admin inventory screen,
  and account deletion still purges notifications. `group_security` stays
  (superuser-only), as the base of the future fine-grained roles.

### Fixed

- Security (audit 2026-11, S1): outside `ENVIRONMENT=local` the API refuses
  to start when `SECRET_KEY`, `POSTGRES_PASSWORD` or
  `FIRST_SUPERUSER_PASSWORD` still holds a `changeme-…` placeholder of
  `.env.example` (only `changethis` was rejected).
- Security (S4): the refresh token carries the user's security stamp and
  `POST /login/refresh-token` refuses it once the stamp changed; disabling or
  resetting the 2FA also revokes the stored sessions. A stolen session no
  longer survives 30 days. Users signed in before this release sign in again.
- Security (S7): `GET /cart/me/checkout-quote` counts the refused promo codes
  per customer (10 per 10 minutes); past that the code is not looked up and
  the quote says to retry later, so it no longer serves as an oracle to guess
  codes. A customer re-pricing a valid code is never throttled.
- Money (audit 2026-11, S3): a gift card is always sold at its reference
  price — no promo code, group price or promotion applies to it (a card
  bought 20 % off was still issued at face value, i.e. free store credit).
- Money (S6): a full refund cancels the order's unused gift cards and takes
  back the store credit of the redeemed ones, within the holder's balance;
  what was already spent, and the cards of a partially refunded order, are
  reported to the admin (log + `ALERT_WEBHOOK_URL`).
- Stock (audit 2026-11, B1): every move of an order to « Cancelled » (the
  admin's included, not only the customer's) releases its pending stock
  reservations and gives the promo-code use back, once
  (`release_cancelled_order_holds`, called by `set_order_status`).
- Stock (B2): a new payment attempt on an order whose reservations were
  released (refused card, reservation sweep) takes the same quantities again
  under the stock locks, or is refused with `payment.order.out_of_stock`
  (409). Paid later, such an order used to be sold with no stock behind it.
  The sweep now also covers « PaymentFailed » orders.
- Payments (B3): with `PAYZEN_MANUAL_VALIDATION`, the `AUTHORISED`
  notification publishes `payment.authorized`; the order moves to « Paid »
  (« DepositPaid ») so the sweep keeps its stock and it reaches the step that
  captures it. Stock confirmation, invoice and gift cards still wait for the
  capture.
- Stock (B5): a released reservation is credited back to `supplier_quantity`
  for every product the checkout took it from, manual products with a
  `supplier_name` included (they lost it for good).
- Orders (B6): a settled payment moves an order to « Paid » only from a
  status before payment; the capture at « InTransit » no longer sends it back.
- Stock (B7): the reservation sweep filters and orders its batch in SQL, so
  orders it must skip no longer fill every batch.
- Payments (audit 2026-11, S9): `POST /payments/initiate` refuses
  (`payment.method.fee_mismatch`, 409) a method other than the checkout's
  whose fee differs from the one billed on the order — quoting with a free
  method and paying with a charged one skipped its fee.
- Security (audit 2026-11, S5): with `ADMIN_2FA_REQUIRED`, a superuser who
  has not enrolled is refused (`auth.totp.enrollment_required`) by
  `get_current_user` itself, on every route — the routes checking
  `is_superuser` by hand and `BaseRouter` granted admin powers, and the
  internal fields were revealed before the check. `GET /users/me` and the
  enrolment endpoints use the new `CurrentUserEnrolling`.
- Security (audit 2026-11, S2): new `ADMIN_FRONTEND_HOST`. A superuser's
  refresh token is only exchanged from that origin
  (`login.refresh_token.admin_origin`, 403, nothing revoked): the storefront
  and the admin share the API and its cookie, so an XSS on the storefront
  could mint an admin access token. **Set it in production** (warned when
  missing outside `local`).
- Stock (audit 2026-11, B4): the live supplier check at checkout, the
  inventory sync and the catalogue sync no longer write the supplier's raw
  count into `supplier_quantity`: they subtract the units our open orders
  took (pending reservations, and paid orders not yet ordered from the
  supplier). At checkout the live answer is settled again under the stock
  locks, so a concurrent reservation is counted.
- Security (audit 2026-11, S11): the login lockout is per (account,
  address): five wrong passwords lock that address out of the account for
  15 minutes, the owner still signs in from elsewhere — anyone could lock
  any account, an administrator's included, indefinitely. A new
  `LOGIN_ACCOUNT_LOCKOUT_MAX_FAILURES` (50 consecutive failures, any
  address) locks the account itself against a distributed brute force; a
  password reset lifts it.
- Storefront (U1): the mobile menu button announced `$t('layout.menu')`
  literally to screen readers; the design guard now rejects a static
  attribute containing `$t(`.
- Admin → Paiements: the status tag was always grey (a payment status name
  was read as a colour); settled payments, payments to capture or validate
  and failed payments now show their tone.
- Admin: four borders and backgrounds used tokens that do not exist
  (`--n-border`, `--n-surface-2`) and fell back to a fixed grey, or drew no
  border at all (content language tabs, product link kind): they use
  `--n-line` and `--n-tile`.
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
