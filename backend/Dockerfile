# Python 3.14 : uvloop >= 0.22 est requis (0.21 importait
# asyncio.events.BaseDefaultEventLoopPolicy, retiré en 3.14 ; les workers
# uvicorn mouraient à l'import). Voir uv.lock. La CI tourne sur la même
# version (ci.yml).
ARG PYTHON_IMAGE=python:3.14-slim

# ── Build stage : l'environnement virtuel, avec les outils de compilation ─────
FROM ${PYTHON_IMAGE} AS builder

# Outils de compilation pour les paquets sans roue binaire ; ils restent dans
# cette étape et ne partent pas en production.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# uv figé (la 0.4.15 d'origine datait d'août 2024) ; même version en CI.
# Depuis PyPI plutôt que l'image ghcr.io/astral-sh/uv : les tirages anonymes
# de ghcr.io sont limités par IP et la CI E2E a été refusée (429) alors que
# rien n'avait changé (03/10/2026). PyPI est déjà joint pour les dépendances.
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
RUN pip install --no-cache-dir uv==0.8.17

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dépendances seules d'abord (couche en cache tant que le lock ne change pas).
# INSTALL_DEV=true (docker-compose.override.yml) ajoute pytest & co pour
# lancer les tests dans le conteneur de développement ; jamais en production.
ARG INSTALL_DEV=false
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    if [ "$INSTALL_DEV" = "true" ]; then DEV_FLAG=""; else DEV_FLAG="--no-dev"; fi \
    && uv sync --frozen --no-install-project $DEV_FLAG

COPY ./pyproject.toml ./uv.lock ./alembic.ini /app/
COPY ./app /app/app

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_DEV" = "true" ]; then DEV_FLAG=""; else DEV_FLAG="--no-dev"; fi \
    && uv sync --frozen $DEV_FLAG

# ── Runtime stage : bibliothèques d'exécution seulement, utilisateur non-root ─
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    # `uv run` utilise l'environnement construit, sans jamais le resynchroniser
    # (pas de téléchargement ni d'écriture au démarrage).
    UV_NO_SYNC=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/.uv-cache

# Bibliothèques d'exécution de WeasyPrint (PDF des factures), curl pour les
# healthchecks. Ni compilateur ni en-têtes de développement.
# `apt-get upgrade` : l'image de base suit les versions ponctuelles de Debian,
# pas ses correctifs de sécurité ; Trivy (security.yml) bloque sur ceux qui
# manquent.
# SECURITY_UPDATES_DATE (jour UTC, passé par la CI) : sans lui, le cache de
# couches de GitHub Actions resservirait la couche d'une mise à jour plus
# ancienne tant que l'image de base ne bouge pas, et les correctifs publiés
# depuis n'arriveraient jamais (Trivy les signale alors).
ARG SECURITY_UPDATES_DATE=
RUN echo "security updates: ${SECURITY_UPDATES_DATE:-local}" \
    && apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libwebp7 \
    libffi8 \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

# pip n'a aucun rôle à l'exécution (le venv construit est copié tel quel et
# `uv run` ne synchronise rien) ; il embarque ses propres copies de urllib3,
# msgpack et setuptools, que Trivy signale. La roue pip d'ensurepip aussi.
RUN python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.*/ensurepip/_bundled /root/.cache/pip

# Le binaire uv installé dans l'étape de build (même version, aucun tirage).
COPY --from=builder /usr/local/bin/uv /bin/uv

# Utilisateur applicatif sans privilèges. L'entrypoint démarre en root le
# temps de rendre le volume de stockage à cet utilisateur (volumes créés par
# une image antérieure, qui tournait en root), puis abandonne ses droits.
ARG APP_UID=10001
RUN groupadd --system --gid ${APP_UID} app \
    && useradd --system --uid ${APP_UID} --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /tmp/fastapi_ecommerce_storage \
    && chown app:app /tmp/fastapi_ecommerce_storage

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
RUN chmod +x /app/app/scripts/entrypoint.sh

ENTRYPOINT ["/app/app/scripts/entrypoint.sh"]
CMD ["api"]
