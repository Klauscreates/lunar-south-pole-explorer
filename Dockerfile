# Build the verified snapshot; scientific regeneration is not a serving task.
FROM node:24-bookworm-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
COPY apps/web/scripts/sync-cesium.mjs scripts/sync-cesium.mjs
RUN npm ci
WORKDIR /app
COPY apps/web apps/web
COPY outputs outputs
COPY science science
COPY data data
COPY scripts scripts
COPY run_reference_lander.py run_reference_lander.py
COPY run_local_terrain.py run_local_terrain.py
WORKDIR /app/apps/web
RUN npm run build && npm prune --omit=dev --ignore-scripts

FROM python:3.13-slim-bookworm AS runtime
COPY --from=build /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home node
WORKDIR /app
RUN python3 -m venv /app/.venv
COPY requirements-serve.txt ./
RUN /app/.venv/bin/pip install --no-cache-dir -r requirements-serve.txt
COPY --from=build --chown=node:node /app/apps/web /app/apps/web
COPY --chown=node:node scripts/terrain_server.py scripts/terrain_server.py
COPY --chown=node:node data/web_terrain data/web_terrain
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PYTHONUNBUFFERED=1 \
    PLANNER_HOST=0.0.0.0 PORT=10000 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
USER node
EXPOSE 10000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "apps/web/scripts/planner.mjs", "--production"]
