# Implementation Plan

## Active

- **agent-context-compression-ratio-thresholds** — In progress. Upgrade agent context compression from hard-budget-only behavior to staged context governance with ~80% proactive compaction, selective micro compaction, richer compression observability, and a Phase 2 Session Memory / SM Compact roadmap. See `docs/plan/agent-context-compression.md`
  - [x] 1. Ratio-based thresholds and pressure states
  - [x] 2. Selective micro compaction
  - [x] 3. Compression observability and frontend messaging
  - [x] 4. Phase 2 Session Memory / SM Compact design hooks

- **agent-manual-stop-state** — Complete. Persisted manual stop state for interrupted agent replies so the current UI and reloaded history both show a stable stopped marker. See `docs/plan/agent-manual-stop-state.md`
  - [x] 1. Backend persisted stop state
  - [x] 2. Frontend stop finalization
  - [x] 3. History rendering and verification

## History

- **agent-context-compression** — Complete. Added shared agent context compression for non-stream, stream, and regenerate flows, with agent-level compression config and frontend-visible compression SSE events.

- **agent-chat-parity** — Aligned non-streaming agent chat request semantics with the streaming path for file parsing, vision inputs, history overrides, user-input-request prompting, and tool metadata/timeouts.

- **backend-babel-i18n-migration** — Introduced a Babel-backed backend i18n runtime with compatibility fallback so existing `t()`, `msg_key`, `BusinessError`, and `ResponseCode` flows stayed compatible during migration.
