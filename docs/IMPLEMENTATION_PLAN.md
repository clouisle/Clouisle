# Implementation Plan

## Active

- **retrieval-tuning-and-dataset-authoring** — In progress. Turn batch evaluation into dataset-driven parameter search: fix metric pollution from ungraded cases, make tuned parameters persistable to production, build evaluation datasets by grading retrieval results instead of hand-writing chunk UUIDs, and add bounded staged coordinate search with production-path verification. See `docs/plan/retrieval-tuning-and-dataset-authoring.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Metric correctness — exclude ungraded cases from ranking means
  - [x] 3. Stage 1: Retrieval Lab API contract and independent permissions — canEvaluate/canUpdate props wired through dashboard and platform routes
  - [x] 4. Stage 2: Dataset revision tracking and query fingerprinting — atomic mutations with optimistic locking, query-based upsert, and comprehensive tests
  - [x] 5. Stage 3: Query-scoped visual labeling — query isolation prevents cross-query label pollution, versioned storage envelope with migration, and comprehensive test coverage
  - [ ] 6. Knowledge base retrieval defaults so tuned parameters can land in production
  - [x] 7. Stage 4: Multi-strategy candidate pooling and dataset upsert — four-strategy candidate pool with provenance/rank preservation, dataset selection toolbar, create/update case promotion preview, quality diagnostics panel (judged/unjudged, positive/negative, per-strategy unique contributions, overlap, pool-relative coverage), bulk mark unlabeled as irrelevant, and bilingual i18n
  - [ ] 8. Stage 5: Dataset quality panel and run comparison
  - [ ] 9. Stage 6: Tuning backend — sweep model, API, staged coordinate search, budget guards
  - [ ] 10. Stage 7: Tuning executor — Celery orchestration with cancel/recover and live verification
  - [ ] 11. Stage 8: Tuning frontend — parameter space editor, comparison table, recommendation and apply
  - [ ] 12. Stage 9: i18n, generated types, documentation, and full loop validation

- **retrieval-failure-handling** — In progress. Make first-use lexical retrieval safe, preserve sanitized per-channel diagnostics, return actionable localized retrieval guidance without exposing infrastructure details, remove rerank fail-open degradation, and add stage-aware error reporting. See `docs/plan/retrieval-failure-handling.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Lexical index and alias initialization
  - [x] 3. Sanitized retrieval diagnostics and endpoint mapping
  - [x] 4. Localized failure copy
  - [x] 5. Preserve dual-channel failure classifications
  - [x] 6. Focused tests, live retry, underlying channel diagnosis, and reconciliation of 184 missing lexical documents
  - [x] 7. Actionable safe error categories and per-side Retrieval Lab guidance
  - [x] 8. Normalize lexical result names to the search response contract and cover HTTP 500 classification
  - [x] 9. Final live fulltext and hybrid A/B verification
  - [ ] 10. Remove rerank fail-open, add stage-aware errors, restore toast notifications

