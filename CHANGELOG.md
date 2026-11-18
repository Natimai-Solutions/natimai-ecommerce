# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are git tags
`vMAJOR.MINOR.PATCH` with a matching GitHub release. The **Deploy** workflow
takes a tag as its `ref`.

## [Unreleased]

### Security

- `pnpm audit` ignores GHSA-fc5q-39xc-vjpf (`picomatch` ≤ 4.0.7, ReDoS) until
  a patched version exists: build tooling only, no fix published. To remove
  then (see the work plan, §9).
- An account linked to Google / Microsoft that also has a chosen password
  needs that password to be erased, a recent sign-in no longer stands for it
  (`users.has_password`, migration `e1f2a3b4c5d6`; unknown for the accounts
  older than the column, which keep the previous rule).

### Added

- Tests: the freight from the product page to the invoice (one freight,
  billed once), two checkouts truly in parallel on one cart (two sessions:
  one order), and `scripts/release/deploy.sh` run for real with fake
  docker/curl (dump before migrating, rollback when the new version does not
  start or is never ready, no migration without a dump).
- A job arq gives up on before running it (expired in the queue, past its
  tries before it could start, unknown function) is journaled as failed and
  alerts, like a job that ran and failed: arq only stored a result read by
  no one, and « État du système » kept the task « ok ». Review of 17/11/2026.
- A departure carries an import mode (`grouped_departures.service_level`,
  optional): an order whose lines share one mode joins the next departure of
  that mode, else one carrying no mode — an order paid by sea went with the
  next air departure and showed its date. The storefront shows the departure
  of the mode chosen on the product page and of the cart's mode at checkout
  (`GET /grouped-departures/next?service_level=`). A supplier has a lead time
  (`suppliers.lead_time_days`), added to each mode's delay on the product
  page when the article is not in local stock (`supplier_lead_days`).
  Migration `b9c0d1e2f3a4`. Functional audit D1.
- A deposit order partially refunded keeps its status too and follows its
  departure: its balance (total − deposit) stays right, the refund lowering
  what is owed and what was paid alike. A refund made before the invoice
  (issued with the balance) had no invoice to correct, so its credit note
  was skipped and the invoice billed the whole total: issuing the invoice
  now credits every completed refund without a note.
- A recurring departure left open below its threshold past its cut-off
  opens its following departure in advance: the new orders go there while
  the admin decides (they were attached to no departure). The link
  (`grouped_departures.next_departure_id`, migration `a8b9c0d1e2f3`) keeps a
  later close from opening a second one. Decision of 18/11/2026 (option B).
- A route into a customs clearance place must carry a mode (rapide,
  économique…): saving one without is refused
  (`shipping_route.import_mode_required`). The article price holds the
  freight of the routes with a mode while the checkout leaves out every route
  ending where customs clear: such a route's freight was billed nowhere. An
  inactive route is exempt (an old one can still be switched off); the active
  ones saved before are listed by the setup checklist. Decision of 18/11/2026.
- The fixed fee of an import route (the forwarder's fee per shipment,
  `base_price`) was billed nowhere: neither in the article price nor at
  checkout. It is now spread per billable kg (actual or volumetric weight,
  whichever is higher) over the weight of a departure at its threshold,
  entered on the route (`import_fixed_basis_kg`, migration `f7a8b9c0d1e2`):
  rate = price per kg + fee ÷ that weight, the same on the product page, the
  cart, the order line's cost and the cached catalogue price. The route form
  shows the resulting rate. The setup checklist blocks while imported
  articles have no import route carrying a mode, or an import route has a
  fee and no weight to spread it over. Decision of 18/11/2026.
- A stuck worker restarts (Z3, decision of 18/11/2026): the worker ends
  itself when its event loop is blocked for 5 minutes or Redis is unreachable
  for 3 (`app/core/worker_watchdog.py`), so Docker starts a fresh one; a
  server cron (`scripts/ops/restart-unhealthy.sh`, every 5 minutes) restarts
  any container Docker reports unhealthy and alerts, and stops after 3
  restarts in an hour. DEPLOYMENT.md §12.1.
