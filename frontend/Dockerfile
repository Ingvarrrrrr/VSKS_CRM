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
# heap 1536MB — Phase 26 раздула CreateOrderView, 768MB перестало хватать
# (было FATAL ERROR: Reached heap limit Allocation failed). 1536 — компромисс
# между скоростью OOM-recovery и реальной потребностью vite + Vuetify + ApexCharts.
ENV NODE_OPTIONS="--max-old-space-size=1536"
RUN npm run build

# ── Runtime stage — только готовый bundle + server.mjs ────────────
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/server.mjs ./server.mjs
EXPOSE 3080
CMD ["node", "server.mjs"]
