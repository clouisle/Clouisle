#!/bin/bash
set -e

# Create log directories
mkdir -p /var/log/supervisor /var/log/postgresql
chown postgres:postgres /var/log/postgresql

# Initialize PostgreSQL if needed
if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
    echo "Initializing PostgreSQL database..."
    chown -R postgres:postgres /var/lib/postgresql/data
    su postgres -c "/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/data"

    # Start PostgreSQL temporarily to create database
    su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/data -l /var/log/postgresql/postgresql.log start"
    sleep 3

    # Create database and user
    su postgres -c "psql -c \"ALTER USER postgres PASSWORD '${POSTGRES_PASSWORD:-password}';\""
    su postgres -c "psql -c \"CREATE DATABASE ${POSTGRES_DB:-clouisle};\""

    # Stop PostgreSQL (supervisor will start it)
    su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/data stop"
fi

# Create Qdrant config
mkdir -p /etc/qdrant
cat > /etc/qdrant/config.yaml << EOF
storage:
  storage_path: /var/lib/qdrant/storage
service:
  api_key: ${QDRANT_API_KEY:-clouisle-qdrant-cbd3c07d}
  host: 0.0.0.0
  http_port: 6333
  grpc_port: 6334
EOF

# Set default environment variables for internal services
export POSTGRES_SERVER=${POSTGRES_SERVER:-localhost}
export POSTGRES_PORT=${POSTGRES_PORT:-5432}
export POSTGRES_USER=${POSTGRES_USER:-postgres}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-password}
export POSTGRES_DB=${POSTGRES_DB:-clouisle}
export REDIS_HOST=${REDIS_HOST:-localhost}
export REDIS_PORT=${REDIS_PORT:-6379}
export REDIS_PASSWORD=${REDIS_PASSWORD:-clouisle-redis-cbd3c07d}
export QDRANT_URL=${QDRANT_URL:-http://localhost:6333}
export QDRANT_API_KEY=${QDRANT_API_KEY:-clouisle-qdrant-cbd3c07d}

exec "$@"
