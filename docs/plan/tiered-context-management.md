# Tiered Context Management Design Document

## Background & Goals

Agent runs can exhaust the input budget with tool schemas and a single active round even when old history can be summarized. Preserve task continuity without silently losing instructions, violating provider tool protocols, bypassing authorization, or re-executing side effects. Non-extreme requests should survive ordinary context growth and summarizer failures; irreducible inputs and unavailable dependencies must fail clearly.

## High-Level Design

Keep persisted conversation/tool records authoritative. Build a model-only view with a complete token budget, history summary, complete tool-call groups and reversible references to older outputs. Progressively reduce excess history and completed active-round results, retaining current instructions, pending approvals and recent tool exchanges. Discover tool definitions only from the authorized set; execution retains its existing authorization and approval boundary. Rebuild the same view after recovery. Emit existing compression events and expose meaningful diagnostics without leaking content.

## Implementation Plan

### Stage 1: Budget and History
- **Files modified**: `backend/app/services/chat_context.py`, `backend/app/llm/token_counter.py`, related tests.
- **Specific logic**: Partition budget by source; preserve model-window provenance; bound history safely. When summarization fails, apply a deterministic, explicitly marked fallback without advancing the summary watermark. Respect disabled compression.
- **Validation**: Exercise fitting and over-budget input, failing summarizer, branch watermarks and unavailable model-window metadata.

### Stage 2: Active Round and Recovery
- **Files modified**: `backend/app/services/chat_context.py`, `backend/app/services/agent_loop.py`, `backend/app/services/agent_run_worker.py`, tool-result services and related tests.
- **Specific logic**: Compact only completed tool exchanges, preserve pending calls and provider protocol; maintain access to original authorized tool results. Preserve side-effect status across restart, approvals and branches. Fail explicitly when irreducible content cannot fit.
- **Validation**: Exercise long single-round tool chains, paired parallel calls, recovery, approval and side-effect safety; compare source records before and after compaction.

### Stage 3: Authorized Tool Discovery
- **Files modified**: Agent tool loading and execution paths, tool definitions, tests.
- **Specific logic**: Offer discoverable tool schemas from the current authorized Agent tool set, preserving always-needed tools and existing execution checks. Ensure tools can be searched again and state survives resume; never expose or execute unauthorized tools.
- **Validation**: Large MCP catalog, missed search, unauthorized tools, approval and resumed run.

### Stage 4: UI, Configuration and Documentation
- **Files modified**: Agent schemas and orchestration UI, localized strings, chat compression events, public guides and changelog.
- **Specific logic**: Extend existing settings without changing disabled-compression semantics; communicate applied compression and irreducible failures, expose safe budget diagnostics.
- **Validation**: Exercise settings and chat in browser in both supported locales where practical; check export/import and API compatibility.

### Stage 5: End-to-End Verification
- **Files modified**: targeted regression tests and any necessary fixes.
- **Specific logic**: Test complete AgentRun including tools, pressure, recovery and authorization across relevant adapters.
- **Validation**: Run backend and frontend full test suites, lint, type checks and i18n checks; run real application and browser UI scenarios; record actual results.

### Stage 6: Durable Chat Visibility
- **Files modified**: AgentRun worker, run persistence and conversation history schemas; chat stream hook and history conversion, with regression tests.
- **Specific logic**: Persist content-free compression diagnostics with the owning run and expose them only with authorized visible conversation rounds. Preserve their order in historical chat; propagate terminal errors and retain active-conversation subscriptions without cross-conversation leakage.
- **Validation**: Exercise authentication failure, active-run event delivery and conversation switching, plus compression history after Redis expiry and branch changes.

### Stage 7: Reuse Checkpoints Before Pressure Decisions
- **Files modified**: `backend/app/services/chat_context.py`, `backend/tests/services/test_context_checkpoint.py`, `CHANGELOG.md`.
- **Specific logic**: Reconstruct validated active-round checkpoint markers before estimating pressure; preserve complete tool groups, current branch hashes and semantic source binding. Extend coverage only when the reconstructed view exceeds the trigger. Reuse alone must not emit a new compression event or rewrite earlier markers.
- **Validation**: Exercise repeated model views with unchanged and newly appended results, genuine pressure, changed result versions and changed semantic source; verify stable request prefixes, event counts and unchanged source records. Run focused backend tests and a real context preparation smoke scenario; browser verification requires a restarted worker.