- A separate billing address (decision of 18/11/2026): an address carries
  an optional business id (n° TAHITI, SIRET…); at checkout « Facturer à une
  autre adresse (société) » picks one, frozen on the order (`billing_name`,
  `billing_address`, `billing_tax_id`, migration `e6f7a8b9c0d1`) and printed
  as the buyer on the invoice and the credit notes, tax id included. The
  admin order page shows it.
- « Payer ma commande » warns when a transfer, cheque or cash payment is
  announced and not received yet: a customer who already sent it would pay
  twice (decision of 18/11/2026: a warning, not a refusal).
- The order's address is built by the server from the saved address
  (`shipping_address_id`): company, street, city, country; the recipient and
  the phone have their own columns (`orders.shipping_recipient`,
  `orders.shipping_phone`, migration `d5e6f7a8b9c0`). The storefront used to
  compose the text, recipient and phone inside, and the invoice took it as
  the buyer's address. The order pages and the e-mail show the three; the
  address cards (checkout, account) show the recipient, the company and the
  phone, and say when the recipient is missing. Review of 17/11/2026.
- A partial refund no longer moves a fully paid order to
  « PartiallyRefunded » whatever its progress (it then followed its departure
  no more): the order keeps its status, the refund shows on the payment and
  its credit note. A deposit order keeps the old rule until its balance
  deducts refunds. Review of 17/11/2026.
- « État du système » tells a stopped worker (no health key in Redis) and a
  scheduled task that missed its next run by more than 20 minutes (« En
  retard », worked out from its cron), instead of « ok » on the last success.
  The events the poller gave up on (FAILED) are listed, with « Relancer »
  (back to pending, attempts reset) and « Écarter » (closed, then purged by
  the retention). A replay is claimed in one statement: two clicks no longer
  replay twice. Review of 17/11/2026.
- The generic order update (`PUT /order/{id}`) checks a status change
  before writing anything: the other fields used to be saved, then the
  status refused. Review of 17/11/2026.
- Storefront: at sign-in the visitor's server cart catches up with the local
  one before the merge (an article added just before the session came back
  was dropped by it); the cart store's fallback messages are translated.
  Back office: changing a departure's status from its edit form asks the
  same confirmation as « Étape suivante » (it moves every order and e-mails
  each customer). Review of 17/11/2026.
- The checkout estimate counts distinct refused promo codes, not answers: it
  is re-asked at every change of the checkout, and ten re-quotes of the same
  expired code locked every code out for 10 minutes. Review of 17/11/2026.
- The order confirmation e-mail names the products in the customer's
  language, prints the estimated delivery on the shop's clock (it was a day
  early every afternoon at Tahiti), and for a pickup shows where to collect
  the order instead of the customer's address. Review of 17/11/2026.
- No more « handler abandoned » alerts for nothing: the credit note of a
  refund no longer waits for an invoice when the capture did not cover the
  order (parked for review, never invoiced), and the balance of a deposit
  order is not requested from an erased account (anonymised address).
  Review of 17/11/2026.
- Task alerts: a supplier health probe answering « unhealthy » now counts as
  a failure (it alerted nobody); the one-article Icecat task is no longer
  journaled (an article Icecat does not know marked « the » task failed);
  `last_alert_at` is stamped once the alert is out, not before (a webhook
  down at that moment silenced the task for 6 hours). Review of 17/11/2026.
- « État du système » lists the open group departures past their cut-off
  (threshold not reached, waiting for the admin), with how long, and turns
  « à surveiller ». The 15-minute cron no longer asks the supplier for the
  live stock of a departure it then leaves open: only one that closes is
  checked. Review of 17/11/2026.
- A waiting payment that already carries money received at the counter,
  left open when its part is paid by another payment, now alerts the shop
  (`ALERT_WEBHOOK_URL`: order, amounts received, what to do) instead of a log
  line only. Review of 17/11/2026.
