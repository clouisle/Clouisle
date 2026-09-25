# Introduction to Clouisle

Clouisle is a multi-agent collaboration platform and workflow engine for production use.

## What is Clouisle?

Clouisle lets organizations build, orchestrate, and deploy production-ready AI agent teams with sandboxed execution, hybrid knowledge retrieval (RAG), and enterprise-grade security. Agents, workflows, knowledge bases, tools, and models are configured per team, governed by RBAC, and observable from the admin console.

## Key Features

- **Multi-Agent Orchestration**: Compose published agents into multi-agent pipelines with visual workflows (`agent` and `sub_workflow` nodes)
- **AI Agent Management**: Create and configure conversational AI agents with tools, skills, memory, and RAG modes
- **Visual Workflow Engine**: Drag-and-drop graph builder with 19 node types, nested sub-workflows, and human-in-the-loop approval
- **Knowledge Base System**: Store and retrieve documents with hybrid vector + full-text search and reranking
- **Sandboxed Execution**: Run agent and workflow code in isolated sandbox sessions with CPU/memory/disk limits
- **Enterprise Security**: Multi-tenancy, RBAC, SSO (OIDC/SAML/CAS), TOTP 2FA, and field-level audit logging
- **Multi-LLM Support**: 23 built-in providers, plus any OpenAI-compatible endpoint

## Why Choose Clouisle?

- **Production-Ready**: Built for enterprise deployment
- **Flexible**: Supports multiple LLM providers and custom tools
- **Secure**: Comprehensive security features and compliance
- **Scalable**: Horizontal scaling for high availability

## Where to go next

- Start locally with the [Development Setup](./development.md) guide.
- Learn the team authorization model in [Multi-Tenancy](../concepts/multi-tenancy.md).
- Compare conversational agents and graph-based workflows in [Agent vs Workflow](../concepts/agent-vs-workflow.md).
- See [RAG Explained](../concepts/rag-explained.md) for retrieval modes and [Vector Embeddings](../concepts/vector-embeddings.md) for embedding compatibility.
