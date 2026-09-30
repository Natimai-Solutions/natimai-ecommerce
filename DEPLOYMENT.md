# Deployment guide

Environment variables and first‑deployment steps for the e‑commerce stack
(FastAPI backend, Quasar storefront, Quasar admin, PostgreSQL, Redis, ARQ worker,
outbox poller, ClamAV).

> This is the canonical reference for **which variables to set**, plus the first
> deploy steps (§8), post‑deployment checks (§10) and the operations runbook (§11).

---

## 1. Where variables live

- **Backend** reads a single `.env` file at the repository root (the backend's
  pydantic settings use `env_file="../.env"`). Unknown keys are ignored.
- **docker-compose** injects a few values directly into the `api`, `arq-worker`
  and `outbox-poller` services. Notably it sets **`POSTGRES_SERVER=postgres`**
  (the DB service name), overriding the code default of `db`.
- **Frontends** (storefront, admin) are built with Vite: only variables prefixed
  with `VITE_` are exposed to the browser, and they are baked in **at build
  time** — changing them requires rebuilding the frontend image.

Create the root `.env` from the template in section 6 before the first start.

---

## 2. Backend — required (deployment fails or is insecure without these)

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key — random and unique | `openssl rand -hex 32` |
| `POSTGRES_SERVER` | PostgreSQL host (compose sets `postgres`) | `postgres` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password (≥ 16 chars, not `changethis`) | — |
| `POSTGRES_DB` | Database name | `fastapi_ecommerce` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `REDIS_SERVER` | Redis host | `redis` |
| `FIRST_SUPERUSER` | Bootstrap admin email | `admin@example.com` |
| `FIRST_SUPERUSER_PASSWORD` | Bootstrap admin password (≥ 12 chars, not `changethisA1`) | — |
| `ENVIRONMENT` | `local` / `staging` / `production` — enables the non‑default‑secret guards | `production` |

`POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` are read both by the
`postgres` container (which creates the role and the database) and by the API,
the worker, the poller and the outbox health checker. They used to be hardcoded
to `postgres` in `docker-compose.yml` and not overridden by the production
file, so a deployed stack ran on that password while ignoring the `.env`
entirely. Compose now interpolates them everywhere, with the old values as
defaults so a bare `docker compose up` still works with no `.env`.

When `ENVIRONMENT != local`, the app refuses to start if `SECRET_KEY`,
`POSTGRES_PASSWORD` or `FIRST_SUPERUSER_PASSWORD` are left at `changethis` —
or, for `SECRET_KEY`, left **empty**. `POSTGRES_PASSWORD` is additionally
rejected when it is a well-known development default (`postgres`, `password`):
the `changethis` check alone never saw the compose value. An empty key used to be silently replaced
by a random one: every token then died on restart and each replica signed with
a different key, so no session survived a rolling update. In `local` only, that
random fallback still applies, with a warning.

---

## 3. Backend — by domain

### 3.1 App / CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_NAME` | `FastAPI Ecommerce` | Used as default email "from" name |
| `SHOP_NAME` | `Natimai` | Storefront brand name |
| `FRONTEND_HOST` | `http://localhost:5173` | Public storefront URL (CORS + email links) |
| `BACKEND_CORS_ORIGINS` | `[]` | Extra CORS origins (comma list or JSON array) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL — do **not** increase |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token TTL |
| `SENTRY_DSN` | — | Error monitoring DSN. Ignored when `ENVIRONMENT=local`. The Sentry `environment` tag is set from `ENVIRONMENT`, so staging and production stay separable in the same project. |
| `SENTRY_TRACES_SAMPLE_RATE` | `1.0` | Share of transactions traced. `1.0` means **every** request is sent — fine to start, expensive once traffic grows. Lower it (e.g. `0.1`) once you know your volume. |
| `ALERT_WEBHOOK_URL` | — | Ops alert webhook (Slack-style `{"text": …}`; Mattermost-compatible, Discord via `/slack` suffix). Fired on outbox degraded/recovered state changes and when an ARQ outbox job is abandoned after 8 tries (~15 min of backoff). Empty = log only. **Recommended in production** |

> **Authentication model (cookie).** The **refresh token** is delivered as an
> **HttpOnly, Secure, SameSite=Lax** cookie (unreadable by JS → XSS-resistant);
> the **access token** (15 min) lives only in the SPA's **memory** and is restored
> on startup via `/login/refresh-token`. Deployment implications:
> `BACKEND_CORS_ORIGINS` must list the **exact origins** of the frontends (never
> `*`), because requests are *credentialed* (CORS `allow_credentials` is on); in
> production everything must be **HTTPS** (the cookie is `Secure`). The subdomain
> scheme (`shop.`/`admin.` → `api.`) is *same-site*, so `SameSite=Lax` still sends
> the cookie. Optional tuning: `REFRESH_COOKIE_SAMESITE`, `REFRESH_COOKIE_DOMAIN`,
> `REFRESH_COOKIE_SECURE` (see `.env.example`).

### 3.2 Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_SERVER` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_USER` / `REDIS_PASSWORD` | — | Auth (if Redis requires it) |

### 3.3 Email (transactional)

| Variable | Description |
|----------|-------------|
| `EMAILS_FROM_EMAIL` | Sender address |
| `EMAILS_FROM_NAME` | Display name (defaults to `PROJECT_NAME`) |
| `EMAILS_API_URL` | Email API URL (e.g. Mailgun) |
| `EMAILS_API_KEY` | Email API key |
| `EMAIL_SUPPORT` | Recipient for quote requests and admin alerts |
| `EMAIL_CONTACT` | Address shown in customer emails |

Without `EMAILS_API_URL` + `EMAILS_API_KEY`, emails are silently disabled
(`emails_enabled = False`). Mailgun provider variables (`MAILGUN_DOMAIN`,
`MAILGUN_API_KEY`, `MAILGUN_FROM_EMAIL`, `MAILGUN_FROM_NAME`) are used when a
notification provider is set to `mailgun`.

`PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` accepts `noop`, `mailgun` or
`slack_webhook` and is **validated at startup**: an unknown value now stops
the app instead of falling back to `noop`, which reports success and throws
the message away. A single typo in the `.env` used to discard every order
confirmation, payment receipt and invoice, leaving only a warning in the logs.

### 3.4 Authentication — social login (OAuth 2.0) · Phase 2

Optional. Required only to enable "Continue with Google / Microsoft".

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client id |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `MICROSOFT_CLIENT_ID` | — | Microsoft (Entra) app id |
| `MICROSOFT_CLIENT_SECRET` | — | Microsoft app secret |
| `MICROSOFT_TENANT_ID` | `common` | Microsoft tenant. `common`: personal accounts only (see the linking rules below); the shop's tenant id or domain to also accept its own work accounts |
| `OAUTH_REDIRECT_BASE_URL` | — | Public **backend** URL used to build the provider `redirect_uri`, e.g. `https://api.example.com` |
| `FRONTEND_OAUTH_REDIRECT_URL` | — | **Storefront** URL the backend redirects to after login. Must point at the callback route: `https://shop.example.com/oauth/callback` |

If a provider's id/secret are missing, its `/auth/{provider}/login` endpoint
returns `503 oauth.provider.not_configured`. See section 7 to enable end‑to‑end.

**Account linking rules** (fix of 30/09/2026 against account takeover, « nOAuth »):

- An e-mail is used — to create an account or to link an existing one — only
  when the provider vouches for it: Google's `email_verified`; for Microsoft, a
  personal account (outlook.com, hotmail…), the shop's own tenant when
  `MICROSOFT_TENANT_ID` is a tenant id or domain, or the optional `xms_edov`
  claim. Otherwise the sign-in is refused (`oauth_error=email_not_verified`).
