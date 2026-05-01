# ---- Builder ----
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libxml2-dev libxmlsec1-dev \
    libxmlsec1-openssl pkg-config && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# ---- Runtime ----
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git gnupg locales \
    coreutils findutils file zip unzip \
    libpq5 libxml2 libxmlsec1 libxmlsec1-openssl \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8

RUN pip install --no-cache-dir uv

RUN groupadd --gid 1000 clouisle \
    && useradd --uid 1000 --gid clouisle --shell /bin/bash --create-home clouisle

WORKDIR /app
COPY --from=builder /app/.venv /app/backend/.venv
COPY backend/ ./backend/
COPY main.py ./

RUN mkdir -p /app/uploads /tmp/clouisle-sandbox \
    && find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && chown -R clouisle:clouisle /app /tmp/clouisle-sandbox

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

USER clouisle

CMD ["python", "main.py", "sandbox-worker"]
