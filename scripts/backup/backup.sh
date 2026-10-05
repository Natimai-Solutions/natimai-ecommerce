#!/usr/bin/env bash
# Sauvegarde PostgreSQL (pg_dump format custom) + volume des uploads.
#
# À planifier en cron sur le serveur de production, par exemple :
#   0 2 * * * cd /opt/fastapi-ecommerce && ./scripts/backup/backup.sh >> /var/log/ecommerce-backup.log 2>&1
#
# La copie HORS SERVEUR est indispensable : un backup sur le disque du serveur
# ne protège ni d'une panne disque ni d'un ransomware. Renseigner
# OFFSITE_RCLONE_REMOTE pour l'activer — tant qu'elle ne l'est pas, la rotation
# est DÉSACTIVÉE (on ne supprime pas des archives qui n'existent qu'ici).
# Voir docs/DEPLOYMENT.md §12 (procédure de restauration incluse — à TESTER avant
# d'accepter la moindre commande réelle).
#
# Variables surchargeables par l'environnement :
#   BACKUP_DIR             répertoire de destination (défaut ./backups)
#   RETENTION_DAYS         ancienneté max des sauvegardes conservées (défaut 14)
#   COMPOSE_CMD            commande compose (défaut "docker compose")
#   API_INDEX              réplique api à interroger (défaut 1 ; `api` tourne en
#                          replicas: 2 en prod, `exec` sans --index est ambigu)
#   PGUSER / PGDATABASE    identifiants Postgres (défauts du compose)
#   OFFSITE_RCLONE_REMOTE  destination rclone (ex. "remote:ecommerce-backups")
#   RETENTION_LOCAL_ONLY   "true" pour autoriser la rotation sans copie distante
#   ALERT_WEBHOOK_URL      si défini, tout échec y est notifié (même webhook que
#                          l'application, cf. app/core/alerting.py)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
API_INDEX="${API_INDEX:-1}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-fastapi_ecommerce}"
OFFSITE_RCLONE_REMOTE="${OFFSITE_RCLONE_REMOTE:-}"
RETENTION_LOCAL_ONLY="${RETENTION_LOCAL_ONLY:-false}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/db_${STAMP}.dump"
STORAGE_FILE="$BACKUP_DIR/storage_${STAMP}.tar.gz"

# On écrit dans des .part : une sortie tronquée (pg_dump tué, disque plein) ne
# doit jamais porter un nom d'archive valide, sinon la rotation la supprimera
# dans 14 jours en la faisant passer pour une sauvegarde saine.
# Une sauvegarde qui échoue en silence est pire que pas de sauvegarde : on croit
# être protégé. Le trap nettoie les fichiers partiels ET notifie le webhook
# d'alerting pour toute sortie non nulle, y compris un `set -e` en cours de route.
on_exit() {
  local exit_code=$?
  rm -f "$DB_FILE.part" "$STORAGE_FILE.part"
  [ "$exit_code" -eq 0 ] && return 0
  echo "[$(date -Is)] ÉCHEC de la sauvegarde (code $exit_code)" >&2
  if [ -n "$ALERT_WEBHOOK_URL" ]; then
    curl -fsS --max-time 10 -H 'Content-Type: application/json' \
      -d "{\"text\":\"Sauvegarde ecommerce ÉCHOUÉE sur $(hostname) (code ${exit_code}) — voir le log du cron\"}" \
      "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
  fi
  return "$exit_code"
}
trap on_exit EXIT

echo "[$(date -Is)] Sauvegarde PostgreSQL ($PGDATABASE) …"
# Format custom (-Fc) : compressé, restaurable table par table avec pg_restore.
$COMPOSE_CMD exec -T postgres pg_dump -U "$PGUSER" -d "$PGDATABASE" -Fc \
  > "$DB_FILE.part"

# Un dump custom valide commence par le magic "PGDMP".
if ! head -c 5 "$DB_FILE.part" | grep -q "PGDMP"; then
  echo "ERREUR : dump PostgreSQL invalide (magic PGDMP absent)" >&2
  exit 1
fi
mv "$DB_FILE.part" "$DB_FILE"

echo "[$(date -Is)] Sauvegarde du volume des uploads …"
# Le volume storage_data est monté dans le conteneur api ; tar streamé vers l'hôte.
$COMPOSE_CMD exec --index "$API_INDEX" -T api \
  tar czf - -C /tmp fastapi_ecommerce_storage > "$STORAGE_FILE.part"

# Le dump avait sa vérification, pas l'archive : un tar tronqué passait inaperçu.
if ! tar tzf "$STORAGE_FILE.part" > /dev/null 2>&1; then
  echo "ERREUR : archive des uploads illisible" >&2
  exit 1
fi
mv "$STORAGE_FILE.part" "$STORAGE_FILE"

echo "[$(date -Is)] Sauvegardes vérifiées :"
ls -lh "$DB_FILE" "$STORAGE_FILE"

# ── Copie hors serveur ────────────────────────────────────────────────────────
offsite_done=false
if [ -n "$OFFSITE_RCLONE_REMOTE" ]; then
  echo "[$(date -Is)] Copie hors serveur vers $OFFSITE_RCLONE_REMOTE …"
  rclone copy "$DB_FILE" "$OFFSITE_RCLONE_REMOTE"
  rclone copy "$STORAGE_FILE" "$OFFSITE_RCLONE_REMOTE"
  offsite_done=true
else
  echo "[$(date -Is)] AVERTISSEMENT : OFFSITE_RCLONE_REMOTE non défini —" \
       "les sauvegardes ne quittent pas ce serveur." >&2
fi

# ── Rotation ──────────────────────────────────────────────────────────────────
if [ "$offsite_done" = true ] || [ "$RETENTION_LOCAL_ONLY" = "true" ]; then
  echo "[$(date -Is)] Rotation (> ${RETENTION_DAYS} jours) …"
  find "$BACKUP_DIR" -name 'db_*.dump' -mtime "+${RETENTION_DAYS}" -delete
  find "$BACKUP_DIR" -name 'storage_*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete
else
  echo "[$(date -Is)] Rotation ignorée : aucune copie distante configurée." \
       "Forcer avec RETENTION_LOCAL_ONLY=true en connaissance de cause." >&2
fi

echo "[$(date -Is)] OK — $(ls -1 "$BACKUP_DIR" | wc -l) fichier(s) dans $BACKUP_DIR"
