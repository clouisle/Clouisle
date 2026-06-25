# YUN-101 Editable Agent User Messages Design Document

## Background & Goals

- Agent conversation user messages need to support editing after they are sent.
- Edits must reuse the existing message version/branch model so changed content is traceable and switchable.
- After an edit, visible conversation history and future model context must use the edited branch rather than stale descendants from the previous user message.

Success criteria:
- A user can enter edit mode for their own Agent user message and save changed text.
- Saving creates a new user-message version instead of mutating the original row.
- A new assistant response is generated from the edited content.
- Existing version switching can move between original and edited user message branches.
- Ownership, agent matching, branch activation, session-memory invalidation, and audit/history behavior remain consistent.

## High-Level Design

Existing message versioning fields on `Message` are the persistence layer:

- `parent_id`: root/original message for a version group.
- `version_number`: ordinal in that version group.
- `branch_parent_id`: previous visible canonical message in the branch lineage.
- `is_active`: whether a row is part of the currently visible branch.

The edit flow creates a new user `Message` version, activates the prefix plus that edited user message before model context is prepared, streams a newly generated assistant message below the edited user version, then activates the complete edited branch. Existing conversation retrieval and context builders already use `get_visible_conversation_messages`, so keeping activation correct keeps display and future context correct.

Frontend adds an inline edit state for user messages, calls a new edit stream API, and reloads the conversation after the stream completes so backend version counts and active branch state are canonical.

## Implementation Plan

### Stage 1: Planning docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-101-edit-agent-user-message-history.md`
- **Specific logic**: Register YUN-101 in the implementation index and keep this design document current as implementation details are confirmed.
- **Validation**: Confirm the index links to this file and task status reflects completed stages.

### Stage 2: Backend edit schema, endpoint, and branch activation — Complete

- **Files modified**: `backend/app/schemas/agent.py`, `backend/app/api/v1/endpoints/chat.py`
- **Specific logic**:
  - Add an `EditMessageRequest` schema with required `content`.
  - Add `POST /agents/{agent_id}/messages/{message_id}/edit/stream` beside existing message version/regenerate endpoints.
  - Validate message existence, conversation ownership, path agent match, user role, non-empty text, and changed content.
  - Create a new user `Message` version using `get_version_root_id`, `get_branch_version_count`, `get_prefix_path_before`, and copied attachments.
  - Recompute RAG for edited text when enabled; do not copy stale `rag_context`.
  - Activate prefix plus edited user before preparing model context.
  - Generate and stream a new assistant response using the existing chat/regenerate SSE conventions and helper functions.
  - Activate prefix plus edited user plus final assistant message and call `stale_session_memory_if_source_outside_active_branch`.
  - Restore the original branch if generation fails before a usable assistant message is persisted.
- **Validation**: Backend tests cover new version creation, active branch contents, old downstream deactivation, version switching back, and validation failures.

### Stage 3: Audit and i18n for backend errors — Complete

- **Files modified**: `backend/app/api/v1/endpoints/chat.py`, backend i18n resources required by backend error conventions, audit i18n resources if required
- **Specific logic**:
  - Log message edits with `AuditLogService.log(...)` directly.
  - Include agent/conversation/original/new message/version metadata.
  - Store bounded before/after text information to avoid unbounded sensitive audit payloads.
  - Add backend i18n message keys for every edit validation failure introduced by the chat endpoint.
- **Validation**: Tests assert audit metadata exists and validation errors return the expected localized business-error path.

### Stage 4: Frontend API and hook — Complete

- **Files modified**: `frontend/lib/api/agents.ts`, `frontend/hooks/use-chat.ts`
- **Specific logic**:
  - Add an edit stream client method next to `regenerateStream`.
  - Expose `editMessage(messageId, content)` from `useChat`.
  - Block edits while a send/regenerate/edit stream is active.
  - Process stream events consistently with regenerate and reload the conversation at completion or after errors.
- **Validation**: Type/lint checks pass and manual chat edit produces streamed assistant output.

### Stage 5: Frontend inline edit UI and i18n — Complete

- **Files modified**: `frontend/components/chat/message.tsx`, `frontend/components/chat/chat-container.tsx`, `frontend/app/(chat)/chat/[id]/page.tsx`, `frontend/i18n/en/chat.json`, `frontend/i18n/zh/chat.json`, generated `frontend/i18n/types/*`
- **Specific logic**:
  - Add user-message Edit action when not streaming.
  - Render textarea edit mode with Save/Cancel controls.
  - Disable Save for empty, unchanged, or currently saving content.
  - Support Escape cancel and Cmd/Ctrl+Enter save.
  - Preserve attachments; edit only text content.
  - Reuse existing version switcher for user messages with multiple versions.
  - Add English and Chinese translation keys and regenerate i18n types.
- **Validation**: Manual browser verification confirms edit, cancel, validation, version switching, and page-refresh persistence.

### Stage 6: Tests and regression checks — Complete

- **Files modified**: `backend/tests/api/v1/test_chat_message_edit.py` and frontend tests if existing infrastructure is practical
- **Specific logic**:
  - Add focused backend API/service tests for edit/version/branch/audit behavior.
  - Add frontend component or hook tests if the surrounding chat components already have a test pattern.
- **Validation**: Run focused tests and project checks listed below.

## Testing Strategy

Happy path:
- Send a user message, receive assistant output, edit the user message, and confirm a new assistant response appears on the edited branch.
- Switch back to the original user message version and confirm the original assistant branch returns.
- Switch forward to the edited version and confirm the edited branch returns after refresh.

Error path:
- Edit by another user is rejected.
- Assistant/tool message edit is rejected.
- Empty or unchanged content is rejected.
- Mismatched path `agent_id` is rejected.
- Generation failure restores a coherent active branch.

Regression scope:
- Existing assistant regenerate behavior.
- Existing message version switching.
- Conversation retrieval for user/admin views.
- Chat context building and session-memory stale guard.

Commands:

```bash
cd backend
uv run pytest tests/api/v1/test_chat_message_edit.py
uv run pytest tests/api/v1 -k "chat or version or regenerate"
uv run ruff check .
uv run ruff format --check .
uv run mypy app/
```

```bash
cd frontend
node scripts/gen-i18n-types.ts
bun run lint
bun run build
```

## Risks & Mitigation

- **Stale descendants in context**: Activate prefix plus edited user before model context preparation.
- **Large duplicate streaming code**: Reuse existing chat/regenerate helpers and extract only the smallest safe helper if needed.
- **Sensitive audit payloads**: Store bounded/truncated before/after content information.
- **Attachment/RAG mismatch**: Preserve attachments but recompute RAG for edited text.
- **Version-switch branch ambiguity**: Add tests for user-message version switching with assistant descendants.

Rollback plan:
- Remove the new endpoint and frontend call path; existing persisted original messages and assistant regeneration/version switching remain unchanged because edits create additional rows instead of mutating original content.
