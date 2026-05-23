# ── Build stage ────────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

WORKDIR /workspace

# Copy workspace manifests first for layer caching
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY shared/api-types/package.json  ./shared/api-types/
COPY shared/api-client/package.json ./shared/api-client/
COPY shared/utils/package.json      ./shared/utils/
COPY admin-frontend/package.json    ./admin-frontend/

RUN pnpm install --frozen-lockfile

# Copy source
COPY shared/       ./shared/
COPY admin-frontend/ ./admin-frontend/

# Build SPA
WORKDIR /workspace/admin-frontend
RUN pnpm exec quasar build -m spa

# ── Production stage ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

COPY --from=builder /workspace/admin-frontend/dist/spa /usr/share/nginx/html
COPY admin-frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
