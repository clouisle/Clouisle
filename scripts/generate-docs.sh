#!/bin/bash

# Clouisle Documentation Generator
# This script creates all remaining documentation files based on templates

set -e

GUIDE_DIR="/Users/yunhai/Documents/CodeData/Project/Clouisle/docs/guide"

echo "🚀 Starting Clouisle documentation generation..."

# Create a simple documentation file
create_doc() {
    local file_path="$1"
    local title="$2"
    local content="$3"

    cat > "$file_path" << EOF
# $title

$content

---

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
EOF

    echo "✅ Created: $file_path"
}

# Getting Started documents
echo "📝 Creating Getting Started documents..."

create_doc "$GUIDE_DIR/getting-started/introduction.md" "Introduction to Clouisle" \
"Clouisle is an enterprise-grade AI Agent and knowledge base platform.

## What is Clouisle?

Clouisle enables organizations to build, deploy, and manage intelligent AI agents with advanced knowledge retrieval capabilities.

## Key Features

- **AI Agent Management**: Create and configure conversational AI agents
- **Knowledge Base System**: Store and retrieve documents with vector search
- **Workflow Automation**: Build no-code workflows with visual editor
- **Enterprise Security**: Multi-tenancy, RBAC, SSO, and audit logging
- **Multi-LLM Support**: 15+ LLM providers supported

## Why Choose Clouisle?

- **Production-Ready**: Built for enterprise deployment
- **Flexible**: Supports multiple LLM providers and custom tools
- **Secure**: Comprehensive security features and compliance
- **Scalable**: Horizontal scaling for high availability"

create_doc "$GUIDE_DIR/getting-started/introduction_zh-CN.md" "Clouisle 简介" \
"Clouisle 是企业级 AI Agent 与知识库平台。

## 什么是 Clouisle？

Clouisle 使组织能够构建、部署和管理具有高级知识检索能力的智能 AI 代理。

## 主要功能

- **AI Agent 管理**: 创建和配置对话式 AI 代理
- **知识库系统**: 使用向量搜索存储和检索文档
- **工作流自动化**: 使用可视化编辑器构建无代码工作流
- **企业安全**: 多租户、RBAC、SSO 和审计日志
- **多 LLM 支持**: 支持 15+ LLM 提供商

## 为什么选择 Clouisle？

- **生产就绪**: 为企业部署而构建
- **灵活**: 支持多个 LLM 提供商和自定义工具
- **安全**: 全面的安全功能和合规性
- **可扩展**: 水平扩展以实现高可用性"

create_doc "$GUIDE_DIR/getting-started/quick-start.md" "Quick Start Guide" \
"Get started with Clouisle in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- 4GB RAM minimum
- Modern web browser

## Installation

