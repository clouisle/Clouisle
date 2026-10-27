# Changelog

This document records all significant changes to the project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Fixed

- Inactive accounts are rejected before API-key identity processing when submitting an Agent chat run.
- A fixed personal tool connection whose owner has left the team now returns an access-denied error rather than an internal error.
- Client-side fallback errors (permission denied, session expired, timeout, network, server and not-found) now come from the shared `errors` i18n catalogs instead of a second hardcoded map, and regional locales such as `zh-CN` or an app language without the locale cookie no longer fall back to English.

### Added

- The profile Settings dialog now has a Tool Connections tab for the active team. It lists every connection available to the user with its tool, account label, scope, default flag and status, and supports adding a connection from a tool picker, setting a default, re-authenticating an expired account and deleting one. The tab and those actions are hidden when the caller cannot perform them: it requires `tool:read`, while team-wide connections are managed only by team owners/admins.

### Changed

- Tool configuration now uses a caller-confirmation switch. Existing deny policies stay blocked until explicitly changed; MCP operation rules retain inheritance and existing deny overrides.

- Tool execution approval is now caller-only. Interactive Agent chat pauses for the user who initiated the call, and only that caller can approve or reject it once; team members, team administrators and superusers cannot decide, and the former designated-user and team-role approver settings can no longer be created or saved. Stored legacy `user`/`team_role` policies, including nested MCP operation overrides, are preserved unchanged but fail closed with `6510` before the tool runs, never becoming caller confirmation or allow; administrators must re-save them. Unstarted executions associated with an external gate — awaiting confirmation or ready, including work whose external gate was already approved — are cancelled on upgrade with their pending gates and are never resumed; executing and terminal rows are left for audit. Workflows, tool tests, discovery, API keys, embeds, channels and schedules still never prompt, and stored legacy external approval configuration there fails closed. Rolling back the application does not reactivate cancelled executions; start a new run.
- Tool permission denial, missing connections, and inactive authorization now return localized guidance naming the specific Agent tool and prompting access or connection login.
- MCP header and environment templates suggest declared connection field names when typing `{{`.
- MCP HTTP and SSE header values are visible while editing, making connection templates readable; connection secrets remain masked.
- Simplified tool connection cards by removing internal credential-field names and allowing actions to wrap on narrow screens; account labels and management controls remain available.
- macOS Celery prefork children use a verified `certifi` CA bundle when no explicit TLS CA file/directory is configured, avoiding the MCP HTTP client's Objective-C `SecPolicyCreateSSL` fork crash. Explicit CA overrides and Linux behavior are unchanged.
- Agent tools and manual workflow tool nodes now default to automatic current-user connections for personal/selectable identities: explicit default first, otherwise the sole personal account. Multiple accounts require a default; missing or expired authorization prompts configuration/login without borrowing another account. Authors can still pin a connection, background entrypoints remain fixed-only, and MCP discovery now uses the invoking user's credentials as well as execution.
- HTTP tools support URL placeholders with final-target SSRF validation and variable completion in request configuration. Code tools expose selected connection fields through the per-execution `credentials` mapping in Python and JavaScript; sandbox queue payloads carry encrypted credentials rather than plaintext. Database querying moves from custom-tool creation to builtin tools backed by personal/team connections, with existing definitions and bindings migrated.
- Upgrade API/Agent and Sandbox Workers together with the same tool-secret keyring; retain old keys until queued sandbox jobs drain. Database migration preserves historical tool rows and connection ids, rewrites live/versioned definitions atomically, and conservatively retains disabled/approval restrictions. Conflicting defaults or duplicate same-engine Agent attachments stop migration rather than silently switching identities; resolve them in the previous release before upgrading. The code editor's Run remains connectionless; saved-tool Test selects a connection.
- Removed separate tool-connection delegation grants and their API/model contract. Selecting a connection in an Agent or workflow definition now authorizes that saved definition to use the identity when shared or run in the background; configuration-time binding checks, owner-only personal selection, secret isolation and runtime connection/team validation remain.
- MCP tool and approval-rule lists now scroll internally above a responsive height limit (400px or 45vh), keeping headings and manual rule controls outside the scroll region.
- MCP listings and tool calls now attach OAuth credentials from the selected authorized connection even when provider discovery used an absent or empty `mcp_config.oauth`. Existing connection authorization, token refresh and version checks still apply.
- OAuth tool connections accept provider-declared token lifetimes longer than seven days; nonpositive and datetime-overflowing lifetimes remain rejected. This prevents valid long-lived tokens from being reported as unusable.
- MCP editors now combine discovered tool names, descriptions and approval selectors into one list. Saved rules missing from the current discovery result remain editable under Other operation rules; refreshing discovery never deletes them.
- MCP tool descriptions retain a two-line preview with full text in the shared shadcn tooltip on hover or keyboard focus, without a disclosure control.
- The in-chat MCP server-request panel now stays hidden during empty background polls, rather than appearing on every loading cycle. Actual pending requests remain actionable.
- MCP child-operation approval rules now apply in interactive Agent chat without gating discovery, testing or workflows. MCP invocation details stay inside the thought trace, and partial streamed MCP names no longer replace the thought header.
- Tool-domain secrets (tool connections, approval execution parameters, OAuth client secrets/PKCE verifiers, tool interaction responses) now use versioned envelope encryption (`enc:tool:v1:<key_id>:…`) with a configurable keyring (`TOOL_SECRET_KEYS` / `TOOL_SECRET_PRIMARY_KEY_ID`). Existing single-key ciphertext still decrypts; rotate with `python -m app.core.tool_secret_rotation` (compare-and-swap, dry-run supported). See [environment variables](deployment/environment-variables.md#tool_secret_keys).
- Builtin tool outputs now separate complete structured display data from concise model text through shared utilities. Document and sandbox reads preserve line/snapshot anchors; referenced search, memory and short results omit redundant presentation fields. Explicit model summaries survive durable replay without leaking storage envelopes into public message results. Web/document URL readers persist full extracted text for scoped continuation instead of truncating it. TOON remains an evaluated alternative, not a global format or runtime dependency.
- Document attachments now use on-demand persistent text representations and bounded `read_asset` / `search_asset` tools instead of automatic full-text injection. Models can continue through long documents, including oversized lines, with version-bound cursors. The truncating `parse_asset` tool and obsolete Agent text-length settings were removed; native PDF viewing requires explicit page selection. Original Asset permissions, expiry and active-branch visibility apply on every read/search. Complete extraction fails explicitly beyond its resource ceiling rather than silently discarding the tail.
- Unified SSO login providers, email, Webhook, and manual Feishu directory sync under Integration records and `/site-settings/integrations`, with static capabilities and separate login/settings permission domains.
- Moved management APIs to `/api/v1/admin/integrations` and public login discovery to `/api/v1/sso/integrations`. Existing login/callback URLs, integration UUIDs, and identity bindings are preserved. Credentials are encrypted and omitted from admin responses.
- Schema cutover requires a database backup and matching `SECRET_KEY`; rollback restores the matching database/application version. See [upgrade instructions](admin-guide/settings/SSO.md#upgrading-existing-installations). The Feishu integration additionally provides opt-in sign-in (`user_login`); see [Configure Feishu sign-in](admin-guide/settings/SSO.md#configure-feishu-sign-in).
- Added Feishu notifications as an opt-in integration capability. Admins can send test messages to an explicitly selected linked user; notification delivery runs asynchronously and reports per-channel status for bound active recipients.
- Team ownership transfers now write an audit event with the old/new owner and identify the acting administrator, including super administrators.
- Super administrators bypass global permission checks and may grant team-admin membership to any user; regular operators can grant the team-admin role only to users with `team:manage`.
- Fixed a `NameError` in Feishu's scheduled recovery task, restoring recovery of persisted receipts and unsent replies after their receipts complete.
- Made WeChat polling/recovery and Feishu Agent recovery schedules follow administrator feature switches without restarting Beat (normally within two seconds). Feishu Wiki dispatch runs only with an enabled integration and at least one enabled source, independently of other capabilities. Restart Beat once when upgrading to load the new scheduler; already queued tasks keep their feature checks.
- Routed bounded, oldest-due WeChat polling batches through the ordinary worker deployment instead of a dedicated polling worker. Durable claims, global backlog limits and shared HTTP connections remain; idle/replayed polls do not create Agent tasks, and recovery remains fair across bindings and completed-receipt outboxes. Follow the maintenance-window cutover and concurrent-index instructions before enabling at scale.
- Added an always-visible bilingual Feishu Agent chat setup checklist naming the required permissions, event subscription and publication/approval steps; clarified that WebSocket connectivity does not confirm message readiness.
- Moved Feishu replying-Agent selection to Personal settings → Feishu, shared with `/use`. Admin integration settings now manage transport only. Existing session choices migrate per user; switching does not reroute accepted messages or active runs.
- Added an immediately saved personal Feishu Agent chat switch, independent of shared channel availability. Turning off preserves selection/history and pauses intake, queued processing and unsent replies.
- Simplified personal Feishu settings with a prioritized setup hint and a help-icon tooltip beside the replying-Agent label, separate from save actions; clarified automatic switch saving, paused-message handling, per-Agent conversation reuse and bilingual commands.
- Expanded personal Feishu and WeChat instruction tooltips to describe each bot's supported commands and what they do.
- Added Account security → Connected Accounts → Link Feishu for existing accounts, with explicit authorization, same-tab confirmation, owner-scoped completion and identity-conflict rejection; corrected the earlier binding guidance.
- Excluded self-service Feishu account links from directory user/profile and department-membership synchronization, preventing duplicate imports while preserving ordinary directory-managed users. Link provenance survives sign-in; upgrades recover previous manual links from retained binding audit events.
- Compacted personal WeChat settings with header authorization/refresh, inline actions and responsive forms. Removed Agent activity and collection history panels and their requests; current-run status, stop controls and backend history remain.
- Aligned personal Feishu and WeChat settings card styling, spacing, action sizes and save-button order without changing channel behavior.
- Fixed WeChat Agent first-run dispatch being delayed by the retry backoff. Terminal receipt completion, reply outbox creation and session release now commit atomically, so a failed outbox write remains recoverable instead of silently losing the model reply. Restart all ordinary Celery workers after upgrading; already completed historical receipts without final deliveries require explicit reconciliation and are not automatically resent.
- WeChat Agent chat now combines adjacent ordinary messages from one `getupdates` response into one prompt, including text and attachments, with one run and one reply. Original message identities remain deduplicated; merged receipts share the run without producing duplicate replies. Commands split groups, waiting structured answers keep their existing handling, and separate responses are never combined. No extra waiting window or database migration is required; restart ordinary workers to load the change.
- Fixed silent rejection of Feishu file, image and rich-text messages. Accepted resources now become private conversation Assets and durable Agent inputs, with attachment limits and explicit failure replies. Upgrade the receipt schema via API startup and restart ordinary workers/receivers; resend previously ignored messages.
- Feishu and WeChat replies now split at paragraph, line and sentence boundaries within the existing 3500-byte UTF-8 limit. Long Markdown tables repeat headers and separator rows; oversized cells continue in column-preserving rows, and long code blocks repeat language fences. Headers too large to fit fall back to bounded plain-text splitting. Restart ordinary workers to load the change; inbound grouping is unchanged.
- Chat input attachments and `view_asset` now resolve through authorized private Asset storage. Supported image, audio, video and PDF inputs are serialized according to the selected adapter's actual modality and MIME capabilities; parseable documents use extracted text when native file input is unavailable. Durable tool replay stores only asset references and metadata, then reloads and reauthorizes content before another model turn.
- Fixed Agent context planning rejecting `model_config`; model configuration now flows through both planning and finalized-context entrypoints to asset input preparation.
- Added Agent `list_assets` filename search, media-type filters and cursor pagination so older conversation assets remain discoverable beyond the initial preview. Scope authorization, active-branch visibility and asset availability are enforced before metadata is returned.
- Removed automatic asset-directory previews from Agent input. Asset discovery is now on demand through `list_assets`, with 10 results per page by default and a maximum of 30; larger histories use filename search and cursor pagination.

### Added

#### Integrations
- Added optional Feishu WebSocket long connections managed automatically by existing Agent-queue workers, with live receiver status, dynamic feature/configuration changes and singleton failure recovery. No extra service or receiver command is required; HTTP callbacks remain supported.
- Added WeChat iLink integration settings with independent Agent chat and knowledge collection feature switches. Personal bindings remain user-owned; disabled features preserve history, pending work and unsent replies.
- Added WeChat Agent listing and switching commands (`/agents`, `/use`, `/智能体`, `/使用`) with shared personal selection, idle guards, required-variable guidance and preserved per-Agent conversations.

#### Chat and File Previews
- Added a unified artifact list with file counts, expandable results, authenticated downloads, and shared previews for common document, media, and code formats.
- Added DOCX thumbnails, page synchronization, responsive fit-to-width, and zoom controls; added read-only PDF and spreadsheet preview controls.
- Added an Agent setting to hide generated artifact lists from assistant messages in chat and preview; defaults to off.

#### Memory and RAG
- Added optional background memory extraction controls in the admin `memory` site-settings category, including model selection, debounce cooldown, and pending-turn trigger limits.
- Added the bounded `get_memory_subgraph` Agent tool for relationship-aware memory retrieval.

#### Models and Workflows
- Added the TypeSafe AI (`typesafe`) decision-model provider and the `decision` model type, which evaluates a state against typed `choice`, `score`, or `noul` questions and returns typed answers with probability distributions and confidence.
- Added the Decision workflow node: it asks one typed question, routes on the returned answer (or the highest-probability score level), and supports a fallback branch plus an optional confidence threshold.

### Changed

#### Agent Studio

- On phones, the Agent preview opens as a full-screen, drawer-like overlay instead of compressing the editor and chat side by side.

#### Assets and Media
- Persisted generated images and videos as scoped Assets and exposed conversation/workflow-scoped media references for model use.
- Updated CSV handling for GBK/GB18030 content and removed duplicate spreadsheet viewer downloads.

#### Agent Retrieval and Chat Timeline
- Agents with no knowledge-base associations now persist and run with `rag_mode: off`; the Agent editor hides the RAG selector until a knowledge base is selected.
- Chat thought-process rendering preserves the emitted order of retrieval, compression, reasoning, tool, and generation steps.
- RAG context remains `null` when retrieval did not run and `[]` when retrieval ran but returned no contexts.

### Fixed

#### Integrations
- Added the missing Chinese and English Agent chat capability labels so the integrations page renders Feishu capability badges without missing-message errors.

#### Asset Access and Previews
- Protected generated images, generated videos, and sandbox artifacts with scope-aware authorization and authenticated client downloads.

- Preserved explicit too-large, unauthorized, permission-denied, unsupported, and parse-failure preview states without falling back to unprotected URLs.

#### Chat Experience
- Deduplicated overlapping Agent conversation pages and preserved the loaded pagination position when refreshing the chat sidebar.

#### Database Tools
- Replaced regex and keyword-based SQL checks with bounded, dialect-aware AST validation; safely quote database-discovered table names before sampling.


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
- **Notifications**: Email (SMTP) and generic Webhook delivery, plus in-app notifications
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