### Stage 8: Discovery Labels and Sandbox Visibility
- **Files modified**: `backend/app/services/tool_discovery.py`, `backend/tests/services/test_tool_discovery.py`, `frontend/components/chat/message.tsx`, `frontend/components/chat/message.test.tsx`, `frontend/i18n/{en,zh}/chat.json`, `frontend/i18n/types/chat.ts` and changelog.
- **Specific logic**: Keep configured sandbox primitives in the always-visible subset of the already-authorized catalog, without adding unconfigured tools or changing execution permissions. Localize discovery meta-tool names by internal tool name in chat, including older persisted messages.
- **Validation**: Exercise large and small catalogs, absent sandbox tools, authorized sandbox visibility, and localized historical and live tool calls. Run focused backend and frontend tests and inspect the actual chat timeline.
- Verification: browser history renders “发现工具” and “加载工具”; focused backend and frontend suites pass. After worker restart, browser run `55e57109-3287-4743-8f6d-f3e276c230ad` sent discovery tools plus configured `read`, `write`, `edit`, and `bash` on its first model request. The model called `bash`; the recorded execution exited 0 with `sandbox-check-ok`, which appeared in the chat.

### Stage 9: PR Review Corrections
- **Files modified**: Agent loop, worker, discovery, context planning and readback services; chat hook, message conversion and Agent settings; relevant behavior tests and referenced guides.
- **Specific logic**: Preserve readback in resumed runs; bind tool execution to schemas declared for the current turn; share overflow retry budget; identify real user goals and the entire protected round; reject invalid pagination; keep error messages on their active branch and maintain timeline order; label controls and correct documentation.
- **Validation**: Exercise resumed runs, same-turn tool load, empty stream overflow, asset views, steering, stale branches, fractional pagination, accessibility and event ordering; run focused suites and pre-push checks. Roll back individual changes by reverting their commits without altering saved conversation records.
- Verification: after correcting the test fixture, 150 focused backend tests passed and Ruff passed; a worker tool-loading smoke scenario exposed `read_tool_result` for a recovered complete tool exchange. Frontend focused tests: 95 passed; TypeScript and ESLint passed. No browser session was started for this review pass.

### Stage 10: Review Follow-ups
- **Files modified**: tool discovery and Agent pause/recovery services, chat hook, relevant behavior tests, and changelog.
- **Specific logic**: Keep bounded discovery searches useful for late query terms and CJK suffixes; preserve the original model-response tool visibility across pauses; prevent errors from an edited-away branch from returning; make checkpoint ordering regression meaningful.
- **Validation**: Exercise long and mixed queries, pause/replay with newly loaded tools, edited-branch reloads, and ordering. Run focused tests and pre-push gates; no browser or service startup. Revert individual commits if recovery or search behavior regresses.
- Verification: after reassessing the recovery control flow, 144 focused backend tests passed, including replay and approval coverage; 72 frontend hook tests passed, as did Ruff, ESLint and TypeScript. Search smoke checks found both a long CJK suffix and a later query keyword. No browser or application service was started.

### Stage 11: Resume Snapshot and Search Review
- **Files modified**: Agent loop and worker, tool discovery, affected backend and frontend behavior tests, changelog.
- **Specific logic**: Bind pending calls to the actual submitted tool schemas after retries and across discovery transitions; allow only authorized core tools for legacy missing snapshots. Deduplicate CJK search terms within the existing budget and strengthen boundary tests.
- **Validation**: Exercise streaming and nonstream retries, legacy and discovery-transition resumes, worker reconstruction, repeated CJK input and chat history. Run focused tests and pre-push gates; do not start services or browsers. Revert the specific change if authorization or resume behavior regresses.
- Verification: 166 focused backend tests and 56 frontend hook tests passed; Ruff and frontend ESLint passed. A search smoke check retained the calendar bigram after repeated CJK input. No application services or browsers were started.

