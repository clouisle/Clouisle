# YUN-97 Observability Upgrade Design Document

## Background & Goals
- Admin observability already has backend endpoints and a frontend page, but the information architecture hides token/cost, workers, and slow-query setup behind broader tabs.
- Operators need faster answers for success/error/timeout rates, latency percentiles, TTFT, QPS/TPS, token concentration, top slow Agent/Workflow, failed Workflow nodes, and abnormal dependency states.
- Success criteria:
  - Overview provides actionable alert cards and clearer navigation across observability domains.
  - Agent and Workflow views highlight slow/error-prone entities and expose P50/P90/P95/P99 plus success/error/timeout signals.
  - Token/cost and worker/slow-query visualizations are first-class enough to discover from tabs.
  - Slow-query unavailable state explains setup steps clearly.
  - Redis/DB/Worker abnormal states show reason and suggested actions.
  - New copy exists in both English and Chinese, and generated i18n types are refreshed.

## High-Level Design
- Reuse `frontend/lib/api/admin/observability.ts`; no backend changes unless an API gap blocks the UI.
- Extend `frontend/app/(dashboard)/dashboard/observability/page.tsx` tab IA to add `tokens`, `workers`, and `slow-queries` tabs while preserving existing query-string tab behavior.
- Keep existing panel file as the main presentation layer and add small helper components for alerts, top lists, token model ranking, worker action guidance, and slow-query guidance.
- Use existing `getOverview`, `getAgents`, `getWorkflows`, `getTimeouts`, `getThroughput`, `getTokens`, `getSystemHealth`, `getSystemTrend`, `getSlowQueries`, and `getWorkers` calls.

## Implementation Plan

### Stage 1: Planning and structure
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-97-observability-upgrade.md`
- **Specific logic**: Register this complex task and document the scoped frontend-first approach.
- **Validation**: Confirm docs are created before implementation and the implementation index links to this plan.

### Stage 2: Navigation and page data loading
- **Files modified**: `frontend/app/(dashboard)/dashboard/observability/page.tsx`
- **Specific logic**: Add tabs for token/cost, workers, and slow queries. Fetch only the data required by the active tab, using existing APIs and preserving the global time range where supported.
- **Validation**: Run TypeScript/lint checks to ensure tab union and data guards stay consistent.

### Stage 3: Observability panel upgrades
- **Files modified**: `frontend/app/(dashboard)/dashboard/observability/_components/observability-panels.tsx`
- **Specific logic**: Add alert/navigation cards, top slow/failed/token lists, dedicated token/cost, worker, and slow-query panels, clearer dependency abnormal reason/action copy, and fuller percentile/TTFT metric displays.
- **Validation**: Compile and lint the frontend; verify empty, loading, error, unavailable, and abnormal states are represented by code paths.

### Stage 4: i18n and generated types
- **Files modified**: `frontend/i18n/en/dashboard.json`, `frontend/i18n/zh/dashboard.json`, generated files under `frontend/i18n/types/`
- **Specific logic**: Add all new English and Chinese copy together, then regenerate i18n types with the documented script.
- **Validation**: Run translation lint and TypeScript/lint checks.

## Testing Strategy
- Happy path tests:
  - `bun run lint` for frontend static validation.
  - `node scripts/lint-translations.ts --strict` for translation consistency.
  - `node scripts/gen-i18n-types.ts` to refresh generated i18n types.
- Error path tests:
  - Code review of render branches for empty/error/unavailable data including slow-query unavailable and worker inspection failure.
  - Confirm dependency rows render abnormal reason/action when backend sends non-healthy status, reason, message, detail, or error fields.
- Regression scope:
  - Existing overview, health, agents, workflows, timeouts, and throughput tabs keep their routes and API calls.
  - Existing Agent/Workflow detail sheets keep drilldown behavior.

## Risks & Mitigation
- Risk: Backend payloads for `SystemHealthResponse` are loosely typed records.
  - Mitigation: Read common reason fields defensively and fall back to actionable generic guidance.
- Risk: Adding many dashboard cards can make the page noisy.
  - Mitigation: Keep additions grouped as compact cards and reuse existing visual components.
- Risk: Token/cost endpoint may only expose token counts, not currency cost.
  - Mitigation: Label the tab as token/cost and show token-based cost drivers without inventing currency estimates.
- Rollback plan: Revert the frontend page/panel/i18n changes and remove this plan entry if validation fails beyond the three-attempt limit.
