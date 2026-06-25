# Chat Extreme Performance Refactor Design Document

## Background & Goals
- Problem to solve: Chat pages with messages are still slow or freezing, especially conversation switching, rendering source panels, and pages with long streamed messages/tool outputs. Performance traces have shown React scheduler/render work and Console Task overhead; prior surgical fixes helped individual symptoms but did not remove the underlying architectural cost.
- Success criteria:
  - Conversation switch from sidebar does not render the full heavy message tree synchronously.
  - Opening used sources does not mount expensive portal/focus/markdown/tool trees or block clicks/close.
  - Only the actively streaming message updates frequently; historical messages remain memo-stable.
  - Markdown/code/source/tool rendering is lazy, bounded, and split into small memoized components.
  - React render work is dominated by the currently visible/changed message, not the whole chat page.
  - Performance validation confirms reduced long tasks and no repeated Console Task/MutationObserver loops.

## High-Level Design
- Split the current giant message renderer into a lightweight shell plus memoized leaf renderers:
  - `ChatContainer` owns scrolling/windowing only.
  - `ChatMessageItem` owns per-message shell, actions, edit/speech state, and part routing.
  - `MessageBody` renders stable part lists.
  - `MarkdownMessagePart` owns text rendering and only mounts Streamdown when needed.
  - `CitationInlineRenderer` removes DOM mutation/portal citation replacement from the hot render path.
  - `SourcePanel` remains lazy, batched, inline, and mounted only when open.
  - `ToolPartRenderer` and `ReasoningPartRenderer` stay collapsed by default for historical messages.
- Replace DOM-post-processing patterns with render-time parsing where possible:
  - Convert `[[cite:N]]` text markers to inline React tokens before Streamdown when citations exist, or strip them without a DOM TreeWalker when not shown.
  - Avoid `MutationObserver` citation scans on every Streamdown DOM change.
- Reduce streaming update frequency in `useChat`:
  - Accumulate text deltas in refs.
  - Commit to React state on animation frames or a small fixed cadence instead of every SSE chunk.
  - Keep final event immediate.
- Make message props stable:
  - Avoid new inline closures for every message on every parent render.
  - Extract per-message callbacks into a memoized wrapper keyed by message id.
- Keep previous fixes that help:
  - Message count windowing.
  - Source batching/truncation.
  - `ToolContent` unmount-on-close.
  - Console log removal.

## Implementation Plan

### Stage 1: Plan/index and renderer boundary extraction
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/chat-extreme-performance-refactor.md`, `frontend/components/chat/message.tsx`, new files under `frontend/components/chat/message-renderers/`
- **Specific logic**:
  - Register this refactor as a complex task in the implementation index.
  - Extract pure helper functions from `message.tsx` into local renderer modules without behavior changes:
    - markdown/math normalization helpers
    - citation marker helpers
    - code preview helpers
    - speech text helpers only if needed for shell separation
  - Create component boundaries but preserve existing rendering output.
- **Validation**:
  - `bun run lint`
  - `bun run build`
  - Manual smoke: load chat, copy, edit, regenerate, source panel, code preview still work.

### Stage 2: Replace citation DOM MutationObserver with render-time citation handling
- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/message-renderers/markdown-message-part.tsx`, `frontend/components/chat/message-renderers/citation-inline-renderer.tsx`
- **Specific logic**:
  - Remove citation `TreeWalker`, `createPortal`, and citation `MutationObserver` from text rendering.
  - Preprocess citation markers into bounded React-rendered inline badges when citation count is small and sources are available.
  - Strip citation markers before Streamdown when inline citation rendering is disabled or no sources exist.
  - Keep citation badge UI simple with native title only.
- **Validation**:
  - Message with `[[cite:1]]` shows badge.
  - Message without sources strips citation markers.
  - Opening used sources remains clickable/closable.
  - Performance trace no longer shows repeated citation MutationObserver/TreeWalker work.

### Stage 3: Throttle streaming state commits in `useChat`
- **Files modified**: `frontend/hooks/use-chat.ts`
- **Specific logic**:
  - Introduce a small internal scheduler for streaming message updates using `requestAnimationFrame` or a guarded timeout fallback.
  - Mutate the streaming refs per SSE event, but only call `setMessages` through `flushStreamingMessage()`.
  - Flush immediately for structural events: message id assignment, tool start/result, source arrival, terminal events, errors, manual stop.
  - Batch text/reasoning deltas to avoid React rendering each token chunk.
  - Preserve stop/finalize behavior and backend id replacement.
- **Validation**:
  - Streamed text appears smoothly without losing tokens.
  - Stop still finalizes visible partial content.
  - Reasoning/tool/source events appear in order.
  - Performance trace shows fewer React render tasks during streaming.