- The checkout takes an `idempotency_key`, chosen by the storefront once per
  submission (a changed cart is a new one) and kept across a reload: a retry
  whose first attempt went through — its response lost to a timeout — gets
  that order back (`replayed`, the storefront opens the order's page) instead
  of a second order, and the cart the retry rebuilt is emptied. Two attempts
  in flight meet on a unique index (`orders.checkout_key`, migration
  `c4d5e6f7a8b9`) before any stock or payment is touched; a double click that
  finds its cart ordered gets the order too. The storefront now handles
  `cart.already_checked_out` (another tab). D5, review of 17/11/2026.
- The import mode the customer paid for (rapide, économique…) shows on the
  back-office order page, under each line — the shop ships by it —, on the
  customer's order page and in the confirmation e-mail, by its customer label
  (kept for a route withdrawn since). It follows a quote request, the issued
  quote and its acceptance into the cart, and « commander à nouveau » (an
  article already in the cart keeps the cart's mode; a mode no longer on
  offer falls back to the default one). Review of 17/11/2026.
- The order confirmation e-mail lists the lines, the delivery mode, the
  delivery address, the group departure and the estimated delivery, in the
  customer's language (functional audit M4).
- A delivery address carries the recipient's name, an optional company and a
  phone for the carrier, optional (migration `d0e1f2a3b4c5`), prefilled from the
  profile; the order keeps them in its address text (functional audit M8).
- Back office → « État du système » (`GET /admin/system-status`): the last
  run of every background task (succeeded, with errors, failed, and the
  error), the outbox backlog and its oldest pending event, the e-mails given
  up in the last 24 h or stuck in the queue, the age of each currency rate,
  and whether the e-mail provider and the alert webhook are configured.
- Every background task run is journaled (`task_runs`, migration
  `b8c9d0e1f2a3`) and a failure — an exception, or a result reporting errors
  (the price and stock sync returned « success » with errors) — posts to
  `ALERT_WEBHOOK_URL`, on the first failure then at most every 6 hours.
- An e-mail given up after its retries alerts the shop (at most once an
  hour): an expired provider key stopped every e-mail without a sound.

- `docs/internal/AUDIT_FONCTIONNEL_2026-11.md`: functional audit (are the
  features solid, which ones are missing), three parallel reviews of the
  customer journey, the back office and operations, and the business engine.

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

- An order with a deposit is paid with a single payment method, deposit and
  balance alike (`payment.method.must_match`): its fee is spread over both
  parts. Another method is accepted only when that one can no longer be used
  (switched off, no longer offered, amount above its ceiling).
- The payment that settles a part closes the other payments still waiting on
  it (a transfer announced at checkout, then the order paid by card): they
  stayed « en attente de validation » on a settled order.
- « Payer ma commande »: an order still entirely unpaid can be paid with
  another payment method — it is re-billed that method's fee (total and fees
  follow, up or down) instead of « ce moyen n'a pas les frais de la
  commande ». The page shows the fee of each method and the new total. A
  deposit or a balance keeps the order's amount: only the accepted methods
  are listed.
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

