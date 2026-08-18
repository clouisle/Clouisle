# Three-Level Agent Context Compression Redesign Design Document

## Background & Goals

Clouisle currently combines request-time file trimming, session-memory compaction, selective tool-result compaction, deterministic macro summaries, model-generated context checkpoints, emergency fallback, and reactive retry. The mechanisms operate on different representations of history and have mutually exclusive gates. In particular:

- `working_history_override` bypasses checkpoint loading and generation during an active tool loop.
- `_split_turn_blocks` groups all tool iterations under one user message, so a single research request can become one uncompressible block.
- Protected tool-call rounds prevent current tool results from being compacted.
- Macro compaction only summarizes old blocks; it cannot reduce a single large active block.
- Emergency fallback claims to keep only system and user messages but re-adds protected assistant/tool messages, so it can still exceed the hard budget.
- Session memory is generated asynchronously after successful replies and cannot rescue the request that created the overflow.

Observed failures include a 32K model with a 27K input budget accumulating roughly 38K tokens inside one user request after multiple web-search iterations, and a 10K model whose system prompt alone consumed nearly the entire input budget.

### Goals

1. Guarantee that request-time context preparation either returns a model-ready message list at or below the hard input budget or returns a precise, recoverable error.
2. Separate current active-tool growth from historical conversation compaction.
3. Make the active tool loop bounded before the next provider call, not after the request has already failed.
4. Adopt Pi-style between-turn compaction: valid cut points, structured incremental summaries, persistent watermarks, and suffix reconstruction.
5. Preserve tool-call/tool-result protocol validity, active-branch semantics, edits, regeneration, and media/file behavior.
6. Reduce overlapping compression decisions and make compression actions observable and predictable.

### Non-goals

- Do not delete or rewrite original `messages` rows.
- Do not use a character-only `chars / 4` estimate for Chinese-heavy or provider-specific contexts.
- Do not use session memory as a substitute for the current-request compaction path.
- Do not add a second unbounded summarizer retry loop.
- Do not change model selection, provider request semantics, or tool authorization.

## High-Level Design

The final pipeline has one budget controller and three compression layers:

```text
Budget plan and message segmentation
    |
    +-- L1: always-on token-bounded content normalization
    |
    +-- L2: active tool-loop rolling compaction before the next model call
    |
    +-- L3: between-turn historical compaction after a completed Agent round
    |
    +-- protocol-safe recovery if the hard budget is still exceeded
```

`ConversationSessionMemory` remains a separate optional semantic-memory segment. It is generated asynchronously after successful assistant replies and has its own fixed budget; it is not an emergency compression stage.

### L0: Budget contract and message segments

Create a single budget/plan representation containing:

- resolved model context limit and tokenizer metadata;
- output reserve and safety margin;
- hard input budget;
- proactive target budget and keep-recent token budget;
- per-segment token estimates and reduction provenance.

Segment messages into `system`, optional system sections, historical checkpoint, historical turns, current user, active tool rounds, tool results, reasoning, and media. The invariant is strict: a successful prepared context must not exceed `input_budget`.

### L1: Always-on bounded normalization

Before messages are appended to an active history or sent to a model, enforce token-aware caps for uploaded file content, web/tool results, reasoning, and other optional content. Truncation changes only content payloads and preserves tool-call IDs, tool-call declarations, and result pairing. Tool results receive both per-result and active-window budgets so one search response cannot consume the entire context.

### L2: Active tool-loop rolling compaction

After every tool batch and before the next provider call, split the current execution into completed tool iterations and the pending/current iteration. If the projected context exceeds the active target, replace older completed iterations with a bounded deterministic or model-generated progress summary while retaining the current user message, the latest valid tool-call/tool-result pairs, and any unfinished tool state. This state is request-local and does not create a historical checkpoint.

### L3: Between-turn historical compaction

Run only at a safe boundary after a terminal Agent round, or before a new user message is added. Read completed active-branch rounds after the existing checkpoint watermark, choose a valid cut point from the newest side using `keep_recent_tokens`, summarize the old prefix, and persist one monotonic checkpoint. The next request renders the checkpoint summary followed by the raw suffix and the new user message. The active tool round is never included in the historical prefix.

The primary cut-point policy keeps complete `round_id` groups. A later split-turn extension may permit an assistant cut point only when all required tool results remain in the retained suffix and a separate `turn_prefix_summary` is stored.

### Structured incremental summary

The summary contract uses stable structured fields:

```text
Goal
Constraints & Preferences
Progress: Done / In Progress / Blocked
Key Decisions
Next Steps
Critical Context
Tool State
Important Artifacts
Open Questions
Latest User Intent
```

If a previous checkpoint exists, the summarizer receives the previous structured payload and only the newly covered transcript. Transcript entries are bounded before the summarizer call; reasoning is excluded; IDs, paths, URLs, tool conclusions, and unfinished work are retained. A summary is accepted only when it is valid and smaller than the covered prefix.

### Persistence and reconstruction

