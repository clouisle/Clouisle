# Implementation Plan

## Active

- **tiered-context-management** — In progress. See `docs/plan/tiered-context-management.md`.
  - [x] 1. Budget diagnostics and resilient history compaction
  - [ ] 2. Active-round compaction, recoverable results and durable safety
  - [x] 3. Authorized on-demand tool discovery
  - [x] 4. Configuration, UI, documentation and compatibility
  - [ ] 5. Complete regression and browser verification
  - [ ] 6. Persist compression history and repair live run/error visibility

- **team-tool-approval-management** — Completed. See `docs/plan/team-tool-approval-management.md`.
  - [x] 1. Add team-level view of individual tool approval settings
  - [x] 2. Audit approval decisions and tool approval configuration changes
  - [x] 3. Verify authorization, API-key approval and workflow boundaries
  - [x] 4. Update user guidance and changelogs

- **tool-only-api-key-approval** — Completed. See `docs/plan/tool-only-api-key-approval.md`.
  - [x] 1. Remove site, team and entrypoint policy layers
  - [x] 2. Support API-key-bound Agent approval and resume
  - [x] 3. Exclude workflows from tool approval
  - [x] 4. Update API page, guides and security regression verification


- **pr480-browser-qa-fixes** — Completed. See `docs/plan/pr480-browser-qa-fixes.md`.
  - [x] 1. Fix API approval translation
  - [x] 2. Correct MCP errors, browsing and policy enforcement
  - [x] 3. Restore approval policy administration
  - [x] 4. Fix connection management and destructive-action safeguards
  - [x] 5. Verify browser workflows, approval and regression tests

- **agent-api-approval-parameters** — Completed. See `docs/plan/agent-api-approval-parameters.md`.
  - [x] 1. Document Agent API approval interaction and authentication
  - [x] 2. Correct the approval preview of tool call arguments
  - [x] 3. Verify behavior, security and documentation


- **pr480-review-fixes** — In progress. See `docs/plan/pr480-review-fixes.md`.
  - [x] 1. Fix chat stream route and policy-layer enforcement
  - [x] 2. Fix migrations, connection writes, OAuth and MCP budgets
  - [x] 3. Fix interaction, package import, resume and stop semantics
  - [x] 4. Fix frontend masking, picker, bounds and reconnect races
  - [ ] 5. Decide OAuth callback binding and non-interactive gate contract

- **im-chat-run-discovery** — Completed. See `docs/plan/im-chat-run-discovery.md`.
  - [x] 1. Discover owner-scoped active runs
  - [x] 2. Recover chat state safely
  - [x] 3. Verify and document cross-surface recovery

- **im-agent-tool-approval** — Completed. See `docs/plan/im-agent-tool-approval.md`.
  - [x] 1. Define trusted channel origins and shared approval boundary
  - [x] 2. Implement Feishu and WeChat confirmation delivery and decisions
  - [x] 3. Verify authorization, replay, recovery and ask-user regressions
  - [x] 4. Update channel and deployment documentation

- **multi-tool-approval-resume** — Completed. See `docs/plan/multi-tool-approval-resume.md`.
  - [x] 1. Preserve and resume unstarted calls across approvals
  - [x] 2. Verify separate decisions, ordering, and interruption safety
  - [x] 3. Update operator and user guidance

- **approval-tool-description** — Completed. See `docs/plan/approval-tool-description.md`.
  - [x] 1. Preserve the called tool's description with the approval pause
  - [x] 2. Display it in the chat approval panel
  - [x] 3. Verify waiting, restoration, and missing-description behavior

- **caller-only-tool-confirmation** — Completed. See `docs/plan/caller-only-tool-confirmation.md`.
  - [x] 1. Define safe legacy-data cutover
  - [x] 2. Restrict execution and API contracts to caller confirmation
  - [x] 3. Remove external approver configuration and obsolete surfaces
  - [x] 4. Verify migration, interactive and non-interactive behavior

- **tool-runtime-coverage** — Completed. See `docs/plan/tool-runtime-coverage.md`.
  - [x] 1. Investigate and resolve pre-push failures
  - [x] 2. Cover tool runtime authorization, connections and approvals
  - [x] 3. Run coverage gates and push

- **user-tool-connections-management** — Completed. See `docs/plan/user-tool-connections-management.md`.
  - [x] 1. Design document & secondary task registration
  - [x] 2. User tool connections component & quick creation
  - [x] 3. SettingsDialog integration & i18n
  - [x] 4. Component tests & regression verification

- **agent-tool-access-guidance** — Completed. See `docs/plan/agent-tool-access-guidance.md`.
  - [x] 1. Contextualize tool permission and connection failures
  - [x] 2. Verify chat error delivery and localization

- **automatic-tool-connections** — Completed. See `docs/plan/automatic-tool-connections.md`.
  - [x] 1. Runtime current-user selection and identity-bound execution
  - [x] 2. Automatic/fixed authoring controls and localized guidance
  - [x] 3. Integration verification and documentation

