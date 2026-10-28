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

## Testing Strategy

Cover long history, first-turn repeated tools, parallel protocol pairing, failed summary, irreducible inputs, disabled compression, estimated model limits, model overflow, authorization and raw-result recovery. Verify no duplicate side effects across retry, approval and worker recovery. Run full suites and an actual browser flow with live application dependencies.

## Risks & Mitigation

Compression is lossy: preserve references and make omissions explicit; do not infer expendable fields of unknown tools. Provider tool and reasoning protocols differ: validate complete exchanges and avoid unsafe edits. Tool discovery can miss needed capabilities: offer repeated discovery without weakening authorization. Estimates can differ from provider counts: conservative margins and bounded safe retries, never replay completed operations. Large requests cannot always fit: return actionable errors rather than discard user instructions. Roll back by reverting this feature's commits; preserve original stored messages and existing configuration semantics.
