#!/bin/sh
# Mise à jour à la main sur le serveur, en construisant les images sur place
# (docs/DEPLOYMENT.md §8.2). POSIX sh : tourne sous ash (BusyBox), dash, bash.
#
# Étapes : git pull (avance rapide seulement) → aperçu des commits et des
# migrations → confirmation → sauvegarde de la base → build --pull →
# migrations → mise en service → contrôle de santé.
#
# Usage (depuis n'importe où) :
#   ./scripts/release/update.sh            # demande confirmation
#   ./scripts/release/update.sh -y         # sans confirmation
#   ./scripts/release/update.sh --no-pull  # déploie le commit déjà extrait
#
# Variables facultatives :
#   API_URL   origine de l'API pour le contrôle de santé (défaut : VITE_API_URL
#             du .env)
#   BRANCH    branche à suivre (défaut : la branche courante)
set -eu

ASSUME_YES=false
DO_PULL=true
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=true ;;
    --no-pull) DO_PULL=false ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "✗ Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/../.."

compose() {
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    -f docker-compose.proxy.yml "$@"
}

if [ ! -f .env ]; then
  echo "✗ .env absent de $(pwd) : il reste sur le serveur, jamais dans le dépôt." >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "✗ Modifications locales dans le dépôt : à ranger avant de mettre à jour." >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

PREVIOUS="$(git rev-parse HEAD)"

if [ "$DO_PULL" = true ]; then
  BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
  echo "→ Récupération de origin/$BRANCH"
  git fetch --quiet origin "$BRANCH"
  TARGET="$(git rev-parse FETCH_HEAD)"
  if [ "$TARGET" = "$PREVIOUS" ]; then
    echo "✓ Déjà à jour ($(git rev-parse --short HEAD))."
    printf 'Reconstruire et redéployer quand même ? [o/N] '
    if [ "$ASSUME_YES" = true ]; then echo o; else
      read -r answer
      case "$answer" in o|O|y|Y) ;; *) exit 0 ;; esac
    fi
  else
    echo
    echo "Commits à déployer :"
    git log --oneline --no-merges "$PREVIOUS..$TARGET" | head -40
    MIGRATIONS="$(git diff --name-only --diff-filter=A "$PREVIOUS" "$TARGET" -- backend/app/alembic/versions/)"
    if [ -n "$MIGRATIONS" ]; then
      echo
      echo "Nouvelles migrations :"
      echo "$MIGRATIONS" | sed 's/^/  /'
    fi
    if git diff --quiet "$PREVIOUS" "$TARGET" -- .env.example docker-compose*.yml Caddyfile* 2>/dev/null; then :; else
      echo
      echo "⚠ .env.example, compose ou Caddyfile ont changé : relire le diff et le CHANGELOG."
    fi
    echo
    if [ "$ASSUME_YES" != true ]; then
      printf 'Déployer %s ? [o/N] ' "$(git rev-parse --short "$TARGET")"
      read -r answer
      case "$answer" in o|O|y|Y) ;; *) echo "Abandon."; exit 0 ;; esac
    fi
    git merge --ff-only --quiet "$TARGET"
  fi
fi

SHORT="$(git rev-parse --short=12 HEAD)"

echo "→ Sauvegarde de la base avant migration"
mkdir -p backups
DUMP="backups/pre_deploy_${SHORT}_$(date +%Y%m%d_%H%M%S).dump"
if compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  # Données des clients : lisible par le seul propriétaire.
  (umask 077; : > "$DUMP.part")
  compose exec -T postgres sh -c \
    'pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-fastapi_ecommerce}" -Fc' \
    > "$DUMP.part"
  if head -c 5 "$DUMP.part" | grep -q PGDMP; then
    mv "$DUMP.part" "$DUMP"
    echo "✓ $DUMP"
  else
    rm -f "$DUMP.part"
    echo "✗ Sauvegarde invalide : mise à jour arrêtée (code déjà tiré, rien de déployé)." >&2
    exit 1
  fi
else
  echo "  (base arrêtée : premier déploiement, rien à sauvegarder)"
  DUMP=""
fi

failed() {
  echo >&2
  echo "✗ $1" >&2
  echo "  Version précédente : $PREVIOUS" >&2
  [ -n "$DUMP" ] && echo "  Sauvegarde avant migration : $DUMP" >&2
  echo "  Retour arrière du code : git checkout $PREVIOUS puis relancer ce script avec --no-pull" >&2
  echo "  Retour de la base (si le schéma doit revenir) : ./scripts/backup/restore.sh --production $DUMP" >&2
  exit 1
}

echo "→ Construction des images (--pull : images de base à jour)"
compose build --pull || failed "La construction a échoué (rien n'a changé en service)."

echo "→ Migrations et données initiales"
compose run --rm migrate || failed "Les migrations ont échoué : l'ancienne version tourne toujours."

echo "→ Mise en service"
if ! compose up -d --remove-orphans; then
  compose ps >&2 || true
  compose logs --tail 80 api >&2 || true
  failed "La mise en service a échoué."
fi

if [ -z "${API_URL:-}" ]; then
  API_URL="$(sed -n 's/^VITE_API_URL=//p' .env | tail -n 1 | tr -d "\"' ")"
fi
if [ -n "$API_URL" ]; then
  echo "→ Contrôle de santé $API_URL"
  attempt=1
  until curl -fsS --max-time 5 "$API_URL/api/v1/healthz/ready" >/dev/null 2>&1; do
    if [ "$attempt" -ge 30 ]; then
      compose ps >&2
      compose logs --tail 80 api >&2
      failed "L'API ne répond pas « ready » après 5 min."
    fi
    attempt=$((attempt + 1))
    sleep 10
  done
  echo "✓ API prête"
else
  echo "  (pas de VITE_API_URL dans .env ni d'API_URL : contrôle de santé sauté)"
fi

echo "→ Révision de la base"
compose exec -T api alembic current 2>/dev/null | tail -n 1 || true

echo "→ Worker (dernières lignes)"
compose logs --tail 5 arq-worker 2>/dev/null || true

# Images sans tag laissées par la construction ; les 5 derniers dumps suffisent
# (la sauvegarde quotidienne garde l'historique).
docker image prune -f >/dev/null
ls -1t backups/pre_deploy_*.dump 2>/dev/null | tail -n +6 | while read -r old; do
  rm -f "$old"
done

echo
echo "✓ Déployé : $SHORT (précédent : $(echo "$PREVIOUS" | cut -c1-12))"