- **tool-connections-completion** — Completed. See `docs/plan/tool-connections-completion.md`.
  - [x] 1. HTTP URL templates and variable completion
  - [x] 2. Secure code-tool connection credentials
  - [x] 3. Builtin database cutover and saved-resource migration
  - [x] 4. Integration verification and documentation

- **remove-tool-connection-delegation** — Completed. See `docs/plan/remove-tool-connection-delegation.md`.
  - [x] 1. Backend grant removal and persisted-binding execution authorization
  - [x] 2. Frontend delegation cutover and localized hints
  - [x] 3. Data migration, verification and documentation alignment

- **mcp-chat-approval-display** — Completed. See `docs/plan/mcp-chat-approval-display.md`.
  - [x] 1. Restore explicit MCP child approvals in Agent chat
  - [x] 2. Stabilize streamed MCP thought presentation
  - [x] 3. Verify dispatch, resume and presentation regressions

- **in-chat-tool-approvals** — Completed. See `docs/plan/in-chat-tool-approvals.md`.
  - [x] 1. Backend direct execution decision endpoint and notification deep-linking
  - [x] 2. Inline Approve/Reject actions in PendingToolApprovalCard and auto-resume
  - [x] 3. Remove standalone approvals center page and obsolete navigation links
  - [x] 4. Automated verification and test suite alignment

- **explicit-agent-tool-approvals** — Completed. See `docs/plan/explicit-agent-tool-approvals.md`.
  - [x] 1. Agent ToolConfig require_approval schema and execution boundary bypass for workflows
  - [x] 2. Eliminate heuristic concurrency/read-only approval deduction on builtin tools
  - [x] 3. Frontend Agent orchestration per-tool confirmation switch and localization
  - [x] 4. Automated verification and regression test alignment

- **tool-connections-approvals-mcp** — Completed. See `docs/plan/tool-connections-approvals-mcp.md`.
  - [x] 0. Connection identity, unified approval and MCP protocol design
  - [x] 1. Connection models, encrypted secrets and migration
  - [x] 2. Shared identity resolution and execution entrypoint cutover
  - [x] 3. Unified approvals and durable execution recovery
  - [x] 4. MCP protocol, OAuth and managed sessions
  - [x] 5. Bidirectional interactions and unified UI
  - [x] 6. End-to-end verification and operator documentation

- **network-allowlist-switches** — Completed. See `docs/plan/network-allowlist-switches.md`.
  - [x] 1. Site settings, model endpoints and SSRF
  - [x] 2. Sandbox policy and isolation
  - [x] 3. Admin UI and localization
  - [x] 4. Integrated verification and operator documentation

- **agent-prompt-runtime-conflicts** — Completed. See `docs/plan/agent-prompt-runtime-conflicts.md`.
  - [x] 1. Correct runtime capability guidance
  - [x] 2. Separate generated business rules from platform protocols
  - [x] 3. Verify prompt composition and tool boundaries

- **prompt-generator-quota-errors** — Completed. See `docs/plan/prompt-generator-quota-errors.md`.
  - [x] 1. Preserve safe provider-quota error semantics
  - [x] 2. Verify dialog reporting and document recovery

- **agent-prompt-generation-alignment** — Completed. See `docs/plan/agent-prompt-generation-alignment.md`.
  - [x] 1. Align editor context and bilingual generation instructions
  - [x] 2. Verify compatibility and document the generation contract

- **deepseek-search-provider** — Completed. See `docs/plan/deepseek-search-provider.md`.
  - [x] 1. Site configuration, encrypted key and runtime dispatch
  - [x] 2. Admin dialog, enabled-engine selectors and localization
  - [x] 3. Documentation and integrated verification

- **enabled-search-engine-selection** — Completed. See `docs/plan/enabled-search-engine-selection.md`.
  - [x] 1. Safe enabled-engine availability API
  - [x] 2. Agent and workflow search-engine selectors
  - [x] 3. Verification and documentation

- **site-managed-web-search** — Completed. See `docs/plan/site-managed-web-search.md`.
  - [x] 1. Centralize Tavily/Bocha site configuration and migrate credentials
  - [x] 2. Add configured SearXNG with safe Base URL handling
  - [x] 3. Integrated verification and operator documentation

- **keyed-web-search-only** — Completed. See `docs/plan/keyed-web-search-only.md`.
  - [x] 1. Remove keyless providers and migrate saved selections
  - [x] 2. Update selector, translations and behavior contracts
  - [x] 3. Verify explicit failures and update operator docs

- **bing-keyless-web-search** — Superseded by `keyed-web-search-only` after unrelated live results. See `docs/plan/bing-keyless-web-search.md`.
  - [x] 1. Backend provider and saved Agent configuration cutover
  - [x] 2. Frontend engine selector and documentation cutover
  - [x] 3. Behavior tests and real-search verification

- **dashboard-search-debounce** — Completed. See `docs/plan/dashboard-search-debounce.md`.
  - [x] 1. Activity and audit searches
  - [x] 2. Applications and capabilities
  - [x] 3. Knowledge, memories and models
  - [x] 4. Integrated verification

