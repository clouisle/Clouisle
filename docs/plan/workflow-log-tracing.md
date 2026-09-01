# Workflow Log Trace Design Document

## Background & Goals

Workflow logs retrieve ordered `NodeExecution` records but currently reduce each record to a summary. The test-run drawer displays a per-node trace with expandable structured results, so historical logs do not provide equivalent diagnostic context.

Success criteria:
- Opening a historical workflow run exposes a trace in recorded execution order.
- Each node has its status, timing, token usage, model (when present), error, recorded inputs/configuration, and rendered output available on demand.
- Node-specific outputs use the existing test-run renderer, preserving Agent artifacts/dialogue and media previews.
- No execution, persistence, authorization, or SSE protocol changes are introduced.

## High-Level Design

`NodeExecutionOut` already returns the durable execution metadata required by the log drawer. The dashboard drawer will add a Trace tab beside its run-level inputs and outputs. It will map each returned `NodeExecution` into an expandable trace card. Cards use `execution_order` as the chain order, existing status semantics, and the existing `renderNodeOutput` function that the test-run drawer already uses.

This keeps live test traces event-driven and historical traces persistence-driven while making their detailed output surface consistent.

## Implementation Plan

### Stage 1: Persisted trace contract review
- **Status**: Complete
- **Files modified**: none.
- **Specific logic**: Confirm that the existing node-execution endpoint supplies order, state, timing, optional inputs/configuration, outputs, model, token metrics, and sanitized errors.
- **Validation**: Review the endpoint schema and lifecycle persistence paths.

### Stage 2: Historical trace presentation
- **Status**: Complete
- **Files modified**: `frontend/app/(dashboard)/activities/_components/workflow-run-drawer.tsx`.
- **Specific logic**: Add a Trace tab that renders each `NodeExecution` as an ordered, expandable step. Reuse `renderNodeOutput` for typed output rendering; preserve run-level summary and inputs/outputs tabs.
- **Validation**: Component tests assert ordered trace metadata, expandable details, errors, empty traces, and specialized outputs.

### Stage 3: Regression coverage and documentation
- **Status**: Complete
- **Files modified**: `frontend/app/(dashboard)/activities/_components/workflow-run-drawer-issue255.test.tsx`, `docs/IMPLEMENTATION_PLAN.md`, this document.
- **Specific logic**: Cover the persisted trace contract and record the implementation decision; do not introduce backend compatibility paths.
- **Validation**: Run targeted Bun tests, TypeScript, ESLint, i18n lint if translations change, and repository diff checks.

## Testing Strategy

- Happy path: an ordered successful trace renders its node metadata and specialized output.
- Error path: failed node displays the sanitized stored error; empty runs display the existing empty trace state.
- Regression: run-level details, deletion permission gating, and test-run output rendering remain intact.

## Risks & Mitigation

- Historical records can predate optional detail fields. Render each section only when its persisted value is present.
- Outputs can be structured or media-bearing. Reuse the established output renderer rather than stringifying it differently.
- The trace must not reveal raw internal tracebacks. Continue consuming only sanitized `error_message` returned by the current endpoint.

## Rollback Plan

Remove the Trace tab and its view without changing persisted runs or API contracts.