- Relecture du 17/11/2026 of the November changes (five independent reviews):
  - « Payer » is no longer offered online once instalments were received on
    the part due (the amount offered was refused by the initiation); the page
    says « not payable online » instead of « fully paid » for a cancelled
    order or one under review.
  - The order line records the import mode it is really priced on; « price
    unavailable » follows the caller's language.
  - Invoices, credit notes, quotes, the FEC and the CSV export are dated on
    the shop's clock, like their number (« FA-2026-… » was dated 01/01/2027,
    and every afternoon at Tahiti printed the next day).
  - A background task stopped by its timeout or by the worker is journaled as
    failed and alerts; a task alternating success and failure alerts at most
    once an hour.
  - Payment events follow the order lifecycle (an infected document on a
    delivered order made it payable again; a replayed partial refund reopened
    a refunded one). « PaymentReview » can go back to « à payer ».
  - The next departure of a recurring one opens with a cut-off in the future
    and a single « (suivant) » suffix; shortages and unpaid orders of an
    automatic close are logged.
  - `deploy.sh`: the rollback also runs when `docker compose up` itself fails
    (an API that does not start), a deployed shop whose database is stopped is
    not migrated without a dump, the dump is owner-readable only, and a first
    deployment no longer ends in error on the dump rotation.
  - Supplier units of a partially refunded or backordered order stay held;
    a refunded gift card whose credit was entirely spent is deactivated.
  - `has_password` is filled for existing accounts where it can be deduced
    (migration `f2a3b4c5d6e7`).
  - Storefront: a variant shows and carries its own import-mode prices (the
    cart line showed the parent's); the checkout says when the delivery modes
    could not be loaded and offers to retry instead of a dead end. Admin: the
    dates of a departure no longer move forward a day at each save for a
    browser east of the shop.
- Checkout by card or PayPal answered 500 on an order already committed: the
  response and the log read rows expired by the second commit (or by the
  rollback when the provider failed). The values are read once before the
  provider call (relecture du 17/11/2026 ; introduced with the deferred
  provider call, never released).
- Checkout: the card / PayPal provider is called once the order is committed,
  no longer inside the transaction that holds the stock rows locked (a slow
  provider, up to 30 s, made every other checkout of the same products wait;
  a failed commit left a payment form open at the provider). If the provider
  fails at that point the order stays placed (`payment_start_failed`) and the
  storefront opens its payment page to try again.

- Back office, order page: an order without a shipping leg yet (unpaid, or
  placed before the logistics phase) showed « Commande introuvable » since
  the API messages were translated — the page recognised the empty journey
  by its French message. It now reads the 404 (code `order.journey.empty`).
  A refused status change says why in words instead of quoting status codes.

- The worker watches the outbox every ten minutes: an event waiting for more
  than 15 minutes (a stopped poller) alerts the shop, once an hour.
- Deployment: the database is dumped before the migrations
  (`backups/pre_deploy_*.dump`), and a version whose health check fails is
  replaced by the previous one (`.deployed_tag`, `AUTO_ROLLBACK=false` to
  keep it) — it stayed in service.

- A grouped departure past its cut-off closes on its own when its threshold
  is reached (the next one of a recurring departure opens); one below its
  threshold stays open and the shop is alerted once. Only the admin closed
  them: meanwhile new orders were attached to no departure.
- The checkout refuses an order without a delivery mode when one is offered
  for the address (`checkout.delivery_type.required`): when the storefront
  failed to load the modes, the order left with none and no last leg billed.

- Outbox: a handler given up after its retries is now kept in the database
  (`outbox_handler_failures`, migration `c9d0e1f2a3b4`) — its event was
  `DONE` and only a log line said the delivery never happened. « État du
  système » lists them, with « Rejouer ». The CRUD writes no longer publish
  events no handler reads (all of them did: a supplier sync queued one event
  per product ahead of the payment ones), and a nightly purge clears the
  delivered outbox events (30 days), the replayed failures (90 days), the
  e-mail bodies (90 days) and rows (1 year), and the supplier sync logs
  (90 days).

- Order statuses follow a lifecycle: a cancelled or refunded order is closed,
  and an order paid or on its way no longer goes back to « awaiting
  payment » (`order.status.transition_refused`, 409); a fulfilment step back
  stays possible. The back office asks for confirmation (and an optional
  reason) before changing an order's status, and before moving a departure to
  its next step, which moves all its orders and e-mails each customer.
- Invoice and credit-note numbers take the fiscal year on the shop's clock
  (`SHOP_TIMEZONE`): issued in UTC, a document of 31 December after 14:00 at
  Tahiti took the next year's number. The departure reminders and cut-off
  days follow `SHOP_TIMEZONE` too.

- One checkout per cart: the cart row is locked until the order commits, so
  two submissions at once (double click, two tabs, a retry) no longer create
  two orders (`cart.already_checked_out`, 409).
- A product whose cost is in a currency with no rate in force is no longer
  sellable (`currency_rate_missing` blocker): its page and the cart answered
  500, and one such article failed a whole list. An uncomputable price is a
  409 `product.price_unavailable`, never a 500.
- Checkout errors speak the customer's language: the codes raised with an
  English, technical message (« Cart is empty », « Insufficient stock for
  product <uuid> ») have a French message, the French ones an English one;
  a stock refusal names the article and what is left, and links to the cart.

- **The import freight is billed.** The product page showed the price of the
  chosen import mode, freight included, while the catalogue, the cart and the
  order priced with no route — no freight — and the checkout skipped the
  import leg as « already in the price »: the freight (and the customs,
  margin and tax computed on it) was billed nowhere, and the cost price
  ignored it too. A price asked without a route is now computed on the
  **default import route**; a cart line and an order line carry the mode
  their price is computed on (`import_service_level`, migration
  `a7b8c9d0e1f2`); the product page passes the mode it shows, and the cart
  lets the customer switch the whole cart to another mode
  (`GET /cart/import-modes`). The cached catalogue prices are refreshed when
  an import route changes. **Prices of imported articles rise by the default
  freight at the first refresh after deployment.**
- An unpaid order can be paid again: `GET /orders/me/{id}` says what is
  payable now (`pay_now_kind`, `pay_now_amount`); the order page shows
  « Payer », the payment-return page « Réessayer le paiement » (it sent back
  to an emptied cart), and the « payment refused » e-mail links to it.
- « Demander un devis » in the cart: the request, its admin screen, the PDF
  and the e-mail existed, nothing in the storefront reached them.
- Backups: the shipped crontab set `BACKUP_REMOTE`, which `backup.sh` does
  not read — nothing left the server; it now sets `OFFSITE_RCLONE_REMOTE`
  and the documented directory. `STORAGE_RCLONE_SOURCE` backs up the bucket
  when files are stored in S3 (the local volume is then empty, and the
  script says so), and a successful run leaves `backups/last_success` and
  calls `BACKUP_HEARTBEAT_URL`.

- Review of the November 2026 audit fixes — low-severity points:
  - money: the balance of a deposit order cannot be paid with a method dearer
    than the one billed (S9); a gift card is issued for what its line cost
    when sold below its face value (S3); a refund that cannot take back
    points already spent alerts the shop (S6); a group price typed with cents
    is rounded like every price; a provider notification of success without
    amount or currency goes to review;
  - orders: cancelling an order (admin included) closes its card / PayPal
    payments still pending; deleting an order releases its reservations;
  - hardening: the two-factor endpoints are limited per account as well as
    per address; an IP literal on `OUTBOUND_WEBHOOK_ALLOWED_HOSTS` is not a
    webhook host; errors logged by the HTTP retries and Icecat no longer
    quote the API key; the decompressed XLSX cap goes from 300 to 120 Mo; an
    unreachable antivirus refuses the import with a message (it was a 500);
  - outbox: an event left RUNNING counts as an attempt and is abandoned at
    `MAX_ATTEMPTS`; the credit note of a refunded deposit no longer waits
    for an invoice that is not coming;
  - storefront: one catalogue search for `?page=N` (page 1 flashed); one
    refresh at the OAuth return; « Mes commandes » reads every invoice, not
    the 50 latest; the « show password » control is a button (keyboard,
    name); `srcset` on the category tiles and the first catalogue images
    loaded eagerly;
  - admin: departure dates saved on the shop's clock; « server unreachable »
    instead of axios' own words; the last hard-coded French notices are
    translated; the icon-button guard also covers dropdowns, FABs and
    clickable icons.

- Review of the November 2026 audit fixes — storefront: the « could not add
  to cart » message is a toast at the bottom of the screen on every page
  with product cards (catalogue, related products, wishlist, comparison; U8
  only covered the home page) and closes by itself; the mobile filter sheet
  closes when the screen becomes wide (the page stayed locked, U6); the
  search suggestions reopen after Escape when typing or pressing ↓, and
  « all results » is an option reachable with the arrows (U7); a slower load
  of a product left meanwhile no longer clears the variant selected on the
  current one.

- Review of the November 2026 audit fixes — sessions and hardening: an
  administrator signs in from the back office only (the refresh alone was
  checked), and `ADMIN_FRONTEND_HOST` defaults to `https://admin.<DOMAIN>`
  outside local (the check was off until the variable was set, S2); wrong
  authenticator codes now lock the second factor for
  `LOGIN_LOCKOUT_MINUTES` (the right password cleared the counter before the
  code was checked, S11); the promo-code limit of the checkout quote is
  counted atomically and only for guesses — a code refused for the cart
  (minimum not reached…) no longer locks the customer out (S7);
  `POST /users/me/2fa/setup` is rate-limited; the Slack notification webhook
  goes through the same allow-list and public-address guard as the outbound
  webhook; the FEC export neutralises formulas; the SSRF guard refuses the
  shared address space (100.64.0.0/10).

- Review of the November 2026 audit fixes — stock, cancellation and refunds:
  money that arrives after an order's reservation was given back (sweep,
  refused attempt, late notification) takes the stock again before
  confirming it, and alerts when the goods are gone (B2 was fixed on
  `/payments/initiate` only); a receipt at the counter is refused for a
  cancelled order or one whose stock is gone; two attempts started together
  no longer reserve twice; a refusal no longer revives a cancelled order nor
  an order another payment secured; « awaiting validation » on a balance no
  longer sends a shipped order back to « awaiting payment »; a validated
  manual payment cannot be rejected; two cancellations at once give the promo
  code back once; `PUT /orders/{id}` changes the status through the one
  status service.
