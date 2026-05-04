# ── Builder stage — компилируем bundle, отбрасываем после ─────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY . .
# heap 768MB не даёт vite/tsc сожрать всю память сервера (Exit 137 OOM)
ENV NODE_OPTIONS="--max-old-space-size=768"
RUN npm run build

# ── Runtime stage — только готовый bundle + server.mjs ────────────
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/server.mjs ./server.mjs
EXPOSE 3080
CMD ["node", "server.mjs"]