- With `MICROSOFT_TENANT_ID=common` (or `organizations`), a work account from
  **another** organisation cannot sign in: its directory can put any address in
  `mail`. Set the shop's tenant id to accept your own staff's work accounts, or
  add the `xms_edov` optional claim to the app registration.
- Administrator accounts (`is_superuser`) never sign in through OAuth, even with
  a link created earlier: they use their password (`superuser_oauth_disabled`,
  `account_exists`).

### 3.5 Payment — PayZen / Lyra · Phase 2

| Variable | Default | Description |
|----------|---------|-------------|
| `PAYZEN_SITE_ID` | — | PayZen site id |
| `PAYZEN_API_PASSWORD_TEST` | — | REST API password (TEST mode) |
| `PAYZEN_API_PASSWORD_PROD` | — | REST API password (PRODUCTION mode) |
| `PAYZEN_PUBLIC_KEY_TEST` | — | Public key for the SmartForm JS (TEST) |
| `PAYZEN_PUBLIC_KEY_PROD` | — | Public key for the SmartForm JS (PRODUCTION) |
| `PAYZEN_MODE` | `TEST` | Set `PRODUCTION` in prod |
| `PAYZEN_MANUAL_VALIDATION` | `false` | `true` → authorise the card at checkout (status `Authorized`) and capture later (deferred debit), e.g. at shipment via `POST /admin/payments/{id}/capture`. ⚠️ authorisations expire (~7 days). |
| `PAYZEN_API_ENDPOINT` | `https://api.osb.pf` | REST API base URL |
| `PAYZEN_STATIC_URL` | `https://static.osb.pf` | Base URL of the SmartForm JS/CSS SDK (Krypton client) |
| `PAYZEN_IPN_URL` | — | Server‑to‑server webhook URL (auto‑computed if empty) |
| `PAYZEN_RETURN_URL` | — | Default browser return URL after payment |
| `PAYZEN_CURRENCY` | `XPF` | Billing currency |
| `REFERENCE_CURRENCY` | `XPF` | Pivot currency for cost/price normalisation |
| `INSURANCE_RATE_PCT` | `0.0` | Insurance %, applied on **cost + variable import freight** (CAF/CIF basis) before customs. `0` = no insurance in the price: set the rate actually billed by the insurer, otherwise the premium is paid and never recovered. |

The `api_password` and `public_key` actually used follow `PAYZEN_MODE`
(`*_TEST` vs `*_PROD`).

### 3.6 Supplier orders — Ingram Micro · Phase 2 (item 8)

Catalog sync:

| Variable | Default | Description |
|----------|---------|-------------|
| `INGRAM_CLIENT_ID` | — | OAuth client id (required for sync) |
| `INGRAM_CLIENT_SECRET` | — | OAuth client secret |
| `INGRAM_CUSTOMER_NUMBER` | — | Ingram customer number |
| `INGRAM_COUNTRY_CODE` | `FR` | API country code |
| `INGRAM_ENVIRONMENT` | `sandbox` | Set `production` in prod |
| `INGRAM_SYNC_ENABLED` | `true` | Toggle the catalog cron |
| `INGRAM_SYNC_INTERVAL_HOURS` | `6` | Catalog sync frequency |
| `SUPPLIER_SYNC_MIN_PRICE` | `0` | Minimum price **in XPF** (0 = off) |
| `SUPPLIER_SYNC_MIN_QUANTITY` | `0` | Minimum quantity (0 = off) |

Automatic purchase‑order creation on `payment.captured`:

| Variable | Default | Description |
|----------|---------|-------------|
| `INGRAM_ORDER_CREATION_ENABLED` | `false` | Master switch for auto PO creation |
| `INGRAM_SHIP_TO_ADDRESS_LINE1` | — | **Required** when enabled — our warehouse address |
| `INGRAM_SHIP_TO_CITY` | — | **Required** when enabled |
| `INGRAM_SHIP_TO_COUNTRY_CODE` | `PF` | Ship‑to country |
| `INGRAM_SHIP_TO_CONTACT` | — | Contact name |
| `INGRAM_SHIP_TO_COMPANY_NAME` | — | Company name |
| `INGRAM_SHIP_TO_POSTAL_CODE` | — | Postal code |
| `INGRAM_SHIP_TO_PHONE` | — | Phone |

> Enable `INGRAM_ORDER_CREATION_ENABLED=true` **only after**
> `INGRAM_SHIP_TO_ADDRESS_LINE1` + `INGRAM_SHIP_TO_CITY` are set, otherwise every
> generated PO is persisted as `ERROR` (ship‑to not configured).

Inbound order‑status webhook (Phase 3):

| Variable | Default | Description |
|----------|---------|-------------|
| `INGRAM_WEBHOOK_SECRET` | — | Bearer token Ingram sends in `Authorization` header on `POST /webhooks/ingram/order-status`. If not set, the endpoint returns `503`. |

> Generate with `openssl rand -hex 32` and register the value in the Ingram portal
> as the webhook secret for the order‑status callback URL
> `https://api.example.com/api/v1/webhooks/ingram/order-status`.

### 3.7 System settings (Phase 3)

System settings are stored in the `system_settings` database table and managed
via admin endpoints (`GET/PUT /admin/system-settings`). No environment variable
is needed — the seed migration inserts the initial value.

| Key | Seeded value | Description |
|-----|-------------|-------------|
| `default_display_currency` | `XPF` | Currency shown to customers in the storefront. Exposed to unauthenticated callers via `GET /system/settings`. Phase 4 will add a runtime toggle. |

> To change the default display currency after first deployment:
> ```http
> PUT /api/v1/admin/system-settings/default_display_currency
> Authorization: Bearer <superuser-token>
> {"value": "EUR"}
> ```

### 3.9 Product enrichment — Icecat

| Variable | Default | Description |
|----------|---------|-------------|
| `ICECAT_USERNAME` | — | Icecat login (Open Icecat: email) |
| `ICECAT_API_KEY` | — | Icecat API key |
| `ICECAT_ENABLED` | `true` | Toggle enrichment |
| `ICECAT_USE_OPEN` | `true` | `false` = Full Icecat (paid) |
| `ICECAT_LANGUAGE` | `fr` | Product sheet language |

### 3.8 Catalogue freshness, stock reservations and checkout checks

