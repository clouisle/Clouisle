# Conversation Image Reference Pool Design Document

## Background & Goals

Agent media tools currently index only images uploaded with the immediate user message. Historical uploads and generated images are already persisted, but cannot be reused without downloading and uploading them again.

Success means `reference_image_indexes` and `start_image_index` can select all images on the active conversation branch, including images generated earlier in the current tool loop, while preserving one-based chronological ordering.

## High-Level Design

Build one mutable image pool per Agent execution. Populate it from visible user-message `images` and successful `media.image` tool results, then append successful current-round generation results immediately. Pass only a compact numbered inventory to the chat model; resolve image bytes only when a media tool selects an index.

Existing persistence remains unchanged:

- uploaded images: `Message.images`
- generated images: tool `Message.content` containing `kind: media.image`

## Implementation Plan

### Stage 1: Image pool helpers

- **Files modified**: `backend/app/api/v1/endpoints/chat_helpers/general.py`
- Collect usable uploaded/generated image objects in chronological order.
- Ignore malformed, failed, non-image, or source-less tool results.
- Build inventory text containing index, origin, and short context without Base64 or file paths.
- Append successful generated images to the mutable pool during a tool loop.
- **Validation**: unit-test ordering, filtering, append behavior, and inventory privacy.

### Stage 2: Chat execution integration

- **Files modified**: `backend/app/api/v1/endpoints/chat.py`
- Construct the pool from the active branch or operation-specific prefix for normal, streaming, edit, and regenerate flows.
- Pass the pool through every `execute_tool_call()` invocation.
- Refresh inventory metadata after current-round generation.
- **Validation**: test active-branch isolation, no duplicate current upload, and same-round reuse.

### Stage 3: Persisted asset resolution

- **Files modified**: `backend/app/llm/tools/builtin/media.py`
- Recognize backend upload URLs and safely resolve them below the upload root using existing traversal protection.
- Require an existing regular file; do not fetch arbitrary relative URLs.
- Update media-tool descriptions to describe available conversation images.
- **Validation**: test valid generated asset, missing file, traversal, and existing Data URL behavior.

### Stage 4: Verification and completion

- **Files modified**: focused backend tests and `docs/IMPLEMENTATION_PLAN.md`
- Run focused pytest, Ruff, formatting, and changed-file mypy checks.
- Manually verify historical upload, historical generation, same-round generation, edit branch, and regeneration scenarios.
- Mark the implementation checklist complete only after validation.

## Testing Strategy

- Happy paths: current upload, historical upload, historical generation, same-round generation, video start image.
- Error paths: malformed tool JSON, failed generation, source-less image, missing generated file, traversal, out-of-range index.
- Regression scope: streaming/non-streaming chat, edit/regenerate branching, media tool rendering, direct Base64 references.

## Risks & Mitigation

- Wrong model-selected index: deterministic chronological ordering plus concise numbered inventory.
- Inactive branch leakage: reuse existing visible-branch/prefix helpers.
- Large context: inventory metadata only; no historical image bytes in chat context.
- Unsafe local path access: recognize only backend upload routes and reuse `_resolve_upload_path()`.
- Rollback: restore immediate-message-only pools; no schema or stored-data changes are required.
