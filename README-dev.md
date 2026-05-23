# Configuration de Développement

Ce fichier `docker compose.override.yml` configure automatiquement l'environnement de développement avec les fonctionnalités suivantes :

## 📚 Documentation de développement (à finaliser)

La documentation de travail est disponible dans `backend/docs/development/`.

Documents où il reste explicitement du travail à faire :

- [CAHIER_DES_CHARGES_ROUTAGE_MULTI_FOURNISSEURS.md](backend/docs/development/CAHIER_DES_CHARGES_ROUTAGE_MULTI_FOURNISSEURS.md) (statut: à implémenter)
- [PLAN_REFONTE_PAIEMENTS.md](backend/docs/development/PLAN_REFONTE_PAIEMENTS.md) (section "Reste à faire", phase Stripe/PayPal non terminée)
- [PLAN_DEPLOIEMENT_PAR_PHASE.md](backend/docs/development/PLAN_DEPLOIEMENT_PAR_PHASE.md) (roadmap par phases avec éléments à livrer)
- [PLAN_VERIFICATION_FONCTIONNEMENT.md](backend/docs/development/PLAN_VERIFICATION_FONCTIONNEMENT.md) (checklist de vérification avec items non cochés)
- [CHECKLIST_PREPROD_ROLLBACK_E4.md](backend/docs/development/CHECKLIST_PREPROD_ROLLBACK_E4.md) (checklist pre-prod/rollback à compléter)
- [TEST_COVERAGE_GAPS.md](backend/docs/development/TEST_COVERAGE_GAPS.md) (backlog de tests restant)

## ✨ Fonctionnalités de Développement

### 🔄 Hot Reload
- **FastAPI avec reload automatique** : Les changements de code sont détectés automatiquement
- **Montage des volumes** : Le code source est monté en temps réel
- **Rechargement instantané** : Pas besoin de rebuild les containers

### 📊 Logging Amélioré
- **Niveau DEBUG** : Logs plus détaillés pour le développement
- **Logs PostgreSQL** : Toutes les requêtes SQL sont loggées
- **Healthchecks plus tolérants** : Timeouts augmentés pour le debug

### 🗄️ Gestion des Migrations Alembic
- **Service dédié Alembic** : Container spécialement configuré pour les migrations
- **Scripts utilitaires** : Scripts PowerShell et Bash pour faciliter les opérations
- **Génération de fichiers** : Possibilité de créer les fichiers de migration directement

## 🚀 Utilisation

### Démarrage des Services

```powershell
# Démarre tous les services de base (API, Worker, Poller)
docker compose up -d

# Ou démarre seulement certains services
docker compose up -d postgres redis api
```

### Gestion des Migrations avec les Scripts

#### PowerShell (Windows)
```powershell
# Génère une nouvelle migration
.\scripts\alembic-dev.ps1 revision "Add new feature"

# Applique les migrations
.\scripts\alembic-dev.ps1 upgrade

# Affiche l'historique
.\scripts\alembic-dev.ps1 history

# Vérifie l'état actuel
.\scripts\alembic-dev.ps1 current
```

#### Bash (Linux/Mac)
```bash
# Génère une nouvelle migration
./scripts/alembic-dev.sh revision "Add new feature"

# Applique les migrations
./scripts/alembic-dev.sh upgrade

# Affiche l'historique
./scripts/alembic-dev.sh history
```

### Gestion Manuelle des Migrations

```powershell
# Démarre le service Alembic
docker compose --profile alembic run --rm alembic bash

# Dans le container, vous pouvez exécuter :
alembic revision --autogenerate -m "Description de la migration"
alembic upgrade head
alembic history
```

### Commandes Utiles

```powershell
# Voir les logs en temps réel
docker compose logs -f api

# Restart un service après modification
docker compose restart api

# Accéder au container API pour debug
docker compose exec api bash

# Exécuter des tests
docker compose exec api pytest

# Accéder à la base de données
docker compose exec postgres psql -U postgres -d fastapi_ecommerce
```

## 📁 Structure des Volumes

```
./backend/app           → /app/app           (Code source - Hot reload)
./backend/alembic.ini   → /app/alembic.ini   (Configuration Alembic)
./backend/pyproject.toml → /app/pyproject.toml (Dependencies)
```

## 🔧 Configuration des Services

### API (FastAPI)
- **Port** : 8000
- **Mode** : Development avec reload
- **Logs** : DEBUG level
- **Hot reload** : Activé

### Base de Données (PostgreSQL)
- **Port** : 5432 (exposé pour connexions externes)
- **Logs** : Toutes les requêtes SQL
- **Données** : Persistées dans le volume `postgres_data`

### Redis
- **Port** : 6379 (exposé pour connexions externes)
- **Persistance** : Activée avec appendonly
- **Données** : Persistées dans le volume `redis_data`

### ARQ Worker
- **Logs** : DEBUG level
- **Restart** : Désactivé en développement
- **Hot reload** : Code source monté

### Outbox Poller
- **Intervalle** : 5 secondes
- **Logs** : DEBUG level
- **Hot reload** : Code source monté

## 🎯 Profiles Docker Compose

### Profile `alembic`
Service spécialement configuré pour les opérations Alembic :
```powershell
docker compose --profile alembic run --rm alembic [commande]
```

### Profile `migration`
Service de migration pour les déploiements :
```powershell
docker compose --profile migration run --rm migrate
```

## 🛠️ Développement Workflow

1. **Démarrage** : `docker compose up -d`
2. **Développement** : Modifier le code → Hot reload automatique
3. **Migrations** : `.\scripts\alembic-dev.ps1 revision "Description"`
4. **Tests** : `docker compose exec api pytest`
5. **Debug** : Voir les logs avec `docker compose logs -f`

## 🔍 Debugging

### Accès aux Services
- **API** : http://localhost:8000
- **API Docs** : http://localhost:8000/docs
- **PostgreSQL** : localhost:5432
- **Redis** : localhost:6379

### Logs Utiles
```powershell
# Logs API avec hot reload
docker compose logs -f api

# Logs base de données
docker compose logs -f postgres

# Logs tous les services
docker compose logs -f
```

### Connexion Directe
```powershell
# Shell dans le container API
docker compose exec api bash

# PostgreSQL CLI
docker compose exec postgres psql -U postgres -d fastapi_ecommerce

# Redis CLI
docker compose exec redis redis-cli
```

## ⚠️ Notes Importantes

1. **Hot Reload** : Fonctionne uniquement pour les fichiers Python dans `/app`
2. **Permissions** : Les volumes sont montés en read-only sauf pour Alembic
3. **Performance** : Mode développement, non optimisé pour la production
4. **Données** : Les volumes persistent entre les redémarrages
5. **Migration Files** : Générés directement dans votre filesystem local
