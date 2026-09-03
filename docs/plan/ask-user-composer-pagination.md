# Ask-user Composer Pagination Design Document

## Background & Goals

`ask_user` currently renders its editable form inside an assistant message’s tool-call node. The interaction is therefore mixed with durable conversation history and can appear inside the thought/tool timeline.

Move the active interaction to the composer area, alongside the existing agent-input configuration UI. Present exactly one question at a time. A required answer must be provided before advancing; users can return to prior questions; the final page submits one unchanged structured `answers` object for the original pending `tool_call_id`.

Success criteria:
- No `ask_user` form, raw question payload, or interaction card is rendered inside a conversation message.
- Every Agent chat surface renders the pending interaction above its disabled composer.
- One-to-many questions preserve IDs, optional-answer behavior, and the existing durable answer API.
- Previous/next navigation never loses answers and blocks only the required current page.

## High-Level Design

`AskUserForm` remains the single interactive renderer but owns a page index and an accumulated answer map. `PendingAskUserForm` resolves the current pending `ask_user` call from `messages` plus the server-authoritative `pendingAskUserToolCallId`, then submits through the existing callback with that exact ID.

The public/embed chat page, platform preview, run page, and reusable `Chat` shell place that component in their bottom input regions. The ordinary composer remains disabled while the run is waiting. The message renderer treats `ask_user` calls/results as interaction plumbing rather than visible message content, so history does not expose a form or question JSON.

## Implementation Plan

### Stage 1: Paginated composer interaction
- **Files modified**: `frontend/components/chat/ask-user-form.tsx`, `frontend/i18n/en/chat.json`, `frontend/i18n/zh/chat.json`
- **Specific logic**: Resolve a pending call from message parts; render one question per page; validate the current required answer before next; retain previous answers; submit the filtered accumulated map only from the final page.
- **Validation**: Component tests cover one question, required validation, next/previous navigation, optional omissions, disabled state, and rejected durable submission.

### Stage 2: Remove message-node interaction
- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/chat-container.tsx`, `frontend/components/chat/chat.tsx`
- **Specific logic**: Remove question-form callback plumbing from message rows and omit `ask_user` tool calls/results from visible assistant content and thought/tool timelines.
- **Validation**: Message tests prove pending and completed ask-user parts do not render question text, options, raw input, or empty action-only cards; generic tool rendering remains unchanged.

### Stage 3: Wire every Agent composer
- **Files modified**: `frontend/app/(chat)/chat/[id]/page.tsx`, `frontend/app/(chat)/run/[id]/_components/agent-run-page.tsx`, `frontend/app/(platform)/app/apps/[id]/_components/agent-preview-panel.tsx`
- **Specific logic**: Render the pending form above the composer; bind submission to the existing `submitAskUser`; keep static variable configuration out of the way while a pending interactive request is active.
- **Validation**: Page/preview/run tests prove the panel receives the active request and submits through the original callback rather than `ChatContainer`.

### Stage 4: Regression verification and cleanup
- **Files modified**: affected tests and this plan/index
- **Specific logic**: Removed obsolete message-row callback plumbing, mocks, and assertions; recorded the final verification evidence.
- **Validation**: `bun test --isolate` for the eight changed chat/page test files passed 121 tests with 488 assertions; `npx tsc --noEmit -p tsconfig.json` and scoped ESLint with `--max-warnings=0` passed.

## Verification Record

- Focused isolated tests: 121 passed, 0 failed across ask-user form, message, chat container/shell, public chat, Agent run, and preview surfaces.
- TypeScript: `npx tsc --noEmit -p tsconfig.json` passed.
- ESLint: all affected source and test files passed with `--max-warnings=0`.

## Testing Strategy

- Happy path: select answers across multiple pages, go back, then submit the complete ID-keyed map on the final page.
- Error path: required page cannot advance; rejected API submission remains visible; malformed pending input renders no editable panel.
- Regression scope: regular tool cards, chain-of-thought rendering, public/embed chat, standalone run pages, and platform preview.

## Risks & Mitigation

- **Wrong call identity**: `PendingAskUserForm` derives the ID from the exact pending tool call and delegates unchanged to the existing durable submit callback.
- **Stale form state after resume/new question**: key the renderer by tool-call ID so a new request starts at page one with a fresh answer map.
- **Question data unavailable during reconnect**: only render when the matching tool-call part and valid normalized questions exist; the disabled composer preserves the server waiting invariant.
- **UI duplication**: remove the old message-node form and its callback plumbing in the same change.
