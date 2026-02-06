# ---- Builder ----
FROM oven/bun:1-debian AS builder

WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

ARG NEXT_PUBLIC_API_URL=/api/v1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN bun run build

# ---- Runtime ----
FROM nginx:stable-alpine

RUN apk add --no-cache nodejs

# Nginx config
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf

# Next.js standalone app
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3001 \
    HOSTNAME=127.0.0.1

EXPOSE 3000

# Start Next.js server on port 3001 (internal), Nginx on port 3000 (external)
CMD sh -c "node server.js & nginx -g 'daemon off;'"
