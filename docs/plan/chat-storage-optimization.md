# Chat Storage Optimization Design Document

## Background & Goals

- **Problem**: chat history is stored as relational rows in `messages` (one row per message; `jsonb` only for nested fields like `tool_calls`/`images`/`rag_context`; versions/branches via `parent_id`/`branch_parent_id`/`is_active`). This design is correct for versioning/branching, but four performance characteristics degrade as conversations grow (currently 529 rows / 41 conversations, max 93 rows per conversation — no real pressure yet):
  1. `activate_conversation_branch` writes `is_active=false` for the **whole conversation** on every edit/regenerate/version switch (write amplification).
  2. `find_descendant_branch_from` issues **one query per branch hop** (N+1); `get_prefix_path_before` loads the whole conversation **including large `content`/`jsonb` columns** that the chain walk never reads.
  3. Conversation detail endpoints return the **entire conversation** (no pagination); the frontend batches rendering but not transport.
  4. `WHERE conversation_id=? AND is_active=? ORDER BY created_at` has **no matching index** (current indexes: PK, `(conversation_id, branch_parent_id)`, partial `created_at` for observability), so large conversations sort in memory.

- **Success criteria**:
  - Conversation-history query uses an index scan (verified by `EXPLAIN ANALYZE`).
  - Edit/regenerate/switch writes touch only the messages that actually change (difference set), not the whole conversation.
  - Chain walks are single-query, column-trimmed.
  - All existing branch/version/edit/regenerate tests keep passing.

## High-Level Design

No schema shape change — the relational row model is the right one. Optimizations:

| # | Area | File(s) |
|---|---|---|
| P0 | Composite index `(conversation_id, is_active, created_at)` via startup migration | `backend/app/core/init_data.py`, `backend/app/main.py` |
| P1a | Difference-set activation in `activate_conversation_branch` | `backend/app/services/message_branching.py` |
| P1b | One-query chain walk + `.only(...)` column trimming in `find_descendant_branch_from` / `get_prefix_path_before` | `backend/app/services/message_branching.py` |
| P2 | Cursor pagination on conversation detail endpoints (deferred, product decision) | — |

## Implementation Plan

### Stage 1 (P0): messages history index migration
- **Files modified**: `backend/app/core/init_data.py`, `backend/app/main.py`, `backend/tests/test_init_data_routines.py`
- **Specific logic**: new `init_message_history_index()`:
  - probe `information_schema.tables` for `messages` (skip on first run, like `init_message_branch_parent_field`);
  - `CREATE INDEX IF NOT EXISTS idx_messages_conversation_active_created_at ON messages (conversation_id, is_active, created_at)`;
  - call it from the FastAPI lifespan migration block **before** `Tortoise.generate_schemas()` (with `init_agent_tools_credentials`/`init_agent_powered_by_text`) and idempotently from `init_db()`'s early schema-migration section.
- **Validation**: unit test asserting the CREATE INDEX SQL is issued when the index is missing and skipped otherwise; real-DB `EXPLAIN ANALYZE` shows Index Scan on the conversation-history query.

### Stage 2 (P1a): difference-set activation
- **Files modified**: `backend/app/services/message_branching.py`, `backend/tests/services/test_message_branching.py`
- **Specific logic**: `activate_conversation_branch` currently does `UPDATE … SET is_active=false WHERE conversation_id=?` then re-activates the path. Change to:
  1. read current active ids (one indexed SELECT);
  2. `UPDATE … SET is_active=false WHERE id IN (active − path)` (empty when nothing to deactivate);
  3. `UPDATE … SET is_active=true WHERE id IN (path − active)` (empty when nothing to activate).
  - Idempotency preserved: zero writes when the path already equals the active set. Round-step activation logic unchanged.
  - **Version-group invariant**: members of one version group are alternatives — a path may never activate more than one of them. If a polluted branch chain contributes both an old version and its replacement, keep the newest version and drop the old one together with its round's canonical messages (the old reply), so superseded turns cannot resurface even from a polluted chain.
- **Validation**: extend `test_activate_branch_*` tests to assert the UPDATE statements carry only the difference ids, that a no-op activation issues zero UPDATEs, and that a polluted path containing both versions activates only the newest.

### Stage 3 (P1b): single-query, column-trimmed chain walks
- **Files modified**: `backend/app/services/message_branching.py`, `backend/tests/services/test_message_branching.py`
- **Specific logic**:
  - `find_descendant_branch_from`: replace per-hop `Message.filter(branch_parent_id=…)` with one `Message.filter(conversation_id=…)` fetch into an `id → message` map, then walk in memory (same visited-set/version-sibling rules).
  - Both `get_prefix_path_before` and the new descendant fetch use `.only("id","parent_id","branch_parent_id","round_id","round_role","is_round_canonical","is_active","version_number","created_at")` so large `content`/`jsonb` payloads are not read.
- **Validation**: tests assert a single filter call and that `.only(...)` was applied; existing chain-walk tests keep passing.

### Stage 4 (P2, deferred): cursor pagination
- **Design**: `get_visible_conversation_messages(conversation_id, limit=…, before_created_at=…)` already supports the pieces; expose `?limit=&before=` on public/admin/embed conversation detail endpoints and switch the frontend `loadOlder` to cursor-based loading. Requires a cross-stack contract change (adapter → use-chat → page) — schedule when long conversations actually occur.

## Testing Strategy
- Happy path: index exists after migration; activation of a branch path activates exactly path + round steps; chain walks return the same results as before with fewer queries.
- Error path: missing `messages` table (first run) skips index migration; empty difference sets produce zero UPDATEs; cycle guard in chain walks still terminates.
- Regression scope: `tests/services/test_message_branching.py`, `tests/api/test_chat_message_versions*.py`, `tests/api/test_chat_edit_*`, `tests/api/test_chat_regenerate_*`, `tests/test_init_data_routines.py`.

## Risks & Mitigation
- Index write cost on INSERT/UPDATE: negligible at current scale; index is btree on low-cardinality leading column.
- Difference-set activation race: activation already runs inside `in_transaction` + `_lock_conversation` (row lock) at every call site; the extra SELECT runs in the same transaction.
- `.only(...)` on chain walks: models use plain columns only in these paths; any future field added to a walk must be added to the list.
- Rollback: P0/P1 are behavior-preserving; revert individual commits if a regression shows up.
