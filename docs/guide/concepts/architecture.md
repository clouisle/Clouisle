# System Architecture

This document provides an overview of Clouisle's system architecture, explaining how different components work together to deliver an enterprise-grade AI Agent and knowledge base platform.

## Architecture Overview

Clouisle uses a modern, scalable architecture with clear separation between frontend, backend, and infrastructure layers.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js 16)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Admin   │  │  Platform│  │   Chat   │  │  Auth (SSO/Login)│ │
│  │Dashboard │  │   UI     │  │Interface │  │                  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Agent   │  │ Workflow │  │Knowledge │  │   User & Team    │ │
│  │  Engine  │  │  Engine  │  │   Base   │  │   Management     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │   LLM    │  │   Tool   │  │  Audit   │  │   Notification   │ │
│  │ Adapters │  │  System  │  │   Logs   │  │    Service       │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
             ┌──────────┐  ┌──────────┐  ┌──────────┐
             │PostgreSQL│  │  Redis   │  │  Qdrant  │
             │(Database)│  │ (Cache)  │  │ (Vector) │
             └──────────┘  └──────────┘  └──────────┘
```

## Technology Stack

### Frontend Layer

**Framework**: Next.js 16 with App Router
- **Runtime**: Bun 1.0+
- **UI Library**: shadcn/ui (base-vega) + Tailwind CSS
- **Language**: TypeScript
- **State Management**: React hooks + Context API
- **API Client**: Axios with custom interceptors

**Key Features**:
- Server-side rendering (SSR) for optimal performance
- Multiple route groups for different user experiences
- Real-time updates via Server-Sent Events (SSE)
- Internationalization (i18n) support

### Backend Layer

**Framework**: FastAPI (Python 3.13)
- **ORM**: Tortoise ORM with AsyncPG
- **Task Queue**: Celery + Redis
- **Vector Database**: Qdrant
- **LLM Framework**: LangChain + LangGraph
- **Document Processing**: MarkItDown

**Key Features**:
- Async/await throughout for high concurrency
- Unified response format for all endpoints
- Comprehensive error handling with i18n
- Audit logging for all operations
- Multi-channel notification system

### Infrastructure Layer

**Database**: PostgreSQL 16
- Stores all application data (users, teams, agents, workflows, etc.)
- ACID compliance for data integrity
- Full-text search capabilities

**Cache & Queue**: Redis 7
- Session storage
- Celery task broker and result backend
- Rate limiting counters
- Temporary data caching

**Vector Database**: Qdrant
- Stores document embeddings
- Similarity search for RAG
- Collection per embedding dimension
- Efficient vector operations

## Component Interactions

### Request Flow

#### 1. User Request Flow

```
Browser → Nginx (Frontend) → Next.js SSR → API Request → FastAPI Backend
                                                              ↓
                                                         PostgreSQL
                                                              ↓
                                                         Response
```

#### 2. Chat Request Flow (with RAG)

```
User Message → FastAPI → Agent Engine → RAG Retrieval → Qdrant
                              ↓                            ↓
                         LLM Adapter                  Documents
                              ↓                            ↓
                         LLM Provider ← Context ← Chunks Retrieved
                              ↓
                         Response (SSE Stream)
                              ↓
                         Frontend (Real-time Display)
```

#### 3. Document Processing Flow

```
Upload → FastAPI → Celery Task → MarkItDown → Text Extraction
                                      ↓
                                  Chunking
                                      ↓
                              Embedding Generation
                                      ↓
                                  Qdrant Storage
                                      ↓
                              Status Update (PostgreSQL)
```

#### 4. Workflow Execution Flow

```
Trigger → FastAPI → Celery Task → LangGraph Engine
                                        ↓
                                   Node Execution
                                   (LLM, Tool, Code, etc.)
                                        ↓
                                   Result Storage
                                        ↓
                                   SSE Stream (if real-time)