Reuse `ConversationContextCheckpoint` as the persisted compaction entry. Keep the original message rows unchanged. Store the covered watermark, summary text/payload, token metrics, summarizer metadata, and split-turn metadata when needed. Validate the watermark against the active branch before use; stale checkpoints are ignored and marked stale. `history_override` becomes an active-round delta layered on top of historical checkpoint/suffix state instead of a complete-history bypass.

### Recovery and retry

Recovery first removes optional system sections, shrinks summaries, reduces retained active-tool state, and rebuilds a protocol-valid context. It must not blindly re-add every protected message. If no valid context can fit, return a structured context-budget error containing budget, actual tokens, segment totals, and reduction actions. Provider retry is retained only for the case where the local plan fits but the provider reports a context error; it must not repeat an unchanged over-budget preparation.

## Implementation Plan

### Stage 1: Establish budget contract and observability

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - `backend/app/services/chat_sse.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/schemas/agent.py`
  - `backend/tests/services/`
  - `backend/tests/api/`
- **Specific logic**:
  - Introduce a plan/segment dataclass or equivalent internal contract without changing public message schemas.
  - Centralize hard, target, and keep-recent budgets.
  - Record model/context metadata, segment token totals, protected/active-tool totals, actions, and final token count.
  - Define the success invariant and a typed structured failure for unrecoverable contexts.
  - Preserve provider-specific token counting and add a conservative fallback for unmapped model/tokenizer combinations.
- **Validation**:
  - Unit-test budget calculations and pressure boundaries.
  - Reconstruct the known 32K failure and verify diagnostics identify the active-tool segment as the dominant source.
  - Confirm successful preparation never returns a context above the hard budget.

### Stage 2: Implement always-on bounded content normalization

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - `backend/app/llm/tools/builtin/web_search.py`
  - relevant chat tool/result helpers
  - `backend/app/schemas/agent.py` if Agent-level limits are exposed
  - `backend/tests/services/test_chat_context_file_uploads.py`
  - tool/context regression tests
- **Specific logic**:
  - Add token-aware per-file, per-tool-result, and active-tool-window limits.
  - Normalize web-search output to bounded title/URL/snippet/answer content.
  - Preserve tool-call IDs, tool declarations, result pairing, media references, and error status.
  - Apply the same limits to `history_override` and database-rebuilt history.
  - Keep reasoning trimming deterministic and priority-based.
- **Validation**:
  - Large web-search and file payloads are bounded before the next model call.
  - Tool protocol fields remain unchanged and paired.
  - Chinese-heavy content does not pass through an unsafe character-only estimate.

### Stage 3: Implement active tool-loop rolling compaction

- **Files modified**:
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/services/chat_context.py`
  - new focused `backend/app/services/context_compaction.py` if extraction reduces coupling
  - streaming, non-streaming, edit, and regenerate tests
- **Specific logic**:
  - Replace the raw `working_history_override`-only decision path with an active-round state that tracks completed iterations, pending tool calls, summaries, and token totals.
  - Run L1 after every tool batch.
  - When projected tokens exceed the active target, compact completed iterations while preserving the current user and a valid latest tool sequence.
  - Use deterministic progress summaries first; optionally call a bounded summarizer when deterministic reduction is insufficient.
  - Ensure the active summary is request-local and does not become a normal user-visible message.
  - Do not invoke historical checkpoint generation on incomplete active rounds.
- **Validation**:
  - Reproduce the 32K conversation: the third provider call receives a context within the 27K input budget and no duplicate context-length retry occurs.
  - Run multi-iteration tool-loop tests with large, small, failed, and media-producing tools.
  - Assert no orphan tool results, orphan tool calls, or invalid message ordering.
  - Verify stream, non-stream, edit, and regenerate paths use the same active-round policy.

### Stage 4: Implement Pi-style between-turn historical compaction

- **Files modified**:
  - `backend/app/services/context_checkpoint.py`
  - `backend/app/services/chat_context.py`
  - `backend/app/services/message_branching.py` where watermark/candidate helpers require alignment
  - `backend/app/models/agent.py` only if split-turn metadata needs a column; prefer existing payload storage first
  - `backend/tests/services/test_context_checkpoint.py`
  - `backend/tests/services/test_chat_context_compression.py`
- **Specific logic**:
  - Trigger only after a terminal round or before a new user message, using a high-water threshold and low-water target.
  - Read only active-branch completed rounds after the current checkpoint watermark.
  - Find valid cut points from newest to oldest using token accumulation and `keep_recent_tokens` rather than a fixed number of blocks.
  - Never cut at a tool result; keep complete round groups by default.
  - Generate structured incremental summaries using the previous checkpoint payload and bounded transcript.
  - Persist the summary and watermark monotonically under a per-conversation lock.
  - Add split-turn prefix handling only where complete-round cutting cannot satisfy the keep budget.
  - Rebuild context as summary plus retained suffix; do not use `history_override` to bypass the checkpoint.
- **Validation**:
  - Short history produces no checkpoint.
  - A long multi-turn history creates one checkpoint and reduces to the target utilization.
  - A subsequent compaction updates the existing summary incrementally rather than re-summarizing all history.
  - Cut points never split a tool-call/tool-result pair.
  - Branch switching, edit, and regenerate mark invalid checkpoints stale and rebuild from the active branch.
  - Summary timeout, malformed JSON, non-beneficial summary, and provider failure preserve the previous checkpoint and use deterministic fallback.

### Stage 5: Rebuild context assembly and retire overlapping paths

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/services/session_memory.py`
  - `backend/app/api/v1/endpoints/chat_sse.py`
  - `backend/app/schemas/agent.py`
  - existing compression tests and implementation index
