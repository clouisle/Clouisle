# Implementation Plan

## Active
- **ask-user-custom-answers-and-skip** — In progress. Allow custom text alongside ask_user choices and permit users to explicitly skip every question while preserving a model-visible durable result. See `docs/plan/ask-user-custom-answers-and-skip.md`
  - [ ] 1. Define custom-answer and explicit-skip contract
  - [ ] 2. Extend durable answer submission
  - [ ] 3. Add composer custom-answer and skip controls
  - [ ] 4. Verify adapters and regressions
- **context-compression-three-level-redesign** — Superseded by `agent-simple-context-summary`. Its planned bounded-normalization, active-tool rolling compaction, and historical-checkpoint layers were not adopted. See `docs/plan/context-compression-three-level-redesign.md`
- **remove-worker-uploads-mount** — In progress. Removed the shared uploads volume mount from the Celery worker (and sandbox-worker) so distributed deployments without distributed storage work: media assets moved onto UploadStorageBackend, worker file access goes through explicit internal `/internal/uploads/*` endpoints on api (`INTERNAL_API_TOKEN` auth), and the workflow `file_to_url` node became a pure URL passthrough. See `docs/plan/remove-worker-uploads-mount.md`
  - [x] 1. Media assets on UploadStorageBackend (list/save/delete/serve)
  - [x] 2. Internal file endpoints + token auth + worker remote-mode branches
  - [x] 3. Deployment manifests, env/secret, and docs
  - [ ] 4. End-to-end verification in a real cluster (local + object modes)

- **pr-315-review-fixes** — In progress. Complete P0–P3 remediation for lexical recovery, lifecycle consistency, global retrieval, AUTO-RAG, Retrieval Lab, and PostgreSQL image publication. See `docs/plan/pr-315-review-fixes.md`
  - [x] 1. Complete remediation design and defect mapping
  - [ ] 2. Authoritative lexical versions, bounded backfill, and reconciliation
  - [ ] 3. Celery loop reuse and independent projection repair
  - [ ] 4. Lifecycle dispatch compensation and transactional chunk mutations
  - [ ] 5. Global retrieval fusion, ordered context, detached shadow, and pipelined telemetry
  - [ ] 6. Bounded fail-open AUTO-RAG history
  - [ ] 7. Sparse settings merge and Retrieval Lab validation
  - [ ] 8. Verified dual-architecture PostgreSQL deployment image
  - [ ] 9. Full validation and evidence

- **postgres-pg-search-alpine-image** — In progress. ARM64 passed at 426,942,814 bytes; native amd64 and release-manifest evidence remain required before adoption. See `docs/plan/postgres-pg-search-alpine-image.md`
  - [x] 1. Reproducible Alpine source build
  - [x] 2. Runtime and size acceptance harness
  - [x] 3. Native multi-architecture CI and publication workflow
  - [ ] 4. Dual-architecture qualification and deployment adoption

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
  - [x] 10. Remove rerank fail-open, add stage-aware errors, restore toast notifications

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

- **yun-96-site-legal-settings** — In progress. Add configurable ICP record and login/register terms/privacy entries with optional required registration acceptance. See `docs/plan/yun-96-site-legal-settings.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend public settings and registration enforcement
  - [x] 3. Frontend admin settings UI and i18n
  - [x] 4. Auth legal footer and registration checkbox
  - [x] 5. Validation and regression checks

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

- **helm-chart-deployment** — In progress. Add a minimal production-ready Helm chart for the current API/worker/sandbox-worker/scheduler/frontend deployment model. See `docs/plan/helm-chart-deployment.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Helm chart scaffold and values schema
  - [x] 3. Application service templates
  - [x] 4. Built-in infrastructure templates
  - [ ] 5. Helm deployment docs and validation

- **admin-capabilities** — In progress. Rename admin Tools to Capabilities, add Tools/Skills tabs, and back them with admin-prefixed APIs. See `docs/plan/admin-capabilities.md`
  - [x] 1. Design docs and implementation index
  - [ ] 2. Admin capability permissions and APIs
  - [ ] 3. Admin route, navigation, search, and i18n
  - [ ] 4. Admin Tools tab on `/admin/tools` APIs
  - [ ] 5. Admin Skills tab on `/admin/skills` APIs
  - [ ] 6. Validation and regression checks

- **agent-skills** — In progress. Redesign Agent Skills around zip/Git package import: scan multiple `SKILL.md` roots, preview/install selected Skills, keep Agent-scoped function calling, and run only declared script Skills in sandbox. See `docs/plan/agent-skills.md`
  - [x] 1. Design docs and implementation index
  - [ ] 2. Backend package-driven Skill model and schemas
  - [ ] 3. Zip/Git scanning, package parsing, and import sessions
  - [ ] 4. Skills import API, permissions, audit, and i18n
  - [x] 5. Skill tool definition and instructions/script execution
  - [x] 6. Frontend import, preview, install, detail, and test UI
  - [ ] 7. Agent selection and end-to-end security/regression tests

- **sandbox-runtime-migration** — In progress. Migrate subprocess-based code execution to a long-running sandbox worker runtime that supports Python/JS package installation, CLI and custom command execution, skill compilation, and compatibility bridges for tools, chat, and workflow code nodes. See `docs/plan/sandbox-runtime-migration.md`
  - [ ] 1. Runtime contracts, policies, and compatibility schema
  - [ ] 2. Queue, gateway, and result transport
  - [ ] 3. Long-running worker, scheduler, and workspace/process isolation
  - [ ] 4. Python environment cache and CLI execution
  - [ ] 5. Node environment cache and CLI execution
  - [ ] 6. Tool, chat, and workflow entry migration
  - [ ] 7. Skill compilation and frontend editor/test path
  - [ ] 8. Deployment rollout, observability, and legacy deprecation

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

- **agent-simple-context-summary** — Complete. Before every provider call, the full request payload is estimated. At more than 90% of the model context limit, one model-generated summary replaces the old history; the new context is system prompt + structured summary + current user request; active tool-round assistant/tool protocol messages after the current user request are also retained, with a persisted conversation watermark.
  - [x] 1. Replace staged compression with 90% preflight summary
  - [x] 2. Cut over non-streaming, streaming, edit, and regenerate paths
  - [x] 3. Remove checkpoint, session-memory, and tool-step compaction paths
  - [x] 4. Keep summary persistence and align configuration surface
  - [x] 5. Verify the real summary replacement smoke path

- **agent-context-compression-ratio-thresholds** — Superseded by `agent-simple-context-summary`; the staged warning/auto-compact/blocking governance and its config fields were removed. See `docs/plan/agent-context-compression.md`

- **agent-context-compression** — Complete (superseded by `agent-simple-context-summary`). The original shared compression pipeline and SSE integration were replaced by the 90% preflight summary flow.

- **agent-chat-parity** — Aligned non-streaming agent chat request semantics with the streaming path for file parsing, vision inputs, history overrides, and tool metadata/timeouts.

- **backend-babel-i18n-migration** — Introduced a Babel-backed backend i18n runtime with compatibility fallback so existing `t()`, `msg_key`, `BusinessError`, and `ResponseCode` flows stayed compatible during migration.
