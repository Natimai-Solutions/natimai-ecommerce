#!/usr/bin/env bash
# Types TypeScript de l'API (shared/api-types/src/schema.ts) — R8 / U2.
#
# Le schéma OpenAPI est produit par l'application elle-même, sans serveur ni
# base : `app.openapi()` suffit. Puis openapi-typescript le transforme.
#
#   ./scripts/gen-api-types.sh          # regénère le fichier commité
#   ./scripts/gen-api-types.sh --check  # échoue si le fichier commité a dérivé
#
# Prérequis : `uv sync` dans backend/ et `pnpm install` à la racine.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/shared/api-types/src/schema.ts"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Des valeurs factices suffisent : la configuration est validée à l'import,
# rien n'est contacté.
export SECRET_KEY="${SECRET_KEY:-types-only-not-a-secret}"
export FIRST_SUPERUSER="${FIRST_SUPERUSER:-types@example.com}"
export FIRST_SUPERUSER_PASSWORD="${FIRST_SUPERUSER_PASSWORD:-types-only-password}"
export POSTGRES_SERVER="${POSTGRES_SERVER:-localhost}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-types-only}"

(cd "$ROOT/backend" && uv run --no-sync python -c '
import json, sys, warnings
warnings.simplefilter("ignore")
from app.main import app
json.dump(app.openapi(), sys.stdout)
') > "$TMP/openapi.json"

"$ROOT/node_modules/.bin/openapi-typescript" "$TMP/openapi.json" -o "$TMP/schema.ts" >/dev/null

if [[ "${1:-}" == "--check" ]]; then
  if ! diff -u "$TARGET" "$TMP/schema.ts" > "$TMP/schema.diff"; then
    echo "::error::shared/api-types/src/schema.ts ne correspond plus à l'API : lancer « pnpm gen:types » et commiter." >&2
    head -n 80 "$TMP/schema.diff" >&2
    exit 1
  fi
  echo "shared/api-types/src/schema.ts est à jour."
else
  cp "$TMP/schema.ts" "$TARGET"
  echo "shared/api-types/src/schema.ts regénéré."
fi
