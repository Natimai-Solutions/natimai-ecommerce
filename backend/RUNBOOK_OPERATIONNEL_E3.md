# Runbook Operationnel E3

Ce runbook couvre les actions operationnelles MVP suivantes:
- relance des synchronisations Ingram et Icecat
- relance des jobs ARQ et outbox
- traitement des IPN PayZen en echec

Il est aligne sur les points d'entree reels de l'application.

## 1. Pre requis

- API accessible (par defaut `http://localhost:8000`)
- Superuser disponible pour les endpoints admin
- Stack locale demarree (`docker compose up -d`) ou environnement backend local actif

Variables utilisees dans les exemples PowerShell:

```powershell
$API_BASE = "http://localhost:8000"
$OPS_ADMIN_EMAIL = "admin@example.com"
$OPS_ADMIN_PASSWORD = "change-me"
```

Obtention du token superuser:

```powershell
$tokenResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/login/access-token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=$OPS_ADMIN_EMAIL&password=$OPS_ADMIN_PASSWORD"

$AUTH_HEADERS = @{ Authorization = "Bearer $($tokenResponse.access_token)" }
```

## 2. Relance sync Ingram et Icecat

### 2.1 Ingram

Verifier la sante de l'integration:

```powershell
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/ingram/health" -Headers $AUTH_HEADERS
```

Relancer une sync catalogue:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/ingram/sync/products" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"categories":["Ordinateur/Serveur"]}'
```

Relancer un refresh inventaire:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/ingram/sync/inventory" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"skus":null}'
```

### 2.2 Icecat

Verifier le statut:

```powershell
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/icecat/status" -Headers $AUTH_HEADERS
```

Relancer enrichissement unitaire:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/icecat/enrich" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"product_id":"<UUID_PRODUIT>"}'
```

Relancer enrichissement batch:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/icecat/enrich/batch" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"limit":50}'
```

### 2.3 Verification post relance

- observer les logs worker/poller
- controler l'endpoint observabilite

```powershell
docker compose logs --since=10m arq-worker outbox-poller api
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/utils/observability/dashboard"
```

## 3. Relance jobs ARQ et outbox

### 3.1 Diagnostic rapide

```powershell
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/utils/observability/dashboard"
```

Points de vigilance:
- `outbox_jobs.stale_pending > 0`
- `outbox_jobs.running` bloque longtemps
- hausse des erreurs checkout

### 3.2 Actions de relance standard

Redemarrer les workers:

```powershell
docker compose restart arq-worker outbox-poller
```

Relancer les evenements outbox en erreur puis forcer un passage:

```powershell
docker compose exec api uv run python app/scripts/outbox_poller.py --mode retry --max-attempts 5
docker compose exec api uv run python app/scripts/outbox_poller.py --mode once --max-events 200
```

Lancer un check/recovery outbox:

```powershell
docker compose exec api uv run python -m app.outbox.health
```

### 3.3 Verification

```powershell
docker compose logs --since=10m arq-worker outbox-poller
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/utils/observability/dashboard"
```

Attendu:
- baisse de `stale_pending`
- reprise des statuts `DONE`
- absence de boucle d'erreur continue dans les logs

## 4. Traitement IPN PayZen en echec

### 4.1 Detection

Signaux frequents:
- retours 400/500 sur `POST /api/v1/payzen/ipn`
- paiement sans statut terminal (`PAID`, `REFUSED`, `ABANDONED`, `CANCELLED`)
- incoherence paiement/commande apres checkout

Diagnostic SQL:

```powershell
docker compose exec postgres psql -U postgres -d fastapi_ecommerce -c "SELECT id, payzen_order_id, payzen_status, payzen_trans_id, updated_at FROM payments WHERE is_active = true ORDER BY updated_at DESC LIMIT 30;"
docker compose exec postgres psql -U postgres -d fastapi_ecommerce -c "SELECT id, payment_id, status, error_code, created_at FROM payment_logs ORDER BY created_at DESC LIMIT 30;"
```

### 4.2 Rejouer un IPN avec signature valide

Script dedie:

```powershell
uv run python app/scripts/replay_payzen_ipn.py `
  --base-url "$API_BASE" `
  --order-id "<PAYMENT_OR_PAYZEN_ORDER_ID>" `
  --trans-status "PAID" `
  --trans-uuid "<PAYZEN_TRANS_UUID>" `
  --amount 1500 `
  --currency 953 `
  --card-brand "VISA"
```

Rejeu a partir d'un payload `kr-answer` deja capture:

```powershell
uv run python app/scripts/replay_payzen_ipn.py `
  --base-url "$API_BASE" `
  --kr-answer-file "./tmp/kr-answer.json"
```

Options utiles:
- `--dry-run`: calcule et affiche la signature sans appel HTTP
- `--mode TEST|PRODUCTION`: force le mode de cle HMAC
- `--hmac-key`: surcharge explicite de la cle HMAC

### 4.3 Verification apres replay

```powershell
docker compose exec postgres psql -U postgres -d fastapi_ecommerce -c "SELECT id, payzen_order_id, payzen_status, payzen_trans_id, updated_at FROM payments WHERE id = '<PAYMENT_UUID>';"
Invoke-RestMethod -Method Get -Uri "$API_BASE/api/v1/utils/observability/dashboard"
```

Attendu:
- `payments.payzen_status` en statut terminal coherent
- creation/maj de logs de paiement
- coherence des statuts checkout (paiement + commande)

## 5. Escalade

Escalader si l'un des cas suivants persiste apres relance:
- echec signature IPN repete avec cles correctes
- outbox degrade en continu apres `recover_missing_jobs`
- jobs Ingram/Icecat toujours en erreur apres redemarrage worker

Donnees a fournir pour l'analyse:
- `job_id` ARQ concernes
- `payment_id` ou `payzen_order_id`
- extrait logs `api`, `arq-worker`, `outbox-poller`
- sortie de l'endpoint observabilite
