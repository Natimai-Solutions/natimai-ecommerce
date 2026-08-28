#!/usr/bin/env bash
# Restauration d'une sauvegarde produite par backup.sh.
#
# Deux modes :
#
#   --rehearsal  (DÉFAUT, sans risque) restaure le dump dans un conteneur
#                PostgreSQL JETABLE et compare les volumétries. C'est la
#                « répétition à blanc » exigée avant la première commande :
#                une sauvegarde jamais restaurée n'est pas une sauvegarde.
#
#   --production (DESTRUCTIF) restaure dans la base de production. Écrase les
#                données actuelles. Demande une confirmation explicite.
#
# Usage :
#   ./scripts/backup/restore.sh backups/db_20260827_020000.dump
#   ./scripts/backup/restore.sh --production backups/db_20260827_020000.dump
#
# Variables surchargeables :
#   COMPOSE_CMD   commande compose (défaut "docker compose")
#   PGUSER / PGDATABASE   identifiants Postgres
#   PG_IMAGE      image utilisée pour la répétition (défaut postgres:16-alpine)
set -euo pipefail

MODE="rehearsal"
DUMP_FILE=""
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-fastapi_ecommerce}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"

# Tables dont on compare le nombre de lignes : celles qu'on regretterait le
# plus de perdre. Une restauration « réussie » mais vide passerait sinon
# inaperçue.
CHECK_TABLES=(orders order_lines payments invoices products users)

while [ $# -gt 0 ]; do
  case "$1" in
    --production) MODE="production" ;;
    --rehearsal)  MODE="rehearsal" ;;
    -h|--help)    sed -n '2,22p' "$0"; exit 0 ;;
    *)            DUMP_FILE="$1" ;;
  esac
  shift
done

if [ -z "$DUMP_FILE" ]; then
  echo "ERREUR : indiquer le fichier de dump à restaurer." >&2
  echo "Usage : $0 [--rehearsal|--production] <fichier.dump>" >&2
  exit 1
fi

if [ ! -r "$DUMP_FILE" ]; then
  echo "ERREUR : dump illisible : $DUMP_FILE" >&2
  exit 1
fi

# Même garde que dans backup.sh : un dump custom valide commence par PGDMP.
# Inutile de dérouler toute la procédure sur un fichier tronqué.
if ! head -c 5 "$DUMP_FILE" | grep -q "PGDMP"; then
  echo "ERREUR : '$DUMP_FILE' n'est pas un dump PostgreSQL au format custom." >&2
  exit 1
fi

count_rows() {
  # $1 = commande psql complète (jusqu'à -c exclus)
  local table
  for table in "${CHECK_TABLES[@]}"; do
    local n
    n="$("$@" -tAc "SELECT count(*) FROM ${table}" 2>/dev/null || echo "absente")"
    printf '  %-14s %s\n' "$table" "$n"
  done
}

if [ "$MODE" = "rehearsal" ]; then
  CONTAINER="pg-restore-rehearsal-$$"
  echo "[$(date -Is)] Répétition à blanc dans un conteneur jetable ($PG_IMAGE) …"

  # Le conteneur est supprimé quoi qu'il arrive — y compris sur Ctrl-C.
  cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
  trap cleanup EXIT

  docker run -d --name "$CONTAINER" \
    -e POSTGRES_USER="$PGUSER" \
    -e POSTGRES_PASSWORD=rehearsal \
    -e POSTGRES_DB="$PGDATABASE" \
    "$PG_IMAGE" >/dev/null

  echo "[$(date -Is)] Attente du démarrage …"
  for _ in $(seq 1 30); do
    if docker exec "$CONTAINER" pg_isready -U "$PGUSER" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$CONTAINER" pg_isready -U "$PGUSER" >/dev/null

  echo "[$(date -Is)] pg_restore …"
  docker exec -i "$CONTAINER" pg_restore -U "$PGUSER" -d "$PGDATABASE" \
    --clean --if-exists --no-owner < "$DUMP_FILE"

  echo "[$(date -Is)] Volumétrie restaurée :"
  count_rows docker exec "$CONTAINER" psql -U "$PGUSER" -d "$PGDATABASE"

  echo
  echo "[$(date -Is)] Répétition terminée. Comparez ces nombres à la production :"
  echo "  $COMPOSE_CMD exec -T postgres psql -U $PGUSER -d $PGDATABASE -c 'SELECT count(*) FROM orders'"
  exit 0
fi

# ── Mode production (destructif) ──────────────────────────────────────────────
cat >&2 <<WARN

  ⚠  RESTAURATION EN PRODUCTION
     Base   : $PGDATABASE
     Dump   : $DUMP_FILE
     Les données actuelles seront ÉCRASÉES.

WARN
read -r -p "Taper 'restaurer' pour confirmer : " confirm
[ "$confirm" = "restaurer" ] || { echo "Annulé." >&2; exit 1; }

echo "[$(date -Is)] Arrêt des services qui écrivent en base …"
$COMPOSE_CMD stop api arq-worker outbox-poller outbox-health-checker

echo "[$(date -Is)] pg_restore …"
$COMPOSE_CMD exec -T postgres pg_restore -U "$PGUSER" -d "$PGDATABASE" \
  --clean --if-exists --no-owner < "$DUMP_FILE"

echo "[$(date -Is)] Volumétrie restaurée :"
count_rows $COMPOSE_CMD exec -T postgres psql -U "$PGUSER" -d "$PGDATABASE"

echo "[$(date -Is)] Redémarrage …"
$COMPOSE_CMD up -d

echo "[$(date -Is)] Restaurez aussi le volume des uploads si nécessaire :"
# --index : `api` tourne en replicas: 2 en prod, `exec` sans index est ambigu.
echo "  $COMPOSE_CMD exec --index 1 -T api tar xzf - -C /tmp < backups/storage_<STAMP>.tar.gz"
