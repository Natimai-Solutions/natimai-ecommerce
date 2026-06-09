# Deployment guide

Environment variables and first‑deployment steps for the e‑commerce stack
(FastAPI backend, Quasar storefront, Quasar admin, PostgreSQL, Redis, ARQ worker,
outbox poller, ClamAV).

> Operational runbooks (health checks, restarts, FX rates) live in
> [`backend/docs/development/OPS_ENV_ET_CHECKS.md`](backend/docs/development/OPS_ENV_ET_CHECKS.md)
> and [`RUNBOOK_OPERATIONNEL_E3.md`](backend/docs/development/RUNBOOK_OPERATIONNEL_E3.md)
> (French). This file is the canonical reference for **which variables to set**.

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

When `ENVIRONMENT != local`, the app refuses to start if `SECRET_KEY`,
`POSTGRES_PASSWORD` or `FIRST_SUPERUSER_PASSWORD` are left at `changethis`.

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
| `SENTRY_DSN` | — | Error monitoring DSN |

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

### 3.4 Authentication — social login (OAuth 2.0) · Phase 2

Optional. Required only to enable "Continue with Google / Microsoft".

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client id |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `MICROSOFT_CLIENT_ID` | — | Microsoft (Entra) app id |
| `MICROSOFT_CLIENT_SECRET` | — | Microsoft app secret |
| `MICROSOFT_TENANT_ID` | `common` | Microsoft tenant (`common` for multi‑tenant) |
| `OAUTH_REDIRECT_BASE_URL` | — | Public **backend** URL used to build the provider `redirect_uri`, e.g. `https://api.example.com` |
| `FRONTEND_OAUTH_REDIRECT_URL` | — | **Storefront** URL the backend redirects to after login. Must point at the callback route: `https://shop.example.com/oauth/callback` |

If a provider's id/secret are missing, its `/auth/{provider}/login` endpoint
returns `503 oauth.provider.not_configured`. See section 7 to enable end‑to‑end.

### 3.5 Payment — PayZen / Lyra · Phase 2

| Variable | Default | Description |
|----------|---------|-------------|
| `PAYZEN_SITE_ID` | — | PayZen site id |
| `PAYZEN_API_PASSWORD_TEST` | — | REST API password (TEST mode) |
| `PAYZEN_API_PASSWORD_PROD` | — | REST API password (PRODUCTION mode) |
| `PAYZEN_PUBLIC_KEY_TEST` | — | Public key for the SmartForm JS (TEST) |
| `PAYZEN_PUBLIC_KEY_PROD` | — | Public key for the SmartForm JS (PRODUCTION) |
| `PAYZEN_MODE` | `TEST` | Set `PRODUCTION` in prod |
| `PAYZEN_API_ENDPOINT` | `https://api.osb.pf` | REST API base URL |
| `PAYZEN_STATIC_URL` | `https://static.osb.pf` | Base URL of the SmartForm JS/CSS SDK (Krypton client) |
| `PAYZEN_IPN_URL` | — | Server‑to‑server webhook URL (auto‑computed if empty) |
| `PAYZEN_RETURN_URL` | — | Default browser return URL after payment |
| `PAYZEN_CURRENCY` | `XPF` | Billing currency |
| `REFERENCE_CURRENCY` | `XPF` | Pivot currency for cost/price normalisation |
| `INSURANCE_RATE_PCT` | `0.0` | Insurance % added before customs (CIF basis) |

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

### 3.9 File storage (payment attachments)

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_STORAGE_BACKEND` | `local` | `s3` in production |
| `FILE_STORAGE_LOCAL_ROOT` | `/tmp/fastapi_ecommerce_storage` | Dev only |
| `S3_ENDPOINT_URL` | — | S3 endpoint (when backend=s3) |
| `S3_ACCESS_KEY_ID` | — | S3 access key |
| `S3_SECRET_KEY_ID` | — | S3 secret key |
| `S3_BUCKET_NAME` | — | S3 bucket |
| `S3_REGION` | `us-east-1` | S3 region |

### 3.10 Antivirus & security

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAMAV_ENABLED` | `false` | Scan uploaded attachments (`true` if ClamAV deployed) |
| `CLAMAV_HOST` | `clamav` | ClamAV daemon host |
| `CLAMAV_PORT` | `3310` | ClamAV daemon port |
| `ENABLE_GROUP_PERMISSIONS` | `false` | Enable RBAC group checks (turn on after security groups are seeded and verified) |

---

## 4. Frontend (Vite, build‑time)

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
`GET /api/v1/auth/{provider}/callback` → redirect to
`FRONTEND_OAUTH_REDIRECT_URL?access_token=…&refresh_token=…`, captured by the
`/oauth/callback` page. Inactive users are rejected with `?oauth_error=user_inactive`.

---

## 8. First deployment

```bash
# 1. Apply database migrations
docker compose exec api alembic upgrade head
docker compose exec api alembic current   # expect a single head

# 2. Seed initial data (superuser, payment statuses, price groups,
#    TGC tax rates, FX rates, security groups)
docker compose exec api python -m app.initial_data

# 3. Bring up the async workers
docker compose up -d arq-worker outbox-poller
```

Then verify health and supplier sync as described in
[`OPS_ENV_ET_CHECKS.md`](backend/docs/development/OPS_ENV_ET_CHECKS.md) §2–3.

### Production overrides checklist

| Variable | Dev default | Production |
|----------|-------------|------------|
| `ENVIRONMENT` | `local` | `production` |
| `INGRAM_ENVIRONMENT` | `sandbox` | `production` |
| `FILE_STORAGE_BACKEND` | `local` | `s3` |
| `PAYZEN_MODE` | `TEST` | `PRODUCTION` |
| `CLAMAV_ENABLED` | `false` | `true` (if ClamAV deployed) |
| `INGRAM_ORDER_CREATION_ENABLED` | `false` | `true` (after ship‑to set) |
```