- **yun-117-knowledge-retrieval-lab** — Complete. Replace heuristic keyword matching with an evaluated Dense + BM25 hybrid pipeline and upgrade the existing search test into a retrieval evaluation lab. See `docs/plan/yun-117-knowledge-retrieval-lab.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Retrieval evaluation baseline — deterministic chunk/document Recall@K, MRR@K, nDCG@K, expected-empty accuracy, latency percentiles, and current `VectorStore.search` snapshot adapter; 6,246 backend tests passed with 97.82% lines/95.11% branches; 1,998 frontend tests passed with 97.77% lines/95.04% functions
  - [x] 3. Correct current retrieval semantics — strict modes, stage-specific scores/ranks, dense-only thresholding, explicit dense failures, hybrid degradation, authoritative status filters, lexical-only AUTO RAG, and bounded global multi-KB ranking; 6,255 backend tests passed with 97.82% lines/95.09% branches; 1,998 frontend tests passed with 97.77% lines/95.04% functions
  - [x] 4. Unified retrieval service — one authorization-safe request/response contract now owns bounded multi-KB concurrency, timeout/failure diagnostics, global deterministic ranking/truncation, and VectorStore delegation across API, AUTO, Agentic, AgentService, and workflow callers; 6,267 backend tests passed with 97.81% lines/95.07% branches; 1,998 frontend tests passed with 97.77% lines/95.04% functions
  - [x] 5. OpenSearch BM25 indexing and weighted fusion — OpenSearch lexical store, lifecycle dual writes/deletes, resumable backfill/reconciliation, weighted RRF, and deployment support complete; 6,294 backend tests passed with 97.71% lines/95.02% branches; frontend gates passed with 97.77% lines/95.04% functions and 470/470 source census; deployment static validation passed
  - [x] 6. Global rerank and bounded context assembly — one cross-KB rerank pass, fail-open/fail-closed and calibrated threshold handling, authorized adjacent-chunk expansion, document aggregation with chunk-level citation provenance, and final document/chunk/token budgets; 6,305 backend tests passed with 97.71% lines/95.02% branches; 1,998 frontend tests passed with 97.77% lines/95.04% functions and 470/470 source census
  - [x] 7. Instant retrieval playground and A/B comparison — shared production-faithful Retrieval Lab for dashboard/platform routes, dedicated test permissions, raw stage diagnostics/timings, independent A/B calls, local grades/presets, and confirmed authorized production apply; 6,311 backend tests passed with 97.72% lines/95.02% branches; 2,001 frontend tests passed with 97.80% lines/95.14% functions and 470/470 source census
  - [x] 8. Batch evaluation datasets and runs — persistent datasets/case snapshots, bounded JSON/CSV import, immutable versioned runs, redelivery-safe Celery execution, durable failure/cancellation, active-run mutation guards, aggregate metrics, and shared dashboard/platform UI; 6,345 backend tests passed with 97.69% lines/95.02% branches; 2,008 frontend tests passed with 97.81% lines/95.15% functions
  - [x] 9. Query contextualization experiment — default-off, AUTO-only retrieval query rewriting uses bounded active-branch history, the agent chat model, a strict timeout, grounded structured output, retrieval-only rewrites, and privacy-safe disabled/not-needed/rewritten/fallback diagnostics; 6,357 backend tests passed with 97.70% lines/95.03% branches; 2,008 frontend tests passed with 97.81% lines/95.15% functions and 471/471 source census
  - [x] 10. Learned Sparse evaluation gate — deterministic evaluation-only comparison of Dense+BM25, Dense+learned-sparse, and three-way retrieval across Chinese, English, mixed-language, and identifier cohorts; aggregate Recall/nDCG and operational gates remain an explicit no-go without a measured provider, and production sparse indexing stays disabled; 6,365 backend tests passed with 97.70% lines/95.02% branches; 2,008 frontend tests passed with 97.81% lines/95.15% functions and 471/471 source census
  - [x] 11. Rollout, observability, documentation, and validation — environment kill switch plus mutable global/team/percentage rollout, deterministic hashing, answer-isolated privacy-safe shadow execution, and fail-open Redis metrics; 6,371 backend tests passed with 97.70% lines/95.03% branches; 2,008 frontend tests passed with 97.81% lines/95.15% functions and 471/471 source census

- **issue-255-test-coverage** — Complete. Established honest backend and frontend coverage measurement, covered critical happy/error paths, and enforced independent 95% CI gates. See `docs/plan/issue-255-test-coverage.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend and frontend coverage baselines
  - [x] 3. Backend critical-path coverage — 6,240 tests passed and 3 skipped; 97.81% lines and 95.11% branches
  - [x] 4. Frontend critical-path coverage — 1,998 isolated tests; 97.77% lines, 95.04% functions; 470/470 source census passing
  - [x] 5. Agent UI automation guide and reusable prompt
  - [x] 6. CI reporting, final 95% gates, and documentation

- **admin-video-model-generation-test** — Complete. Replace constructor-only video model tests with a confirmed, billable real generation and completion check. See `docs/plan/admin-video-model-generation-test.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Real generation and polling test
  - [x] 3. Frontend cost confirmation and i18n
  - [x] 4. Focused tests and validation

- **minimax-media-integration** — Complete. Add MiniMax image, video, and synchronous TTS adapters using the existing media model and workflow architecture. See `docs/plan/minimax-media-integration.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Shared MiniMax HTTP client
  - [x] 3. Image generation adapter
  - [x] 4. Video generation adapter
  - [x] 5. Synchronous TTS adapter
  - [x] 6. Frontend provider exposure and backend i18n
  - [x] 7. Focused tests and validation

