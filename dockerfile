# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Build
# Run everything on the host (faster caching), then copy artefacts in.
# Before running docker compose up, run these from inside backstage-app/:
#   yarn install
#   yarn tsc
#   yarn build:backend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-bookworm-slim AS build

WORKDIR /app

# Copy pre-built backend bundle produced by `yarn build:backend`
COPY backstage-app/packages/backend/dist/skeleton.tar.gz  skeleton.tar.gz
COPY backstage-app/packages/backend/dist/bundle.tar.gz    bundle.tar.gz
COPY backstage-app/yarn.lock                              yarn.lock
COPY backstage-app/package.json                           package.json

RUN tar xzf skeleton.tar.gz && rm skeleton.tar.gz

# Install only production dependencies
RUN --mount=type=cache,target=/root/.yarn/berry/cache \
    yarn workspaces focus --all --production

RUN tar xzf bundle.tar.gz && rm bundle.tar.gz

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-bookworm-slim

# Install libssl for Postgres client (pg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libssl3 && \
    rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production
# Required for Node 20 + Backstage scaffolder
ENV NODE_OPTIONS="--no-node-snapshot"

WORKDIR /app
USER node

COPY --from=build --chown=node:node /app .

# Copy config files — production config is mounted via docker-compose volume
COPY --chown=node:node backstage-app/app-config.yaml ./app-config.yaml

EXPOSE 7007

CMD ["node", "packages/backend", \
     "--config", "app-config.yaml", \
     "--config", "app-config.production.yaml"]
