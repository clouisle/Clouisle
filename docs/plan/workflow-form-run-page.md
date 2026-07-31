# Workflow Form Run Page Design Document

## Background & Goals

The current `/run/[id]?type=workflow` route reuses the Agent chat shell. Workflow parameters are split between a collapsible variable panel and a chat input, and each discrete run is displayed as another message exchange. This obscures structured inputs, execution state, results, and persisted run history.

This change will:

- Replace only the Workflow branch with a form-first runner while preserving Agent chat behavior.
- Let the workflow creator select the published run-page presentation:
  - `simple`: form, status, and result only.
  - `result_first`: result first, with progressively disclosed trace and details.
- Show persistent history limited to the current user's non-debug runs for that workflow.
- Ensure the external run page always executes the latest published workflow snapshot.
- Keep editor draft/debug execution in the existing editor runner.

Success means a user can submit typed inputs, understand the active state and final result, revisit their runs after refresh, and never see another member's inputs or outputs.

## High-Level Design

### Modules and data flow

1. `/run/[id]` dispatches to an Agent or Workflow component based on `type`; invalid or missing types retain the Agent default.
2. The Agent component mechanically preserves the current metadata, conversation, chat, variable, and input behavior.
3. The Workflow component loads workflow metadata and `run_page_config`, uses `extractVariables` plus `useVariableForm`, and calls `useWorkflowRun` directly.
4. `useWorkflowRun` continues producing legacy chat-compatible messages for existing consumers, while adding explicit status, outputs, submitted-input snapshots, safe errors, and confirmed cancellation for the form page.
5. SSE events update the live result and optional trace. Completion refreshes the first page of the user's persistent history.
6. Personal history endpoints derive ownership from the authenticated user and enforce ownership on list, detail, and node-detail access.
7. Normal orchestration resolves the latest `WorkflowVersion` snapshot; debug orchestration resolves the live draft.

### Page structure

Desktop uses a centered `max-w-6xl` task layout with an input column and a larger result/history column. Mobile stacks inputs, current result, then history. No chat bubbles, assistant welcome copy, suggested prompts, or fixed-width drawers are used.

The `simple` presentation never requests or reveals node details. The `result_first` presentation defaults to the result and exposes Trace and Details through standard tabs or collapsibles. Both modes include personal history, with detail loaded on selection.

### Persistence

Add `run_page_config` as a dedicated JSON field with the default:

```json
{"presentation_mode": "simple"}
```

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

Rollback is additive: the Workflow route can return to the existing chat branch, older code can ignore `run_page_config`, and new personal endpoints can be removed without changing team history semantics. The published-snapshot execution correction should remain an independent commit because reverting it restores a correctness defect.