- A refund recorded « pending » (PayZen, done in its back office) can now be
  confirmed from the order (`POST /admin/payments/{id}/refunds/confirm`):
  nothing completed it before, so no credit note was issued, the order kept
  its status and the gift cards and points were never taken back (S6).
- Guest-checkout accounts (unverified address) are no longer sent the
  abandoned-cart reminder (S8).

- Review of the November 2026 audit fixes — defects the fixes themselves
  introduced: the account's cart is read back at sign-in (signing out emptied
  the device and the first article added then replaced the server cart; the
  merge also runs once when the boot and the OAuth return both ask);
  `ADMIN_ALLOWED_IPS` now applies to the optional-auth routes too (the generic
  CRUD skipped it), accepts commas and stops the start on a typo; the ARQ
  worker and the outbox poller get the raw `REDIS_PASSWORD` (a password with
  `+`, `/` or `=` locked them out); `GET /payments/status/{id}` answers 404
  to a non-ASCII token (it was a 500) and the token expires after 7 days; a
  malformed webhook URL is refused instead of crashing the departure
  reminders; the address form applies an autofilled country (it stayed on
  PF); the PayPal return no longer starts polling after the page is left.

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
- Security (S5, end): enrolling an administrator's 2FA needs a one-time
  code e-mailed to the account by `POST /users/me/2fa/setup` (8 digits,
  15 minutes, 5 tries), sent with the authenticator's code to `/confirm`
  (`email_code`). A stolen password alone no longer enrols the thief's
  authenticator. Admin → Sécurité asks for it.