Three background/edge behaviours that decide whether the catalogue tells the
truth. All three are safe to leave at their defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCK_RESERVATION_TTL_HOURS` | `48` | Stock is decremented when the order is drafted. A checkout abandoned on the payment page used to hold it forever — only `payment.rejected` ever gave it back. An hourly sweep releases orders still in `Pending` past this age. Orders in `AwaitingPayment` (bank transfer under validation) or `PaymentReview` are never touched: a human or an event still owns them. `0` disables the sweep. |
| `SUPPLIER_DELISTING_GRACE_HOURS` | `72` | A SKU the supplier stops returning stays sellable with its last known price and stock. The first absence is only recorded (`products.supplier_missing_since`); the product is deactivated once the gap outlives this delay, so a transient supplier fault cannot empty the catalogue. `0` records the absence but never deactivates. |
| `CHECKOUT_SUPPLIER_AVAILABILITY_CHECK` | `true` | Re-ask the supplier what it actually has before reserving, instead of trusting a snapshot up to two hours old. One request per order, on supplier-managed lines only. A supplier that answers "out of stock" refuses the order; a supplier that cannot be reached never blocks a sale — the snapshot stands. |
| `CHECKOUT_SUPPLIER_CHECK_TIMEOUT_SECONDS` | `8` | Deliberately short: this runs on the checkout critical path, unlike the 60 s the background sync can afford. |
| `TERRITORY_PROFILE` | `PF` | Where the shop sells: `PF` (Polynésie française: XPF, TGC, Papeete customs corridor and island tree) or `FR` (France métropolitaine: EUR, TVA, no Polynesian starter data). Fills `REFERENCE_CURRENCY`, `SHOP_COUNTRY_CODE`, `TAX_TERRITORY_CODE`, `DEFAULT_TAX_CODE`, `INVOICE_FEES_TAX_CODE`, `PAYZEN_CURRENCY` and `SEED_FRENCH_POLYNESIA_LOGISTICS` unless each is set explicitly. The seed creates the profile's tax rates and starter FX rates. |
| `SHOP_MODE` | `full` | `simple` for a one-warehouse shop selling its own stock, shipped directly to the customer: the admin hides suppliers, customs, exchange rates, spec catalog and multi-leg logistics, the product form defaults to a fixed price, and the supplier sync / Icecat crons are not scheduled. Nothing is deleted: switching back to `full` shows everything again. |
| `SHOP_COUNTRY_CODE` | from profile | ISO country of the shop (address fallback, root of the place tree). |
| `TAX_TERRITORY_CODE` / `DEFAULT_TAX_CODE` | from profile | Territory of the shop's own tax rates and the rate applied when neither the product nor its category says otherwise. |
| `CART_ABANDONMENT_REMINDER_DELAY_HOURS` | `24` | A logged-in customer's cart untouched for this long, never ordered, gets one reminder e-mail (hourly sweep, `cart.abandoned` outbox event). Customers can opt out of commercial e-mails in their preferences. `0` disables the sweep. |
| `CART_ABANDONMENT_MAX_AGE_DAYS` | `14` | Carts older than this are never reminded. |
| `SUPPLIER_FILE_IMPORT_INLINE_MAX_ROWS` | `2000` | A CSV / Excel catalog up to this many rows is imported inside the request. A larger file is stored (`FILE_STORAGE_BACKEND`), a sync log is opened and an ARQ job imports it; the admin screen polls the log. Simulations of a large file resolve only this many rows. |
| `SUPPLIER_FILE_IMPORT_MAX_ROWS` | `250000` | Hard cap on a catalog file (worker memory). The upload itself is capped at 20 MB. |

### 3.9 File storage (payment attachments, queued catalog imports, public media)

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_STORAGE_BACKEND` | `local` | `s3` in production |
| `FILE_STORAGE_LOCAL_ROOT` | `/tmp/fastapi_ecommerce_storage` | Dev only |
| `MEDIA_PUBLIC_BASE_URL` | — | Public origin of the API (`https://api.example.pf`). Images uploaded from the admin (homepage, products, categories, pages) are re-encoded to WebP, stored under `media/…` in the same storage, and served by `GET /api/v1/media/{id}/{width}.webp` with a one-year immutable cache. Their absolute URLs are built from this origin; empty, the origin of the upload request is used (fine in development, wrong behind a proxy). |
| `MEDIA_MAX_UPLOAD_BYTES` | `8388608` | Largest image accepted by `POST /admin/media` (8 MB). Keep it under Caddy's `request_body` limit (16 MB). |
| `S3_ENDPOINT_URL` | — | S3 endpoint (when backend=s3) |
| `S3_ACCESS_KEY_ID` | — | S3 access key |
| `S3_SECRET_KEY_ID` | — | S3 secret key |
| `S3_BUCKET_NAME` | — | S3 bucket |
| `S3_REGION` | `us-east-1` | S3 region |

### 3.9bis Invoicing (M3)

| Variable | Default | Description |
|----------|---------|-------------|
| `INVOICE_SELLER_NAME` | `Natimai Solutions` | Seller name printed on invoices |
| `INVOICE_SELLER_ADDRESS` | *(empty)* | **Required** — outside `ENVIRONMENT=local`, issuance is now **refused** (and an operational alert raised) while the trading name, the address or the registration number is missing. Not issuing is reversible: the order stays invoiceable once the identity is filled. Issuing a non-compliant document is not — the number is already burned in a gap-free sequence, and the invoice is immutable |
| `INVOICE_SELLER_REGISTRATION` | *(empty)* | **Required** — RC Papeete number + n° TAHITI |
| `INVOICE_SELLER_EMAIL` / `INVOICE_SELLER_PHONE` | *(empty)* | Contact details on the document |
| `INVOICE_LEGAL_FOOTER` | *(empty)* | Legal mentions printed at the bottom of the invoice |
| `INVOICE_FEES_TAX_CODE` | `TGC_NORMAL` | `TaxRate.code` used to ventilate shipping/payment fees in the tax breakdown. ⚠️ Confirm with your accountant |

> **PDF rendering** relies on WeasyPrint and its system libraries (pango,
> cairo, gdk-pixbuf) — present in the backend image. The import is lazy: on a
> host without them, invoices are still **issued and stored** (the snapshot is
> the source of truth) and only the PDF endpoints answer `503`
> (`invoice.pdf.unavailable`).

> **Delivery.** Issuing is not delivering: the invoice is e-mailed to the
> customer on `invoice.issued`, carrying the amounts and a link to the account
> page rather than the PDF (a missing font must not cost the customer the
> notice that they have been invoiced). `invoices.emailed_at` makes it
> idempotent — the outbox delivers at least once. This needs
> `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` set to a real provider; the value is
> validated at startup, an unknown one no longer falls back to `noop`.

> **Credit notes (Z2).** A refund issues a credit note (`AV-AAAA-NNNNN`) on its
> own gap-free counter, keyed on the refund id so a replayed event cannot burn
> a second number. The tax split comes from the original invoice, never
> recomputed, and is prorated on a partial refund. Endpoints: customer
> `GET /invoices/me/credit-notes[…]`, admin `GET /admin/credit-notes[…]`
> including `export.csv`.

### 3.10 Antivirus & security

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAMAV_ENABLED` | `false` | Scan uploaded attachments. **Mandatory outside `ENVIRONMENT=local`**: with `false` the NoOp scanner marks every file clean, so the backend refuses to start (warning only in local). The compose files and k8s manifests already set it to `true` |
| `CLAMAV_HOST` | `clamav` | ClamAV daemon host |
| `CLAMAV_PORT` | `3310` | ClamAV daemon port |
| `ENABLE_GROUP_PERMISSIONS` | `false` | Enable RBAC group checks (turn on after security groups are seeded and verified) |
| `SEED_FRENCH_POLYNESIA_LOGISTICS` | `true` | Seed the French Polynesia starter logistics (France → Papeete import corridor, PF zone tree + postal codes) on `initial_data`. Set `false` for a classic one-warehouse shop: only carriers and shipping statuses are seeded; create your warehouse and warehouse → customer routes (grid by weight band, franco) in *Trajets & Lieux* and your carriers in *Transporteurs* |
| `CLIENT_IP_HEADER` | *(empty)* | **Set this whenever the API sits behind Cloudflare or a reverse proxy.** Name of the trusted header carrying the real client IP: `CF-Connecting-IP` (Cloudflare) or `X-Forwarded-For` (Caddy/nginx/traefik — the **last**, proxy-appended entry of the chain is used; earlier entries are client-forgeable). Used by the login rate limiter — left empty, all requests share the proxy's IP and the per-IP throttle (10 login attempts/min) becomes a **global** throttle for every customer. Leave empty **only** when the API is directly exposed (a forged header would otherwise bypass the throttle). |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `10` | Login attempts per IP per window (Redis-backed, fail-open) |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `60` | Throttle window |
| `LOGIN_LOCKOUT_MAX_FAILURES` | `5` | Consecutive wrong passwords before the account locks |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Account lock duration |

---

## 4. Frontend (Vite, build‑time)

> **Docker build**: both frontend images accept a `VITE_API_URL` build arg
> (wired by `docker-compose.yml` from the root `.env`). Set
> `VITE_API_URL=https://api.<DOMAIN>` in the root `.env` before
> `docker compose build` — without it the images embed `localhost:8000`.
> The per-app `.env` files below apply to non‑Docker (dev) builds.

