# Embedded Agent Chat Performance Design Document

## Background & Goals

- Problem to solve: Agent conversations embedded into external websites via script still use the older embed streaming hook path. The shared chat renderer has been optimized, but embedded streaming still commits React state for every text/reasoning SSE chunk and repeatedly scans full streamed text for user-input XML.
- Success criteria:
  - Embedded chat streams long answers with fewer React renders.
  - Existing embed iframe/script behavior stays unchanged.
  - Reasoning, RAG/source tasks, tool calls/results, user-input request cards, stop, and errors still render correctly.
  - No new dependencies, new renderer, browser automation, or service startup are introduced.

## High-Level Design

- Keep using the existing shared chat components:
  - `frontend/components/chat/chat-container.tsx`
  - `frontend/components/chat/message.tsx`
- Apply the proven main-chat streaming batching pattern from `frontend/hooks/use-chat.ts` to `frontend/hooks/use-embed-chat.ts`:
  - mutate streaming refs on SSE events
  - schedule text/reasoning UI commits with `requestAnimationFrame` or `setTimeout(..., 16)`
  - flush structural/final/error events immediately
- Keep XML parsing behavior but gate the expensive full-text scan until `<user_input_request>` is likely present.

## Implementation Plan

### Stage 1: Design docs and implementation index

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/embed-chat-performance.md`
- **Specific logic**: Register this performance follow-up and document the focused approach.
- **Validation**: Confirm the plan names existing reusable chat optimization files and avoids a new abstraction.

### Stage 2: Embedded streaming commit batching

- **Files modified**: `frontend/hooks/use-embed-chat.ts`
- **Specific logic**:
  - Add `scheduledStreamingFlushRef`.
  - Add `cancelScheduledStreamingFlush()`, `flushStreamingMessage()`, and `scheduleStreamingMessageFlush()`.
  - Use scheduled flushes for `content_delta` and `reasoning_delta` instead of direct per-token `setMessages`.
  - Preserve historical message object identity by updating only the active assistant message.
- **Validation**: Inspect that hot-path token/reasoning events no longer call `setMessages` directly.

### Stage 3: User-input XML parse gating

- **Files modified**: `frontend/hooks/use-embed-chat.ts`
- **Specific logic**:
  - Add local `userInputRequestCandidateSeen` and `userInputRequestScanTail` in `sendMessage()`.
  - Only call `parseUserInputRequestSegments()` after detecting the start tag.
  - Reset scan state after parsing completes.
- **Validation**: Confirm ordinary text deltas do not join/scan the full message on every chunk.

### Stage 4: Final/stop/error cleanup

- **Files modified**: `frontend/hooks/use-embed-chat.ts`
- **Specific logic**:
  - Cancel scheduled flushes before `message_end`, missing-terminal fallback, errors, stop, and reset.
  - Render final parts with `isStreaming=false` and preserve usage/timing metadata.
  - Complete running reasoning/task states before final rendering.
- **Validation**: Inspect that no scheduled flush survives after stream completion, abort, or reset.

### Stage 5: Validation and regression checks

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md` only if checklist status is updated after validation.
- **Specific logic**: Run focused static checks and mark this plan complete when checks pass.
- **Validation**:
  - `cd frontend && bun run lint`
  - `cd frontend && bun run build`
  - `git diff --check`

## Testing Strategy

- Happy path tests:
  - Embedded chat can send and stream a long text response.
  - Reasoning, RAG/source, tool call/result, and user-input request parts still appear in order.
  - Existing iframe events for ready, close, conversation changes, and errors remain untouched.
- Error path tests:
  - Stop/abort does not leave scheduled updates alive.
  - Error events still call the existing `onError` path.
  - Missing terminal event fallback still finalizes visible partial output.
- Regression scope:
  - Main chat `useChat` should not be changed in this pass except as a reference.
  - Shared `ChatContainer` and `Message` should remain reusable and unchanged unless a concrete issue appears.

## Risks & Mitigation

- Risk: batching could delay perceived streaming output.
  - Mitigation: flush once per animation frame and immediately flush structural/final events.
- Risk: terminal events race with a scheduled flush.
  - Mitigation: cancel scheduled flushes before final/error/stop updates.
- Risk: XML request card parsing changes.
  - Mitigation: keep the existing parser and only add the same candidate gate pattern used by main chat.
- Rollback plan: revert the `use-embed-chat.ts` batching change; docs are isolated and can be reverted separately.
