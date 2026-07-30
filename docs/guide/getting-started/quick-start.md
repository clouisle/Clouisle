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
#   SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD, QDRANT_API_KEY
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

1. Log in with the default admin credentials (set in `.env`)
2. Create your first team
3. Add an AI model (Settings → Models)
4. Create a knowledge base and upload documents
5. Build an AI agent and start chatting

## Next Steps

- [Basic Concepts](./basic-concepts.md)
- [Development Setup](./development.md) — for contributors
- [User Guide](../user-guide/)
- [Admin Guide](../admin-guide/)
- [Deployment Guide](../deployment/DEPLOYMENT.md)