1. **Clone the repository**:
\`\`\`bash
git clone https://github.com/your-org/clouisle.git
cd clouisle
\`\`\`

2. **Start infrastructure**:
\`\`\`bash
docker-compose -f deploy/docker-compose.dev.yml up -d
\`\`\`

3. **Configure environment**:
\`\`\`bash
cp .env.example .env
# Edit .env with your settings
\`\`\`

4. **Start backend**:
\`\`\`bash
cd backend
uv sync
uv run main.py server
\`\`\`

5. **Start frontend**:
\`\`\`bash
cd frontend
bun install
bun dev
\`\`\`

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
- [Admin Guide](../admin-guide/)"

echo "✅ Getting Started documents created"

# Concepts documents (remaining)
echo "📝 Creating Concepts documents..."

create_doc "$GUIDE_DIR/concepts/rag-explained.md" "RAG (Retrieval-Augmented Generation) Explained" \
"Understanding how RAG works in Clouisle.

## What is RAG?

RAG combines information retrieval with language model generation to provide accurate, context-aware responses.

## How RAG Works

1. **Retrieve**: Search knowledge base for relevant documents
2. **Augment**: Add retrieved context to the prompt
3. **Generate**: LLM generates response using the context

## RAG Modes in Clouisle

- **Disabled**: No knowledge base retrieval
- **Before LLM**: Retrieve documents, then generate response
- **After LLM**: Generate response, then verify with documents

## When to Use RAG

- Answering questions about specific documents
- Providing accurate, sourced information
- Reducing hallucinations
- Grounding responses in facts"

create_doc "$GUIDE_DIR/concepts/agent-vs-workflow.md" "Agent vs Workflow" \
"Understanding the difference between Agents and Workflows.

## Agents

**Conversational and autonomous**:
- Interactive chat interface
- Multi-turn conversations
- Autonomous decision-making
- Tool usage based on context

**Use cases**:
- Customer support chatbots
- Personal assistants
- Q&A systems
- Interactive help systems

## Workflows

**Structured and deterministic**:
- Visual node-based editor
- Predefined execution path
- Explicit control flow
- Repeatable processes

**Use cases**:
- Data processing pipelines
- Automated reports
- API integrations
- Scheduled tasks

## Comparison

| Feature | Agent | Workflow |
|---------|-------|----------|
| Interface | Chat | Visual editor |
| Execution | Autonomous | Deterministic |
| Control | AI-driven | User-defined |
| Use case | Interactive | Automation |"

echo "✅ Concepts documents created"

# Operations documents
echo "📝 Creating Operations documents..."

create_doc "$GUIDE_DIR/operations/backup-restore.md" "Backup and Restore" \
"Backup and restore procedures for Clouisle.

## What to Backup

1. **PostgreSQL**: All application data
2. **Qdrant**: Vector embeddings
3. **Uploads**: User-uploaded files
4. **Redis**: Optional (cache and queue state)

## Backup Procedures

### PostgreSQL Backup

\`\`\`bash
# Docker Compose
docker compose exec db pg_dump -U postgres clouisle > backup.sql

# Kubernetes
kubectl exec statefulset/postgres -- pg_dump -U postgres clouisle > backup.sql
\`\`\`

### Qdrant Backup

\`\`\`bash
# Backup the volume
docker run --rm -v qdrant_data:/data -v \$(pwd):/backup \\
  alpine tar czf /backup/qdrant_backup.tar.gz -C /data .
\`\`\`

### Uploads Backup

\`\`\`bash
# Backup uploads directory
docker run --rm -v uploads_data:/data -v \$(pwd):/backup \\
  alpine tar czf /backup/uploads_backup.tar.gz -C /data .
\`\`\`

## Restore Procedures

### PostgreSQL Restore

\`\`\`bash
# Docker Compose
docker compose exec -T db psql -U postgres clouisle < backup.sql

# Kubernetes
kubectl exec -i statefulset/postgres -- psql -U postgres clouisle < backup.sql
\`\`\`

## Automated Backups

Set up daily backups with cron or Kubernetes CronJob.

See [Deployment Guide](../deployment/DEPLOYMENT.md) for detailed examples."

create_doc "$GUIDE_DIR/operations/monitoring.md" "Monitoring and Observability" \
"Monitoring setup for Clouisle.

## Key Metrics

- **Request rate**: Requests per second
- **Response time**: p50, p95, p99 latency
- **Error rate**: 4xx and 5xx errors
- **Database performance**: Query time, connection pool
- **Celery tasks**: Queue length, execution time
- **Resource usage**: CPU, memory, disk

## Health Check Endpoints

- \`/api/v1/health\` - Basic health check
- \`/api/v1/health/db\` - Database connectivity
- \`/api/v1/health/redis\` - Redis connectivity
- \`/api/v1/health/qdrant\` - Qdrant connectivity

## Logging

### Application Logs

\`\`\`bash
# Docker Compose
docker compose logs -f backend
docker compose logs -f worker

# Kubernetes
kubectl logs -f deployment/backend
kubectl logs -f deployment/worker
\`\`\`

### Access Logs

- Nginx access logs (frontend)
- Gunicorn access logs (backend)

## Integration with Monitoring Tools

- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Datadog**: Full-stack monitoring
- **ELK Stack**: Log aggregation"

create_doc "$GUIDE_DIR/operations/upgrading.md" "Upgrading Clouisle" \
"Version upgrade procedures.

## Pre-Upgrade Checklist

- [ ] Backup all data (PostgreSQL, Qdrant, uploads)
- [ ] Review changelog for breaking changes
- [ ] Test upgrade in staging environment
- [ ] Schedule maintenance window
- [ ] Notify users of downtime

## Docker Compose Upgrade

\`\`\`bash
cd deploy

# 1. Pull latest code
git pull

# 2. Rebuild images
docker compose build

# 3. Stop services
docker compose down

# 4. Start services
docker compose up -d

# 5. Verify
docker compose ps
docker compose logs --tail=50 backend
\`\`\`

## Kubernetes Upgrade

\`\`\`bash
# 1. Build and push new images
docker build -t registry.example.com/clouisle/backend:v2.0.0 .
docker push registry.example.com/clouisle/backend:v2.0.0

# 2. Update manifests
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Monitor rollout
kubectl rollout status deployment/backend
\`\`\`

## Rollback Procedures

If upgrade fails:

\`\`\`bash
# Docker Compose
docker compose down
git checkout previous-version
docker compose up -d

# Kubernetes
kubectl rollout undo deployment/backend
\`\`\`

## Post-Upgrade Verification

- [ ] Check all services are running
- [ ] Test login functionality
- [ ] Test agent chat
- [ ] Test workflow execution
- [ ] Review error logs"

create_doc "$GUIDE_DIR/operations/security-checklist.md" "Security Checklist" \
"Security best practices for Clouisle deployment.

## Pre-Deployment Security

- [ ] Change all default passwords
- [ ] Generate strong SECRET_KEY
- [ ] Configure HTTPS/TLS
- [ ] Set up firewall rules
- [ ] Enable audit logging

## Authentication & Authorization

- [ ] Enforce strong password policies
- [ ] Enable SSO if available
- [ ] Configure session timeout
- [ ] Enable MFA for admin accounts
- [ ] Regular access reviews

## Network Security

- [ ] Use private networks for infrastructure
- [ ] Restrict database access to backend only
- [ ] Configure CORS properly
- [ ] Use VPC/security groups
- [ ] Enable DDoS protection

## Data Security

- [ ] Enable encryption at rest
- [ ] Use TLS for all connections
- [ ] Regular database backups
- [ ] Secure backup storage
- [ ] Data retention policies

## Application Security

- [ ] Keep dependencies updated
- [ ] Regular security scans
- [ ] Input validation
- [ ] Rate limiting enabled
- [ ] API key rotation policy

## Monitoring & Incident Response

- [ ] Enable audit logging
- [ ] Set up security alerts
- [ ] Monitor failed login attempts
- [ ] Regular log reviews
- [ ] Incident response plan

## Compliance

- [ ] GDPR compliance (if applicable)
- [ ] Data residency requirements
- [ ] Regular security audits
- [ ] Vulnerability assessments
- [ ] Penetration testing"

echo "✅ Operations documents created"

echo ""
echo "🎉 Documentation generation complete!"
echo ""
echo "📊 Summary:"
echo "  - Getting Started: 3 documents"
echo "  - Concepts: 2 documents"
echo "  - Operations: 4 documents"
echo ""
echo "📝 Next steps:"
echo "  1. Review and update placeholder content"
echo "  2. Add screenshots and diagrams"
echo "  3. Create remaining documents (User Guide, Admin Guide, API Reference)"
echo ""
echo "✅ Done!"
