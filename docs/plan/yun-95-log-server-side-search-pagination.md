# YUN-95 Log Server-Side Search Pagination Design Document

## Background & Goals

- Agent logs currently search and date-filter only the conversations already loaded on the current page.
- Workflow logs currently date-filter only the runs already loaded on the current page, and need exact run ID search.
- Success criteria: backend applies search/date/status filters before pagination; frontend requests only the active page; pagination totals match filtered results.

## High-Level Design

- Extend the existing paginated endpoints without changing response shapes.
- Reuse existing `PageData` responses and page/page_size query pattern.
- Frontend API clients map camelCase options to backend snake_case query params.
- Log pages render backend-returned items directly instead of local filtered arrays.

## Implementation Plan

### Stage 1: Documentation

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-95-log-server-side-search-pagination.md`
- **Specific logic**: Record the backend, frontend, and validation stages for this multi-module change.
- **Validation**: The plan references only this task and remains concise.

### Stage 2: Backend Agent log filters

- **Files modified**: `backend/app/api/v1/endpoints/agents.py`
- **Specific logic**:
  - Add `search`, `created_after`, `created_before`, and `sort_by` query params to `list_agent_conversations`.
  - Filter by title and created_at before `count()` and pagination.
  - Whitelist sort fields: `created_at`, `updated_at`, `message_count`; default to `updated_at` descending.
- **Validation**: Query with search/date/sort and confirm `items.length <= page_size` and filtered `total`.

### Stage 3: Backend workflow run filters

- **Files modified**: `backend/app/api/v1/endpoints/workflows.py`
- **Specific logic**:
  - Add `search`, `created_after`, `created_before` to `list_workflow_runs`.
  - Search by complete run ID before `count()` and pagination.
  - Invalid or incomplete run ID searches should produce no results rather than fuzzy matches.
  - Preserve status/is_debug filters and newest-first ordering.
- **Validation**: Query with complete run ID, status, and date filter; confirm filtered `total` and page-sized results.

### Stage 4: Frontend API clients

- **Files modified**: `frontend/lib/api/agents.ts`, `frontend/lib/api/workflows.ts`
- **Specific logic**:
  - Extend `getAgentConversations` options with search/date/sort params.
  - Extend `WorkflowRunQueryParams` with search/date params.
  - Omit empty optional params.
- **Validation**: TypeScript/lint verifies call sites.

### Stage 5: Agent logs page

- **Files modified**: `frontend/app/(platform)/app/apps/[id]/logs/page.tsx`
- **Specific logic**:
  - Debounce search input.
  - Convert date presets to `createdAfter` ISO timestamps.
  - Fetch page 1 when search/date/sort changes; keep filters while paging.
  - Remove current-page-only local filtering and render `conversations` directly.
- **Validation**: Search for a title outside page 1 and confirm it appears in filtered page 1.

### Stage 6: Workflow logs page

- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/logs/page.tsx`, `frontend/i18n/en/workflow.json`, `frontend/i18n/zh/workflow.json`, generated workflow type file
- **Specific logic**:
  - Add run ID search input.
  - Debounce search input.
  - Convert date presets to `createdAfter` ISO timestamps.
  - Fetch page 1 when search/status/date changes; keep filters while paging.
  - Remove current-page-only local filtering and render `runs` directly.
- **Validation**: Search by complete run ID with status/date filters and confirm pagination totals match.

## Testing Strategy

- Run `cd frontend && node scripts/gen-i18n-types.ts && node scripts/lint-translations.ts` after i18n changes.
- Run `cd frontend && bun run lint`.
- Run `cd backend && uv run ruff check .`.
- If time allows, run `cd frontend && bun run build` and `cd backend && uv run mypy app/`.
- Manually verify Agent logs and workflow logs in the browser if the dev stack is available.

## Risks & Mitigation

- Exact run ID search uses UUID equality only; no fuzzy or partial ID search is supported.
- Filter changes can leave the user on an out-of-range page; reset page to 1 whenever filters change.
- Browser-local cutoff timestamps preserve current date preset behavior but depend on client clock.
