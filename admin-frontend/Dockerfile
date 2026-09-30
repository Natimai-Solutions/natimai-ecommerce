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

# Build SPA (run from workspace root with explicit filter)
RUN pnpm --filter admin run build

# ── Production stage ────────────────────────────────────────────────────────────
FROM nginx:1.31-alpine AS runner

COPY --from=builder /workspace/admin-frontend/dist/spa /usr/share/nginx/html
COPY admin-frontend/nginx.conf /etc/nginx/conf.d/default.conf

# nginx écoute sur 80 (cf. nginx.conf). En dev, docker-compose publie 3001:80 ;
# en prod, le reverse proxy (Caddy) atteint le conteneur sur admin-frontend:80.
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