- **volcengine-tts-seed-audio** — Complete. Add Volcengine OpenSpeech TTS and standalone Seed Audio generation using generic model configuration. See `docs/plan/volcengine-tts-seed-audio.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Audio-generation types and routing
  - [x] 3. Volcengine TTS adapter
  - [x] 4. Seed Audio adapter
  - [x] 5. Real admin connection-test routing
  - [x] 6. Frontend model management and i18n
  - [x] 7. Focused tests and validation

- **volcengine-ark-common-model-support** — Complete. Expose Volcengine Ark chat, text embedding, rerank, Seedream image, and Seedance video models. See `docs/plan/volcengine-ark-common-model-support.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Frontend provider exposure and naming
  - [x] 3. Text embedding and Seedream support
  - [x] 4. Seedance API compatibility
  - [x] 5. Tests and validation

- **workflow-media-preview-url-output** — Complete. Show generated media inside workflow canvas nodes and expose URL-only outputs. See `docs/plan/workflow-media-preview-url-output.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. URL-only backend output contract
  - [x] 3. Canvas runtime trace projection
  - [x] 4. In-node media preview
  - [x] 5. Tests and validation
  - [x] 6. Aspect-fit previews and fullscreen media viewing

- **conversation-image-reference-pool** — Complete. Make active-branch uploaded and generated images reusable by Agent media tools without re-uploading. See `docs/plan/conversation-image-reference-pool.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Conversation image pool and inventory
  - [x] 3. Chat execution-path integration
  - [x] 4. Persisted asset resolution
  - [x] 5. Tests and validation

- **openai-responses-image-provider** — Complete. Add an explicit image-only OpenAI Responses provider with optional reference-image inputs while preserving the existing OpenAI Images API path. See `docs/plan/openai-responses-image-provider.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend provider registration and Responses image adapter
  - [x] 3. Frontend image-provider controls and i18n
  - [x] 4. Regression tests and validation

- **yun-107-media-generation-integration** — Complete. Thread uploaded images into Agent media tools and add a first-class Workflow media-generation node. See `docs/plan/yun-107-media-generation-integration.md`
  - [x] 1. Agent current-image plumbing
  - [x] 2. Workflow media executor
  - [x] 3. Workflow editor node/config/rendering
  - [x] 4. i18n, generated types, and validation

- **scoped-rbac-landing** — Complete. Decouple team authorization from global RBAC by first closing authorization gaps, then adding team-scoped role assignments. See `docs/plan/scoped-rbac.md`
  - [x] 1. Planning docs
  - [x] 2. Shared team access and immediate workflow authorization fixes
  - [x] 3. Scoped role assignment model and migration
  - [x] 4. Scoped permission helper and core endpoint migration
  - [x] 5. Frontend compatibility and documentation

- **yun-105-click-captcha-hardening** — In progress. Harden click captcha with a Cloudflare-like single click check, pointer trajectory validation, and backend-only proof minting. See `docs/plan/yun-105-click-captcha-hardening.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend pointer payload and trajectory scoring
  - [x] 3. Frontend click-area pointer collection
  - [x] 4. Tests and validation

- **yun-105-click-captcha** — In progress. Replace typed captcha with click-based human verification while preserving login/register verification coverage. See `docs/plan/yun-105-click-captcha.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend click captcha contract and enforcement
  - [x] 3. Frontend login click interaction and i18n
  - [x] 4. Documentation and validation

- **embed-chat-performance** — In progress. Apply the optimized chat streaming/rendering patterns to the script-embedded Agent chat widget. See `docs/plan/embed-chat-performance.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Embedded streaming commit batching
  - [x] 3. User-input XML parse gating
  - [x] 4. Final/stop/error cleanup
  - [x] 5. Validation and regression checks