- Storefront (audit 2026-11, F1): each server render runs in its own
  `AsyncLocalStorage` scope (`src-ssr/middlewares/render.ts`); the API
  language, the formatting context (`setFormatContextResolver` in
  `@app/utils`) and the i18n composer of the store messages are read from
  it. Concurrent French and English renders shared them as module
  variables: wrong `Accept-Language`, wrong date format, hydration
  mismatches.
- Storefront (audit 2026-11, F2): only the latest request writes on the
  product page, the catalogue search and the checkout quote. An older answer
  arriving last showed another product (and an endless skeleton), results of
  an earlier query, or wrong amounts on « Payer X ».
- Storefront (U2): the catalogue, the product page and the cart show the
  API's message (`{ error: { message } }`) or a translated fallback, never
  axios' « Request failed with status code 503 ».
- Storefront: signing out forgets the cart on this device (the account's
  server cart is kept); on a shared computer the next person saw it.
- Storefront (audit 2026-11, U3–U7): on mobile the checkout recap folds
  behind a one-line total; « Payer » says what is still missing; the
  address form takes the browser's autofill (`autocomplete`, no field
  waiting for another); the mobile filter panel is a modal dialog (focus
  trapped, Escape, no scroll behind); the search suggestions are a keyboard
  combobox (arrows, Enter, `aria-activedescendant`).
- Admin: the 57 icon-only buttons have an `aria-label` (their tooltip was
  the only name); `shared/ui/src/a11y-guard.test.ts` refuses an icon
  `q-btn` without one in both apps.
- Storefront: shop images get a `srcset` of their WebP widths (480 / 960 /
  1600 px, derived from the stored URL) and `sizes`; the product page's
  main photo is `fetchpriority="high"`.
- Security (audit 2026-11, S10): admin CSV exports neutralise any text
  cell starting with `= + - @`, tab or carriage return (leading apostrophe);
  numbers stay numbers.