### Stage 4: Split message shell/actions/body and memoize historical messages
- **Files modified**: `frontend/components/chat/message.tsx`, new `frontend/components/chat/message-renderers/chat-message-item.tsx`, `message-actions.tsx`, `message-body.tsx`
- **Specific logic**:
  - Move copy/edit/speech/regenerate UI into `MessageActions` so action state changes do not rerender markdown/tool subtrees.
  - Move part classification into a memoized `useMessageParts` helper keyed by `message.parts` and `hideToolCalls`.
  - Wrap message body/parts with `React.memo` and custom comparators that compare stable part arrays and streaming flags.
  - Ensure historical messages receive `isStreaming=false` and do not observe streaming-only DOM work.
- **Validation**:
  - Copy/edit/speech state updates affect only the relevant action UI or one message.
  - React Profiler shows historical message bodies are not rerendered during streaming of the last message.

### Stage 5: Rework chat list windowing and conversation switching
- **Files modified**: `frontend/components/chat/chat-container.tsx`, `frontend/app/(chat)/chat/[id]/page.tsx`
- **Specific logic**:
  - Keep initial render count low and make it configurable constants.
  - Convert `visibleMessages` to `useMemo` and avoid recomputing `lastMessageText` from full `messages` every render.
  - Replace inline per-message callbacks inside `map` with a memoized `ChatMessageRow` that owns id-bound callbacks.
  - On conversation id change, reset scroll/window state predictably but render only the latest batch first.
  - Preserve load-older behavior.
- **Validation**:
  - Direct URL load and sidebar switch both render the same latest-message window.
  - Switching between long conversations does not synchronously render old hidden messages.
  - Scroll-to-bottom and load older messages still work.

### Stage 6: Bound heavyweight tool/source/reasoning rendering
- **Files modified**: `frontend/components/chat/message-parts/source-content.tsx`, `frontend/components/chat/message-parts/tool-content.tsx`, `frontend/components/chat/message-parts/reasoning-content.tsx`, `frontend/components/ai-elements/tool.tsx`
- **Specific logic**:
  - Keep large source content truncated and batch-rendered.
  - Ensure tool output is collapsed/unmounted unless opened.
  - Render large JSON/code outputs as preview snippets first, with explicit expand action.
  - Keep reasoning collapsed for historical messages unless user opened it.
- **Validation**:
  - Large tool/source messages no longer mount full payloads by default.
  - Expand controls work and are reversible.
  - No behavior regression for hidden-tool-call agent setting.

### Stage 7: Performance and regression validation
- **Files modified**: none unless validation finds defects
- **Specific logic**:
  - Run static checks and production build.
  - Run manual browser performance smoke tests for:
    - long conversation direct load
    - sidebar switch into long conversation
    - streaming long answer
    - opening/closing used sources
    - opening/closing tool output
    - code preview
    - edit/regenerate/version switch
- **Validation**:
  - `bun run lint`
  - `bun run build`
  - `git diff --check`
  - Browser Performance: fewer long tasks; no repeated Console Task; no citation MutationObserver loop; React render work restricted to visible/changed message.

## Testing Strategy
- Happy path tests:
  - Load existing conversation with text, citations, sources, files, images, reasoning, tool calls, and media results.
  - Stream a new response and confirm text/tool/source ordering.
  - Open used sources and close/continue interacting.
  - Use copy, speech, edit, regenerate, version switch, code preview.
- Error path tests:
  - SSE error during stream still shows preserved error message.
  - Stop mid-stream preserves partial text.
  - Broken/unsupported citation index does not crash.
  - Invalid/blocked markdown image URL renders fallback text.
  - Large source/tool output remains bounded.
- Regression scope:
  - Agent hidden tool calls.
  - Knowledge source display.
  - User input request XML card.
  - Message version switching.
  - Code preview canvas.
  - i18n keys in `en` and `zh` remain synced.

## Risks & Mitigation
- Risk: Changing citation rendering could alter markdown output around citation markers.
  - Mitigation: Keep fallback path that strips markers; test common inline citation placements.
- Risk: Streaming throttle could delay perceived output or drop final chunks.
  - Mitigation: Flush immediately on terminal/structural events and on stop/error/finalize.
- Risk: Splitting `message.tsx` may accidentally break rarely used media/tool variants.
  - Mitigation: Move code in small stages without changing logic first, then optimize.
- Risk: Memo comparators may hide legitimate updates if props are unstable or mutated.
  - Mitigation: Use immutable part replacement at React state boundaries and avoid comparing nested mutable content except by object identity from state.
- Rollback plan:
  - Each stage is independently revertible.
  - If render-time citation parsing causes issues, revert only Stage 2 and keep other memo/windowing changes.
  - If stream throttling causes ordering bugs, revert Stage 3 and keep renderer split.