- **chat-extreme-performance-refactor** — In progress. Refactor the chat page/message renderer for extreme performance: bounded rendering, streaming batching, memoized message bodies, and lazy source/tool output. See `docs/plan/chat-extreme-performance-refactor.md`
  - [x] 1. Design docs and implementation index
  - [ ] 2. Renderer boundary extraction
  - [x] 3. Render-time citation handling
  - [x] 4. Streaming state commit throttling
  - [x] 5. Message shell/body memoization
  - [x] 6. Chat list/windowing and conversation switch optimization
  - [x] 7. Source/tool/reasoning bounded rendering
  - [ ] 8. Performance and regression validation

- **yun-101-edit-agent-user-message-history** — In progress. Let users edit their own Agent conversation messages, store edits as message versions, and keep downstream context on the active edited branch. See `docs/plan/yun-101-edit-agent-user-message-history.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend edit endpoint, branching, audit, and tests
  - [x] 3. Frontend edit API, UI, and i18n
  - [x] 4. Validation and regression checks

- **yun-102-configurable-theme** — In progress. Expand site theme configuration to cover practical core colors with native color pickers and runtime CSS variable application. See `docs/plan/yun-102-configurable-theme.md`
  - [x] 1. Backend theme settings and validation (`ruff check`, `ruff format --check`, `mypy app/`)
  - [x] 2. Public/admin theme API typing and normalization
  - [x] 3. Runtime CSS variable mapping
  - [x] 4. Admin color picker UI and i18n
  - [x] 5. Targeted validation

- **yun-97-observability-upgrade** — In progress. Upgrade admin observability IA, alerts, drilldowns, token/cost, workers, and slow-query guidance using existing APIs. See `docs/plan/yun-97-observability-upgrade.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Observability navigation, overview, and alert cards
  - [x] 3. Token/cost, worker, slow-query, Agent, and Workflow display upgrades
  - [x] 4. i18n, generated types, and validation

- **yun-106-object-storage-switch** — Complete. Add configurable switching between local upload storage and S3-compatible object storage. See `docs/plan/yun-106-object-storage-switch.md`
  - [x] 1. Planning docs
  - [x] 2. Backend settings and storage adapter
  - [x] 3. Upload endpoint integration
  - [x] 4. Admin settings UI
  - [x] 5. Skills package storage integration
  - [x] 6. Knowledge-base document storage integration
  - [x] 7. Tests and checks

- **yun-95-log-server-side-search-pagination** — Complete. Move Agent and workflow log search/date filtering to backend queries before pagination. See `docs/plan/yun-95-log-server-side-search-pagination.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend log search/date filters
  - [x] 3. Frontend API params and log pages
  - [x] 4. Validation and regression checks

- **yun-96-site-legal-settings** — In progress. Add configurable ICP record and login/register terms/privacy entries with optional required registration acceptance. See `docs/plan/yun-96-site-legal-settings.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend public settings and registration enforcement
  - [x] 3. Frontend admin settings UI and i18n
  - [x] 4. Auth legal footer and registration checkbox
  - [x] 5. Validation and regression checks

- **default-team-registration** — Complete. Let admins configure a default team and team role assigned to newly registered users. See `docs/plan/default-team-registration.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend settings, validation, and registration assignment
  - [x] 3. Frontend security settings UI and i18n
  - [x] 4. Tests and validation

- **yun-75-admin-observability-dashboard** — Complete. Add platform-admin observability APIs and dashboard pages for AI conversation/workflow performance, timeouts, throughput, and system health. See `docs/plan/admin-observability-dashboard.md`
  - [x] 1. Planning docs and backend API scaffolding
  - [x] 2. Core backend observability metrics and tests
  - [x] 3. System health, worker, throughput, and token metrics
  - [x] 4. Frontend observability API client and route
  - [x] 5. Six observability subpages, navigation, i18n, and generated types
  - [x] 6. Validation and regression checks

- **yun-85-admin-agent-workflow-management** — In progress. Add admin dashboard management for Agents and Workflows with tabbed lists and admin-prefixed APIs. See `docs/plan/yun-85-admin-agent-workflow-management.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend admin permissions and APIs
  - [x] 3. Frontend admin API clients
  - [x] 4. Dashboard Apps management route and tab panels
  - [x] 5. Navigation, route permissions, i18n, and generated types
  - [x] 6. Validation and regression checks