- **Specific logic**:
  - Compose context from historical checkpoint, retained suffix, active-round state, and current user rather than choosing between database history and `history_override`.
  - Keep `ConversationSessionMemory` as optional semantic memory with an independent fixed budget.
  - Remove or deprecate duplicate request-time macro/session-memory paths once the new layers are proven.
  - Replace the current emergency fallback with protocol-safe recovery and accurate error details.
  - Restrict reactive retry to local-fit/provider-rejection cases.
  - Preserve compression SSE event names while exposing actual level, action, before/after tokens, and segment metrics.
- **Validation**:
  - All Chat paths—streaming, non-streaming, edit, regenerate, and embed where applicable—use the same context planner.
  - No stale `history_override is None` gate prevents historical checkpoint use.
  - Existing session-memory extraction remains asynchronous and does not block current context preparation.

### Stage 6: Rollout, regression, and cleanup

- **Files modified**:
  - `backend/tests/api/`
  - `backend/tests/services/`
  - `backend/tests/llm/`
  - `docs/IMPLEMENTATION_PLAN.md`
  - this design document
- **Specific logic**:
  - Add a feature gate for the new planner during rollout.
  - Compare old and new token/action metrics on representative short chats, long chats, tool-heavy research chats, file chats, image chats, and branch edits.
  - Remove dead configuration and old fallback code only after the new planner is the default and rollback evidence is complete.
- **Validation**:
  - Targeted backend tests, full backend suite, coverage gate, and Ruff.
  - Read-only reproduction of the previously failing 10K and 32K conversations.
  - Verify no provider request is made with a locally over-budget message list.
  - Record before/after token usage, compaction latency, summary failures, and protocol validation results.

## Testing Strategy

### Happy paths

1. Short conversation: no compression and no compression SSE.
2. Long completed history: one valid cut point, structured summary, retained recent suffix.
3. Incremental checkpoint: previous summary plus only new covered rounds.
4. Tool-heavy request: L1 limits results and L2 compacts completed iterations before the next provider call.
5. File and image context: attachments remain usable while oversized text is bounded.
6. Branch-aware history: active checkpoint and suffix reconstruct the selected branch only.

### Error paths

1. Summarizer timeout or malformed output: deterministic bounded fallback.
2. Summary not smaller than prefix: checkpoint is not written.
3. No valid cut point: active-round compaction or structured unrecoverable error.
4. Provider context error after local fit: one stricter retry only.
5. Provider context error while local plan is over budget: no unchanged retry; invoke recovery/error path.
6. Concurrent checkpoint writers: newer watermark wins.
7. Protected tool-call sequence: no orphan or reordered tool messages.

### Regression scope

- Streaming Agent chat.
- Non-streaming Agent chat.
- Regenerate and edit active branches.
- Tool execution and multi-iteration research flows.
- File, image, RAG, and asset-manifest context.
- Session-memory asynchronous extraction.
- Compression SSE and frontend compatibility.
- Model metadata and tokenizer selection.

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| Summary loses a required fact | Structured schema, incremental previous summary, recent raw suffix, artifact/tool-state fields, and summary-benefit validation |
| Tool protocol becomes invalid | Cut only at validated boundaries; compact content rather than IDs; explicit message-sequence tests |
| Active summary loses useful research detail | Keep recent completed iterations raw, retain URLs/key findings, and cap rather than erase current tool state |
| Summary model adds latency/cost | High/low-water hysteresis, bounded transcript, one summary call per checkpoint, and deterministic fallback |
| Tokenizer estimate differs from provider | Resolve provider/model metadata, use provider-specific tokenizer mappings, and retain conservative safety margin |
| Checkpoint becomes stale after edits/branches | Watermark active-branch validation and monotonic persistence |
| New planner regresses existing paths | Feature gate, path-complete tests, staged rollout, and retain old path until evidence is recorded |
| System prompt itself consumes most of a small context window | Surface prompt-budget diagnostics and require a larger model or shorter optional system sections; do not silently truncate user-authored instructions |

## Rollback Plan

Keep the old request-time path behind a feature gate until the new planner passes the active-tool and branch regression matrix. If rollout fails, disable the new planner, retain original messages and existing checkpoint rows, and revert to the prior deterministic/session-memory path. Checkpoint data is additive and must not be required for message persistence or conversation rendering.
