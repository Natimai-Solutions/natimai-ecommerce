#!/usr/bin/env bash
# Redémarre les conteneurs du projet que Docker déclare « unhealthy », et
# prévient (ALERT_WEBHOOK_URL).
#
# Docker relance un conteneur dont le processus s'arrête (restart:
# unless-stopped), pas un conteneur seulement « unhealthy ». Le worker se
# termine lui-même quand il est bloqué (app/core/worker_watchdog.py) ; ce
# script rattrape le reste — un processus figé en entier, un autre service
# dont le healthcheck échoue (décision du 18/11/2026, Z3).
#
# À planifier toutes les 5 minutes : voir ecommerce-autoheal.cron.
#
# Variables surchargeables par l'environnement :
#   COMPOSE_PROJECT_NAME  projet compose surveillé (défaut : nom du dépôt)
#   ALERT_WEBHOOK_URL     webhook notifié à chaque redémarrage (même valeur que
#                         l'application, cf. app/core/alerting.py)
#   MAX_RESTARTS_PER_HOUR au-delà, le conteneur n'est plus redémarré (une
#                         boucle de redémarrages cache la panne) — alerte seule
#   STATE_DIR             où compter les redémarrages (défaut /var/tmp)
#   DRY_RUN               "true" : n'affiche que ce qui serait fait
set -euo pipefail

cd "$(dirname "$0")/../.."
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
MAX_RESTARTS_PER_HOUR="${MAX_RESTARTS_PER_HOUR:-3}"
STATE_DIR="${STATE_DIR:-/var/tmp}"
DRY_RUN="${DRY_RUN:-false}"
STATE_FILE="$STATE_DIR/ecommerce-autoheal-$PROJECT.log"

alert() {
  echo "[$(date -Is)] $1"
  if [ -n "$ALERT_WEBHOOK_URL" ] && [ "$DRY_RUN" != "true" ]; then
    local text=${1//\"/\'}
    curl -fsS --max-time 10 -H 'Content-Type: application/json' \
      -d "{\"text\":\"[$(hostname)] $text\"}" \
      "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
  fi
}

mkdir -p "$STATE_DIR"
touch "$STATE_FILE"
now=$(date +%s)
# Only the last hour of restarts is kept.
awk -v limit=$((now - 3600)) '$1 >= limit' "$STATE_FILE" > "$STATE_FILE.tmp" || true
mv "$STATE_FILE.tmp" "$STATE_FILE"

unhealthy=$(docker ps \
  --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "health=unhealthy" \
  --format '{{.Names}}')

[ -z "$unhealthy" ] && exit 0

for name in $unhealthy; do
  recent=$(awk -v n="$name" '$2 == n' "$STATE_FILE" | wc -l)
  if [ "$recent" -ge "$MAX_RESTARTS_PER_HOUR" ]; then
    alert "Conteneur $name toujours unhealthy après $recent redémarrages en une heure : NON redémarré, intervention nécessaire."
    continue
  fi
  if [ "$DRY_RUN" = "true" ]; then
    echo "[$(date -Is)] (DRY_RUN) redémarrerait $name"
    continue
  fi
  if docker restart "$name" >/dev/null; then
    echo "$now $name" >> "$STATE_FILE"
    alert "Conteneur $name unhealthy : redémarré automatiquement ($((recent + 1)) en une heure)."
  else
    alert "Conteneur $name unhealthy : le redémarrage a ÉCHOUÉ."
  fi
done
