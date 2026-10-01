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
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

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
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libwebp7 \
    libffi8 \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

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
