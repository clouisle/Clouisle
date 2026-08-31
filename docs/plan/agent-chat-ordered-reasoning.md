# Ordered Agent Reasoning Timeline
**Status: Complete — Stage 9 keeps tasks and tool executions inside each collapsible ChainOfThought and makes its header identify the current operation.**

## Background & Goals

The Agent chat renderer currently loses chronology at the presentation layer. `frontend/hooks/use-chat.ts` can store several reasoning segments, but it groups adjacent tool calls into `tool-group` segments, synthesizes RAG/generating tasks outside the event list, and attaches results back to a group. `frontend/components/chat/message.tsx` then removes reasoning/tasks/tool results from the body, renders one global `ChainOfThought` before all text, and renders the remaining text afterward. A stream such as reasoning A → text A → tool A → reasoning B → text B therefore appears as one thought panel followed by text.

The target is an ordered Agent timeline:

```text
RAG/task (when emitted) → reasoning A → text A → tool A → reasoning B → text B
```

Every reasoning process must have its own visible/collapsible block, and tool execution cards must stay at the occurrence where their call was received. Live streaming, reconnect replay, finalized/error/stopped messages, and loaded conversation history must use the same ordering rule.

### Assumption and explicit boundary

One reasoning process means one Agent model iteration (`reasoning_start`/`reasoning_end`). The existing backend already emits one pair per tool-loop iteration and durable persistence orders non-canonical assistant/tool rows by `round_index`; no backend protocol or database migration is needed for this contract. Within one provider response, the persisted model currently stores scalar `reasoning_content`, `content`, and `tool_calls`, so exact token-level ordering such as reasoning → partial text → reasoning after a page reload remains outside this change. If that finer-grained replay is later required, it needs a separate ordered-event/parts persistence design.

Tool call plus its result remains one execution card, anchored at the call position. This removes aggregation of distinct calls/reasoning blocks without creating duplicate result cards or regressing rich media/artifact output handling. The public `Message`/`ChatContainer` open-state props remain compatible; when a message-level controlled state is supplied it opens/closes all of that message's reasoning blocks together, while each block is still a separate DOM component and has its own uncontrolled state otherwise.

## High-Level Design

- Treat the stream segment list as the canonical presentation order. A tool occurrence owns exactly one tool call and, when available, its matching result; duplicate `tool_call` updates merge into that occurrence in place and never create a second occurrence.
- Add RAG and generating task transitions to the same ordered segment list at the event that starts them. Compression already follows this pattern. Aggregate `taskState` remains for lifecycle/fallback checks, but is no longer used to prepend/append visual tasks.
- Keep each reasoning start as a new segment and update it by its recorded reasoning index. Do not use a message-global reasoning bucket for rendering.
- Build `Message.parts` by one ordered segment walk, retaining source documents as the existing citation footer. Reconnect seeding and terminal finalization must use the same segment representation.
- Render assistant parts with one chronological walk. Each reasoning iteration owns one collapsible `ChainOfThought` whose content keeps its task and tool nodes together; ordinary/final text remains in the normal message surface. Use existing `ChainOfThoughtStep` and `Tool` primitives plus `TextWithCitations` and the current media/user-input/error renderers. Do not adopt the legacy `message-parts/ReasoningContent` or `ToolContent` components in this change because the current message renderer owns richer media/artifact result handling.
- Keep `hideReasoning` independent from `hideToolCalls`; hiding the reasoning panels must not accidentally hide visible tools.

## Implementation Plan

