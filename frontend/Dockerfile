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

# Full source only for what we're building
COPY shared/   ./shared/
COPY frontend/ ./frontend/

# Install only frontend + workspace deps (skips admin's postinstall)
RUN pnpm install --frozen-lockfile --filter "frontend..."

# Public API origin baked into the Vite build (the browser calls this URL).
# MUST be provided for any non-local build — e.g. https://api.example.com —
# otherwise the image ships with localhost:8000 and is unusable in production.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Build SSR (run from workspace root with explicit filter)
RUN pnpm --filter frontend run build

# Strip workspace:* deps from the generated SSR package.json
# (their code is already bundled into the JS via ssr.noExternal)
RUN node -e "const fs=require('fs');const p='/workspace/frontend/dist/ssr/package.json';const pkg=JSON.parse(fs.readFileSync(p,'utf8'));for(const k of Object.keys(pkg.dependencies||{})){if(String(pkg.dependencies[k]).startsWith('workspace:'))delete pkg.dependencies[k];}fs.writeFileSync(p,JSON.stringify(pkg,null,2));"

# ── Production stage ────────────────────────────────────────────────────────────
FROM node:24-alpine AS runner

ENV NODE_ENV=production
WORKDIR /app

COPY --from=builder /workspace/frontend/dist/ssr ./

RUN npm install --omit=dev --ignore-scripts

EXPOSE 3000

CMD ["node", "index.js"]