- **yun-80-retry-failed-chunk** — In progress. Add single failed knowledge-base chunk retry without reprocessing the whole document. See `docs/plan/yun-80-retry-failed-chunk.md`
  - [x] 1. Backend chunk retry task and API
  - [x] 2. Frontend API and detail-page controls
  - [x] 3. Document-list recovery access
  - [x] 4. Validation and regression checks

- **yun-78-clouisle-packages** — In progress. Add `.clouisle` import/export for Tools, Agents, Workflows, and Knowledge Bases with manifest validation, dependency preview, conflict handling, secret-safe packages, and audit logs. See `docs/plan/yun-78-clouisle-packages.md`
  - [x] 1. Planning docs
  - [x] 2. Backend schemas, session model, and migration
  - [x] 3. Shared package validation service
  - [x] 4. Resource adapters for Tool, Agent, Workflow, and Knowledge Base
  - [x] 5. Packages API and audit logging
  - [x] 6. Frontend API and shared import dialog
  - [x] 7. Resource page import/export integration
  - [x] 8. Tests and validation

- **agent-message-version-branch-aware-context** — Complete. Make Agent message version switching branch-aware and prevent stale session memory from leaking previous-version context. See `docs/plan/agent-message-version-branch-aware-context.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Message branch schema and migration
  - [x] 3. Branch helper service and active path activation
  - [x] 4. Chat regenerate/switch-version branch behavior
  - [x] 5. Branch-aware history and session memory guards
  - [x] 6. Validation and regression checks

- **agent-reference-image-inputs** — In progress. Let Agent media generation tools use selected uploaded chat images as reference inputs via indexed references and backend base64 conversion. See `docs/plan/agent-reference-image-inputs.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Uploaded image labeling and tool context plumbing
  - [x] 3. Image generation indexed reference resolution and i18n
  - [x] 4. Tests and backend validation
  - [x] 5. Video start-image entrypoint and explicit unsupported-provider failure
  - [x] 6. SiliconFlow video start-image support
  - [x] 7. Runway video start-image support
  - [x] 8. DashScope video start-image support
  - [x] 9. Kling video start-image support
  - [x] 10. Luma video start-image support
  - [x] 11. Pika video start-image support
  - [x] 12. Volcengine video start-image support

- **auth-layout-switcher** — Complete. Add a configurable centered/split authentication page layout, managed from admin site settings. See `docs/plan/auth-layout-switcher.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Public site setting and admin general settings UI
  - [x] 3. Shared auth layout and split preview panel
  - [x] 4. Auth page integration and i18n
  - [x] 5. Validation and responsive checks

- **pr-124-security-review** — Complete. Address PR #124 security review findings for path traversal, SSRF, ReDoS, XXE, sensitive logging, and duration timing. See `docs/plan/pr-124-security-review.md`
  - [x] 1. Security review plan
  - [x] 2. Path traversal hardening
  - [x] 3. SSRF and ReDoS hardening
  - [x] 4. XXE, sensitive logging, and timing fixes
  - [x] 5. Validation and PR update

- **helm-chart-deployment** — In progress. Add a minimal production-ready Helm chart for the current API/worker/sandbox-worker/scheduler/frontend deployment model. See `docs/plan/helm-chart-deployment.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Helm chart scaffold and values schema
  - [x] 3. Application service templates
  - [x] 4. Built-in infrastructure templates
  - [ ] 5. Helm deployment docs and validation

- **deploy-config-refresh** — Complete. Refresh Docker Compose, K8s, image build, and deployment env documentation to match the current API/worker/sandbox-worker/scheduler runtime model. See `docs/plan/deploy-config-refresh.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Docker Compose services and env examples
  - [x] 3. K8s manifest and CI image build
  - [x] 4. Deployment README, legacy Nginx example, and validation

- **kb-upload-file-limits** — Complete. Enforce knowledge base document upload restrictions and make the max upload size configurable in admin storage settings. See `docs/plan/kb-upload-file-limits.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Site setting and backend enforcement
  - [x] 3. Admin storage UI
  - [x] 4. Upload dialogs and validation
  - [x] 5. Validation and regression checks

