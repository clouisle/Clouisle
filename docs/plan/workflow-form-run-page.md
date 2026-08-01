# Workflow Form Run Page Design Document

## Background & Goals

The current `/run/[id]?type=workflow` route uses a form-first runner, but its history controls and result presentation still diverge from the Agent Chat workspace. This follow-up aligns the Workflow runner with the existing Agent Chat interaction pattern and provides one semantic result presentation for live and historical runs.

Success means users can collapse and reopen the run-history rail, create a new run through the same affordance as a new chat, and read historical Answer Markdown, media, and typed node outputs without seeing JSON unless the output is unsupported.

## High-Level Design

- Keep Agent and Workflow route branches, published snapshot execution, authenticated personal history, and discrete `WorkflowRun` persistence unchanged.
- Use the Agent Chat custom collapsible `w-64` rail pattern for Workflow history. The Workflow identity and ghost `SquarePen` action create a new run; the main header keeps equivalent actions when the rail is collapsed.
- Resolve both live and historical results through `workflow-result-renderer.tsx` in this order: streamed Answer text, canonical `outputs.answer`, completed Answer-node output, typed/media node output, and JSON fallback.
- Always load historical node executions for result resolution. `simple` hides Trace, while `result_first` exposes it.
- Reuse Chat's exported `TextWithCitations` Markdown component and the existing workflow `renderNodeOutput` media/type branches.

## Implementation Status

- **Consistency follow-up**: complete
- **Original stages 1–9**: complete

## Verification

- Focused result renderer tests pass.
- Dispatcher, `useWorkflowRun`, and `VariableForm` tests pass when run in separate Bun processes.
- Modified files pass TypeScript, ESLint, translation checks, and production build.
- Browser/manual visual verification is intentionally left to the user.

## Files

- `frontend/app/(chat)/run/[id]/_components/workflow-run-page.tsx`
- `frontend/app/(chat)/run/[id]/_components/workflow-result-renderer.tsx`
- `frontend/app/(chat)/run/[id]/_components/workflow-result-renderer.test.ts`
- `frontend/components/chat/message.tsx`
- `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer.tsx`

Existing `trigger_config` and `embed_config` are intentionally not reused because their current writers replace their entire object and because they belong to different product domains.

## Implementation Plan