### Stage 0: Register the approved feature plan

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/agent-chat-ordered-reasoning.md`
- **Specific logic**: During implementation (not during this read-only plan), add the feature index/checklist and copy this design into the repository's required complex-task planning files. Mark stages as they complete.
- **Validation**: Confirm the index links the detailed plan and checklist status matches the implementation.

### Stage 1: Make live/reconnect stream state occurrence-ordered

- **Files modified**: `frontend/hooks/use-chat.ts`
- **Specific logic**:
  1. Replace the internal multi-call `tool-group` representation with a per-occurrence tool segment (one normal or MCP call plus optional matching result). Keep `mergeToolCall` for initial/complete argument updates and preserve a terminal `done`/`error` state. A duplicate ID updates the existing segment in place; adjacent different IDs always get different segments.
  2. Attach a result to its matching call occurrence without moving that occurrence. Provide a deterministic orphan-result fallback for malformed/replayed event sequences instead of dropping the result; normal call-before-result streams remain atomic call/result output.
  3. On `rag_start`, append a running RAG task segment; on `rag_context`, update the latest RAG task in place (or create a completed task at that event position when no start was received). On the first content transition, append the generating task at that position rather than synthesizing it at the end. Preserve repeated compression task occurrences and their start/end positions.
  4. On each `reasoning_start`, append a fresh reasoning block and segment, recording one start time. Route deltas and end/finalization updates through `currentReasoningIndex` and its corresponding segment so multiple blocks cannot overwrite one another. Keep the existing duration calculation and terminal cleanup behavior.
  5. Replace the global text/user-input XML filter-rebuild with a segment-local transformation. When a complete `<user_input_request>` is found, split/clean only the current text segment and insert the request immediately after that cleaned text; never filter/reappend all earlier text, reasoning, or tools.
  6. Update `createAssistantStreamStateFromParts` to seed all ordered task/reasoning/tool occurrences from persisted parts without grouping, and update `buildMessageParts`, `hasRenderableStreamingProgress`, and `finalizeStreamingState` for the new segment shape. Remove the old RAG/generating prepend/append path while continuing to append citation source parts only after a non-streaming response.
  7. Keep all `renderSession`, stop, error, regenerate, edit, and durable reconnect callsites using the same builder; no separate ordering path is allowed.
- **Validation**: Focused hook tests must prove two reasoning start/delta/end cycles, duplicate tool argument updates, terminal-state preservation, task placement, XML split handling, and exact part order both while streaming and after finalization/error/stop.

### Stage 2: Align persisted-history reconstruction with the supported order

- **Files modified**: `frontend/lib/utils/message-converter.ts`
- **Specific logic**:
  1. Preserve backend round order when reconstructing assistant step traces. Sort deterministically by `round_index`, then the backend timestamp/original index tie-breaker rather than relying on a global result map's insertion behavior.
  2. Process each assistant step in order as reasoning → step text → its tool-call occurrences, and attach each corresponding tool result to that call occurrence. Use occurrence-aware queues/reverse-nearest matching so repeated or per-tool persisted rows cannot overwrite one another.
  3. Keep the final canonical reasoning/text after all non-canonical steps, preserve media-result conversion at the tool execution position, and retain the legacy flat `tool_calls` compatibility path and existing RAG-source footer behavior.
  4. Do not add a database `parts` column or alter backend schemas; document the iteration-level persistence boundary in the plan.
- **Validation**: Existing ordered-step, per-step-duration, and created-at-duration tests remain green; new fixtures assert two assistant reasoning rounds and multiple tool calls/results reconstruct in exact round order, including the final answer and legacy flat payloads.

### Stage 3: Replace the global thought panel with an ordered assistant renderer

- **Files modified**: `frontend/components/chat/message.tsx`
- **Specific logic**:
  1. Retain source collection, attachment handling, copy/speech/actions, and error/stopped boundaries, but stop partitioning reasoning/tasks/tool calls into a separate global chain for display. Preserve each part's original index while walking non-source parts.
  2. Render every reasoning part at its original index in its own `ChainOfThought` instance with per-part streaming state, duration label, and only that part's text in its content. Forward the existing optional message-level open/callback props consistently to all instances; use stable occurrence/index keys, never text or labels.
  3. Render task parts at their original locations (RAG, compression, generating) as the existing status-step presentation, skipping only the intentionally unsupported `thinking` task as before. Do not force RAG to the front or generating to the end.
  4. Render each normal/MCP tool call at its original location with the current rich `Tool`/`ToolInput`/`ToolOutput` and media/artifact handling. Pair only that call's result; do not search in a way that lets another occurrence's result replace it. Keep call/result as one execution card anchored at the call.
  5. Keep ordinary text, media, user-input requests, truncation, and other visible parts in the same walk using existing renderers. Continue placing citation sources in the existing footer and stopped/error/action controls at message-level positions.
  6. Make `hideReasoning` suppress reasoning/task timeline items only and make `hideToolCalls` suppress tool calls/results only. A message with reasoning plus `hideReasoning` must still show tools unless `hideToolCalls` is true. Preserve custom `renderPart` behavior for ordinary parts and original indexes.
  7. Recompute loading/standalone-error/action predicates from the ordered visible timeline rather than from the old global-chain/content split. Remove `buildChainOfThoughtSteps`, its forced category ordering, and now-unused aggregation-only imports/helpers.
- **Validation**: Static and mounted message tests assert two separate reasoning blocks, alternating reasoning/text/tool/reasoning/text DOM order, repeated identical reasoning text rendered twice, task positions, normal/MCP tool states and rich outputs, independent hide flags, loading/error behavior, and action/after-content placement.

### Stage 4: Update focused regression coverage

- **Files modified**: `frontend/hooks/use-chat.test.ts`, `frontend/hooks/use-chat.test.tsx`, `frontend/hooks/use-chat-issue255.test.ts`, `frontend/lib/utils/message-converter.test.ts`, `frontend/components/chat/message.test.tsx`
- **Specific logic**:
  - Replace the `groups reasoning tools and maps task and tool states` expectation with an ordered-timeline contract. Assert exact relative positions rather than only membership or global category order.
  - Add a live stream fixture with reasoning A → text/tool activity → reasoning B → text B and assert two reasoning parts, one occurrence per distinct tool ID, correct completion/error states, and no reordering after `message_end`.
  - Extend duplicate/slow-argument tests to prove an update changes the existing call in place and never groups a different adjacent call; cover a result arriving after an intervening segment and the orphan fallback.
  - Add RAG-start and first-content assertions proving task segments are emitted where events occur; preserve source-document footer assertions.
  - Add reconnect/replay coverage with two reasoning cycles so `createAssistantStreamStateFromParts` and durable event application produce the same sequence.
  - Add converter fixtures for multiple persisted assistant steps, multiple tool results, per-step durations, final canonical content, and flat legacy tool fields.
  - Add message DOM-order tests for repeated reasoning labels and for reasoning hidden/tool visible. Update test mocks only for the primitives/attributes actually used by the new ordered renderer.
- **Validation**: Run the focused files after each stage; failures must identify a violated ordering invariant rather than be weakened to membership-only assertions.

### Stage 5: Full verification and cleanup

- **Files modified**: Only files required by failing checks; remove imports/helpers made obsolete by the cutover. No backend source changes unless a test demonstrates the explicit persistence boundary was misread.
- **Specific logic**: Run frontend type/lint/i18n/coverage gates and the existing backend stream/durable smoke tests. Review the diff for stale `tool-group`, global ChainOfThought aggregation, forced RAG/generating placement, and comments describing the old behavior. Do not start a browser or application service; DOM/server-render tests provide the surface verification available under repository rules.
- **Validation commands**:
  - `cd frontend && bun test hooks/use-chat.test.ts hooks/use-chat.test.tsx hooks/use-chat-issue255.test.ts lib/utils/message-converter.test.ts components/chat/message.test.tsx`
  - `cd frontend && bunx tsc --noEmit && bun run lint && bun run i18n:lint`
  - `cd frontend && bun run test:coverage && bun run coverage:check` (the repository's frontend coverage gate)
  - `cd backend && uv run pytest tests/api/test_chat_sse_triptych_issue255.py tests/api/test_chat_stream_loop_arcs_issue255_companion.py tests/services/test_agent_run_durable.py tests/services/test_agent_loop_behavioral_smoke.py -q`
  - Run the repository's normal pre-commit/diff checks only after focused behavior is green.
- **Observed**: Focused isolated frontend tests passed (101 tests across 5 files), full frontend coverage passed (2275 tests across 515 files), LCOV coverage completeness passed for 489 eligible files, TypeScript and translation lint passed, ESLint passed with two pre-existing warnings, diff check passed, and the backend stream/durable smoke suite passed (17 tests). The repository pre-commit command was unavailable in the environment (`pre-commit` was not installed; `uv run pre-commit` also could not spawn it).
### Stage 6: Nest tool-call nodes inside the collapsible thought process (superseded)

- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/message.test.tsx`, and only the related test mocks if required.
- **Specific logic**:
  1. Keep the received order and each reasoning iteration boundary, but group contiguous internal process entries (tasks, reasoning, and tool executions) under a collapsible `ChainOfThought` container. Ordinary/final answer text remains outside the container and retains its original position.
  2. Render each tool call/result pair as a compact tool node inside the thought content. The existing `Tool` header remains the per-node disclosure control, so the thought container hides all nodes while closed and tool parameters/results stay closed until that node is opened.
  3. Keep tool status, MCP naming, rich outputs, media/artifact handling, independent hide flags, and controlled message-level thought state unchanged.