### Stage 12: Review Corrections
- **Files modified**: run store, checkpoint and discovery services, chat history query and database index configuration, chat hook and message renderer, targeted tests, user guides and changelog.
- **Specific logic**: Preserve concurrent checkpoint writes without restoring consumed resume fields; hash the model-visible result consistently; keep requested tools accurately represented after eviction. Preserve recovered failure messages, distinguish actual history omission, and constrain indexed compression-event retrieval.
- **Validation**: Exercise repeated pauses, JSON tool checkpoint versions, capacity-bound discovery, failed-run reloads and both fallback types; verify history retrieval and database index behavior. Run focused backend and frontend tests and smoke checks without starting services or a browser. Revert the relevant changes if recovery or history behavior regresses.
- Verification: 165 focused backend tests and 122 frontend tests passed; Ruff, TypeScript and ESLint passed. SQLite ORM tests exercised pause persistence and compression-event history; a direct JSON rendering smoke check confirmed checkpoint hash input. No service or browser was started; existing PostgreSQL indexes require the documented concurrent upgrade step.

### Current verification and open items
- Backend full suite: 10,910 passed, 4 skipped; line coverage 96.75%, branch coverage 95.02%. Frontend full suite: 3,264 passed; function coverage 95.45%, line coverage 97.72%. Results predate any subsequent edits.
- Browser verification used a temporary private Agent and a 10,000-token model configuration. The run completed, persisted a `readback_only` checkpoint covering 11 results, and executed nine `read_tool_result` calls; the temporary Agent and model were removed. Semantic checkpoint creation and provider-side overflow retry were not observed in this run.
- Retained browser run `f5cc071b-fd51-437a-b715-b2577e16937c` completed with a `readback_only` checkpoint covering 10 results; 9 model requests contained omission markers. Live UI showed compaction with incorrect zero saved tokens, subsequently corrected. New compression events are persisted with the run and restored on history reload; earlier events without persisted diagnostics cannot be reconstructed.
- Provider overflow retries reduce only provably unprotected assistant text or optional tool schemas, before any streamed chunk, with a bounded retry count. Active-round semantic checkpoints summarize complete tool groups, bind source hashes, retain original records and survive approval pauses.
- Durable visibility changes: 151 backend and 134 frontend targeted tests passed; frontend TypeScript and ESLint and backend Ruff passed. After restarting API and worker, browser verification covered the cases below.
- Browser run `cde0fa3f-363b-4432-bbec-0fa8dfd915ed` completed and, after refresh and expanding the execution timeline, displayed persisted compression events including 8502 → 7691 tokens. A normal new chat displayed its live response.
- Real invalid credentials now classify as `AuthenticationError` and display “API Key 无效” in the chat. A history reload could omit the failed assistant message; the frontend preserves the current persisted-ID error message during reload. A focused regression test, ESLint and TypeScript passed.
- Checkpoint reuse computes pressure from verified restored entries. Real run `43d4f1d1-ec99-4bdc-b9ed-878036c80c14` completed with 16 tool calls and 9 compression events, versus 8 in the prior 16-tool run; different model outputs prevent an isolated frequency comparison. New event before-values ranged 8,238–8,933, with 7,646–7,964 after; the 8,000 input budget leaves little headroom. The first checkpoint reported a branch-version mismatch and was not persisted; later checkpoints persisted readback-only. Request trajectory comparison showed earlier message changes in nine compression transitions, so no provider-cache improvement is established. Semantic-summary extension and provider cache hits remain unverified.

## Testing Strategy

Cover long history, first-turn repeated tools, parallel protocol pairing, failed summary, irreducible inputs, disabled compression, estimated model limits, model overflow, authorization and raw-result recovery. Verify no duplicate side effects across retry, approval and worker recovery. Run full suites and an actual browser flow with live application dependencies.

## Risks & Mitigation

Compression is lossy: preserve references and make omissions explicit; do not infer expendable fields of unknown tools. Provider tool and reasoning protocols differ: validate complete exchanges and avoid unsafe edits. Tool discovery can miss needed capabilities: offer repeated discovery without weakening authorization. Estimates can differ from provider counts: conservative margins and bounded safe retries, never replay completed operations. Large requests cannot always fit: return actionable errors rather than discard user instructions. Roll back by reverting this feature's commits; preserve original stored messages and existing configuration semantics.
