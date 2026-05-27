# Agent Message Version Branch-Aware Context Design Document

## Background & Goals

- Problem to solve: Agent message versions are currently managed as a flat list with `parent_id`, `is_active`, and `version_number`. Switching a historical version uses linear `created_at` deactivation, so descendant replies that belong to the selected version are not restored. Regenerated replies can also see stale previous-version content through conversation-scoped session memory summaries.
- Success criteria:
  - Version switching activates the selected version and its descendant branch when present.
  - Regeneration uses only the branch prefix before the regenerated assistant message.
  - Session memory summaries are not injected when their source is outside the current branch or after the context cutoff.
  - Existing frontend version controls keep working after conversation reload.

## High-Level Design

- Add explicit branch lineage to `Message` with `branch_parent_id`.
- Keep `parent_id` as the version-group root pointer.
- Keep `is_active` as the materialized current visible branch path for compatibility with existing API response logic.
- Centralize branch operations in a backend service so conversation retrieval, prompt context building, version switching, and session memory use the same active-branch semantics.

## Implementation Plan

### Stage 1: Planning docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/agent-message-version-branch-aware-context.md`
- **Specific logic**: Track implementation stages and verification expectations.
- **Validation**: Confirm the plan index links to this file and stage 1 is checked.

### Stage 2: Message branch schema and migration

- **Files modified**: `backend/app/models/agent.py`, `backend/app/core/init_data.py`, `backend/app/main.py`
- **Specific logic**:
  - Add nullable `Message.branch_parent_id`.
  - Add an idempotent startup migration to add the column and indexes.
  - Backfill current active canonical messages into a linear branch per conversation.
  - Backfill inactive version children so alternatives inherit the root message predecessor.
- **Validation**: Startup migration is idempotent and does not fail when `messages` does not exist.

### Stage 3: Branch helper service

- **Files modified**: `backend/app/services/message_branching.py`
- **Specific logic**:
  - Resolve version roots and groups.
  - Return active visible messages in branch order.
  - Build prefix path before a message.
  - Follow descendant branch from a selected version.
  - Activate exactly one branch path and its round support messages.
  - Check whether a message belongs to the active branch.
- **Validation**: Unit-level helper tests or focused script-created objects confirm path activation and descendant selection.

### Stage 4: Chat creation, regenerate, and switch-version

- **Files modified**: `backend/app/api/v1/endpoints/chat.py`
- **Specific logic**:
  - Set `branch_parent_id` for user, assistant, and round support messages.
  - Regenerated assistant versions inherit the old version's `branch_parent_id`.
  - `switch_message_version` activates prefix + target descendant path instead of timestamp-deactivating later messages.
  - Stale session memory after branch changes when needed.
- **Validation**: Switching between two assistant versions restores each version's own continuation path.

### Stage 5: Branch-aware history and memory

- **Files modified**: `backend/app/api/v1/endpoints/agents.py`, `backend/app/api/v1/admin/endpoints/conversations.py`, `backend/app/services/chat_context.py`, `backend/app/services/session_memory.py`
- **Specific logic**:
  - Use the shared active-branch helper for conversation responses and model context history.
  - Apply cutoffs only inside the active branch.
  - Skip session memory injection if the snapshot source is not on the active branch or falls after the prompt cutoff.
  - Extract session memory from branch-aware history only.
- **Validation**: A stale summary containing a sentinel from an inactive branch does not appear in prepared model messages.

### Stage 6: Validation and regression checks

- **Files modified**: tests as needed under `backend/tests/`.
- **Specific logic**:
  - Add focused tests for branch switching, regeneration context exclusion, session memory guard, version counts, and round tool-step activation.
- **Validation**:
  - `uv run ruff check .`
  - `uv run mypy app/`
  - `uv run pytest` or targeted tests if the full suite is too large.
  - Frontend `bun run lint` / `bun run build` only if frontend files change.

## Testing Strategy

- Happy path tests:
  - Create A1 v1 with continuation, regenerate A1 v2 with a different continuation, then switch both ways and verify visible messages.
  - Regenerate an assistant message and verify the new prompt contains the preceding user message but not the old assistant content.
- Error path tests:
  - Reject switching to a version outside the current message's version group.
  - Skip stale session memory when source message is inactive or outside branch.
- Regression scope:
  - Existing message version list API.
  - Conversation detail payload and `version_count` computation.
  - Tool-call rounds nested under canonical assistant messages.

## Risks & Mitigation

- Old hidden branches cannot be perfectly reconstructed from existing data. Backfill preserves current active paths and makes new branch operations correct going forward.
- Round step messages can disappear if only canonical messages are activated. Activation must include non-canonical messages for active round IDs.
- Session memory is conversation-scoped. Guard injection by branch membership and stale snapshots after branch switches.
- Multiple endpoints query active messages. Use the shared helper to avoid divergent behavior.

Rollback plan: remove branch-aware endpoint logic and fall back to existing `is_active` queries; keep the nullable `branch_parent_id` column unused if rollback is needed.