```

## Scalability Considerations

### Horizontal Scaling

**Frontend**:
- Stateless Next.js instances
- Can scale to multiple replicas
- Load balancer distributes traffic

**Backend**:
- Stateless FastAPI instances
- Can scale to multiple replicas
- Session stored in Redis (shared)

**Celery Workers**:
- Can scale to multiple workers
- Queue-based task distribution
- Separate queues for different task types

**Celery Beat**:
- **Must run exactly 1 instance** (scheduled tasks)
- Uses database lock to prevent duplicates

### Vertical Scaling

**PostgreSQL**:
- Increase CPU/RAM for better query performance
- Connection pooling for efficiency

**Redis**:
- Increase memory for larger cache
- Persistence for durability

**Qdrant**:
- Increase memory for larger vector collections
- SSD for faster disk I/O

## Security Architecture

### Authentication & Authorization

**Multi-layer Security**:
1. **Frontend**: Route guards, role-based UI rendering
2. **Backend**: JWT token validation, permission checks
3. **Database**: Row-level security via team isolation

**Authentication Methods**:
- Password-based (with bcrypt hashing)
- SSO (OAuth2, OIDC, SAML, CAS)
- API Keys (for programmatic access)

### Data Isolation

**Team-based Multi-tenancy**:
- All resources belong to a team
- Users can be members of multiple teams
- Queries automatically filtered by team membership
- Super admins can access all data

### Audit Trail

**Comprehensive Logging**:
- All user actions logged
- Before/after snapshots for changes
- IP address and user agent tracking
- Retention policies for compliance

## Performance Optimizations

### Caching Strategy

**Redis Caching**:
- User sessions (30-minute TTL)
- Site settings (5-minute TTL)
- Rate limit counters (1-hour TTL)

**Database Indexing**:
- Primary keys (UUID)
- Foreign keys
- Frequently queried fields (email, username, team_id)

### Async Operations

**Background Tasks**:
- Document processing (Celery)
- Email sending (Celery)
- Workflow execution (Celery)
- Notification delivery (Celery)

**Real-time Updates**:
- SSE for chat responses
- SSE for workflow execution
- WebSocket for future features

## Deployment Architecture

### Docker Compose (Development/Small Production)

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Host                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Frontend │  │ Backend  │  │  Worker  │  │   Beat   │   │
│  │  :3000   │  │  :8000   │  │          │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │PostgreSQL│  │  Redis   │  │  Qdrant  │                 │
│  │  :5432   │  │  :6379   │  │  :6333   │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### Kubernetes (Large Production)

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Ingress (Nginx)                                     │   │
│  │    ├── /api/* → Backend Service                      │   │
│  │    └── /*     → Frontend Service                     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Frontend │  │ Backend  │  │  Worker  │  │   Beat   │   │
│  │ (2 pods) │  │ (2 pods) │  │ (2 pods) │  │ (1 pod)  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │PostgreSQL│  │  Redis   │  │  Qdrant  │                 │
│  │(StatefulSet)│(Deployment)│(StatefulSet)│               │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## Monitoring & Observability

### Logging

**Application Logs**:
- Structured JSON logging
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging
- Error stack traces

**Access Logs**:
- Nginx access logs (frontend)
- Gunicorn access logs (backend)
- API endpoint usage

### Metrics

**Key Metrics to Monitor**:
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Database query time
- Celery task queue length
- Celery task execution time
- Memory usage
- CPU usage

### Health Checks

**Endpoints**:
- `/api/v1/health` - Basic health check
- `/api/v1/health/db` - Database connectivity
- `/api/v1/health/redis` - Redis connectivity
- `/api/v1/health/qdrant` - Qdrant connectivity

## Future Architecture Considerations

### Planned Enhancements

**Microservices**:
- Split monolithic backend into services
- Agent service, Workflow service, KB service
- Service mesh for inter-service communication

**Event-Driven Architecture**:
- Event bus (Kafka/RabbitMQ)
- Event sourcing for audit trail
- CQRS pattern for read/write separation

**Advanced Caching**:
- CDN for static assets
- Edge caching for API responses
- Distributed caching (Redis Cluster)

**High Availability**:
- Multi-region deployment
- Database replication
- Automatic failover

## Related Documentation

- [Multi-Tenancy Model](./multi-tenancy.md) - Team-based isolation
- [RAG Explained](./rag-explained.md) - Retrieval-Augmented Generation
- [Agent vs Workflow](./agent-vs-workflow.md) - Comparison guide
- [Vector Embeddings](./vector-embeddings.md) - Vector search concepts
- [Deployment Guide](../deployment/DEPLOYMENT.md) - Deployment instructions