### Storefront (`frontend/`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | yes | Backend base URL **without** `/api/v1` (the client appends it), e.g. `https://api.example.com` |
| `VITE_PUBLIC_SITE_URL` | no | Public storefront URL (SEO/canonical links) |
| `VITE_OAUTH_ENABLED` | no | `true` shows the Google/Microsoft buttons on the login page. Leave unset/`false` until backend OAuth is configured (section 7) |

### Admin (`admin-frontend/`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | yes | Backend base URL without `/api/v1` |

---

## 5. Phase 2 — card payment requires a logged‑in customer

`POST /payments/initiate` is tied to a user account (`Payment.user_id` is
non‑nullable). The storefront therefore requires the customer to log in before
paying by card:

- Cart → **"Payer par carte bancaire"** → `/checkout`.
- If not authenticated, `/checkout` shows a **"Se connecter"** button →
  `/connexion?redirect=/checkout`.
- Login uses `POST /login/access-token` (email/password). Tokens are stored under
  the `frontend.*` localStorage keys.

No extra variable is needed for email/password login — only `VITE_API_URL`.

---

## 6. Minimal `.env` template (repository root)

```dotenv
# --- Core (required) ---
ENVIRONMENT=production
SECRET_KEY=replace-with-openssl-rand-hex-32
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=replace-with-strong-password
POSTGRES_DB=fastapi_ecommerce
REDIS_SERVER=redis
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=replace-with-strong-password

# --- URLs / CORS ---
FRONTEND_HOST=https://shop.example.com
BACKEND_CORS_ORIGINS=https://shop.example.com,https://admin.example.com
# Public API origin baked into the frontends at `docker compose build`
VITE_API_URL=https://api.example.com

# --- Email (Mailgun example) ---
EMAILS_FROM_EMAIL=no-reply@example.com
EMAILS_API_URL=https://api.mailgun.net/v3/example.com/messages
EMAILS_API_KEY=
EMAIL_SUPPORT=support@example.com
EMAIL_CONTACT=contact@example.com

# --- Payment (PayZen) ---
PAYZEN_MODE=PRODUCTION
PAYZEN_SITE_ID=
PAYZEN_API_PASSWORD_PROD=
PAYZEN_PUBLIC_KEY_PROD=
PAYZEN_API_ENDPOINT=https://api.osb.pf
PAYZEN_STATIC_URL=https://static.osb.pf

# --- Ingram Micro (catalog + auto PO) ---
INGRAM_ENVIRONMENT=production
INGRAM_CLIENT_ID=
INGRAM_CLIENT_SECRET=
INGRAM_CUSTOMER_NUMBER=
INGRAM_ORDER_CREATION_ENABLED=false
INGRAM_SHIP_TO_ADDRESS_LINE1=
INGRAM_SHIP_TO_CITY=
INGRAM_WEBHOOK_SECRET=  # generate: openssl rand -hex 32

# --- Icecat ---
ICECAT_USERNAME=
ICECAT_API_KEY=

# --- Storage ---
FILE_STORAGE_BACKEND=s3
MEDIA_PUBLIC_BASE_URL=https://api.example.pf
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_KEY_ID=
S3_BUCKET_NAME=

# --- OAuth social login (optional — see section 7) ---
# GOOGLE_CLIENT_ID=
# GOOGLE_CLIENT_SECRET=
# MICROSOFT_CLIENT_ID=
# MICROSOFT_CLIENT_SECRET=
# OAUTH_REDIRECT_BASE_URL=https://api.example.com
# FRONTEND_OAUTH_REDIRECT_URL=https://shop.example.com/oauth/callback
```

Frontend build env (set per frontend image, not in the root `.env`):

```dotenv
# frontend/.env
VITE_API_URL=https://api.example.com
VITE_PUBLIC_SITE_URL=https://shop.example.com
# VITE_OAUTH_ENABLED=true   # only once backend OAuth is configured

# admin-frontend/.env
VITE_API_URL=https://api.example.com
```

---

## 7. Enabling social login (Google / Microsoft)

1. Create OAuth apps and set redirect URIs to
   `${OAUTH_REDIRECT_BASE_URL}/api/v1/auth/{google|microsoft}/callback`.
2. Backend `.env`: set the provider id/secret, `OAUTH_REDIRECT_BASE_URL`
   (public backend URL) and `FRONTEND_OAUTH_REDIRECT_URL`
   (`https://shop.example.com/oauth/callback`).
3. Storefront build: set `VITE_OAUTH_ENABLED=true` and rebuild.

Flow: storefront → `GET /api/v1/auth/{provider}/login` → provider →
`GET /api/v1/auth/{provider}/callback` → the backend sets the **HttpOnly refresh
cookie** and redirects to `FRONTEND_OAUTH_REDIRECT_URL` (no token in the URL).
The `/oauth/callback` page then calls `/login/refresh-token` to obtain its
in-memory access token. Inactive users are rejected with `?oauth_error=user_inactive`.

---

## 8. Deployment chain — docker compose on the server (the single supported path)

**Decision (2026‑08‑25 production audit):** the stack is built and run **on the
server** with docker compose. The GHCR images pushed by
`.github/workflows/deploy.yml` are generic build artifacts (frontends built
without a real `VITE_API_URL`) and are **not** consumed by this path. The
Kubernetes manifests under `infra/k8s/` are **unmaintained** — do not deploy
from them (their secrets do not match `config.py` and `FIRST_SUPERUSER` is
missing, which crash‑loops the pods).

```bash
# 0. Prerequisites: root .env complete — including VITE_API_URL=https://api.<DOMAIN>
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml"

# 1. Get the code and build the images on the server.
#    --pull is not optional: base images are floating tags (node:22-alpine,
#    python:3.12-slim), and without it Docker keeps reusing whatever it pulled
#    months ago — which is how a "floating" tag ends up carrying known CVEs.
git pull
$COMPOSE build --pull

# 2. Migrations + seed via the one-shot migrate service
#    (runs `alembic upgrade head` then `app/initial_data.py` — idempotent).
#    Always BEFORE rolling out the new code.
$COMPOSE run --rm migrate

# 3. Roll out
$COMPOSE up -d

# 4. Post-deployment checks (section 10)
```

**Rollback:** `git checkout <previous-tag-or-sha>` then repeat build → up. A
migration rollback (`docker compose run --rm --entrypoint "" migrate uv run
alembic downgrade -1`) is only safe for reversible migrations — prefer
roll‑forward fixes, and restore from backup (section 12) as the last resort.