- **platform-infinite-scroll** — Completed. See `docs/plan/platform-infinite-scroll.md`.
  - [x] 1. Shared sentinel and truncated lists
  - [x] 2. Applications and execution logs
  - [x] 3. Documents and notifications
  - [x] 4. Verification and delivery

- **run-execution-trajectory** — Completed. See `docs/plan/run-execution-trajectory.md`.
  - [x] 1. Runtime model context capture
  - [x] 2. Correlated trajectory and payload API
  - [x] 3. Independent execution inspector
  - [x] 4. Verification and operator documentation

- **builtin-tool-output** — Completed. See `docs/plan/builtin-tool-output.md`.
  - [x] 1. Shared result utils and replay contract
  - [x] 2. Asset, sandbox and persistent web reading outputs
  - [x] 3. Search, memory and short-result renderers
  - [x] 4. Encoding evaluation, regression verification and delivery

- **asset-document-reading** — Completed. See `docs/plan/asset-document-reading.md`.
  - [x] 1. Complete extraction and persistent text representations
  - [x] 2. Bounded reads, search and continuation
  - [x] 3. Tool and chat-context cutover
  - [x] 4. End-to-end verification and delivery

- **backend-push-gate-repair** — Completed. See `docs/plan/backend-push-gate-repair.md`.
  - [x] 1. Repair backend regression contracts and serialization
  - [x] 2. Verify unchanged backend/frontend coverage gates
  - [x] 3. Commit and push with hooks enabled

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

- **pr-473-review-fixes** — Completed (13 confirmed issues and candidate #14 fixed; #15 remains unconfirmed, parser unchanged). See `docs/plan/pr-473-review-fixes.md`
  - [x] 1. Detailed design, evidence thresholds, and agent ownership
  - [x] 2. Feishu callback compatibility and atomic delivery finalization (#1, #4; verify #14)
  - [x] 3. Integration migration, notification compatibility, webhook clearing, and send-time gates (#5–#7, #10)
  - [x] 4. Agent asset/context/public contracts and HTML candidate comparison (#2, #3, #8; verify #15)
  - [x] 5. Model update and edit hydration (#9, #13)
  - [x] 6. Infinite-scroll generations and WeChat draft preservation (#11, #12)
  - [x] 7. Full validation and evidence-based disposition

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

- **helm-chart-deployment** — Complete. Add a minimal production-ready Helm chart for the current API/worker/sandbox-worker/scheduler/frontend deployment model. See `docs/plan/helm-chart-deployment.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Helm chart scaffold and values schema
  - [x] 3. Application service templates
  - [x] 4. Built-in infrastructure templates
  - [x] 5. Helm deployment docs and validation

- **admin-capabilities** — Complete. Rename admin Tools to Capabilities, add Tools/Skills tabs, and back them with admin-prefixed APIs. See `docs/plan/admin-capabilities.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Admin capability permissions and APIs
  - [x] 3. Admin route, navigation, search, and i18n
  - [x] 4. Admin Tools tab on `/admin/tools` APIs
  - [x] 5. Admin Skills tab on `/admin/skills` APIs
  - [x] 6. Validation and regression checks

- **agent-skills** — In progress. Redesign Agent Skills around zip/Git package import: scan multiple `SKILL.md` roots, preview/install selected Skills, keep Agent-scoped function calling, and run only declared script Skills in sandbox. See `docs/plan/agent-skills.md`
  - [x] 1. Design docs and implementation index
  - [x] 2. Backend package-driven Skill model and schemas
  - [x] 3. Zip/Git scanning, package parsing, and import sessions
  - [x] 4. Skills import API, permissions, audit, and i18n
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

- **model-provider-icons** — Complete. Render a shared provider icon and localized provider label on every model display surface (admin table/dialog, catalog cards, KB/agent/workflow selectors), with `provider_display_name` precedence, model-family inference for custom gateways, and a monogram fallback. See `docs/plan/model-provider-icons.md`
  - [x] 1. Shared provider icon/label primitives and vendored assets
  - [x] 2. Admin model table, dialog, and team authorization surfaces
  - [x] 3. Platform catalog, team page, and knowledge base surfaces
  - [x] 4. Agent and workflow model pickers
  - [x] 5. Tests, coverage, lint, and regression verification

- **docs-code-alignment-audit** — Completed. Verification of `docs/` against `98d3e88e`.
  - [x] Internal link integrity (854 links, 0 broken after fix)
  - [x] API route/verb coverage vs generated OpenAPI schema (377 documented calls, 0 unmatched)
  - [x] Environment variables vs `config.py` and deploy manifests (all 84 settings documented)
  - [x] Permission codes vs `core/permissions.py` (0 unknown codes)
  - [x] Settings defaults vs `DEFAULT_SETTINGS`; agent/model/workflow defaults spot-checked
  - [x] Stale-feature sweep (keyless search, legacy delivery tables, removed channels)
  - [x] Fixed sorting guide, notification analysis payload, and one broken design-doc link
