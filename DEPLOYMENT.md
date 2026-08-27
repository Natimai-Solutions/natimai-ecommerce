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
| `PAYZEN_MANUAL_VALIDATION` | `false` | `true` → authorise the card at checkout (status `Authorized`) and capture later (deferred debit), e.g. at shipment via `POST /admin/payments/{id}/capture`. ⚠️ authorisations expire (~7 days). |
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
| `CLAMAV_ENABLED` | `false` | Scan uploaded attachments. **Mandatory outside `ENVIRONMENT=local`**: with `false` the NoOp scanner marks every file clean, so the backend refuses to start (warning only in local). The compose files and k8s manifests already set it to `true` |
| `CLAMAV_HOST` | `clamav` | ClamAV daemon host |
| `CLAMAV_PORT` | `3310` | ClamAV daemon port |
| `ENABLE_GROUP_PERMISSIONS` | `false` | Enable RBAC group checks (turn on after security groups are seeded and verified) |
| `CLIENT_IP_HEADER` | *(empty)* | **Set this whenever the API sits behind Cloudflare or a reverse proxy.** Name of the trusted header carrying the real client IP: `CF-Connecting-IP` (Cloudflare) or `X-Forwarded-For` (Caddy/nginx/traefik). Used by the login rate limiter — left empty, all requests share the proxy's IP and the per-IP throttle (10 login attempts/min) becomes a **global** throttle for every customer. Leave empty **only** when the API is directly exposed (a forged header would otherwise bypass the throttle). |
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

# 1. Get the code and build the images on the server
git pull
$COMPOSE build

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
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.proxy.yml up -d --build
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

For a **blank-slate rehearsal** (recommended): restore into a throwaway
container instead — `docker run --rm -d --name pg-restore-test postgres:16-alpine`,
`pg_restore` into it, and spot‑check row counts (`orders`, `payments`,
`products`) against production.
