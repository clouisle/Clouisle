# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Admin Observability

- Rebuilt the admin observability console with six focused views for run outcomes, on-demand traces, model/tool/retrieval dependencies, queues, infrastructure, and alerts.
- Added bounded tool and knowledge retrieval spans to durable AgentRun details, plus tool and retrieval success-rate and latency aggregates in the Dependencies view.
- Agent dependency traces retain at most 128 spans per run and display when the cap truncates a trace; historical runs are not backfilled.
- Added translations for every persisted AgentRun lifecycle status in both locales and a raw-status fallback for future values.
- Added bounded PostgreSQL, Redis, Celery worker, and Qdrant connectivity probes for infrastructure dependencies, including measured latency and explicit unhealthy/unconfigured states.
- Added single-leader terminal AgentRun summary reconciliation every minute, repairing stale status, timing, model, and token fields in bounded batches without replaying runs; fixed the ORM query that dropped terminal summaries.
- Model dependency cards now resolve existing telemetry UUIDs to configured model names and provider labels, including custom gateway names, while keeping same-named models separate.
- Reduced queue snapshot latency by collecting active tasks, reserved tasks, scheduled tasks, and active queues concurrently with independent Celery inspectors; preserved existing cache and failure behavior.
- Reduced infrastructure snapshot latency by collecting health probes and slow-query statistics concurrently and shortening Celery reply collection to 0.5 seconds; retained existing probe deadlines, failure behavior, and caching.
- Added Redis-backed API instance discovery with per-instance reporter leases, host-scoped resource samples, readable names, and stale/offline aging; infrastructure now lists retained instances across backends rather than only the serving process.
- Added a two-month calendar range picker to observability, with rolling presets at the bottom of its popover, inclusive local-day selection, URL persistence, and consistent UTC filtering for overview, runs, and dependency statistics.
- Added the same calendar range picker to the dashboard with 7/30/90-day and all-time shortcuts; custom dates consistently filter trends, rankings, model usage, workflow summaries, and conversation/message/token summaries and averages, while unrelated cumulative indicators retain their definitions.


#### Sandbox Security
- Added a persisted Security setting for exact sandbox egress hostnames; updates apply to new jobs without restarting workers.

#### Chat and File Previews
- Added a unified artifact list with file counts, expandable results, authenticated downloads, and shared previews for common document, media, and code formats.
- Added DOCX thumbnails, page synchronization, responsive fit-to-width, and zoom controls; added read-only PDF and spreadsheet preview controls.

#### Sandbox Lifecycle Audit
- Added audit events for sandbox task start, completion, failure, cancellation, and recovery. Entries capture available task/session/worker context and safe error codes without recording code, arguments, output, or raw exception text.

#### Memory and RAG
- Added optional background memory extraction controls in the admin `memory` site-settings category, including model selection, debounce cooldown, and pending-turn trigger limits.
- Added the bounded `get_memory_subgraph` Agent tool for relationship-aware memory retrieval.

#### Models and Workflows
- Added the TypeSafe AI (`typesafe`) decision-model provider and the `decision` model type, which evaluates a state against typed `choice`, `score`, or `noul` questions and returns typed answers with probability distributions and confidence.
- Added the Decision workflow node: it asks one typed question, routes on the returned answer (or the highest-probability score level), and supports a fallback branch plus an optional confidence threshold.

### Changed

#### Admin Observability

- Aligned console tabs and filters with the shared dashboard Tabs, Select, and Input components; standardized control heights.

#### Assets and Media
- Persisted generated images and videos as scoped Assets and exposed conversation/workflow-scoped media references for model use.
- Updated CSV handling for GBK/GB18030 content and removed duplicate spreadsheet viewer downloads.

#### Agent Retrieval and Chat Timeline
- Agents with no knowledge-base associations now persist and run with `rag_mode: off`; the Agent editor hides the RAG selector until a knowledge base is selected.
- RAG context remains `null` when retrieval did not run and `[]` when retrieval ran but returned no contexts.

