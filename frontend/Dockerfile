# Dockerfile do frontend (Next.js) — build em multi-stage para imagem enxuta.

# --- Etapa 1: build ---
FROM node:22-slim AS builder
WORKDIR /app
# Instala dependências primeiro (aproveita cache).
COPY package.json package-lock.json ./
RUN npm ci
# Copia o código e gera o build de produção (saída "standalone").
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- Etapa 2: runtime (só o necessário para rodar) ---
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
# Copia o servidor standalone e os arquivos estáticos.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
