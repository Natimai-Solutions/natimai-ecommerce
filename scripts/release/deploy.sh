#!/usr/bin/env bash
# Déploiement sur le serveur à partir des images GHCR (appelé par
# .github/workflows/deploy.yml, utilisable aussi à la main).
#
# Le dépôt doit déjà être sur le commit à déployer (le workflow fait le
# checkout avant d'appeler ce script) : les fichiers compose et le Caddyfile
# viennent de ce commit, les images de GHCR.
#
# Entrées (variables d'environnement) :
#   IMAGE_PREFIX   ghcr.io/<owner>/<repo>
#   IMAGE_TAG      sha du commit (tag des images)
#   API_URL        https://api.<domaine> (contrôle de santé final ; facultatif)
#   GHCR_USER      utilisateur pour docker login (facultatif)
#   AUTO_ROLLBACK  "false" pour laisser en service une version dont le contrôle
#                  de santé échoue (défaut : retour à la version précédente)
# Le jeton GHCR, s'il faut se connecter, est lu sur l'entrée standard (jamais
# en argument : il serait visible dans la liste des processus).
#
# Usage manuel :
#   IMAGE_PREFIX=ghcr.io/org/repo IMAGE_TAG=<sha> ./scripts/release/deploy.sh
set -euo pipefail

: "${IMAGE_PREFIX:?IMAGE_PREFIX manquant}"
: "${IMAGE_TAG:?IMAGE_TAG manquant}"
export IMAGE_PREFIX IMAGE_TAG

cd "$(dirname "$0")/../.."

if [[ ! -f .env ]]; then
  echo "✗ .env absent de $(pwd) : il reste sur le serveur, jamais dans le dépôt." >&2
  exit 1
fi

COMPOSE=(docker compose
  -f docker-compose.yml
  -f docker-compose.prod.yml
  -f docker-compose.proxy.yml
  -f docker-compose.images.yml)

registry="${IMAGE_PREFIX%%/*}"
if [[ -n "${GHCR_USER:-}" && ! -t 0 ]]; then
  token="$(cat)"
  if [[ -n "$token" ]]; then
    echo "→ Connexion à $registry"
    printf '%s' "$token" | docker login "$registry" -u "$GHCR_USER" --password-stdin >/dev/null
    # Le jeton du workflow expire avec lui : ne pas le laisser sur le disque.
    trap 'docker logout "$registry" >/dev/null 2>&1 || true' EXIT
  fi
fi

echo "→ Images $IMAGE_PREFIX/*:$IMAGE_TAG"
# Images applicatives et images tierces (postgres, redis, caddy, clamav) :
# les tags flottants des secondes doivent être rafraîchis eux aussi.
"${COMPOSE[@]}" pull --quiet

# Version en service avant ce déploiement : celle vers laquelle revenir.
PREVIOUS_TAG=""
[[ -f .deployed_tag ]] && PREVIOUS_TAG="$(cat .deployed_tag)"

echo "→ Sauvegarde de la base avant migration"
# Une migration ratée ou une version à abandonner se rattrapent avec ce dump
# (scripts/backup/restore.sh). Il n'y en avait pas : le seul filet était la
# sauvegarde de la nuit.
mkdir -p backups
PRE_DUMP="backups/pre_deploy_${IMAGE_TAG:0:12}_$(date +%Y%m%d_%H%M%S).dump"
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx postgres; then
  "${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-fastapi_ecommerce}" -Fc' \
    > "$PRE_DUMP.part"
  if head -c 5 "$PRE_DUMP.part" | grep -q PGDMP; then
    mv "$PRE_DUMP.part" "$PRE_DUMP"
    echo "✓ $PRE_DUMP"
  else
    rm -f "$PRE_DUMP.part"
    echo "✗ Sauvegarde avant migration invalide : déploiement arrêté." >&2
    exit 1
  fi
else
  echo "  (base pas encore démarrée : premier déploiement, rien à sauvegarder)"
fi

echo "→ Migrations et données initiales"
# Toujours AVANT le nouveau code (alembic upgrade head + initial_data,
# idempotents).
"${COMPOSE[@]}" run --rm --no-build migrate

echo "→ Mise en service"
"${COMPOSE[@]}" up -d --no-build --remove-orphans

if [[ -n "${API_URL:-}" ]]; then
  echo "→ Contrôle de santé $API_URL"
  for attempt in $(seq 1 30); do
    if curl -fsS --max-time 5 "$API_URL/api/v1/healthz/ready" >/dev/null 2>&1; then
      echo "✓ API prête (essai $attempt)"
      break
    fi
    if [[ "$attempt" == 30 ]]; then
      echo "✗ L'API ne répond pas « ready » après 5 min." >&2
      "${COMPOSE[@]}" ps >&2
      "${COMPOSE[@]}" logs --tail 80 api >&2
      if [[ "${AUTO_ROLLBACK:-true}" != "false" && -n "$PREVIOUS_TAG" ]]; then
        # La version cassée restait en service. Les migrations sont
        # additives : l'ancien code tourne sur le schéma migré. Si ce n'est
        # pas le cas, restaurer le dump pris avant la migration.
        echo "→ Retour à la version précédente $PREVIOUS_TAG" >&2
        IMAGE_TAG="$PREVIOUS_TAG" "${COMPOSE[@]}" up -d --no-build --remove-orphans >&2
        echo "  Base sauvegardée avant migration : ${PRE_DUMP:-aucune}" >&2
        echo "  (./scripts/backup/restore.sh --production <dump> si le schéma doit revenir)" >&2
      fi
      exit 1
    fi
    sleep 10
  done
fi

# Les images des déploiements précédents restent pour un retour arrière
# rapide ; on ne retire que celles qui ne portent plus aucun tag.
docker image prune -f >/dev/null

echo "$IMAGE_TAG" > .deployed_tag
# Les dumps d'avant déploiement : les 5 derniers suffisent (la sauvegarde
# quotidienne garde l'historique).
ls -1t backups/pre_deploy_*.dump 2>/dev/null | tail -n +6 | xargs -r rm -f

echo "✓ Déployé : $IMAGE_TAG"
