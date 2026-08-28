# Python 3.13 : possible depuis le retrait de passlib, qui importait le module
# stdlib `crypt` supprimé en 3.13. Toute la suite tourne déjà sur 3.13 en local.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

# Install system dependencies for WeasyPrint and other requirements
RUN apt-get update && apt-get install -y \
    # WeasyPrint dependencies
    libwebp-dev \
    libwebp7 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Additional common dependencies
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.4.15 /uv /bin/uv

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# Install dependencies
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

ENV PYTHONPATH=/app

COPY ./pyproject.toml ./uv.lock ./alembic.ini /app/
COPY ./app /app/app

# Sync the project
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

# Make entrypoint script executable
RUN chmod +x /app/app/scripts/entrypoint.sh

# Set working directory and entrypoint
WORKDIR /app
ENTRYPOINT ["/app/app/scripts/entrypoint.sh"]
CMD ["api"]