# Implementation Plan

## Active

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