### Stage 1: Planning and regression baseline

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/workflow-form-run-page.md`, focused existing tests.
- **Specific logic**: Register stages and preserve baseline assertions for Agent routing, team-wide workflow logs, and save-before-publish ordering.
- **Validation**: Run focused existing tests before behavioral changes.

### Stage 2: Run-page configuration persistence

- **Files modified**: `backend/app/models/workflow.py`, `backend/app/schemas/workflow.py`, workflow user/admin endpoints, `backend/app/core/init_data.py`, `backend/app/main.py`, package resource service, `frontend/lib/api/workflows.ts`.
- **Specific logic**: Add the JSON field, idempotent startup migration, strict `simple | result_first` validation, API serialization/update support, and package import/export support.
- **Validation**: Verify defaulting, update/read round trips, package portability, and invalid-value rejection.

### Stage 3: Publish settings

- **Files modified**: workflow editor page, new publish dialog, workflow i18n, tests.
- **Specific logic**: Open a standard publish settings dialog, persist presentation mode, then execute the existing save-before-publish flow. Keep unpublish unchanged.
- **Validation**: Verify both modes, existing selection, permissions, keyboard behavior, loading, and failures.

### Stage 4: Published snapshot execution

- **Files modified**: `backend/app/services/workflow/orchestrator.py`, orchestrator/API lifecycle tests.
- **Specific logic**: Use the latest published `WorkflowVersion.definition` for non-debug runs and the live definition for debug runs. Fail fast when a normal run has no published snapshot.
- **Validation**: Prove draft edits do not affect normal runs, debug sees drafts, and missing snapshots fail.

### Stage 5: Personal workflow history

- **Files modified**: workflow endpoints/access helpers, frontend workflow API client, API tests.
- **Specific logic**: Add authenticated mine list/detail/node endpoints. Filter lists by workflow, `current_user.id`, and `is_debug=false`; enforce ownership on details. Preserve existing team log endpoints.
- **Validation**: Test two-user isolation, guessed run IDs, exclusion of debug/system-triggered runs, pagination, and unchanged team logs.

### Stage 6: Route split

- **Files modified**: `frontend/app/(chat)/run/[id]/page.tsx`, new Agent and Workflow components, route tests.
- **Specific logic**: Make the route a thin dispatcher. Mechanically move the Agent implementation. Mount the Workflow implementation without `ChatContainer`, `ChatInput`, or debug query handling.
- **Validation**: Keep all Agent regressions passing and verify only the selected branch fetches data.

### Stage 7: Form execution state

- **Files modified**: `frontend/components/chat/variable-form.tsx`, `frontend/lib/utils/extract-variables.ts`, `frontend/hooks/use-workflow-run.ts`, tests.
- **Specific logic**: Add backward-compatible full-size/disabled/upload-busy form props, preserve typed defaults, render `query` as an ordinary workflow field, and add explicit run states/output/error/cancel state without removing legacy messages.
- **Validation**: Cover every field type, upload constraints/failures, server errors, state transitions, cancellation races, reset/rerun, and legacy hook compatibility.

### Stage 8: Results and history UI

- **Files modified**: Workflow page plus focused result/history components, run i18n, component tests.
- **Specific logic**: Implement responsive `simple` and `result_first` modes, output precedence, live status, progressive trace/details, history pagination and selection, post-run refresh, and accessible loading/error/empty states.
- **Validation**: Cover no-input/no-output workflows, media/JSON output, failures, interrupted streams, partial cancelled output, history reload, and narrow/desktop layouts.

### Stage 9: Final verification

- **Files modified**: synchronized English/Chinese translations, generated i18n types through scripts, plan status, relevant developer docs.
- **Specific logic**: Remove Workflow chat terminology and document new API/behavior conventions.
- **Validation**: Run focused tests, frontend translation generation and strict lint, frontend lint/build, backend Ruff/format/mypy/tests, and manual end-to-end checks.

## Testing Strategy

### Happy paths

- Configure each presentation mode during publish.
- Submit scalar, structured, and file inputs.
- Observe running state and final result.
- Rerun with retained values and reset to defaults.
- Refresh and select a persisted personal history item.

### Error paths

- Missing required values and malformed array/object JSON.
- File size/count/type rejection and upload failure.
- Start validation failure, node failure, stream interruption, cancellation failure/race.
- Normal run without a published snapshot.
- History load/detail failure and cross-user run access.

### Regression scope

- Agent chat run route and conversations.
- Embedded Agent and Workflow runners.
- Workflow editor debug drawer.
- Team Logs and Activities.
- Publish/unpublish and package import/export.
- Existing `VariableForm`, `useRun`, and `useWorkflowRun` consumers.

## Risks & Mitigation

- **Chat-shaped shared hook**: add fields without removing existing messages or event conversion.
- **Duplicate output sources**: centralize precedence as streamed Answer, canonical outputs, output event, last valid node output, then no-output state.
- **Cancellation races**: mark cancelled only after backend confirmation and prevent a late response from overwriting a terminal state.
- **Transport errors**: report interrupted live updates separately from confirmed execution failure; reconcile through personal run detail when needed.
- **History privacy**: enforce ownership on the server for list, detail, and nodes, not only in the UI.
- **Publish partial failure**: report configuration save and publish independently; never report successful publication when only settings saved.
- **Renderer dependency**: reuse the existing node output renderer initially; move it to a shared directory only if build boundaries require it.



## Implementation Status

- **Stage 1**: complete
- **Stage 2**: complete
- **Stage 3**: complete
- **Stage 4**: complete
- **Stage 5**: complete
- **Stage 6**: complete
- **Stage 7**: complete
- **Stage 8**: complete
- **Stage 9**: complete

## Known Follow-ups

- Add dedicated Workflow runner component tests and backend cross-user privacy tests.
- Surface history detail errors and add history pagination beyond the latest ten runs.
- Harden concurrent upload busy-state aggregation.
- Remove the mutable draft non-empty precondition from published snapshot lookup and record publish provenance on workflow versions.
- Run full backend mypy/pytest and manual authenticated E2E in an environment with those services available.