#### Dependencies and Tooling
- Updated backend and frontend dependency manifests and lockfiles to current compatible releases.
- Made the Python lint policy explicit for stable Ruff upgrades and audited the complete Bun production dependency closure.
- Replaced the sandbox tests' Redis-server process with an in-process fake and removed the Redis server install from backend CI.
- Added `MIT-0` to the approved permissive-license policy.

### Fixed

#### Admin Observability
- Kept the Dependencies view available when tool and retrieval spans have no token counts; those rows now report unavailable token usage instead of failing the response.
- Migrated `model_name` and `message_started_at` on existing PostgreSQL `observability_runs` tables before Tortoise schema and index generation, preventing API startup and summary-query failures on older databases.

#### Sandbox Sessions
- Routed session jobs to per-worker Celery queues and persisted a fenced worker/storage binding. Stale-generation messages are rejected; a command with uncertain completion is never automatically replayed.
- Added sandbox-worker readiness heartbeats, same-disk supervised restart and checkpoint recovery, plus bounded atomic rebinding to a fresh workspace generation when the original worker storage is unavailable. AgentRun receives `WORKSPACE_RESET` and replans instead of reusing stale paths or process state.
- Kept each sandbox worker's workspace and checkpoints on worker-local storage (Compose named volume; Kubernetes node-local hostPath DaemonSet). Same-node process replacement can restore checkpointed data; permanent loss of the node or disk cannot.
- Used the platform's `ELOOP` errno constant when rejecting symlinked workspace paths.
- Routed deferred cleanup and idle-eviction retries through separate Redis indexes so an unavailable owner queue cannot block later sessions; spread first-time session placement across ready workers and bounded binding/tombstone retention.
- Rejected zero-valued sandbox worker recovery timeouts.
- Routed isolated sandbox and dependency-install egress through a per-job HTTPS proxy with exact-host allowlisting; blocked hosts are reported in execution diagnostics.
- Kept legacy code execution and workflow code nodes behind the sandbox gateway; disabled, unavailable, and failed runtimes fail closed without executing payloads on the caller.
- Bounded Python and Node dependency installation to 300 seconds by default; timed-out install process groups are terminated and incomplete environments are discarded.
- Bounded captured sandbox output in memory and applied per-process `prlimit` controls. Direct payloads drop all capabilities in Bubblewrap; the trusted egress bridge raises loopback in its isolated network namespace, then sets `no-new-privileges` and clears payload capabilities. Supplied workers receive `NET_ADMIN` for that setup and remain resource-capped.

#### Asset Access and Previews
- Protected generated images, generated videos, and sandbox artifacts with scope-aware authorization and authenticated client downloads.
- Preserved explicit too-large, unauthorized, permission-denied, unsupported, and parse-failure preview states without falling back to unprotected URLs.

#### Chat Experience
- Kept agent conversations pinned to the latest message as soon as a send begins, before streaming starts.
- Deduplicated overlapping Agent conversation pages and preserved the loaded pagination position when refreshing the chat sidebar.

#### Dependency Compatibility
- Adapted Redis, MCP, SMTP, sandbox session, React, Radix, TypeScript, and ICU message-format integrations to their refreshed APIs while preserving exception tracebacks.

## [0.2.9] - 2026-06-09

### Added

#### Admin and Observability
- Added an admin observability dashboard for platform usage, performance, errors, and activity monitoring.
- Added admin management panels and routes for agents and workflows.

#### Packages
- Added Clouisle package import and export support for moving apps and resources between environments.

#### Knowledge Base
- Added multimodal knowledge base asset support for uploaded images and media references.
- Added failed chunk retry and bulk knowledge base document/chunk actions.

#### Chat and Agents
- Added uploaded chat images as media references.
- Expanded prompt generation context for agent configuration.

### Changed

#### Chat Experience
- Reworked chat message rendering, chain-of-thought displays, tool displays, and scrolling behavior to reduce flicker and frozen states.
- Optimized AI conversation streaming timeout handling.

