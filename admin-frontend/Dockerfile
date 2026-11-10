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
COPY shared/         ./shared/
COPY admin-frontend/ ./admin-frontend/

# Install only admin + workspace deps (skips frontend's postinstall)
RUN pnpm install --frozen-lockfile --filter "admin..."

# Public API origin baked into the Vite build (the browser calls this URL).
# MUST be provided for any non-local build — e.g. https://api.example.com —
# otherwise the image ships with localhost:8000 and is unusable in production.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
# Sentry du navigateur (R8 / U3) ; vide = désactivé.
ARG VITE_SENTRY_DSN=
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT=
ENV VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT
ARG VITE_APP_RELEASE=
ENV VITE_APP_RELEASE=$VITE_APP_RELEASE

# Build SPA (run from workspace root with explicit filter)
RUN pnpm --filter admin run build

# ── Production stage ────────────────────────────────────────────────────────────
FROM nginx:1.31-alpine AS runner

# Correctifs de sécurité Alpine que l'image de base n'a pas encore (Trivy,
# security.yml, bloque sur ceux qui ont un correctif publié).
# SECURITY_UPDATES_DATE (jour UTC, passé par la CI) : sans lui, le cache de
# couches de GitHub Actions resservirait la couche d'une mise à jour plus
# ancienne tant que l'image de base ne bouge pas, et les correctifs publiés
# depuis n'arriveraient jamais (Trivy les signale alors).
ARG SECURITY_UPDATES_DATE=
RUN echo "security updates: ${SECURITY_UPDATES_DATE:-local}" && apk upgrade --no-cache

COPY --from=builder /workspace/admin-frontend/dist/spa /usr/share/nginx/html
COPY admin-frontend/nginx.conf /etc/nginx/conf.d/default.conf

# nginx écoute sur 80 (cf. nginx.conf). En dev, docker-compose publie 3001:80 ;
# en prod, le reverse proxy (Caddy) atteint le conteneur sur admin-frontend:80.
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
