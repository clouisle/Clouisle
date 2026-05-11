# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-05-11

### Fixed

#### Chat and Agent Runtime
- Preserved uploaded file context across agent conversations by caching parsed file content and reusing it during follow-up turns.
- Restored knowledge search tool execution in backend chat tool handling.
- Avoided wrapping errored agent messages in the full message container so error display matches manual interruption behavior.
- Returned structured, localized validation errors for unsupported HTTP tool URL templates.

#### Security and Dependencies
- Updated `langchain-core` to the patched backend dependency version for the reported security advisory.
- Adjusted Dependabot frontend update grouping so incompatible frontend dependency upgrades are handled separately.

#### Documentation
- Corrected backend startup commands in the English README, Chinese guide README, and quick-start guide.
- Documented explicit `celery_app` usage for Celery worker and beat startup commands.

## [0.1.2] - 2026-03-04

### Added

#### 🧠 User Memory System
- Interactive memory graph visualization with D3.js force-directed layout
- Memory management dashboard with full CRUD operations
- LLM function calling for autonomous memory creation and updates
- Semantic search with vector retrieval using Qdrant
- Multi-tenant data isolation with user-based filtering
- 10 entity types with color-coded nodes (person, preference, skill, project, goal, fact, concept, organization, location, custom)
- 9 relation types with color-coded edges (prefers, works_on, knows, uses, works_at, located_in, has_goal, related_to, part_of)
- Configurable auto-extract, importance threshold, and max memories per retrieval
- Search, filter, zoom controls for graph visualization
- Entity detail sheet with relationship navigation

#### 🎯 Agent Features
- Agent user input request feature with XML-based structured input
- Multiple choice options support in conversations
- Dynamic question generation during chat flow
- Memory configuration in agent orchestration form

#### 🔍 Workflow Enhancements
- Knowledge retrieval node for workflow integration
- Parameter extractor node for data processing
- Sub-workflow support for modular workflow design
- Variable reference validation system
- Loop iteration with internal variable access
- Debug mode with breakpoints and time-travel debugging
- Real-time execution monitoring with streaming updates

#### 📚 Documentation
- Comprehensive bilingual documentation (EN/ZH) with 18,000+ lines
- Architecture guides and API references
- Deployment guides for Docker and Kubernetes
- MCP (Model Context Protocol) documentation
- Sandbox execution documentation
- Auto-generation scripts for documentation

#### 🔐 Authentication & Security
- SSO provider name routing
- JSONPath support in SSO attribute mapping
- Email templates for password reset and verification
- Default role assignment on registration
- Global role synchronization from team membership

#### 📬 Notifications
- Browser push notifications for new messages
- User locale-aware notification delivery
- Workflow run notifications to triggering user
- Knowledge base document processing notifications

#### 🌐 Internationalization
- Complete frontend i18n support with modular structure
- Complete backend i18n support for system messages
- User locale persistence and auto-sync
- Language-aware system prompts for agents
- Builtin tool display names in user's language
- Default language site setting

#### 🏗️ Infrastructure
- Health check endpoint for container orchestration
- CI/CD workflow for automated Docker image builds
- Multi-stage Docker builds for optimized images
- Kubernetes manifests without YAML anchors

### Changed

- Reorganized platform header dropdown menu with logical grouping
- Improved conversation list updates and state management
- Enhanced error handling with better user feedback
- Optimized chunk reindexing with bulk updates
- Refactored LLM chat adapters for better modularity
- Improved vector store service performance

### Fixed

#### Frontend
- SSE parser dropping events when TCP splits across chunks (#61)
- Tool call status stuck on "Running" after completion (#60)
- Prompt editor newlines preservation (#59)
- Chat input auto-resize for multi-line text (#59)
- Dev page auto-refresh and auth redirect loop (#58)
- Password validation and email verification (#57)
- Locale sync and favicon theme switching
- Conversation list updates and reasoning block state management
- Browser notification icon using absolute URL

#### Backend
- Bcrypt 5.0 compatibility by using bcrypt directly
- N+1 queries in user serialization with prefetched data (#56)
- SSO callback URL construction using public site_url
- Duplicate /api/v1 prefix in SSO login URL
- Language detection from user.locale instead of request header
- Workflow run notifications using triggering user's locale
- Knowledge base document notifications using uploader's locale
- Skip logging middleware for SSE stream responses

#### Deployment
- Bun lockfile compatibility in Docker build (#52)
- CORS configuration using JSON array format (#51)
- Kubernetes manifest compatibility for kubectl

### Security

- Enhanced password validation
- Secure credential storage for custom tools
- API key scoped access with expiration tracking

## [0.1.0] - 2026-02-01

### Added

#### Core Features
- Multi-provider LLM support (15+ providers: OpenAI, Anthropic, Google, xAI, DeepSeek, Azure, Moonshot, Zhipu, Qwen, Ollama, Custom)
- Visual workflow builder with drag-and-drop interface
- Knowledge base system with RAG integration
- AI agent management with multi-model support
- Tool system (built-in, custom HTTP, MCP integration)

#### Enterprise Features
- Multi-tenancy with team-based resource isolation
- RBAC with granular permission system
- SSO support (OIDC, OAuth2, SAML 2.0, CAS)
- Comprehensive audit logging
- API key management

#### Knowledge Base
- Multi-format document support (PDF, DOCX, XLSX via MarkItDown)
- Intelligent chunking with configurable strategies
- Vector search with Qdrant
- Async processing via Celery

#### Workflow System
- 15+ node types (LLM, Condition, Code, HTTP, Tool, etc.)
- Multiple execution modes (manual, scheduled, webhook, API)
- Real-time monitoring with streaming updates
- Debug mode for testing

#### User Interface
- Dashboard for admin management
- Platform interface for end users
- Chat interface with conversation history
- Responsive design with dark mode support

### Technical Stack

#### Backend
- FastAPI (Python 3.13)
- Tortoise ORM with AsyncPG
- Celery + Redis for task queue
- Qdrant for vector storage
- LangChain + LangGraph for LLM integration

#### Frontend
- Next.js 16 (App Router)
- Bun runtime
- shadcn/ui + Tailwind CSS
- TypeScript

[Unreleased]: https://github.com/yunhai-dev/Clouisle/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/yunhai-dev/Clouisle/compare/v0.2.0...v0.2.1
[0.1.2]: https://github.com/yunhai-dev/Clouisle/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/yunhai-dev/Clouisle/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/yunhai-dev/Clouisle/releases/tag/v0.1.0
