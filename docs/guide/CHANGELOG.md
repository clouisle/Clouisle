# Changelog

This document records all significant changes to the project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0] - 2025-02-07

First public release of Clouisle - an enterprise-grade knowledge base and AI Agent platform.

### Core Features

#### Agent System

- **Agent Types**: Support for Chat Agent and Workflow Agent
- **Agent Orchestration**: Modern three-column layout with real-time preview
  - Prompt editor with AI generation
  - Variable configuration
  - Knowledge base association
  - Tool configuration
  - Vision capability support
- **Agent Publishing**: Publish/unpublish workflow with status management
- **Agent API Access**: OpenAI-compatible API with documentation and code examples
- **Agent Monitor**: Usage statistics, conversation trends, token usage, response time metrics

#### Workflow Engine

- **Visual Workflow Editor**: React Flow based drag-and-drop workflow builder
- **Node Types**:
  - Start/End nodes
  - LLM nodes (with model selection and parameter tuning)
  - Condition nodes (branching logic)
  - Code nodes (JavaScript/Python execution)
  - Tool nodes (HTTP API, MCP, built-in tools)
  - Iteration/Loop nodes
  - Variable assignment/aggregator nodes
  - Sub-workflow nodes
  - Question classifier nodes
  - Parameter extractor nodes
- **Variable System**: Upstream variable reference with validation
- **Execution**: Real-time streaming execution with node-level status tracking

#### Knowledge Base

- **Document Management**:
  - Multi-format support: PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, PPTX
  - URL import
  - Drag-and-drop batch upload
- **Document Processing**:
  - Smart text chunking (configurable chunk_size, chunk_overlap, separator)
  - Chunk preview before committing
  - Text cleaning options
- **Search Modes**:
  - Vector search (semantic similarity)
  - Full-text search (jieba Chinese tokenization)
  - Hybrid search (RRF algorithm)
- **Dynamic Embedding**: Support for multiple embedding dimensions (768, 1024, 1536, 3072)

#### Chat System

- **Universal Chat Components**: Reusable chat component library
- **Message Types**: Text, reasoning (chain of thought), tool calls, files, sources
- **Streaming**: Real-time streaming responses with Streamdown rendering
- **Multi-turn Conversations**: Conversation history management

#### Tool System

- **Built-in Tools**: Calculator, time/timezone
- **HTTP API Tools**: Configurable URL, method, headers, body template
- **MCP Server Tools**: stdio/sse transport, command execution
- **Code Tools**: Online JavaScript/Python editor

### Platform Features

#### User Management

- **Authentication**: Username/password, SSO (OIDC, SAML, CAS)
- **Registration**: Configurable registration, approval workflow, email verification
- **Password Policy**: Configurable strength requirements
- **Session Management**: Timeout, single session mode
- **Login Security**: Max attempts, lockout, captcha

#### Team Management

- **Multi-tenant**: Team-based resource isolation
- **Role-based Access Control**: Customizable roles and permissions
- **Team Members**: Invite, remove, role assignment

#### Model Management

- **Multi-provider Support**: OpenAI, Anthropic, Azure, local models
- **Model Authorization**: Team-level model access control
- **Usage Tracking**: Token usage statistics per team

#### API Key Management

- **API Key CRUD**: Create, rotate, expire API keys
- **Agent Binding**: Restrict API key access to specific agents
- **Rate Limiting**: Configurable rate limits

#### Site Settings

- **General**: Site name, description, URL, icon
- **Default Language**: Configurable default language for system messages
- **Security**: Registration, password policy, session, login security
- **Notifications**: Email (SMTP), DingTalk, WeChat Work, Feishu, Slack, Webhook
- **Auto Notifications**: Configurable system event notifications
- **SSO**: OIDC, SAML, CAS provider configuration
- **Storage**: Audit log retention and archiving

#### Audit Logging

- **Comprehensive Logging**: All user actions logged
- **Log Viewer**: Filterable, searchable audit log interface
- **Export**: CSV export support
- **Archiving**: Configurable retention with automatic archiving

### Internationalization

- **Languages**: English, Chinese (Simplified)
- **User Locale**: Per-user language preference
- **Site Default**: Configurable default language for system messages
- **Dynamic i18n**: All user-facing messages internationalized

### UI/UX

- **Theme**: Light/dark mode with system preference detection
- **Dynamic Favicon**: Theme-aware favicon switching
- **Responsive Design**: Desktop-optimized dashboard
- **Component Library**: shadcn/ui based components

### Technical Stack

#### Backend
- Python 3.13, FastAPI
- Tortoise ORM with AsyncPG
- Celery for background tasks
- Redis for caching and pub/sub
- Qdrant for vector storage

#### Frontend
- Next.js 15, React 19
- TypeScript
- Tailwind CSS
- shadcn/ui components
- Bun package manager

---

## Contributing

When submitting code, please reference related Issues in commit messages:

```
feat(knowledge-base): implement knowledge base search

- Add vector search, full-text search, hybrid search modes
- Integrate jieba Chinese tokenization

Closes #12
```
