# ── Build stage ────────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@10.0.0 --activate

WORKDIR /workspace

# Copy workspace manifests first for layer caching
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY shared/api-types/package.json ./shared/api-types/
COPY shared/api-client/package.json ./shared/api-client/
COPY shared/utils/package.json       ./shared/utils/
COPY frontend/package.json           ./frontend/

RUN pnpm install --frozen-lockfile

# Copy source
COPY shared/ ./shared/
COPY frontend/ ./frontend/

# Build SSR
WORKDIR /workspace/frontend
RUN pnpm exec quasar build -m ssr

# ── Production stage ────────────────────────────────────────────────────────────
FROM node:22-alpine AS runner

ENV NODE_ENV=production
WORKDIR /app

# Copy SSR dist (includes its own package.json with prod deps)
COPY --from=builder /workspace/frontend/dist/ssr ./

# Install only prod dependencies declared by the SSR bundle
RUN npm install --omit=dev --ignore-scripts

EXPOSE 3000

CMD ["node", "index.js"]