Then run the [post‑deployment checks](#10-postdeployment-checks).

### Production overrides checklist

| Variable | Dev default | Production |
|----------|-------------|------------|
| `ENVIRONMENT` | `local` | `production` |
| `INGRAM_ENVIRONMENT` | `sandbox` | `production` |
| `FILE_STORAGE_BACKEND` | `local` | `s3` |
| `PAYZEN_MODE` | `TEST` | `PRODUCTION` |
| `CLAMAV_ENABLED` | `false` | `true` (**required** — startup fails otherwise) |
| `INGRAM_ORDER_CREATION_ENABLED` | `false` | `true` (after ship‑to set) |
```

---

## 9. Reverse proxy (Caddy) — docker‑compose deployment

By default the docker‑compose deployment only exposes "raw" ports
(`8000`, `3000`, `3001`) without TLS. For production, a **Caddy** reverse proxy
([`infra/caddy/Caddyfile`](infra/caddy/Caddyfile) +
[`docker-compose.proxy.yml`](docker-compose.proxy.yml)) provides a single entry
point on `80`/`443`, **automatic Let's Encrypt TLS termination** and per‑subdomain
routing.

> ⚠️ The Kubernetes manifests (`infra/k8s/`, [`infra/DEPLOY.md`](infra/DEPLOY.md))
> are **unmaintained and currently broken** (see section 8) — docker‑compose is
> the only supported deployment path.

### Routing

| Host | Service | Internal port |
|------|---------|---------------|
| `${DOMAIN}` (bare domain) | `frontend` storefront (SSR) | 3000 |
| `www.${DOMAIN}` | 301 redirect → bare domain | — |
| `api.${DOMAIN}` | `api` (FastAPI) | 8000 |
| `admin.${DOMAIN}` | `admin-frontend` (nginx) | 80 |

> **Real client IP behind the proxy** — once the API is served through Caddy
> (or Cloudflare in front of it), set `CLIENT_IP_HEADER=X-Forwarded-For`
> (`CF-Connecting-IP` with Cloudflare) in the backend environment so the login
> rate limiter throttles the actual client, not the proxy. See §3.10.
>
> The `api.` site sets `header_up X-Forwarded-For {remote_host}`, which
> **replaces** any chain sent by the client instead of appending to it — a
> caller cannot pad the header to push its real address out of the trusted hop
> window. Keep `TRUSTED_PROXY_HOPS=1` with this setup; if you put a CDN in
> front of Caddy, drop that `header_up` line and set `TRUSTED_PROXY_HOPS=2`.

### Prerequisites

1. **DNS** — A/AAAA records for the bare domain, `www`, `api` and `admin` pointing
   to the server's public IP. Ports `80` and `443` open (HTTP‑01 challenge).
2. **Root `.env`** — `DOMAIN=example.com` and `ACME_EMAIL=<contact>`.
3. **Consistent public URLs** (see §3.1, §3.4, §4):
   - `FRONTEND_HOST=https://example.com`
   - `BACKEND_CORS_ORIGINS=https://example.com,https://admin.example.com`
   - `OAUTH_REDIRECT_BASE_URL=https://api.example.com` (if OAuth is enabled)
   - `FRONTEND_OAUTH_REDIRECT_URL=https://example.com/oauth/callback`
4. **Frontends rebuilt** with the public API URL (baked at build time):
   `frontend/.env` and `admin-frontend/.env` → `VITE_API_URL=https://api.example.com`
   (the client appends `/api/v1`). Without this, the browser would call `localhost:8000`.

### Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml up -d --build --pull always
```

- Caddy obtains and renews certificates automatically (Let's Encrypt).
- The `!reset` tag removes the direct port exposure of the app services (Caddy
  becomes the only ingress) → **Docker Compose ≥ 2.24** required.
- The `caddy_data` volume **must be persisted** (it holds the certificates) to avoid
  hitting the ACME rate limit on redeploys.

### Network isolation & port exposure

The `prod` + `proxy` overlay hardens exposure at two levels:

- **No host port published except `80`/`443`** (Caddy). The app ports
  (`8000`, `3000`, `3001`) and data ports (`5432`, `6379`, `3310`, `8080`) are
  removed via the `!reset` tag — reachable only on the internal Docker networks.
- **Network partitioning** (defined in `docker-compose.prod.yml`):

  | Network | `internal` | Services | Role |
  |---------|-----------|----------|------|
  | `default` | no (gateway) | caddy, frontend, admin-frontend, clamav, + compute | HTTP routing + Internet egress |
  | `dbnet` | **yes** | postgres, redis (+ api, workers, migrate, health-checker, adminer bridged) | data tier, **no Internet access** |

  Consequences: `postgres`/`redis` are on `dbnet` **only** → neither Caddy nor the
  frontends can reach them, and they have **no egress** (`internal` network). The
  `api` and workers are on both networks (egress via `default`, DB via `dbnet`).
  ClamAV stays on `default` because `freshclam` downloads its signatures from the
  Internet. Adminer is no longer exposed (`:8080` removed) — reach it via an SSH
  tunnel or `docker compose exec`.

### Verification

```bash
docker compose logs -f caddy           # certificate acquisition
curl -I https://api.example.com/api/v1/healthz/liveness
curl -I https://example.com            # storefront
curl -I https://admin.example.com
```

> Tune without exposing production: first test with the Let's Encrypt **staging**
> environment (untrusted certs but no rate limit) by adding
> `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` to the Caddyfile
> global block, then switch back to production once routing is validated.

---

## 10. Post‑deployment checks

After the first deploy (migrations + `initial_data` + workers up), verify:

**Health**
```bash
curl -s $API/api/v1/healthz/liveness   # {"status":"alive","timestamp":...}
# 200 + {"status":"ready","database":true,"redis":true} si tout répond,
# 503 + {"status":"degraded",...} sinon (d'où le -f ci-dessous qui échoue).
curl -fsS $API/api/v1/healthz/ready
```

**Database** — migrations applied and the full‑text search extension present:
```bash
docker compose exec api alembic current     # should be at head
docker compose exec postgres psql -U postgres -d fastapi_ecommerce \
  -c "SELECT extname FROM pg_extension WHERE extname='pg_trgm';"   # 1 row
```

**FX rates seeded** — `GET /api/v1/admin/currency-rates` should return active EUR/USD.

**Async health** — the observability dashboard (`GET /api/v1/utils/observability/dashboard`, superuser) surfaces ARQ + outbox state. Watch for:
- `arq_jobs.queued` high / `arq_jobs.failed > 0` → worker behind or failing (`docker compose logs arq-worker`).
- `outbox_jobs.stale_pending > 0` (events stuck > 15 min) or `outbox_jobs.failed > 0` → see the runbook below.
- no `*_product_sync` job in the last ~7 h → the supplier cron did not fire.

**Supplier sync** — trigger one catalogue sync and confirm products are created (`is_supplier_managed=true`), an enrichment job is queued, enriched products flip to `is_enriched=true` and appear on the public `GET /api/v1/products`.

**FX staleness** — there is no automatic FX cron yet; check that no active rate's `valid_from` is older than ~30 days, and refresh via `PUT /api/v1/admin/currency-rates/{code}` if needed.

## 11. Operations runbook

Operational actions, aligned with the app's real entry points. Examples assume a
superuser bearer token (`$AUTH = "Authorization: Bearer <token>"` from
`POST /api/v1/login/access-token`).

**Restart supplier sync (Ingram / Icecat)**
```bash
curl -s $API/api/v1/suppliers/ingram_micro/health -H "$AUTH"
curl -s -X POST $API/api/v1/suppliers/ingram_micro/sync/products \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"categories":["Ordinateur/Serveur"]}'
curl -s -X POST $API/api/v1/icecat/enrich/batch \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"limit":50}'
```

**Restart ARQ / outbox jobs**
```bash
docker compose restart arq-worker outbox-poller
# retry failed outbox events, then force one drain pass
docker compose exec api python app/scripts/outbox_poller.py --mode retry --max-attempts 5
docker compose exec api python app/scripts/outbox_poller.py --mode once --max-events 200
# outbox health check / recover missing jobs
docker compose exec api python -m app.outbox.health
```

**Replay a failed PayZen IPN** — diagnose, then replay with a valid signature:
```bash
docker compose exec postgres psql -U postgres -d fastapi_ecommerce -c \
  "SELECT id, provider_reference, provider_data->>'trans_status' AS status, updated_at \
   FROM payments ORDER BY updated_at DESC LIMIT 30;"