- **Validation**: Mounted/static message tests prove tool nodes are descendants of the thought process, tool details remain independently collapsible, final text is outside the thought container, and chronological order plus existing rich-output/state assertions remain intact.

- **Observed**: Focused isolated frontend suite passed (102 tests across 5 files), the full frontend coverage suite passed (2276 tests across 515 files), LCOV completeness passed for 489 eligible files, TypeScript passed, ESLint passed with two pre-existing warnings, translation lint passed, diff whitespace checks passed, and the backend stream/durable smoke suite passed (17 tests). The standalone `pre-commit` executable is unavailable, but the repository commit hook passed.

### Stage 8: Separate reasoning, execution, and answer surfaces (superseded by Stage 9)

- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/message.test.tsx`, and only the related test mocks if required.
- **Specific logic**:
  1. Keep one `ChainOfThought` container per reasoning part only. Its content contains only that reasoning text; task and tool entries must never be placed inside it.
  2. Render RAG, compression, and generating entries as standalone task status rows using the existing task primitive, preserving their timeline index and state.
  3. Render each normal/MCP tool call and its matching result as a standalone execution card at the call position. Keep tool input/result disclosure independent from reasoning disclosure.
  4. Leave ordinary and final answer text in the regular message content surface so users can immediately distinguish model output from internal activity.
  5. Preserve chronological order, controlled reasoning open-state semantics, independent hide flags, rich tool output/media/artifact handling, and existing loading/error/action behavior.
- **Validation**: Mounted/static message tests assert that reasoning containers contain no task/tool nodes, task and tool nodes are siblings at their original positions, final text remains outside reasoning containers, and hide flags plus rich tool states continue to work.
- **Observed**: Focused message/task/chat-container regressions passed; the isolated frontend suite passed (2277 tests across 515 files); frontend coverage and LCOV completeness passed; TypeScript, ESLint, translation lint, and diff checks passed; the backend stream/durable smoke suite passed (17 tests). No application service or browser was started.

- **Acceptance**: Live and historical Agent messages display each reasoning iteration and tool execution in chronological order; no distinct reasoning/tool occurrences are collapsed; hide flags and rich tool results retain their existing contracts; all focused and required gates pass.

### Stage 9: Keep activity nested and label the current operation

- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/message.test.tsx`, and the implementation-plan documents.
- **Specific logic**:
  1. Keep task status rows and normal/MCP tool execution cards inside the surrounding collapsible `ChainOfThought`; do not expose them as sibling surfaces.
  2. Preserve one thought container per reasoning iteration and the existing chronological grouping, tool/result pairing, rich output handling, hide flags, and controlled open-state behavior.
  3. Derive the `ChainOfThought` header from the latest task or tool action, using localized task text and the tool display name/server path, while retaining the duration fallback for reasoning-only groups.
