# E4 Checklist Pre-Prod et Plan Rollback

Objectif: fournir une procedure simple et repetable avant mise en production, puis un plan de retour arriere rapide en cas d'incident.

Portee:
- stack Docker Compose (api, arq-worker, outbox-poller, outbox-health-checker, postgres, redis)
- migrations Alembic
- verification applicative minimale (health, observabilite, parcours critique)

## 1) Checklist pre-prod

### 1.1 Preparation release

- [ ] Version release identifiee (commit SHA + tag) et notee dans le ticket de mise en prod.
- [ ] Variables d'environnement prod verifiees (`POSTGRES_*`, `REDIS_URL`, `SECRET_KEY`, `PAYZEN_*`, `INGRAM_*`, `ICECAT_*`).
- [ ] Fichiers compose cibles verifies:
  - `docker-compose.yml`
  - `docker-compose.prod.yml`
  - `docker-compose.health.yml`
- [ ] Fenetre de deploiement validee et canal d'escalade disponible.

### 1.2 Sauvegardes avant changement

- [ ] Backup base PostgreSQL avant migration:

```powershell
docker compose exec postgres pg_dump -U postgres -d fastapi_ecommerce -Fc -f /tmp/predeploy.dump
```

- [ ] Export backup vers machine hote:

```powershell
docker compose cp postgres:/tmp/predeploy.dump ./predeploy.dump
```

- [ ] Verification fichier backup non vide et archive du nom release.

### 1.3 Validation technique pre-deploiement

Depuis `backend/`:

```powershell
uv run ruff check app
uv run mypy app
uv run pytest app/tests/api/test_phase_e1_e2e_critical_journey.py -q
uv run pytest app/tests/api/test_phase_e2_observability_dashboard.py -q
uv run pytest app/tests/api/test_phase_e3_operational_entrypoints.py -q
```

- [ ] Aucun echec lint/type/tests critiques.
- [ ] Endpoint observabilite retourne un payload coherent en environnement cible:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/utils/observability/dashboard"
```

### 1.4 Deploiement

- [ ] Pull/build de la release.
- [ ] Demarrage/refresh des services prod:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.health.yml up -d --build
```

- [ ] Verification etat des services:

```powershell
docker compose ps
docker compose logs --since=5m api arq-worker outbox-poller outbox-health-checker
```

### 1.5 Smoke tests post-deploiement

- [ ] Health API:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/utils/health-check"
```

- [ ] Dashboard observabilite:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/utils/observability/dashboard"
```

- [ ] Runbook E3 operations critiques (au moins une verification):
  - Ingram health
  - Icecat status
  - outbox non bloque

- [ ] Monitoring renforce pendant 30 min:
  - erreurs 5xx API
  - `outbox_jobs.stale_pending`
  - echec checkout / paiement

## 2) Plan rollback

Principe: rollback rapide, puis analyse. Ne pas rester dans un etat partiellement degrade.

### 2.1 Criteres de declenchement rollback

Rollback immediat si un des points suivants persiste plus de 10 minutes:
- indisponibilite API continue
- echec migration bloquant
- hausse massive des 5xx
- paiements/checkout en echec systematique
- backlog outbox qui augmente sans traitement

### 2.2 Rollback niveau 1 (application only)

Objectif: revenir au code precedent sans rollback DB.

1. Identifier la release precedente stable (`<PREV_RELEASE>`).
2. Redeployer la release precedente:

```powershell
# Exemple si pipeline image taggee
docker compose pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.health.yml up -d
```

3. Redemarrer services applicatifs si necessaire:

```powershell
docker compose restart api arq-worker outbox-poller outbox-health-checker
```

4. Rejouer smoke tests section 1.5.

### 2.3 Rollback niveau 2 (migration reversible)

Objectif: revenir a la revision Alembic precedente si migration compatible downgrade.

1. Identifier revision courante et revision cible:

```powershell
./scripts/alembic-dev.ps1 current
./scripts/alembic-dev.ps1 history --verbose
```

2. Executer downgrade controle:

```powershell
./scripts/alembic-dev.ps1 downgrade -1
```

3. Redeployer release precedente (niveau 1) et relancer smoke tests.

Important:
- utiliser ce niveau seulement si le downgrade est confirme safe.
- en cas de doute, passer au niveau 3.

### 2.4 Rollback niveau 3 (restauration backup)

Objectif: restaurer l'etat avant deploiement.

1. Stopper les services applicatifs pour figer les ecritures:

```powershell
docker compose stop api arq-worker outbox-poller outbox-health-checker
```

2. Restaurer la base depuis `predeploy.dump`:

```powershell
docker compose cp ./predeploy.dump postgres:/tmp/predeploy.dump
docker compose exec postgres pg_restore -U postgres -d fastapi_ecommerce --clean --if-exists /tmp/predeploy.dump
```

3. Redemarrer stack precedente stable:

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.health.yml up -d
```

4. Verifier API/observabilite + parcours critiques E1/E2/E3.

### 2.5 Post-incident obligatoire

- [ ] Incident log complete (timeline, cause, impact, actions)
- [ ] Correctif ou garde-fou ajoute avant nouvelle tentative
- [ ] Nouvelle fenetre de deploiement planifiee

## 3) Commandes de reference (copier/coller)

```powershell
# Etat stack
docker compose ps

# Logs recents
docker compose logs --since=10m api arq-worker outbox-poller outbox-health-checker

# Health API
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/utils/health-check"

# Observabilite
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/utils/observability/dashboard"
```
