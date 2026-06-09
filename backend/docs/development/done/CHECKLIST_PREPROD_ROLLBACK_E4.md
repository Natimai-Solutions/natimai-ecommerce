# E4 Checklist Pre-Prod et Plan Rollback

Ce document couvre le déploiement de la refonte multi-fournisseurs paiements (phases 1–7).

---

## 1) Checklist pre-prod

### Base de données
- [ ] Backup complet de la base de production avant migration : `pg_dump -Fc $DATABASE_URL > backup_preprod_$(date +%Y%m%d_%H%M%S).dump`
- [ ] Vérifier que la migration `1a2c9e5f7b31` (drop legacy payzen columns) passe en staging sans erreur
- [ ] Vérifier que la migration `2d7f4b8c9e11` (rename payment_log columns) s'exécute correctement
- [ ] Valider que le backfill `provider_data` / `provider_reference` couvre bien tous les paiements existants

### Application
- [ ] Toutes les variables d'environnement requises sont configurées :
  - `PAYMENT_PROVIDERS` (liste des codes provider activés)
  - `PAYZEN_*` (clés API Payzen si utilisé)
  - `FILE_STORAGE_BACKEND` (`local` ou `s3`)
  - `CLAMAV_ENABLED` (et `CLAMAV_HOST` / `CLAMAV_PORT` si activé)
- [ ] Les tests unitaires et d'intégration passent en entier (`pytest`)
- [ ] Ruff lint propre (`ruff check app/`)
- [ ] Mypy sans erreurs bloquantes

### Routes et webhooks
- [ ] Webhook Payzen IPN configuré vers `/api/v1/payments/webhooks/payzen`
- [ ] Endpoint admin `/api/v1/admin/payments/pending-validation` accessible
- [ ] Tableau de bord observabilité accessible : `/api/v1/utils/observability/dashboard`

### Worker ARQ
- [ ] Le worker ARQ démarre sans erreur
- [ ] Les handlers outbox sont enregistrés : `payment.captured`, `payment.rejected`, `payment.webhook_received`, `payment.document_uploaded`, `payment.document_infected`

---

## 2) Plan rollback

### 2.1 Critères de déclenchement
- Erreurs 500 répétées sur les endpoints paiement
- Worker ARQ bloqué ou events non traités
- Perte de données détectée sur la table `payments`

### 2.2 Rollback niveau 1 (application only)

Redéployer la version précédente de l'application sans toucher la base de données :

```bash
# Redéployer le tag précédent
git checkout <previous-tag>
docker compose up -d --build app worker
```

Les colonnes `payzen_*` peuvent encore exister si la migration drop n'a pas été jouée.
La version précédente continue de fonctionner avec les colonnes legacy.

### 2.3 Rollback niveau 2 (migration reversible)

Si la migration a été jouée et qu'il faut revenir en arrière :

```bash
# Descendre d'une migration
./scripts/alembic-dev.ps1 downgrade -1

# Ou cibler une révision précise
./scripts/alembic-dev.ps1 downgrade c9e1f3a82b46
```

Les migrations `1a2c9e5f7b31` et `2d7f4b8c9e11` ont chacune un `downgrade()` qui restaure
les colonnes supprimées. Les données backfillées dans `provider_data` sont re-propagées
vers les colonnes legacy dans le downgrade.

### 2.4 Rollback niveau 3 (restauration backup)

En dernier recours, restaurer la base depuis le backup pre-prod :

```bash
# Arrêter l'application
docker compose stop app worker

# Restaurer le dump
pg_restore --clean --if-exists -d $DATABASE_URL backup_preprod_<timestamp>.dump

# Redéployer la version précédente
git checkout <previous-tag>
docker compose up -d --build app worker
```

Vérifier après restauration :
- Comptes de lignes `payments`, `payment_logs`, `orders` cohérents
- Webhook Payzen repointe vers l'ancienne URL si nécessaire

---

## 3) Contacts et escalade

| Rôle | Responsable |
|------|-------------|
| Lead backend | Équipe technique |
| DBA / infra | Équipe infrastructure |
| Alerte monitoring | `/api/v1/utils/observability/dashboard` |