- **Validation**: Message tests assert task/tool descendants, independent tool disclosure, chronological grouping, and action-specific thought headers such as the active tool name and compression task text.
- **Observed**: The corrected message renderer passed 41 focused tests; the full frontend suite passed (2277 tests across 515 files), frontend coverage and LCOV completeness passed for 489 eligible files, TypeScript, ESLint, translation lint, and diff checks passed, and the backend stream/durable smoke suite passed (17 tests). No application service or browser was started.

- **Acceptance**: Tool and task details remain inside the collapsible thought process, while its header text tells users which operation the Agent is performing.

## Testing Strategy

### Happy paths

- Two or more tool-loop iterations, each with reasoning, tool execution, and a later reasoning block.
- Text before and after tools, multiple adjacent distinct tools, shared/concurrent tool results, RAG and compression events, media results, and final answer text.
- Reloaded history with ordered `steps`, final canonical fields, and per-step duration reconstruction.

### Error and boundary paths

- Tool call starts with `{}` then receives full arguments; duplicate update after a result must not regress `done`/`error`.
- Tool execution error, missing/orphan result, stream close without terminal event, manually stopped/error-preserved progress, and iteration-cap markers.
- Reasoning-only responses, empty reasoning deltas, repeated identical reasoning text, hidden reasoning with visible tools, and hidden tools with visible reasoning.
- User-input XML split over content chunks; cleaning must not move earlier text or timeline segments.
- Durable replay duplicate/out-of-order envelope filtering must remain unchanged while the resulting parts stay ordered.

### Regression scope

- `Message` action/copy/speech/feedback/version controls and artifact placement.
- Source citation footer and media/image/video preview behavior.
- ChatContainer's existing message-level controlled open callback and scrolling/memoization behavior.
- Backend SSE ordering, durable sequence replay, and round-step persistence are regression-only checks; no backend behavior is intentionally changed.

## Risks & Mitigation

- **Persisted granularity is coarser than live SSE.** State the iteration-level contract and add a follow-up design only if exact intra-turn replay is required; do not pretend a scalar historical field preserves token event order.
- **Tool result identity collisions.** Keep a single occurrence per protocol call ID, use deterministic occurrence matching, and test duplicates/orphans; never merge adjacent calls merely because they are adjacent.
- **Task state drift.** Keep aggregate task state for lifecycle decisions but derive visible task parts only from ordered segments; test start-without-context, context-without-start, and finalization.
- **User-input reconstruction can reorder content.** Limit XML cleanup to the current text segment and retain a split-content regression test.
- **Global open-state semantics across multiple panels.** Preserve the existing public prop contract and document that a supplied message-level control synchronizes its panels; default/uncontrolled panels remain separately mounted. A later UX request for per-panel persistence can be implemented as a separate API change.
- **Rich tool output regressions.** Reuse the current `renderToolResultContent` path and retain artifact/media/MCP assertions instead of replacing it with the simpler legacy `ToolContent` component.
- **Unnecessary backend migration.** Verify existing AgentLoop/AgentRunStream/round-order guarantees first; add schema work only with explicit approval for finer-than-iteration history.
