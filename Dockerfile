FROM node:24.22-trixie-slim AS frontend-build

ARG SINGBOX_SCHEMA_URL=https://github.com/BlackDuty/sing-box-schema/releases/download/v1.13.13/schema.json
ARG MIHOMO_SCHEMA_URL=https://github.com/dongchengjie/meta-json-schema/releases/download/v1.19.29/meta-json-schema.json

WORKDIR /opt/frontend

COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps --prefer-offline --no-audit --no-fund

COPY frontend/ ./
RUN npm run start:build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && mkdir -p dist/assets \
    && curl -fsSL https://validator.remna.dev/wasm_exec.js -o dist/assets/wasm_exec.js \
    && curl -fsSL https://validator.remna.dev/xray.schema.json -o dist/assets/xray.schema.json \
    && curl -fsSL https://validator.remna.dev/xray.schema.cn.json -o dist/assets/xray.schema.cn.json \
    && curl -fsSL ${SINGBOX_SCHEMA_URL} -o dist/assets/singbox.schema.json \
    && curl -fsSL ${MIHOMO_SCHEMA_URL} -o dist/assets/mihomo.schema.json \
    && curl -fsSL https://validator.remna.dev/main.wasm -o dist/assets/main.wasm \
    && rm -rf /var/lib/apt/lists/*

FROM node:24.22-trixie-slim AS backend-build

WORKDIR /opt/app

ENV PRISMA_CLI_BINARY_TARGETS=debian-openssl-3.0.x,linux-arm64-openssl-3.0.x

COPY backend/package*.json ./
COPY backend/prisma ./prisma
COPY backend/prisma.config.ts ./prisma.config.ts
COPY backend/patches ./patches

RUN npm ci --prefer-offline --no-audit --no-fund

COPY backend/ ./

RUN npm run migrate:generate \
    && npm run generate:openapi \
    && test -s openapi.json \
    && npm run build \
    && npm cache clean --force \
    && npm prune --omit=dev

FROM node:24.22-trixie-slim

LABEL org.opencontainers.image.title="Remnawave Custom"
LABEL org.opencontainers.image.description="Remnawave with local policy modules and controlled compatibility patches"
LABEL org.opencontainers.image.source="https://github.com/Ryanlyjp/remnawave-custom-deploy"
LABEL org.opencontainers.image.licenses="AGPL-3.0-only"

WORKDIR /opt/app

ARG BRANCH=main
ARG __RW_METADATA_VERSION=3.4.7-custom
ARG __RW_METADATA_GIT_BACKEND_COMMIT=unknown
ARG __RW_METADATA_GIT_FRONTEND_COMMIT=unknown
ARG __RW_METADATA_GIT_BRANCH=custom/3.4.7-managed-tuic
ARG __RW_METADATA_BUILD_TIME=unknown
ARG __RW_METADATA_BUILD_NUMBER=0

ENV REMNAWAVE_BRANCH=${BRANCH}
ENV PRISMA_HIDE_UPDATE_MESSAGE=true
ENV PRISMA_ENGINES_CHECKSUM_IGNORE_MISSING=1
ENV PM2_DISABLE_VERSION_CHECK=true
ENV NODE_OPTIONS="--max-old-space-size=16384"
ENV __RW_METADATA_VERSION=${__RW_METADATA_VERSION}
ENV __RW_METADATA_GIT_BACKEND_COMMIT=${__RW_METADATA_GIT_BACKEND_COMMIT}
ENV __RW_METADATA_GIT_FRONTEND_COMMIT=${__RW_METADATA_GIT_FRONTEND_COMMIT}
ENV __RW_METADATA_GIT_BRANCH=${__RW_METADATA_GIT_BRANCH}
ENV __RW_METADATA_BUILD_TIME=${__RW_METADATA_BUILD_TIME}
ENV __RW_METADATA_BUILD_NUMBER=${__RW_METADATA_BUILD_NUMBER}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-build /opt/app/dist ./dist
COPY --from=backend-build /opt/app/openapi.json ./openapi.json
COPY --from=frontend-build /opt/frontend/dist ./frontend
COPY --from=backend-build /opt/app/prisma/generated ./prisma/generated
COPY --from=backend-build /opt/app/prisma/migrations ./prisma/migrations
COPY --from=backend-build /opt/app/prisma/schema.prisma ./prisma/schema.prisma
COPY --from=backend-build /opt/app/node_modules ./node_modules

COPY backend/configs /var/lib/remnawave/configs
COPY backend/package*.json ./
COPY backend/prisma.config.ts ./prisma.config.ts
COPY backend/ecosystem.config.js ./
COPY backend/docker-entrypoint.sh ./

RUN npm install pm2 -g \
    && chmod +x /opt/app/dist/cli.js \
    && ln -s /opt/app/dist/cli.js /usr/local/bin/cli

ENTRYPOINT ["/bin/sh", "docker-entrypoint.sh"]
CMD ["pm2-runtime", "start", "ecosystem.config.js", "--env", "production"]