python app/scripts/replay_payzen_ipn.py --base-url $API \
  --order-id <ORDER_ID> --trans-status PAID --trans-uuid <TRANS_UUID> \
  --amount 1500 --currency 953 --card-brand VISA
# or from a captured kr-answer payload: --kr-answer-file ./tmp/kr-answer.json
# useful flags: --dry-run, --mode TEST|PRODUCTION, --hmac-key <key>
```

**Escalate** if, after a restart, an IPN signature keeps failing with correct keys,
the outbox stays degraded after `app.outbox.health`, or supplier jobs keep erroring.
Provide: ARQ `job_id`s, the `payment_id`/`provider_reference`, and `api` /
`arq-worker` / `outbox-poller` log excerpts + the observability dashboard output.

---

## 12. Backups & restore

**Nothing is backed up automatically until you wire this up.** Before accepting
the first real order: schedule the backup script, configure the offsite copy,
and **run the restore procedure once for real** — an untested backup is not a
backup.

### What to back up

| Data | Where | How |
|------|-------|-----|
| PostgreSQL (orders, payments, catalog) | `postgres` service | `pg_dump -Fc` via the script below |
| Uploaded documents (purchase orders…) | `storage_data` volume | tar streamed from the `api` container |
| Caddy certificates | `caddy_data` volume | nice‑to‑have (Let's Encrypt reissues, but reissue is rate‑limited) |
| Root `.env` | server filesystem | copy it to your password manager / secret store — without it nothing restarts |

### Schedule

[`scripts/backup/backup.sh`](scripts/backup/backup.sh) dumps the database
(custom format), archives the uploads volume, verifies **both** artefacts
(`PGDMP` magic for the dump, `tar tzf` for the archive), pushes them offsite,
and only then rotates old files (14 days by default). Each artefact is written
to a `.part` file and renamed only once verified, so a truncated dump can never
masquerade as a good backup.

**Offsite copy is mandatory** (disk failure and ransomware both take the local
backups with them), so it gates the rotation: with no `OFFSITE_RCLONE_REMOTE`
the script warns and **skips the rotation entirely** rather than deleting
archives that never left this disk.

```bash
0 2 * * * cd /opt/fastapi-ecommerce && OFFSITE_RCLONE_REMOTE=remote:ecommerce-backups \
  ./scripts/backup/backup.sh >> /var/log/ecommerce-backup.log 2>&1
```

Local-only rotation can be forced with `RETENTION_LOCAL_ONLY=true` if you push
the backups elsewhere by another means (`scp`, object storage, snapshots).

Any failure exits non-zero and, when `ALERT_WEBHOOK_URL` is set, posts to the
alerting webhook — a backup that fails silently is worse than none, because you
believe you are covered. A ready-to-install crontab lives at
[`scripts/backup/ecommerce-backup.cron`](scripts/backup/ecommerce-backup.cron),
and [`scripts/backup/restore.sh`](scripts/backup/restore.sh) automates the
restore rehearsal described below.

### Restore procedure (test it BEFORE go‑live)

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml"

# 1. Stop everything that writes to the DB (keep postgres up)
$COMPOSE stop api arq-worker outbox-poller outbox-health-checker

# 2. Restore the database (drops and recreates objects from the dump)
$COMPOSE exec -T postgres pg_restore -U postgres -d fastapi_ecommerce \
  --clean --if-exists --no-owner < backups/db_<STAMP>.dump

# 3. Restore the uploads volume
#    --index : `api` runs with replicas: 2 in production, so a bare `exec` is
#    ambiguous. Both replicas share the same volume, index 1 is fine.
$COMPOSE exec --index 1 -T api tar xzf - -C /tmp < backups/storage_<STAMP>.tar.gz

# 4. Restart and check
$COMPOSE up -d
curl -fsS https://api.<DOMAIN>/api/v1/healthz/ready
```

### Rehearsal — do this before the first order

[`scripts/backup/restore.sh`](scripts/backup/restore.sh) automates both the
rehearsal and the real restore. **The default mode is the rehearsal**: it spins
up a throwaway PostgreSQL container, restores the dump into it, prints the row
counts of the tables you would most regret losing (`orders`, `order_lines`,
`payments`, `invoices`, `products`, `users`) and removes the container. Nothing
in production is touched.

```bash
# Rehearsal (safe) — compare the printed counts against production
./scripts/backup/restore.sh backups/db_20260827_020000.dump

# Real restore (destructive, asks for confirmation, stops the writers first)
./scripts/backup/restore.sh --production backups/db_20260827_020000.dump
```

The script refuses a file that is not a custom‑format dump before doing
anything, so a truncated or half‑transferred backup fails fast rather than
half‑way through a production restore.

---

## 13. Legal identity — fill before opening (L1)

The company's identity is a **launch blocker**: incomplete legal notices expose
the publisher, and an invoice without a company name and registration number is
not a valid accounting document.

It is **not stored in the repository** — this codebase is a template, and a
company's details are deployment data. The values live in the `system_settings`
table under `legal_*` keys, editable from the back-office (**Réglages système**)
without a redeploy. Both surfaces read the same rows:

- the storefront legal pages (CGV, mentions légales, confidentialité), served
  publicly via `GET /system/settings` — publishing this information is a legal
  obligation, so no authentication is required;
- the invoice header, which freezes a copy at issuance. Editing a value later
  never rewrites an invoice already issued.

One source at runtime, so an invoice and the legal notices cannot quote
different addresses.

### Filling them in

The keys are created empty by `app.initial_data` (run by the `migrate`
service), so they appear in the back-office ready to fill. Either:

- **Back-office** → Réglages système → edit each `legal_*` row (its description
  says what belongs in it); or
- `PUT /api/v1/admin/system-settings/{key}` with `{"value": "…"}`.

`INVOICE_ISSUER_*` in the root `.env` are now only **bootstrap** values: when a
key is created for the first time and the matching variable is set, it becomes
the initial value. They never overwrite anything already saved — the seed runs
on every deploy, and clobbering the owner's text with a forgotten environment
variable is exactly the silent regression to avoid.

| Key | What it is | Bootstrapped from |
|-----|-----------|-------------------|
| `legal_trading_name` | Trading name | `INVOICE_ISSUER_NAME` |
| `legal_form` | Legal form (SARL, SAS…) | `INVOICE_ISSUER_LEGAL_FORM` |
| `legal_share_capital` | Share capital, XPF (amount only) | — |
| `legal_head_office_address` | Head-office address | `INVOICE_ISSUER_ADDRESS` |
| `legal_rc_number` | Papeete Registre du commerce number | — |
| `legal_tahiti_number` | TAHITI number (local SIRET equivalent) | `INVOICE_ISSUER_REGISTRATION_NUMBER` |
| `legal_tax_id` | Tax identifier | `INVOICE_ISSUER_TAX_ID` |
| `legal_contact_email` / `legal_contact_phone` | General contact | `INVOICE_ISSUER_EMAIL` / `_PHONE` |
| `legal_publication_director` | Publication director | — |
| `legal_host_name` / `_address` / `_contact` | Site host | — |
| `legal_support_email` | After-sales contact | — |
| `legal_cgv_version_date` | CGV effective date | — |
| `legal_privacy_updated_date` | Privacy policy update date | — |
| `legal_delivery_reservation_delay` | Window to raise a delivery reservation | — |
| `legal_invoice_retention` / `legal_technical_log_retention` | Retention periods | — |
| `legal_payment_terms` / `legal_late_penalty_terms` | Invoice footer | `INVOICE_PAYMENT_TERMS` / `_LATE_PENALTY_TERMS` |
| `legal_withdrawal_regime` | Withdrawal regime | — |
| `legal_mediation_scheme` | Consumer mediation scheme | — |

