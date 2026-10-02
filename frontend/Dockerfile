# ── Build stage ────────────────────────────────────────────────────────────────
FROM node:24-alpine AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

WORKDIR /workspace

# Workspace manifests (all package.json needed for workspace resolution)
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY frontend/package.json        ./frontend/
COPY admin-frontend/package.json  ./admin-frontend/
COPY shared/api-types/package.json  ./shared/api-types/
COPY shared/api-client/package.json ./shared/api-client/
COPY shared/utils/package.json      ./shared/utils/
COPY shared/ui/package.json         ./shared/ui/

# Full source only for what we're building
COPY shared/   ./shared/
COPY frontend/ ./frontend/

# Install only frontend + workspace deps (skips admin's postinstall).
# frontend/src-ssr is a workspace package of its own (Express server deps):
# app-vite 3 would otherwise run its own unlocked install there at build time.
RUN pnpm install --frozen-lockfile --filter "frontend..." --filter "frontend-ssr-server"

# Public API origin baked into the Vite build (the browser calls this URL).
# MUST be provided for any non-local build — e.g. https://api.example.com —
# otherwise the image ships with localhost:8000 and is unusable in production.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# URL publique de la vitrine : liens canoniques, JSON-LD, sitemap (R8 / U6).
ARG VITE_PUBLIC_SITE_URL=
ENV VITE_PUBLIC_SITE_URL=$VITE_PUBLIC_SITE_URL
# Sentry du navigateur (R8 / U3) ; vide = désactivé.
ARG VITE_SENTRY_DSN=
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT=
ENV VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT
ARG VITE_APP_RELEASE=
ENV VITE_APP_RELEASE=$VITE_APP_RELEASE

# Build SSR (run from workspace root with explicit filter)
RUN pnpm --filter frontend run build

# The generated dist/ssr/package.json no longer lists the bundled @app/*
# workspace packages: see ssr.extendSSRPackageJson in quasar.config.ts.

# ── Production dependencies of the SSR server, from the lockfile ──────────────
# The generated dist/ssr/package.json pins the direct dependencies only; an
# `npm install` there resolved everything else afresh on every build. Here the
# whole tree comes from pnpm-lock.yaml (--frozen-lockfile), production only,
# with the hoisted linker: plain directories, copied as is to the runner.
FROM node:24-alpine AS prod-deps

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

WORKDIR /workspace
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY frontend/package.json          ./frontend/
COPY frontend/src-ssr/package.json  ./frontend/src-ssr/
COPY admin-frontend/package.json    ./admin-frontend/
COPY shared/api-types/package.json  ./shared/api-types/
COPY shared/api-client/package.json ./shared/api-client/
COPY shared/utils/package.json      ./shared/utils/
COPY shared/ui/package.json         ./shared/ui/

RUN pnpm install --frozen-lockfile --prod --ignore-scripts \
      --config.node-linker=hoisted \
      --filter "frontend..." --filter "frontend-ssr-server" \
    # The @app/* workspace packages are bundled into dist/ssr: their links
    # would only dangle in the runner.
    && rm -rf node_modules/@app

# ── Production stage ────────────────────────────────────────────────────────────
FROM node:24-alpine AS runner

ENV NODE_ENV=production
WORKDIR /app

COPY --from=builder /workspace/frontend/dist/ssr ./
COPY --from=prod-deps /workspace/node_modules ./node_modules

# The image's unprivileged user: the SSR server needs no write access.
USER node

EXPOSE 3000

CMD ["node", "index.js"]
