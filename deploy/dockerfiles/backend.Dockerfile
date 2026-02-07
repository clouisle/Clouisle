# ---- Builder ----
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libxml2-dev libxmlsec1-dev \
    libxmlsec1-openssl pkg-config && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# ---- Runtime ----
FROM python:3.13-slim

# Install runtime dependencies + Node.js (for code sandbox and MCP stdio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libxml2 libxmlsec1 libxmlsec1-openssl curl \
    ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy uv for MCP stdio (uvx command)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Create non-root user for security
RUN groupadd --gid 1000 clouisle \
    && useradd --uid 1000 --gid clouisle --shell /bin/bash --create-home clouisle

WORKDIR /app
COPY --from=builder /app/.venv /app/backend/.venv
COPY backend/ ./backend/
COPY main.py ./

RUN mkdir -p /app/uploads \
    && find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && chown -R clouisle:clouisle /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/backend/.venv/bin:$PATH"

# Switch to non-root user
USER clouisle

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default: start the API server with Gunicorn (production).
# Override with worker/beat commands in docker-compose / K8s.
CMD ["python", "main.py", "server", "-H", "0.0.0.0", "-w", "4", "--no-reload"]