Three of these are **legal questions, not data entry** — they need counsel:

- `legal_withdrawal_regime` — the withdrawal regime applicable to distance
  selling in French Polynesia (the French Code de la consommation does not
  apply directly there): period, how it is exercised, exclusions, return
  shipping costs. If no mandatory regime applies, state the seller's commercial
  return policy instead.
- `legal_mediation_scheme` — the consumer mediation scheme applicable locally,
  if any.
- `legal_invoice_retention` / `legal_technical_log_retention` — retention
  periods to agree with the accountant.

### Check it

```bash
./scripts/release/check-legal-placeholders.sh                       # localhost
API_URL=https://api.example.pf ./scripts/release/check-legal-placeholders.sh
```

It queries the API, so it checks the **environment you point it at**, not what
is written in the repository. It separates the keys that block invoicing from
those that only affect the legal pages. Exit codes: `0` complete, `1`
incomplete, `2` API unreachable or keys never seeded.

Unfilled values render **in red, underlined** on the public pages, and the
invoice PDF shows an `[À COMPLÉTER]` marker — a gap is visible, not silent.

> The script only checks that the fields are **filled**. It says nothing about
> whether the wording is legally sound — the three documents still have to be
> reviewed by a lawyer before opening (L1 in the work plan).

---

## 14. Opening readiness report (PP-F)

The checks the work plan requires to be **done and recorded** before opening.
A reminder nobody knows today's value of is not a check, so they are measured:

```bash
docker compose exec -T api python -m app.scripts.release_readiness
```

Read-only, exits non‑zero when a threshold is crossed.

| Check | Threshold | Why it matters |
|-------|-----------|----------------|
| Icecat enrichment rate | ≥ 80 % of active products | The public search filters on `is_enriched`: an unenriched product is invisible whatever its stock. Below the threshold the storefront is nearly empty — widen Icecat (Full) or plan a specs‑less display. |
| Products without `category_id` | 0 | No category means no filters, no default tax rate — and, since the customs rate is inherited from the category, no resolvable customs rate either. |
| Enriched products hidden by the publication guard | 0 | A product whose customs rate resolves nowhere, or that has no weight, would sell below cost, so the storefront hides it instead of showing a wrong price. Fix by entering the per-category customs rate (**§15** — how to establish it) and filling the missing weights; `GET /admin/catalog/publication-report` breaks the backlog down by category. **Expect this to fail on a freshly synced catalogue** — the supplier feed never carries a customs rate. |
| Manual FX rate age | ≤ 30 days | Supplier costs are converted with these rates; one frozen for months skews every displayed price. |
| Import cost parameters (declaration fee, insurance) | informational | Both are paid whether or not they are billed: at zero they come straight out of the margin, silently. Zero is a legitimate choice (fees bundled by the forwarder, no policy taken) — but a deliberate one, set in **§16**. |
| Attachment storage volume | informational | Compare against the storage volume's capacity. |

Run it again after the first supplier sync, and whenever the catalogue is
reloaded.

---

## 15. Establishing the per‑category customs rates

Section 14 refuses to go green until every enriched product resolves a customs
rate, and the supplier feed never carries one. This section is the procedure to
produce those numbers. It is data entry, not code — but it is the entry that
decides whether every price on the storefront is right.

### What the number has to be

`Category.default_customs_rate_pct` is a **single effective ad‑valorem rate**
applied to the CAF value (cost + freight + insurance) in
`calculate_sale_price`. Real Polynesian import taxation is not a single rate: it
stacks customs duty, the local development tax (TDL) — whose base is **CAF plus
the duty**, so it cascades — and, depending on the tariff position, further
levies (PID, TS, TEAP, PEAGE, SETIL, CPS…). The rate you enter must be the
**aggregate of all of them expressed as one percentage of CAF**.

Do not try to reconstruct that stack by hand. The CCISM, which trains customs
declarants for a living, describes the number of taxes and their interaction as
complex enough to warrant a course. Derive the rate from the official simulator
instead, which applies the real cascade for you.

### Procedure, per category

1. **Find the tariff position.** Open the
   [simulateur de taxation](https://simulateur-douane-polynesie.com/) (Direction
   régionale des douanes de Polynésie française). You can either enter a customs
   code directly or pick from its 97 product chapters. Work from a real,
   representative product of the category — a specific laptop, not "laptops in
   general".
2. **Simulate a round CAF value.** Enter a value in XPF that is representative of
   what you actually import in that category (say 200 000 XPF for a laptop, not
   1 000). Set **origin** to match your corridor — the France → Papeete corridor
   is EU origin, and origin changes the rate — and set the **transport mode** to
   the one most of that category travels by.
3. **Read the total, then take out the VAT.** ⚠️ **This is the step that goes
   wrong.** The simulator returns *droits et taxes* — duties **and** taxes — and
   import VAT (16 % normal rate) is levied on imports, so expect it in there.
   The application already applies the consumption tax separately, from
   `TaxRate` resolved product → category → territory. Fold the simulator's VAT
   into `customs_rate_pct` and **every price carries VAT twice**. So: find the
   VAT line in the simulated breakdown and exclude it. If the output gives only
   a lump sum with no breakdown, do not guess — ask the douanes or a broker for
   the detail before entering anything.
4. **Derive the percentage.** `taux_eff = (duties excluding VAT ÷ simulated CAF)
   × 100`. Enter it in the admin, **Douane par catégorie**.
5. **Check it is genuinely ad valorem.** Re‑run the same simulation at a very
   different value (say ×5). If the ratio moves, the position carries a
   *specific* levy (per unit or per kilo) that a percentage cannot represent
   exactly. Derive the rate at the value closest to your real basket and write
   down that the category is approximate — and re‑derive it if your price points
   shift.

### Worked example — and why step 3 matters this much

The price is built as two **separate** multipliers:

```
price = CAF × (1 + customs) × (1 + margin) × (1 + tax)
                   ↑                              ↑
        "Douane par catégorie"          TaxRate (TGC/VAT 16 %)
```

The tax is already applied at the end. The customs field is not meant to carry it.

Take a CAF of 100 000 XPF on a position bearing 5 % of duties, sold to a price
group carrying a 30 % margin. The simulator reports what you actually pay at the
border:

| Line | Amount |
|------|--------|
| Duties (customs + TDL + other levies) | 5 000 |
| Import VAT, 16 % on 105 000 | 16 800 |
| **Simulator total** | **21 800** — i.e. 21.8 % of CAF |

Enter **21.8** and the application computes
`100 000 × 1.218 × 1.30 × 1.16 = 183 674`.
Enter **5** and it computes
`100 000 × 1.05 × 1.30 × 1.16 = 158 340`.

The gap is not an approximation, it is exactly ×1.16. The simulator total equals
`(1 + duties) × (1 + VAT)` by construction, so folding it into the customs field
applies VAT there **and** again at the end: `(1 + duties) × (1 + VAT)²`. Every
price in the catalogue would be 16 % too expensive. Hence: take the total, drop
the VAT line, enter `5`.

### When a category spans several tariff positions

Categories here come from supplier subcategories ("Ordinateur Portable"), which
are coarser than tariff positions — so one category can legitimately cover
several rates. **Simulate the two or three positions the category realistically
covers**, then:

- **Spread ≤ 2 points** → enter the **highest** of them.
- **Spread > 2 points** → **split the category** rather than average it. The
  supplier subcategory allowlist (`SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST`) and the
  per‑product override (`PUT /admin/products/{id}/customs-rate`, which wins over
  the category) are both available for that.

