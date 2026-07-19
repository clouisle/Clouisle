# YUN-107 Media Generation Integration Design Document

## Background & Goals
- Problem to solve: Agent chat uploaded images were not consistently passed into media tool execution, so image generation could not use them as references. Workflow also lacked a first-class image/video generation node.
- Success criteria:
  - Agent media tools receive uploaded/current images through the shared executor path.
  - Workflow has a dedicated `media_generation` node that reuses existing `generate_image` / `generate_video` behavior.
  - Image/video outputs keep the existing normalized media result shape and render in workflow run output.
  - English and Chinese workflow UI strings stay in sync.

## High-Level Design
- Backend Agent path: keep the current shared media tool implementation and only thread `current_images` through the helper executor boundary.
- Backend Workflow path: add a thin `media_generation` node executor registered through the existing workflow executor registry. It resolves prompt/model/image variables and delegates to the existing media tool functions.
- Frontend Workflow path: add a dedicated React Flow node, config panel, validator support, output rendering, palette registration, and i18n strings.
- Data flow: uploaded image or upstream image variable → executor resolves it to the media tool input contract → shared media generation returns `media.image` / `media.video` → workflow output renderer uses shared tool-result helpers.

## Implementation Plan

### Stage 1: Agent image context plumbing
- **Files modified**: `backend/app/api/v1/endpoints/chat_helpers/tool_executor.py`, `backend/tests/services/test_chat_tool_executor.py`
- **Specific logic**: Add `current_images` to the helper `execute_tool_call` signature and forward it to the shared chat tool executor without reordering or rewriting the list.
- **Validation**: Targeted pytest proves the helper forwards `current_images` and registered tools receive it.

### Stage 2: Workflow media executor
- **Files modified**: `backend/app/services/workflow/executors/media_generation.py`, `backend/app/services/workflow/executors/__init__.py`, `backend/tests/services/workflow/test_media_generation_executor.py`, `backend/tests/services/workflow/test_output_schema.py`
- **Specific logic**: Register a `media_generation` executor that supports `image` and `video` modes, resolves configured model references, resolves reference/start image variables, and delegates to `generate_image` / `generate_video`.
- **Validation**: Targeted pytest covers image reference resolution, video start-image conversion, and output schema override.

### Stage 3: Workflow editor integration
- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/page.tsx`, workflow node/config/drawer/validator/output renderer files under `_components/`, `frontend/lib/utils/tool-result.ts` only as existing helper reference.
- **Specific logic**: Add the `media_generation` node card, config panel, node palette entry, config persistence, validation rules, and media output rendering using existing tool-result helpers.
- **Validation**: Frontend lint and production build.

### Stage 4: i18n and generated types
- **Files modified**: `frontend/i18n/en/workflow.json`, `frontend/i18n/zh/workflow.json`, `frontend/i18n/types/*.ts`
- **Specific logic**: Add synchronized English/Chinese labels, descriptions, config labels, and validation messages for media generation; regenerate i18n types.
- **Validation**: JSON validation and i18n type generation.

## Testing Strategy
- Happy path tests:
  - Agent helper forwards uploaded images into media tool execution.
  - Workflow image mode passes resolved reference images to `generate_image`.
  - Workflow video mode passes a resolved start image as `current_images` with `start_image_index=1`.
  - Workflow output schema exposes normalized media result fields.
- Error path tests:
  - Validator rejects missing model, empty prompt, invalid mode, missing upstream image variable, and invalid output variable name.
- Regression scope:
  - Existing workflow output schema tests.
  - Existing chat tool executor behavior.
  - Frontend workflow editor build and lint.

## Risks & Mitigation
- Possible side effect: workflow model IDs may refer to either `TeamModel` or base `Model`. Mitigation: executor falls back to base model lookup.
- Possible side effect: frontend generated type files update broadly. Mitigation: use the existing generator instead of manual edits.
- Possible side effect: provider-specific media limitations remain. Mitigation: this change reuses existing media tool validation and provider behavior instead of bypassing it.
- Rollback plan: remove the `media_generation` executor registration and frontend node registration; Agent plumbing can be reverted independently because it only adds an optional parameter.
