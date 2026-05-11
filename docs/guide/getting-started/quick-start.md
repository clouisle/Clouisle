# Quick Start Guide

Get started with Clouisle in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- 4GB RAM minimum
- Modern web browser

## Installation

1. **Clone the repository**:
```bash
git clone https://github.com/your-org/clouisle.git
cd clouisle
```

2. **Start infrastructure**:
```bash
docker-compose -f deploy/docker-compose.dev.yml up -d
```

3. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. **Start backend**:
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

5. **Start frontend**:
```bash
cd frontend
bun install
bun dev
```

6. **Access the application**:
- Frontend: http://localhost:3000
- API: http://localhost:8000/docs

## First Steps

1. Log in with default credentials (see .env)
2. Create your first team
3. Add a knowledge base
4. Create an AI agent
5. Start chatting!

## Next Steps

- [Basic Concepts](./basic-concepts.md)
- [User Guide](../user-guide/)
- [Admin Guide](../admin-guide/)

---

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
