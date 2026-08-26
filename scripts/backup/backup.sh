#!/usr/bin/env bash
# Sauvegarde PostgreSQL (pg_dump format custom) + volume des uploads.
#
# À planifier en cron sur le serveur de production, par exemple :
#   0 2 * * * cd /opt/fastapi-ecommerce && ./scripts/backup/backup.sh >> /var/log/ecommerce-backup.log 2>&1
#
# La copie HORS SERVEUR (rclone/scp vers un stockage distant) est indispensable :
# un backup sur le disque du serveur ne protège ni d'une panne disque ni d'un
# ransomware. Voir DEPLOYMENT.md §12 (procédure de restauration incluse —
# à TESTER avant d'accepter la moindre commande réelle).
#
# Variables surchargeables par l'environnement :
#   BACKUP_DIR       répertoire de destination (défaut ./backups)
#   RETENTION_DAYS   ancienneté max des sauvegardes conservées (défaut 14)
#   COMPOSE_CMD      commande compose (défaut "docker compose")
#   PGUSER / PGDATABASE  identifiants Postgres (défauts du compose)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-fastapi_ecommerce}"

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[$(date -Is)] Sauvegarde PostgreSQL ($PGDATABASE) …"
# Format custom (-Fc) : compressé, restaurable table par table avec pg_restore.
$COMPOSE_CMD exec -T postgres pg_dump -U "$PGUSER" -d "$PGDATABASE" -Fc \
  > "$BACKUP_DIR/db_${STAMP}.dump"

echo "[$(date -Is)] Sauvegarde du volume des uploads …"
# Le volume storage_data est monté dans le conteneur api ; tar streamé vers l'hôte.
$COMPOSE_CMD exec -T api tar czf - -C /tmp fastapi_ecommerce_storage \
  > "$BACKUP_DIR/storage_${STAMP}.tar.gz"

echo "[$(date -Is)] Vérification sommaire …"
# Un dump custom valide commence par le magic "PGDMP" ; échoue le cron sinon.
head -c 5 "$BACKUP_DIR/db_${STAMP}.dump" | grep -q "PGDMP" || {
  echo "ERREUR : dump PostgreSQL invalide" >&2
  exit 1
}

echo "[$(date -Is)] Rotation (> ${RETENTION_DAYS} jours) …"
find "$BACKUP_DIR" -name 'db_*.dump' -mtime "+${RETENTION_DAYS}" -delete
find "$BACKUP_DIR" -name 'storage_*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete

# ── Copie hors serveur — À CONFIGURER (exemple rclone) ────────────────────────
# rclone copy "$BACKUP_DIR" remote:ecommerce-backups --max-age 48h

echo "[$(date -Is)] OK — $(ls -1 "$BACKUP_DIR" | wc -l) fichier(s) dans $BACKUP_DIR"