- **agent-hide-tool-calls** — Complete. Add an Agent setting that hides tool call UI without disabling tool execution. See `docs/plan/agent-hide-tool-calls.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend persistence and API
  - [x] 3. Frontend setting and chat renderer suppression
  - [x] 4. Validation and regression checks

- **admin-capabilities** — In progress. Rename admin Tools to Capabilities, add Tools/Skills tabs, and back them with admin-prefixed APIs. See `docs/plan/admin-capabilities.md`
  - [x] 1. Design docs and implementation index
  - [ ] 2. Admin capability permissions and APIs
  - [ ] 3. Admin route, navigation, search, and i18n
  - [ ] 4. Admin Tools tab on `/admin/tools` APIs
  - [ ] 5. Admin Skills tab on `/admin/skills` APIs
  - [ ] 6. Validation and regression checks

- **sandbox-worker-dev-container** — Complete. Add a no-bind-mount local dev container mode for the sandbox worker, preinstall Python/Node/common tools, and remove shell command allowlist restrictions while preserving sandbox resource/path isolation. See `docs/plan/sandbox-worker-dev-container.md`
  - [x] 1. Planning docs
  - [x] 2. Sandbox Worker Dockerfile
  - [x] 3. Local Dev CLI Mode
  - [x] 4. Shell Policy Relaxation
  - [x] 5. Compose and Developer Docs

- **chat-code-preview** — Complete. Add previewable chat code blocks that open a resizable right-side canvas with sandboxed preview/source tabs while leaving unsupported languages source-only. See `docs/plan/chat-code-preview.md`
  - [x] 1. Preview data flow and code fence detection
  - [x] 2. Sandboxed preview canvas and chat page layout
  - [x] 3. i18n and end-to-end validation

- **agent-skills** — In progress. Redesign Agent Skills around zip/Git package import: scan multiple `SKILL.md` roots, preview/install selected Skills, keep Agent-scoped function calling, and run only declared script Skills in sandbox. See `docs/plan/agent-skills.md`
  - [x] 1. Design docs and implementation index
  - [ ] 2. Backend package-driven Skill model and schemas
  - [ ] 3. Zip/Git scanning, package parsing, and import sessions
  - [ ] 4. Skills import API, permissions, audit, and i18n
  - [x] 5. Skill tool definition and instructions/script execution
  - [x] 6. Frontend import, preview, install, detail, and test UI
  - [ ] 7. Agent selection and end-to-end security/regression tests

- **workflow-typed-variables** — Complete. Replace JSON-stringified variable passing with native object/array passthrough across the workflow engine, introduce a TypeSpec system declared per node and auto-inferred from debug runs, swap Redis context serialization to msgpack, and remove `Any` / `unknown` from workflow IO front and back. Hard cutover, no backward compatibility for existing workflow definitions. See `docs/plan/workflow-typed-variables.md`
  - [x] 1. TypeSpec 与 msgpack 序列化层
  - [x] 2. 节点 IO 摆脱字符串化
  - [x] 3. NodeExecutor 输出 schema 声明
  - [x] 4. 调试运行后的 schema 推断与持久化
  - [x] 5. 前端 TypeSpec 镜像与变量选择器
  - [x] 6. 前端节点配置面板 schema UI
  - [x] 7. 清理 Any 与文档
  - [x] 8. 硬切换执行

- **sandbox-runtime-migration** — In progress. Migrate subprocess-based code execution to a long-running sandbox worker runtime that supports Python/JS package installation, CLI and custom command execution, skill compilation, and compatibility bridges for tools, chat, and workflow code nodes. See `docs/plan/sandbox-runtime-migration.md`
  - [ ] 1. Runtime contracts, policies, and compatibility schema
  - [ ] 2. Queue, gateway, and result transport
  - [ ] 3. Long-running worker, scheduler, and workspace/process isolation
  - [ ] 4. Python environment cache and CLI execution
  - [ ] 5. Node environment cache and CLI execution
  - [ ] 6. Tool, chat, and workflow entry migration
  - [ ] 7. Skill compilation and frontend editor/test path
  - [ ] 8. Deployment rollout, observability, and legacy deprecation

- **agent-media-tool-failure-visibility** — Complete. Restored visible media success/failure rendering across live chat, regenerate, and history recovery, while normalizing unsupported image quality values before provider calls. See `docs/plan/agent-media-tool-failure-visibility.md`
  - [x] 1. Backend media SSE parity and tool error flags
  - [x] 2. Frontend history tool error restoration
  - [x] 3. Image quality normalization and validation
  - [x] 4. Targeted verification

- **mermaid-streaming-growth** — In progress. Rework chat Mermaid streaming so diagrams advance only on stable render frontiers, preserve the last successful SVG during streaming, and animate only newly appeared nodes and edges. See `docs/plan/mermaid-streaming-growth.md`
  - [ ] 1. Frontier-based Mermaid rendering
  - [ ] 2. Stable session identity and visual continuity
  - [ ] 3. Entry animation and verification

- **model-provider-params-extension** — In progress. Extend admin model management so known provider-specific params get dedicated controls, unknown params can be attached via JSON extension areas, runtime defaults survive edit/save, and adapter test/use paths honor `default_params`. See `docs/plan/model-provider-params-extension.md`
  - [ ] 1. Admin test API and base adapter param helpers
  - [ ] 2. OpenAI-like adapter passthrough and reasoning params
  - [ ] 3. Anthropic and Gemini normalization
  - [ ] 4. Admin model dialog known params + JSON extension
  - [ ] 5. Regression and verification

- **text-to-image-defaults-first-batch** — Complete. Wired image-model `default_params` into runtime generation requests, added first-class OpenAI/Google/Stability text-to-image controls in admin model management, and covered the new payload/default precedence with focused tests. See `docs/plan/text-to-image-defaults-first-batch.md`
  - [x] 1. Planning docs and runtime merge helper
  - [x] 2. OpenAI-family payload modernization and quality handling
  - [x] 3. Google and Stability default-param passthrough
  - [x] 4. Frontend provider-specific image controls and i18n
  - [x] 5. Targeted regression tests and validation

- **agent-context-compression-ratio-thresholds** — In progress. Upgrade agent context compression from hard-budget-only behavior to staged context governance with ~80% proactive compaction, selective micro compaction, richer compression observability, and a Phase 2 Session Memory / SM Compact roadmap. See `docs/plan/agent-context-compression.md`
  - [x] 1. Ratio-based thresholds and pressure states
  - [x] 2. Selective micro compaction
  - [x] 3. Compression observability and frontend messaging
  - [x] 4. Phase 2 Session Memory / SM Compact design hooks

- **workflow-duplicate-input-params** — Complete. Prevented duplicate input parameter names in workflow code nodes via runtime executor validation, config-time validation, and frontend dialog guards. Tracked as GitHub issue #99. See `docs/plan/fix-duplicate-input-params.md`
  - [x] 1. Add runtime validation in base executor
  - [x] 2. Add config validation in code node
  - [x] 3. Add i18n error messages
  - [x] 4. Add frontend dialog duplicate detection

- **agent-manual-stop-state** — Complete. Persisted manual stop state for interrupted agent replies so the current UI and reloaded history both show a stable stopped marker. See `docs/plan/agent-manual-stop-state.md`
  - [x] 1. Backend persisted stop state
  - [x] 2. Frontend stop finalization
  - [x] 3. History rendering and verification

## History

- **agent-context-compression** — Complete. Added shared agent context compression for non-stream, stream, and regenerate flows, with agent-level compression config and frontend-visible compression SSE events.

- **agent-chat-parity** — Aligned non-streaming agent chat request semantics with the streaming path for file parsing, vision inputs, history overrides, user-input-request prompting, and tool metadata/timeouts.

- **backend-babel-i18n-migration** — Introduced a Babel-backed backend i18n runtime with compatibility fallback so existing `t()`, `msg_key`, `BusinessError`, and `ResponseCode` flows stayed compatible during migration.