#### Platform and Permissions
- Allowed superadmins to transfer team ownership.
- Improved skill capability views and completed skill action mappings.
- Simplified media generation selectors to show model names only.

#### Automation and Dependencies
- Updated GitHub automation action versions and dependency lockfiles.
- Removed generated repository activity and documentation sync workflow reports from version control.

### Fixed

#### Chat and Workflow
- Fixed agent chat flicker, thought-chain scroll state, chat scrolling, agentic workflow rendering, and production chat collapsible freezes.
- Fixed agent message version branch context when continuing conversations.

#### Knowledge Base
- Fixed knowledge base bulk action review issues and media asset processing/search paths.

#### Admin and Tools
- Fixed admin tool management copy and skill capability page regressions.

### Security

#### Dependencies
- Updated backend `aiohttp`, `starlette`, and `idna` dependencies for security maintenance.

## [0.2.5] - 2026-05-20

### Changed

#### UI Consistency
- Unified destructive delete affordances across platform menus and dialogs, including SSO provider, knowledge base, and capability actions.
- Kept notification badge text legible when hovering destructive menu items.
- Aligned workflow run status labels and badge styling across workflow logs, run details, and activity logs.

#### Deployment
- Packaged the backend application as bytecode in Docker images.
- Enabled Docker standalone frontend deployments to proxy `/api/*` requests to the internal backend service.
- Added a server-side API URL resolver for frontend SSR fetches when the public API URL is relative.

### Fixed

#### Chat and Logs
- Fixed Docker builds excluding `logs` route directories and causing logs pages to return 404 in production.
- Prevented `UnboundLocalError` during chat streaming failures.
- Fixed Docker deployment failures for auth and public chat SSR metadata fetches.
- Restored workflow log run details when selecting a run from the workflow logs page.
- Fixed workflow log filtering to use backend run status values and corrected workflow monitor navigation from the logs page.
- Localized workflow run detail labels for started time, finished time, and debug mode.

#### Skills and Automation
- Installed Git in the skill import environment so Git-backed skill imports can complete successfully.

### Security

#### Chat Streaming
- Removed stack trace exposure from chat streaming error responses.

## [0.2.3] - 2026-05-19

### Fixed

#### Authentication
- Redirect unauthenticated users away from protected app and dashboard pages before rendering credential-dependent content.
- Preserve backend invalid-credential messages on login instead of replacing them with the session-expired notice.
- Keep authentication form borders on the centered card layout while preserving the borderless split layout.

#### Dashboard
- Give dashboard trend charts measurable containers to avoid invalid Recharts width and height warnings.

## [0.2.2] - 2026-05-17

### Added

#### Authentication
- Added a configurable split authentication layout so deployments can switch between centered and split-screen auth pages.

#### Automation
- Added automatic GitHub issue and pull request assignment workflow support.

### Changed

#### Frontend and Site Settings
- Updated site settings UI and API wiring for configurable auth layout options.
- Refined numeric input handling across admin and platform forms.
- Updated frontend dependencies including React, React DOM, shadcn, lucide-react, TypeScript, and Next.js lint configuration.

#### CI/CD
- Updated GitHub Actions release and automation dependencies.

### Fixed

#### Documentation
- Corrected PostgreSQL environment variable references in deployment documentation from `POSTGRES_HOST` to `POSTGRES_SERVER`.
- Tightened documentation sync verification notes for repository automation.

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
- Agent interactive question tool with structured multi-question input
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

[Unreleased]: https://github.com/clouisle/Clouisle/compare/v0.2.9...HEAD
[0.2.9]: https://github.com/clouisle/Clouisle/compare/v0.2.5...v0.2.9
[0.2.5]: https://github.com/clouisle/Clouisle/compare/v0.2.1...v0.2.5
[0.2.1]: https://github.com/clouisle/Clouisle/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/clouisle/Clouisle/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/clouisle/Clouisle/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/clouisle/Clouisle/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/clouisle/Clouisle/releases/tag/v0.1.0
