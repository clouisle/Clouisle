# Quick Start Guide

Get started with Clouisle using Docker Compose.

## Prerequisites

- Docker & Docker Compose
- 4GB RAM minimum
- Modern web browser

## 1. Clone the Repository

```bash
git clone https://github.com/clouisle/Clouisle.git
cd clouisle
```

## 2. Configure Environment

```bash
# Copy the Docker deployment environment file
cp deploy/.env.example deploy/.env

# Edit deploy/.env with secure random values for:
#   SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, QDRANT_API_KEY,
#   SANDBOX_ARTIFACT_UPLOAD_API_KEY, INTERNAL_API_TOKEN
# INTERNAL_API_TOKEN is REQUIRED — docker compose refuses to start without it.
# Generate one with: openssl rand -hex 32
```

## 3. Start Clouisle

```bash
cd deploy
docker compose --env-file .env up -d
```

## 4. Access the Application

- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs

## First Steps

1. Register your first account — there is no seeded default admin; the first user to register is automatically promoted to Super Admin
2. Create your first team
3. Add an AI model (Models in the sidebar)
4. Create a knowledge base and upload documents
5. Build an AI agent and start chatting

## Next Steps

- [Basic Concepts](./basic-concepts.md)
- [Development Setup](./development.md) — for contributors
- [User Guide](../user-guide/)
- [Admin Guide](../admin-guide/)
- [Deployment Guide](../deployment/DEPLOYMENT.md)
