# YUN-107 Media Workflow Design Document

## Background & Goals
- Text-to-image and text-to-video already exist as builtin media tools for Agents.
- Workflow tool nodes can call builtin tools, but generated media is only available as an opaque `result`, making downstream display/reference flows unclear.
- Goal: make workflow executions expose generated media artifacts, statuses, and failure details in a stable shape while preserving existing Agent, knowledge base, and base workflow behavior.

Success criteria:
- A workflow tool node invoking `generate_image` or `generate_video` exposes the original result plus first-class media metadata.
- Downstream workflow nodes can reference generated artifacts through predictable output variables.
- Failed media generation remains retry-ready by returning status/error outputs while still marking the node failed for workflow status display.
- Existing non-media tool node behavior remains compatible.

## High-Level Design
- Reuse existing builtin media tools instead of adding a separate node family.
- Extend `ToolNodeExecutor` to detect structured media tool payloads (`display_result.kind` = `media.image` / `media.video`).
- Normalize workflow outputs:
  - `result`: original tool result
  - configured `outputVariable`: original tool result
  - `status`: `success` / `error` based on media success
  - `mediaKind`: `image` or `video`
  - `artifact`: first generated image/video object
  - `artifacts`: all generated image/video objects
  - `error`: user-visible media error when present
- Add typed output declarations for the extra media fields only when the selected builtin tool is media generation.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-107-media-workflow.md`
- **Specific logic**: Register this issue and record the implementation/test stages before code changes.
- **Validation**: Re-read the plan entries and confirm the new issue is tracked.

### Stage 2: Workflow media result normalization
- **Files modified**: `backend/app/services/workflow/executors/tool.py`
- **Specific logic**: Add small helper methods to identify media tool results and append media-specific outputs without altering non-media tool execution.
- **Validation**: Unit tests for image success, video pending/success, media failure, and non-media compatibility.

### Stage 3: Typed output specs
- **Files modified**: `backend/app/services/workflow/executors/tool.py`, `backend/tests/services/workflow/test_output_schema.py`
- **Specific logic**: Add `mediaKind`, `artifact`, `artifacts`, and `error` declarations for `generate_image` / `generate_video` builtin tool configs.
- **Validation**: Output schema tests assert media tool nodes publish stable object/array/string specs.

### Stage 4: Regression tests and validation
- **Files modified**: `backend/tests/services/workflow/test_tool_executor_compat.py`
- **Specific logic**: Mock builtin media tool responses and assert workflow outputs are referenceable/displayable.
- **Validation**: Run focused pytest for workflow tool executor and schema tests, then run ruff on touched backend files.

## Testing Strategy
- Happy path tests: image and video media tool outputs expose artifacts and media status.
- Error path tests: media tool payload with `success: false` exposes `status=error`, `error`, and an `ExecutionResult.error`.
- Regression scope: existing custom/builtin non-media tool output compatibility must remain unchanged.

## Risks & Mitigation
- Risk: Frontend may still render only `result` until workflow result UI is enhanced. Mitigation: preserve `result` and output variable as the full existing media payload while adding stable artifact fields.
- Risk: Some providers return pending video tasks without a video URL. Mitigation: expose `requires_polling`, `task_id`, and `status` inside `result` while keeping `artifact=None` and `artifacts=[]`.
- Rollback plan: remove the helper methods and media-specific output specs; non-media tool behavior is isolated.
