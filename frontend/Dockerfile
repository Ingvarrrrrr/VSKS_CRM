# ── Builder stage — компилируем bundle, отбрасываем после ─────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund

# Cache-buster для шага сборки приложения. GIT_SHA передаётся autodeploy.sh
# реальным хешем коммита и меняется на каждый деплой → эта RUN-инструкция
# гарантированно выполняется заново → Docker считает недействительным кеш
# ВСЕХ последующих слоёв (COPY . . и npm run build), даже если их
# содержимое совпало бы с прошлой сборкой. При этом слои ВЫШЕ (COPY
# package*.json + npm ci — долгая установка зависимостей, от кода не
# зависит) кешируются как обычно, т.к. ARG объявлен и использован ПОСЛЕ них.
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /app/.git-sha

COPY . .
# heap 4096MB (09.10.2026, инцидент 08.10 23:30-00:09: прод 3.9 ГБ RAM
# ушёл в подкачку, load 184, сайт 502 — автодеплой не дождался образа из
# GHCR и собрал фронт ЛОКАЛЬНО на сервере с лимитом 1536МБ, который к этому
# времени уже не хватал OOM при `npm run build`; см. также autodeploy.sh —
# сервер больше НЕ собирает фронт в обычном режиме, сборка только здесь,
# на GitHub Actions раннере с 7 ГБ RAM). 1536 был компромиссом под рост кода
# Phase 26 (CreateOrderView), с тех пор код продолжил расти — 4096 даёт запас
# на раннере, где память не дефицит, и не является нагрузкой на прод.
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npm run build

# ── Runtime stage — только готовый bundle + server.mjs ────────────
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/server.mjs ./server.mjs
EXPOSE 3080
CMD ["node", "server.mjs"]
