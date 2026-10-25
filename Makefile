# Raccourcis de développement (R8 / confort). Chaque cible dit la commande
# qu'elle lance : `make -n <cible>` pour la voir sans l'exécuter.
#
# Pré-requis : uv (backend), pnpm (fronts), docker compose (pile locale).

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := cd backend && uv run

.PHONY: help setup dev dev-front stop logs migrate seed \
        lint format typecheck test test-backend test-fronts coverage \
        gen-types check-types e2e audit seed-demo purge-demo

# Pile « frontend seul » : l'API vient de l'image GHCR (docker-compose.frontend-dev.yml).
FRONT_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.frontend-dev.yml

help: ## Liste des cibles
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Installer les dépendances (uv sync, pnpm install)
	cd backend && uv sync
	pnpm install

dev: ## Démarrer la pile locale (postgres, redis, api, vitrine, admin)
	docker compose up -d --wait postgres redis api frontend admin-frontend

dev-front: ## Travailler sur un frontend sans Python : API depuis l'image GHCR, puis `pnpm dev:front` / `pnpm dev:admin`
	$(FRONT_COMPOSE) pull --quiet api
	$(FRONT_COMPOSE) up -d --wait --no-build postgres redis api
	$(FRONT_COMPOSE) run --rm --no-build migrate
	$(FRONT_COMPOSE) up -d --no-build arq-worker outbox-poller

stop: ## Arrêter la pile locale (complète ou « frontend seul »)
	$(FRONT_COMPOSE) down

logs: ## Suivre les journaux de l'API
	docker compose logs -f api

migrate: ## Migrations Alembic + données initiales (pile docker)
	docker compose run --rm migrate

seed: ## Fixtures du parcours e2e (client, adresse, produit en stock)
	docker compose cp e2e/seed_e2e_data.py api:/app/e2e_seed.py
	docker compose exec -T api python /app/e2e_seed.py

seed-demo: ## Catalogue de démonstration (explicite, idempotent ; refusé en production)
	docker compose exec -T api python -m app.scripts.seed_demo

purge-demo: ## Retirer le catalogue de démonstration
	docker compose exec -T api python -m app.scripts.seed_demo --purge

lint: ## ruff + eslint (sans modification)
	$(BACKEND) ruff check app
	$(BACKEND) ruff format --check app
	pnpm -r lint

format: ## ruff format + prettier (modifie les fichiers)
	$(BACKEND) ruff check --fix app
	$(BACKEND) ruff format app
	pnpm -r --if-present format

typecheck: ## mypy strict + vue-tsc des deux fronts
	$(BACKEND) mypy app
	pnpm -r typecheck

test-backend: ## pytest (Postgres de test requis : TEST_DATABASE_URL)
	$(BACKEND) pytest -q -p no:cacheprovider app/tests

test-fronts: ## vitest (moteur partagé, vitrine, admin)
	pnpm test

test: test-backend test-fronts ## Tous les tests unitaires et d'intégration

coverage: ## Couverture backend (rapport texte)
	cd backend && uv run coverage run -m pytest -q -p no:cacheprovider app/tests && uv run coverage report

gen-types: ## Regénérer shared/api-types depuis le schéma OpenAPI
	pnpm gen:types

check-types: ## Vérifier que shared/api-types est à jour (comme la CI)
	pnpm check:types

e2e: ## Parcours Playwright contre la pile locale
	pnpm --filter e2e test

audit: ## Dépendances vulnérables (pip-audit, pnpm audit)
	cd backend && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/req.txt && uvx pip-audit -r /tmp/req.txt --disable-pip --no-deps
	pnpm audit --prod --audit-level=moderate
