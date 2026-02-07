# ---- Builder ----
FROM oven/bun:1-debian AS builder

WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install

COPY frontend/ ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

ARG NEXT_PUBLIC_API_URL=/api/v1
ARG NEXT_PUBLIC_APP_VERSION=0.0.0-dev
ARG NEXT_PUBLIC_BUILD_DATE=unknown
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}
ENV NEXT_PUBLIC_BUILD_DATE=${NEXT_PUBLIC_BUILD_DATE}

RUN bun run build

# ---- Runtime ----
FROM node:22-alpine

WORKDIR /app

# Copy Next.js standalone build
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["node", "server.js"]
