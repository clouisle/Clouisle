# Agent-level Powered-by Footer Text Design

## Background & Goals
- Problem: the chat page footer "由 {name} 提供" (`poweredBy` i18n + creator username) is hardcoded frontend copy with no configuration. It cannot be customized or removed per agent.
- Goal: make the footer text an Agent-level configuration. Non-empty value replaces the footer text verbatim; empty/null hides the footer entirely (the current default behavior is superseded — the hardcoded creator fallback is removed).

## Success Criteria
- A new agent field `powered_by_text` is created, validated, persisted, returned by admin/public agent APIs, exported/imported by agent packages, and audited on change.
- The agent config form has an input for the footer text (with hint that empty hides the footer).
- The public chat page and the agent run page render the configured text; empty → no footer.
- Backend and frontend tests cover the field end-to-end; frontend coverage gate stays ≥95%.

## High-Level Design
- New nullable text column on `agents` (`powered_by_text`, max 200 chars), following the existing `opening_message` field pattern.
- Schema surfaces: `AgentCreate`, `AgentUpdate`, `AgentOut`, `AgentPublicOut` (admin + public API), the public chat endpoint, the agent detail dict, and package export/import (`_agent_fields`).
- Audit: add `powered_by_text` to `AuditLogService`'s agent `SNAPSHOT_FIELDS` tuple so edits record before/after diffs.
- Frontend: `Agent`/`PublicAgent` types gain the field; the platform agent config form gains an input; the chat page and run page render `powered_by_text` when non-empty and hide the footer otherwise.

## Implementation Plan

### Stage 1: Backend model + schemas
- **Files**: `backend/app/models/agent.py`, `backend/app/schemas/agent.py`
- **Logic**: add `powered_by_text = fields.TextField(null=True, max_length=200, ...)` after `suggested_questions`; add `powered_by_text: str | None = Field(None, max_length=200)` to `AgentCreate` and `AgentUpdate`, `powered_by_text: str | None = None` to `AgentOut` and `AgentPublicOut`.
- **Validation**: create/update accept the field; update only applies when not `None` (same as `opening_message`).

### Stage 2: Backend endpoints + audit + packages
- **Files**: `backend/app/api/v1/admin/endpoints/agents.py`, `backend/app/api/v1/endpoints/agents.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/services/audit_log.py`, `backend/app/services/clouisle_package_resources.py`
- **Logic**: wire the field through admin/public create/update/detail/copy, the public chat `AgentPublicOut` construction, the audit agent field tuple, and package export payload + `_agent_fields` import mapping.

### Stage 3: Backend tests
- **Files**: backend agent API tests (admin + public) and chat preflight test
- **Validation**: create/update round-trip persists the field; public agent output carries it; empty → null.

### Stage 4: Frontend types + config form + pages
- **Files**: `frontend/lib/api/agents.ts`, `frontend/app/(platform)/app/apps/[id]/page.tsx`, `.../_components/agent-config-form.tsx`, `frontend/app/(chat)/chat/[id]/page.tsx`, `frontend/app/(chat)/run/[id]/_components/agent-run-page.tsx`, `frontend/i18n/{zh,en}/agents.json`, `frontend/i18n/types/agents.ts`
- **Logic**: add the field to `Agent`/`AgentCreateInput`/`AgentUpdateInput`/`PublicAgent`; add form state + submit + an input with placeholder/hint; chat page + run page footer render `powered_by_text` when set and hide otherwise (drop the `poweredBy` fallback); regenerate i18n types via `bun run scripts/gen-i18n-types.ts`.

### Stage 5: Frontend tests
- **Files**: `frontend/app/(chat)/chat/[id]/page.test.tsx`, config form tests
- **Validation**: footer shows configured text and is hidden when empty; form submits the field.

## Testing Strategy
- Happy path: create agent with `powered_by_text` → public chat output contains it → page footer renders it; run page renders it.
- Negative path: empty string → stored as null → footer hidden.
- Regression scope: existing agent create/update/detail/copy/audit/package tests keep passing; frontend chat page tests keep passing; full coverage gates.

## Risks & Mitigation
- Tortoise auto-creates tables (no Alembic); adding a column to an existing DB requires `create_all` on new installs only — existing deployments need a manual `ALTER TABLE agents ADD COLUMN powered_by_text` (documented; the project has no migration runner).
- Frontend coverage: new form field and footer branch add lines to `page.tsx`/`agent-config-form.tsx`; add focused tests.
- Rollback: revert the field addition; the footer falls back to nothing (hidden) — no crash.

## Status
In progress.
