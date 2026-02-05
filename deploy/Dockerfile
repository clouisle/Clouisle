# =============================================================================
# Clouisle Multi-Stage Dockerfile (Optimized for Production)
# =============================================================================
# Build targets:
#   - frontend-builder: Build frontend assets
#   - backend-builder: Build backend with dependencies
#   - all-in-one: Full stack with databases (for development/testing)
#   - app: Frontend + Backend + Worker + Beat in one image
#   - frontend: Frontend only
#   - backend: Backend API server only
#   - worker: Celery worker only
#   - beat: Celery beat scheduler only
#
# Usage:
#   docker build --target all-in-one -t clouisle:all-in-one .
#   docker build --target app -t clouisle:app .
#   docker build --target frontend -t clouisle:frontend .
#   docker build --target backend -t clouisle:backend .
#   docker build --target worker -t clouisle:worker .
#   docker build --target beat -t clouisle:beat .
# =============================================================================

# -----------------------------------------------------------------------------
# Stage: Frontend Builder
# -----------------------------------------------------------------------------
FROM oven/bun:1-debian AS frontend-builder

WORKDIR /app

# Copy package files first for better caching
COPY frontend/package.json frontend/bun.lock ./

# Install all dependencies (including dev deps needed for build)
RUN bun install --frozen-lockfile

# Copy frontend source
COPY frontend/ ./

# Build frontend
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
RUN bun run build

# -----------------------------------------------------------------------------
# Stage: Backend Builder (compile dependencies)
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS backend-builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY backend/pyproject.toml backend/uv.lock ./

# Install Python dependencies (production only)
RUN uv sync --frozen --no-dev --no-editable

# -----------------------------------------------------------------------------
# Stage: Backend Runtime Base (minimal runtime)
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS backend-runtime

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libxml2 \
    libxmlsec1 \
    libxmlsec1-openssl \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/cache/apt/archives/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=backend-builder /app/.venv /app/backend/.venv

# Copy application code
COPY backend/ ./backend/
COPY main.py ./

# Create uploads directory
RUN mkdir -p /app/uploads

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/backend/.venv/bin:$PATH"

# Remove __pycache__ and .pyc files
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
RUN find /app -type f -name "*.pyc" -delete 2>/dev/null || true

# -----------------------------------------------------------------------------
# Stage: All-in-One (Frontend + Backend + Databases)
# -----------------------------------------------------------------------------
FROM backend-runtime AS all-in-one

# Install additional dependencies for all-in-one
# Add PostgreSQL official repository for PostgreSQL 16
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg2 \
    lsb-release \
    && echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-16 \
    redis-server \
    nginx \
    supervisor \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Download and install Qdrant (detect architecture)
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        QDRANT_ARCH="aarch64-unknown-linux-musl"; \
    else \
        QDRANT_ARCH="x86_64-unknown-linux-musl"; \
    fi && \
    curl -fsSL -o /tmp/qdrant.tar.gz "https://github.com/qdrant/qdrant/releases/download/v1.12.1/qdrant-${QDRANT_ARCH}.tar.gz" \
    && tar -xzf /tmp/qdrant.tar.gz -C /usr/local/bin/ \
    && rm /tmp/qdrant.tar.gz

# Copy frontend (only production files)
COPY --from=frontend-builder /app/.next/standalone ./frontend/
COPY --from=frontend-builder /app/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/public ./frontend/public

# Create data directories
RUN mkdir -p /var/lib/postgresql/data /var/lib/redis /var/lib/qdrant /var/log/nginx /var/log/supervisor

# Copy configs
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/supervisor/all-in-one.conf /etc/supervisor/conf.d/clouisle.conf
COPY deploy/scripts/all-in-one-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

# -----------------------------------------------------------------------------
# Stage: App (Frontend + Backend + Worker + Beat)
# -----------------------------------------------------------------------------
FROM backend-runtime AS app

# Install supervisor only
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Bun (minimal)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

# Copy frontend (only production files)
COPY --from=frontend-builder /app/.next/standalone ./frontend/
COPY --from=frontend-builder /app/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/public ./frontend/public

# Create log directory
RUN mkdir -p /var/log/supervisor

# Copy supervisor config
COPY deploy/supervisor/app.conf /etc/supervisor/conf.d/clouisle.conf

EXPOSE 3000 8000

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

# -----------------------------------------------------------------------------
# Stage: Frontend Only (Standalone)
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /app

# Copy standalone build
COPY --from=frontend-builder /app/.next/standalone ./
COPY --from=frontend-builder /app/.next/static ./.next/static
COPY --from=frontend-builder /app/public ./public

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

EXPOSE 3000

CMD ["node", "server.js"]

# -----------------------------------------------------------------------------
# Stage: Backend API Server Only
# -----------------------------------------------------------------------------
FROM backend-runtime AS backend

EXPOSE 8000

CMD ["python", "main.py", "server", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]

# -----------------------------------------------------------------------------
# Stage: Celery Worker Only
# -----------------------------------------------------------------------------
FROM backend-runtime AS worker

CMD ["python", "main.py", "worker", "-c", "4", "-Q", "default,workflow"]

# -----------------------------------------------------------------------------
# Stage: Celery Beat Only
# -----------------------------------------------------------------------------
FROM backend-runtime AS beat

CMD ["python", "main.py", "beat"]
