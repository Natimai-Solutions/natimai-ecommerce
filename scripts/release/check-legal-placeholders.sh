#!/usr/bin/env bash
# Garde-fou d'ouverture : refuse tant que l'identité légale n'est pas renseignée.
#
# L'identité vit en base (system_settings, clés legal_*), éditable depuis le
# back-office. Ce script interroge l'endpoint public de l'API — il vérifie donc
# l'environnement RÉEL, pas ce qui est écrit dans le dépôt : lancer contre la
# production répond sur la production.
#
# Une facture sans raison sociale ni numéro d'immatriculation n'est pas un
# document comptable valable, et des mentions légales incomplètes exposent
# l'éditeur.
#
# Il ne vérifie PAS que le contenu est juridiquement correct — cela reste le
# travail d'un conseil (cf. L1 du plan de travail).
#
# Usage :
#   ./scripts/release/check-legal-placeholders.sh
#   API_URL=https://api.exemple.pf ./scripts/release/check-legal-placeholders.sh
set -uo pipefail

API_URL="${API_URL:-http://localhost:8000}"
ENDPOINT="$API_URL/api/v1/system/settings"

# Les clés indispensables à une facture valable : qui vend, où, sous quel
# numéro. Les autres sont requises pour les pages légales.
REQUIRED_FOR_INVOICING="legal_trading_name legal_head_office_address legal_tahiti_number"

echo "Identité légale — $ENDPOINT"

RESPONSE="$(curl -fsS --max-time 15 "$ENDPOINT" 2>/dev/null)" || {
  echo "  ERREUR : API injoignable sur $ENDPOINT" >&2
  echo "  (API_URL=… pour viser un autre environnement)" >&2
  exit 2
}

# Le parsing JSON passe par python3 : awk sur du JSON casse au premier texte
# légal contenant une virgule ou une accolade. La réponse transite par
# l'environnement — le script Python occupe déjà stdin.
export LEGAL_SETTINGS_JSON="$RESPONSE"
export REQUIRED_FOR_INVOICING
python3 <<'PYEOF'
import json
import os
import sys

required_for_invoicing = set(os.environ["REQUIRED_FOR_INVOICING"].split())
settings = {
    row["key"]: (row.get("value") or "").strip()
    for row in json.loads(os.environ["LEGAL_SETTINGS_JSON"])
    if row["key"].startswith("legal_")
}

if not settings:
    print("  ERREUR : aucune clé legal_* — la base n'a pas été seedée "
          "(lancer le service migrate).", file=sys.stderr)
    raise SystemExit(2)

missing = sorted(key for key, value in settings.items() if not value)
blocking = sorted(key for key in missing if key in required_for_invoicing)

print(f"  {len(settings) - len(missing)}/{len(settings)} champ(s) renseigné(s)")

if not missing:
    print()
    print("Identité légale complète. Reste la validation par un conseil "
          "juridique (L1).")
    raise SystemExit(0)

if blocking:
    print("\n  BLOQUANT pour la facturation :")
    for key in blocking:
        print(f"    - {key}")

other = [key for key in missing if key not in required_for_invoicing]
if other:
    print("\n  Manquants sur les pages légales :")
    for key in other:
        print(f"    - {key}")

print(
    "\nÉCHEC — compléter depuis le back-office (Réglages système) "
    "ou via PUT /admin/system-settings/{key}. Voir docs/DEPLOYMENT.md §13.",
    file=sys.stderr,
)
raise SystemExit(1)
PYEOF
