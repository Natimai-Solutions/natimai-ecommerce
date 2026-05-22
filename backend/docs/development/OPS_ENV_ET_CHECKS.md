# Variables d'environnement et checks opérationnels — Phase 1

Ce document couvre les variables à configurer avant le premier déploiement Phase 1
et les vérifications à effectuer en production. Il complète le
[RUNBOOK_OPERATIONNEL_E3.md](RUNBOOK_OPERATIONNEL_E3.md) (procédures de relance).

---

## 1. Variables d'environnement

### 1.1 Obligatoires (déploiement impossible sans)

| Variable | Description | Exemple |
|----------|-------------|---------|
| `SECRET_KEY` | Clé de signature JWT — doit être aléatoire et unique | `openssl rand -hex 32` |
| `POSTGRES_SERVER` | Hôte PostgreSQL | `db` |
| `POSTGRES_USER` | Utilisateur PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL | ≥ 16 chars, pas `changethis` |
| `POSTGRES_DB` | Nom de la base | `app` |
| `REDIS_SERVER` | Hôte Redis | `redis` |
| `FIRST_SUPERUSER` | Email du premier admin | `admin@example.com` |
| `FIRST_SUPERUSER_PASSWORD` | Mot de passe admin initial | ≥ 12 chars, pas `changethisA1` |

### 1.2 Email transactionnel

| Variable | Description |
|----------|-------------|
| `EMAILS_FROM_EMAIL` | Adresse expéditeur |
| `EMAILS_FROM_NAME` | Nom affiché (défaut : `PROJECT_NAME`) |
| `EMAILS_API_URL` | URL de l'API email (ex. Mailgun) |
| `EMAILS_API_KEY` | Clé API email |
| `EMAIL_SUPPORT` | Destinataire des demandes de devis et alertes |
| `EMAIL_CONTACT` | Email affiché dans les emails client |

Sans `EMAILS_API_URL` + `EMAILS_API_KEY`, les emails sont désactivés silencieusement
(`emails_enabled = False`). Les demandes de devis sont persistées mais aucun email ne
part.

### 1.3 Ingram Micro

| Variable | Défaut | Description |
|----------|--------|-------------|
| `INGRAM_CLIENT_ID` | — | Obligatoire pour la sync catalogue |
| `INGRAM_CLIENT_SECRET` | — | Obligatoire pour la sync catalogue |
| `INGRAM_CUSTOMER_NUMBER` | — | Numéro client Ingram |
| `INGRAM_COUNTRY_CODE` | `FR` | Code pays pour les appels API |
| `INGRAM_ENVIRONMENT` | `sandbox` | Mettre `production` en prod |
| `INGRAM_SYNC_ENABLED` | `true` | `false` pour désactiver le cron |
| `INGRAM_SYNC_CATEGORIES` | `["Ordinateur/Serveur"]` | Catégories à synchroniser |
| `INGRAM_SYNC_INTERVAL_HOURS` | `6` | Fréquence sync catalogue (heures) |
| `SUPPLIER_SYNC_MIN_QUANTITY` | `0` | Qté minimale (0 = désactivé) |
| `SUPPLIER_SYNC_MIN_PRICE` | `0` | Prix minimum **en XPF** (0 = désactivé) |

`SUPPLIER_SYNC_MIN_PRICE` est toujours en XPF — la conversion depuis USD/EUR est
appliquée automatiquement dans la sync inventaire.

### 1.4 Icecat

| Variable | Défaut | Description |
|----------|--------|-------------|
| `ICECAT_USERNAME` | — | Identifiant Icecat (Open Icecat : email) |
| `ICECAT_API_KEY` | — | Clé API Icecat |
| `ICECAT_ENABLED` | `true` | `false` pour désactiver l'enrichissement |
| `ICECAT_USE_OPEN` | `true` | `false` pour Full Icecat (payant) |
| `ICECAT_LANGUAGE` | `fr` | Langue des fiches produit |

### 1.5 Stockage fichiers (pièces jointes paiement)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `FILE_STORAGE_BACKEND` | `local` | `s3` en production |
| `FILE_STORAGE_LOCAL_ROOT` | `/tmp/…` | Chemin stockage local (dev uniquement) |
| `S3_ENDPOINT_URL` | — | URL endpoint S3 (si backend=s3) |
| `S3_ACCESS_KEY_ID` | — | Clé d'accès S3 |
| `S3_SECRET_KEY_ID` | — | Clé secrète S3 |
| `S3_BUCKET_NAME` | — | Nom du bucket S3 |
| `S3_REGION` | `us-east-1` | Région S3 |

### 1.6 Paiement (Phase 2+)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `PAYZEN_SITE_ID` | — | Identifiant PayZen |
| `PAYZEN_API_PASSWORD_TEST` | — | Mot de passe API (mode test) |
| `PAYZEN_API_PASSWORD_PROD` | — | Mot de passe API (mode prod) |
| `PAYZEN_MODE` | `TEST` | Mettre `PRODUCTION` en prod |
| `PAYZEN_IPN_URL` | — | URL webhook PayZen (auto-calculé sinon) |
| `PAYZEN_RETURN_URL` | — | URL de retour frontend après paiement |

### 1.7 Divers

| Variable | Défaut | Description |
|----------|--------|-------------|
| `ENVIRONMENT` | `local` | `staging` ou `production` — active les garde-fous secrets |
| `SENTRY_DSN` | — | DSN Sentry pour le monitoring des erreurs |
| `CLAMAV_ENABLED` | `false` | Activer l'antivirus sur les pièces jointes |
| `CLAMAV_HOST` | `clamav` | Hôte du démon ClamAV |
| `FRONTEND_HOST` | `http://localhost:5173` | URL du frontend (CORS + liens emails) |
| `BACKEND_CORS_ORIGINS` | `[]` | Origines CORS supplémentaires (liste JSON) |