Take the highest rather than the average, because the two errors are not
symmetric: under‑pricing is invisible and costs margin on every unit sold, while
over‑pricing is visible and costs at most a sale you can still win back. This is
the same reasoning that makes an unresolved rate hide a product instead of
defaulting to zero.

> **Open question, to settle with the accountant before entering anything:**
> whether import VAT is genuinely recoverable for the company (F7 in the work
> plan).
>
> Step 3 assumes it is: you pay VAT at the border, reclaim it as a registered
> business, then charge VAT to the customer and remit it. On that reading import
> VAT is a **cash‑flow item, not a cost**, and has no business being in the cost
> base — which is exactly why it gets dropped from the simulator total.
>
> If the answer is the opposite, import VAT becomes a real cost that has to be
> carried *inside* the effective rate, and step 3 changes. **The number you type
> differs either way** — so get the answer before deriving forty categories at
> the simulator, not after.

### Record what you did

The rate alone is unauditable: six months on, nobody can tell which position it
came from or whether it still holds. Keep this table filled as you go, and
re‑check it at least once a year and whenever the tariff is revised.

| Category | Tariff position used | Origin | Effective rate | Derived on | Notes |
|----------|---------------------|--------|----------------|-----------|-------|
| _e.g. Ordinateur Portable_ | _8471.30_ | _UE_ | _x.xx %_ | _YYYY‑MM‑DD_ | _specific levy? split?_ |

If this table outgrows the document, the natural next step is a
`Category.customs_tariff_position` column so the justification lives next to the
rate instead of in a file beside it.

> The simulator's own output is explicitly **indicative and non‑contractual**.
> For the positions carrying most of your volume, have the numbers confirmed by
> a customs broker or by the douanes directly before opening — the whole
> catalogue's pricing rests on them.

### Sources

Checked on 2026‑08‑29 — verify before relying on them, tariffs get revised.

- [Simulateur de taxation — douanes de Polynésie française](https://simulateur-douane-polynesie.com/)
  (tariff code or 97 chapters, value in XPF, origin, transport mode; output explicitly indicative)
- [Le calcul des droits de douanes — CCISM](https://www.ccism.pf/la-ccism/exporter/effectuer-ses-formalites-l-import/le-calcul-des-droits-de-douanes)
  (customs value = commercial price + transport + insurance; the four inputs; complexity warning)
- [Tarif des douanes de Polynésie française](https://www.polynesie-francaise.pref.gouv.fr/contenu/telechargement/50120/319486/file/Annexe.pdf)
  (full tariff, common rate DC and reduced rate TR for EU origin)
- [La TVA — DICP Polynésie française](https://www.service-public.pf/dicp/professionnels/vos-impots/taxe-sur-la-valeur-ajoutee/)
  (16 % normal rate, applies to imports)

Two points that shaped the procedure above and are worth re‑checking directly:
the **TDL base is the CAF value plus the customs duty** (hence the cascade), and
the TDL is a **protective tax targeting a list of tariff positions** competing
with local production — so it may simply not apply to IT equipment. Confirm per
position rather than assuming either way.

---

## 16. Per‑declaration customs charges and freight insurance

Two costs of importing that the ad‑valorem rate of §15 does **not** cover. Both
are paid whether or not they are billed: left at zero they come out of the
margin without raising anything. Neither is code — they are numbers to obtain
and enter, and the mechanism that receives them exists.

### 16.1 Charges owed per declaration (F3)

Customs redevances, participations and the forwarder's file fee are owed **per
declaration**, not per article. Spreading them over the lines would make the
unit price wrong in both directions depending on cart size — small carts
over‑charged, large ones under‑charged — so they are billed once per shipment,
like a leg's fixed forfait.

They are carried by the **customs place**, not by the route:

```bash
# Find the customs place: the one this corridor's import leg lands on,
# flagged customs_clearance = true (Papeete, on the seeded corridor)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "$API/place/?limit=200" \
  | jq '.data[] | select(.customs_clearance) | {id, name}'

# Set the aggregate per-declaration amount (reference currency, XPF)
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"customs_declaration_fee": "3500.00"}' \
     "$API/place/{place_id}"
```

Consequences of that placement, all deliberate:

- Several corridors (France, US, Asia) clearing at the same border are **one**
  declaration, because the fee is deduplicated by place. Two distinct customs
  places mean two territories, hence genuinely two declarations.
- The amount is billed even when no leg is charged to the customer — the import
  leg's freight is already inside the unit price (F6), the declaration is not.
- `NULL` or `0` bills nothing, and that is the shipped default: nothing changes
  until you enter a number.

**Where to find the numbers**: the forwarder's fee schedule (file fee, customs
brokerage) and the customs charges listed on a real declaration. Take them from
an actual invoice rather than from the simulator — the simulator prices the
goods, not the paperwork.

> **Do not fold these into the §15 category rate.** That rate is ad valorem: a
> fixed charge encoded as a percentage over‑bills a large shipment and
> under‑bills a small one, which is exactly the defect this separation removes.

**Known limitations**, both erring on the over‑charging side — visible and
refundable, unlike under‑charging:

- An order served entirely from **local stock** clears no customs yet pays the
  fee: which lines come from the supplier is only decided later, inside the
  checkout transaction, after the total is frozen.
- When several orders are **consolidated** into one declaration, each carries
  the whole fee.

Until the logistics phase makes the billing consolidation‑aware, set the amount
to the expected **per‑order share**, not the full declaration cost.

### 16.2 Freight insurance (F4)

`INSURANCE_RATE_PCT` is applied to **cost + variable import freight** — the CAF
basis an ad valorem policy actually covers — before customs duty. The default
`0.0` means no insurance in the price.

1. **Take out a real ad valorem policy.** Carrier and forwarder liability caps
   are per kilo and indemnify almost nothing on dense, expensive goods — a
   stolen GPU is the textbook case.
2. **Enter the rate the insurer bills**, in the API's `.env`
   (`INSURANCE_RATE_PCT=0.35` for 0.35 %), then restart the API. A policy paid
   for but not entered here is a premium that never comes back through sales.
3. Check it landed: the readiness report (§14) prints the current rate.

Storefront prices are recomputed from the CAF formula, so a rate change takes
effect on the next price computation — verify a product's price moved as
expected before considering the change applied.

### 16.3 Where the goods come from: main warehouse, customs regime, dropshipping

Three facts live on places (*Trajets & Lieux*), not in code:

1. **Main warehouse** — flag exactly one warehouse with the star action
   (« Définir comme entrepôt principal »). Supplier goods converge there and
   the last leg to the customer starts there. The French Polynesia seed flags
   the Papeete warehouse when none is set; a classic shop flags its own.
2. **Customs regime of a supplier place** — *Automatique* compares the
   supplier's country with the main warehouse's: same country = local (no
   customs, no import freight, no insurance in the price; no customs rate
   needed to publish; no per-declaration fee), other country = import (§15,
   §16.1, §16.2 apply). Two ways to bend the rule:
   - the `customs_free_countries` system setting (*Paramètres*): ISO codes,
     comma-separated, whose suppliers count as local (customs union, same
     customs territory) — e.g. `FR,DE` for a shop inside the EU;
   - *Local* / *Import* forced on one place, whatever its country.
   A supplier place **without a country** keeps the historical behaviour
   (customs applied): set the country, it drives the price.
3. **Dropshipping** — a supplier place flagged « livre directement le client »
   ships straight to the customer: the order gets a supplier → customer leg
   (the supplier's own customer route if you created one, else the delivery
   mode the customer chose) instead of supplier → main warehouse → customer.
   The customer currently pays the chosen delivery mode once per order, not
   once per parcel — see the work plan before enabling it on several
   suppliers.