- Security (S8): abandoned-cart reminders go to accounts only. A visitor's
  e-mail was never confirmed, so anyone could make the shop mail any
  address; their carts are stamped and counted as `skipped_unverified`.
- Security hardening (audit 2026-11, low severity): rate limit and a single
  error on the 2FA endpoints; recovery codes hashed with HMAC; erasing an
  OAuth-only account needs a sign-in of the last 15 minutes; a password
  change voids a pending reset link; `/payments/me/{id}/confirm` never
  captures a cancelled or refunded payment; PayZen IPN currency required
  and compared; admin refunds and « one code per customer » under a row
  lock; cart lines capped at 999; outbound webhook and supplier feed reach
  public addresses only, checked at connection time (no DNS rebinding);
  Icecat key out of the logs; supplier files scanned by ClamAV and zip bombs
  refused; public reviews and wishlists without account ids; stock alerts
  of a signed-in customer go to their own address; `ADMIN_ALLOWED_IPS`
  enforced by the API on every superuser request; CI with read-only
  `permissions`, third-party actions pinned by SHA, the gist secret limited
  to the badge steps, no CI bypass for a production deploy; optional Redis
  `requirepass` (`REDIS_PASSWORD`).
- Backend robustness (audit 2026-11): the outbox puts back to PENDING an
  event a dead poller left RUNNING, and gives up after `MAX_ATTEMPTS` with an
  alert (it retried forever); the tracking link of the checkout runs in a
  savepoint (a failure no longer turns the checkout into a 500); the
  balance request is stamped only once its e-mail is out (retried
  otherwise); a refund that overtakes the invoice of a captured order waits
  for it instead of losing its credit note; a missing order in a payment
  event is logged instead of failing the handler.
- Storefront bugs (audit 2026-11): the shop's time zone applies in the
  browser after the server render; every catalogue filter (price,
  specifications, page) is in the URL — the price filter no longer survives
  unseen; the checkout prices its quote again after `cart.price.changed`;
  a card form whose PayZen script failed can be loaded again (the order was
  placed and the cart emptied with nothing to click); ordering an accepted
  quote adopts the server cart at the quote's prices (it was mirrored back
  at catalogue prices); the order page fetches its own invoice
  (`/invoices/me/by-order/{id}`) instead of searching the 50 latest; the
  payment return page reads the status signed out, with the signed token
  of the return URL (new `GET /payments/status/{id}?t=`,
  `payment_status_token` in the checkout and initiation responses).
- Admin bugs (audit 2026-11): a second « Enregistrer » after a failed
  step of a new product updates it instead of creating a duplicate (and the
  API's message is shown); a departure's order cutoff is typed on the shop's
  clock; the order page reloads after a status change.
- UX (audit 2026-11): the admin shows the API's error messages, never
  axios' « Request failed with status code … » (design-guard rule); the
  add-to-cart error of the home page is a fixed, announced toast near the
  action; the home page offers « Réessayer » when every API fails (endless
  skeleton before); gallery thumbnails are buttons in a real list; 44 px
  touch targets for « Mot de passe oublié ? » and « Comparer »; the product
  form of the admin is full screen on a phone with sticky actions; the
  product search field no longer forces a horizontal scroll; the last
  hard-coded admin strings are translated; legal pages say they are in
  French in another language, default text included.
- Prices (audit 2026-11): every price shown or billed — computed sale
  price, typed fixed price, group price, promotion, variant supplement — is
  rounded to the reference currency's unit (whole francs in XPF; cents in
  EUR) by `reference_price`; intermediate amounts keep their precision.
  11 600,37 F was shown 11 600 F and two of them billed 23 201 F. One
  `split_incl_tax(amount, rate, currency)` now splits « TTC → HT + TVA » for
  the invoice, the credit note and the margin (the margin rounded to the
  cent in XPF). Stored prices move by less than one franc at the next
  nightly price refresh (`refresh_sale_prices`), or at once from the admin.
- Security: the outbound webhook (departure reminders) only reaches the
  hosts of the new `OUTBOUND_WEBHOOK_ALLOWED_HOSTS` (default: Make, Zapier,
  Slack, IFTTT, Discord); the request is rebuilt on the allow-list entry,
  and the public-address check stays. Extend the list for another service.
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