---

## 2. Checklist premier déploiement Phase 1

### 2.1 Base de données

```bash
# 1. Appliquer toutes les migrations
docker compose exec backend alembic upgrade head

# Vérifier la chaîne attendue (Phase 1) :
# baseline → 8c2f1d4a6e90 → d1e5c3f8a294 → e3b7a1c9d5f2 → f2a4b8c1d9e3
docker compose exec backend alembic current
```

### 2.2 Données initiales

```bash
# Lance initial_data.py : crée le superuser, les statuts paiement,
# les méthodes manuelles, les groupes prix, les taux TGC, et les taux FX USD/EUR.
docker compose exec backend python -m app.initial_data
```

Vérifier que les taux FX sont bien seedés :

```powershell
Invoke-RestMethod -Method Get `
  -Uri "$API_BASE/api/v1/admin/currency-rates" `
  -Headers $AUTH_HEADERS
# Doit retourner EUR (119.332) et USD (100.000) actifs
```

### 2.3 Extensions PostgreSQL

La migration `f2a4b8c1d9e3` exécute `CREATE EXTENSION IF NOT EXISTS pg_trgm`.
Vérifier que l'extension est activée :

```sql
SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm');
-- Doit retourner 1 ligne
```

### 2.4 ARQ worker

```bash
docker compose up -d arq-worker
docker compose logs arq-worker | grep -E "Started|cron|error"
```

Les crons attendus au démarrage (un jeu par fournisseur activé) :
- `ingram_micro_product_sync` — toutes les 6 h
- `ingram_micro_inventory_sync` — toutes les 2 h (à la demi-heure)
- `ingram_micro_api_health_check` — chaque jour à 6 h 00

### 2.5 Outbox poller

```bash
docker compose up -d outbox-poller
docker compose logs outbox-poller | grep -E "Started|polling|error"
```

---

## 3. Checks en production

### 3.1 Healthcheck

```powershell
# Liveness (process alive)
Invoke-RestMethod -Method Get -Uri "$API_BASE/healthz/liveness"
# → {"status":"ok"}

# Readiness (DB + Redis accessibles)
Invoke-RestMethod -Method Get -Uri "$API_BASE/healthz/ready"
# → {"status":"ok","checks":{"db":"ok","redis":"ok"}}
```

### 3.2 ARQ — jobs en cours / récents

```powershell
Invoke-RestMethod -Method Get `
  -Uri "$API_BASE/api/v1/utils/observability/dashboard" `
  -Headers $AUTH_HEADERS
```

Alertes à surveiller :
- `arq_jobs.queued > 50` → le worker est en retard
- `arq_jobs.failed > 0` → consulter les logs : `docker compose logs arq-worker`
- Aucun job `*_product_sync` dans les 7 dernières heures → cron non déclenché

### 3.3 Outbox — événements en attente

```powershell
Invoke-RestMethod -Method Get `
  -Uri "$API_BASE/api/v1/utils/observability/dashboard" `
  -Headers $AUTH_HEADERS
```

Alertes à surveiller :
- `outbox_jobs.stale_pending > 0` → événements bloqués depuis plus de 15 min
- `outbox_jobs.failed > 0` → erreur dans un handler outbox

Relancer les événements bloqués : voir section 3 du
[RUNBOOK_OPERATIONNEL_E3.md](RUNBOOK_OPERATIONNEL_E3.md).

### 3.4 Sync Ingram — vérification post-déploiement

Après le premier déploiement, déclencher manuellement la sync catalogue :

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$API_BASE/api/v1/admin/suppliers/ingram_micro/sync/products" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"categories":["Ordinateur/Serveur"]}'
```

Puis vérifier :
1. Des produits sont créés avec `is_supplier_managed=true`
2. Un job `batch_enrich_products_task` apparaît dans la queue ARQ
3. Après enrichissement, les produits passent à `is_enriched=true`
4. Les produits enrichis apparaissent sur `GET /api/v1/products` (sans auth)

### 3.5 Taux de change — alerte stale

Il n'existe pas encore de cron automatique pour les taux FX (prévu Phase 4).
Vérifier manuellement que les taux ne sont pas trop anciens (> 30 jours) :

```powershell
Invoke-RestMethod -Method Get `
  -Uri "$API_BASE/api/v1/admin/currency-rates?active_only=true" `
  -Headers $AUTH_HEADERS
# Vérifier valid_from de chaque taux actif
```

Si un taux est périmé, le mettre à jour via :

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "$API_BASE/api/v1/admin/currency-rates/EUR" `
  -Headers $AUTH_HEADERS `
  -ContentType "application/json" `
  -Body '{"rate_to_xpf": 119.332, "valid_from": "2026-05-22"}'
```

---

## 4. Variables non documentées dans `.env.example`

Ces variables ont un défaut sensé en dev mais **doivent être surchargées en prod** :

| Variable | Défaut dev | Valeur prod recommandée |
|----------|-----------|------------------------|
| `ENVIRONMENT` | `local` | `production` |
| `INGRAM_ENVIRONMENT` | `sandbox` | `production` |
| `FILE_STORAGE_BACKEND` | `local` | `s3` |
| `PAYZEN_MODE` | `TEST` | `PRODUCTION` |
| `CLAMAV_ENABLED` | `false` | `true` (si ClamAV déployé) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | `15` (ne pas augmenter) |
