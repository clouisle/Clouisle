# Agent Reference Image Inputs Design Document

## Background & Goals

Agent chat can already send uploaded images to vision-capable chat models, and the image-generation tool already has a low-level `images` input. The missing link is letting the Agent select the correct uploaded chat image and pass it to generation safely.

Success criteria:

- Uploaded chat images are visible to the LLM with stable 1-based labels.
- `generate_image` can reference selected uploaded images through indexes instead of receiving every upload.
- Selected chat images are converted to base64-backed `ImageContent`, not local or private URLs.
- Existing text-only image generation and explicit `images` tool inputs keep working.
- Video reference-image support remains explicitly out of scope for this patch.

## High-Level Design

The current chat request persists images on the user message and passes them into `build_vision_content()`. This change adds labels beside those image parts, passes the current image list as hidden tool context, and lets `generate_image` resolve `reference_image_indexes` into provider-safe image references.

Flow:

1. User uploads images in chat.
2. Chat context presents them as `Uploaded image #N:` plus image content.
3. The LLM calls `generate_image` with `reference_image_indexes` for only the images it needs.
4. The backend resolves those indexes against current chat images.
5. Data URLs are converted to `ImageContent(base64=..., format=...)` before `model_manager.generate_image()`.

## Implementation Plan

### Stage 1: Uploaded image labels and tool context

- **Files modified**: `backend/app/services/chat_context.py`, `backend/app/api/v1/endpoints/chat_tools.py`, `backend/app/api/v1/endpoints/chat.py`
- **Specific logic**:
  - Add `Uploaded image #N:` text markers before each image part in `build_vision_content()`.
  - Preserve MIME-derived format when converting data URLs to base64 `ImageContent`.
  - Add optional `current_images` to `execute_tool_call()` and pass it through `tool_registry.execute()`.
  - Pass `chat_in.images` at all chat tool execution call sites.
- **Validation**: Unit test context/tool forwarding and inspect generated tool call execution inputs.

### Stage 2: Image generation indexed reference resolution

- **Files modified**: `backend/app/llm/tools/builtin/media.py`
- **Specific logic**:
  - Add `reference_image_indexes` and hidden `current_images` parameters to `generate_image()`.
  - Add tool schema guidance for indexed references.
  - Resolve 1-based indexes, deduplicate, validate range, and convert selected data URLs to base64 `ImageContent`.
  - Keep explicit `images` compatibility, but make explicit `images` and indexes mutually exclusive.
  - Apply existing `allow_reference_images` behavior to both forms.
- **Validation**: Mock `model_manager.generate_image()` and assert only selected images are passed as base64 references.

### Stage 3: Localized errors

- **Files modified**: `backend/app/core/i18n_legacy.py`, `backend/app/locales/en/LC_MESSAGES/messages.po`, `backend/app/locales/zh/LC_MESSAGES/messages.po`
- **Specific logic**:
  - Add localized errors for conflicting reference inputs, missing uploads, out-of-range indexes, and unusable uploaded images.
- **Validation**: Tool-level tests assert localized errors appear in media tool failure payloads.

### Stage 4: Tests and validation

- **Files modified**: `backend/tests/llm/test_media_builtin_tools.py`, `backend/tests/services/test_chat_tool_executor.py`
- **Specific logic**:
  - Cover data URL format parsing, index selection, deduplication, validation failures, and current image context forwarding.
- **Validation**:
  - `uv run pytest backend/tests/llm/test_media_builtin_tools.py backend/tests/services/test_chat_tool_executor.py`
  - `uv run ruff check` on touched backend Python files.

### Stage 5: Video start-image entrypoint

- **Files modified**: `backend/app/llm/types/video.py`, `backend/app/llm/tools/builtin/media.py`, `backend/app/llm/adapters/video/*`, backend i18n catalogs
- **Specific logic**:
  - Add `VideoGenerationRequest.start_image` for a selected uploaded image used as a first-frame/reference input.
  - Add `generate_video(start_image_index=...)` so the Agent can express a video reference-image intent with the same indexed upload mechanism.
  - Resolve the selected chat upload to base64 `ImageContent`; do not pass local/private URLs.
  - Add a shared video adapter guard that returns a localized unsupported error when a provider receives `start_image` but has not implemented support.
- **Validation**:
  - Tool tests cover start image selection and explicit unsupported-provider failure.
  - Existing text-only video generation remains unchanged.

### Stage 6: SiliconFlow video start-image support

- **Files modified**: `backend/app/llm/adapters/video/siliconflow.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Enable `VideoGenerationRequest.start_image` only for documented SiliconFlow I2V models.
  - Convert `ImageContent` to a data URI and send it as the `/video/submit` `image` field.
  - Keep text-to-video payloads unchanged and keep unsupported errors for non-I2V models.
- **Validation**: Unit test payload construction with a base64 data URI and confirm text-only SiliconFlow generation omits `image`.

### Stage 7: Runway video start-image support

- **Files modified**: `backend/app/llm/adapters/video/runway.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Branch `_build_request()` to use Runway image-to-video when `start_image` is present.
  - Send the selected image as `promptImage` using a data URI and validate against documented image-to-video model IDs.
  - Keep generic task polling through the existing Runway client.
- **Validation**: Unit test endpoint selection, `promptImage` data URI payloads, unsupported model rejection, and unchanged text-to-video requests.

### Stage 8: DashScope video start-image support

- **Files modified**: `backend/app/llm/adapters/video/dashscope.py`, `backend/app/llm/adapters/dashscope_video_client.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Add an image-to-video request branch for Wan I2V models.
  - Send the selected image as `input.img_url` using a `data:{mime};base64,...` value.
  - Preserve the existing text-to-video endpoint and async status handling.
- **Validation**: Unit test the I2V endpoint/payload branch, invalid model failure, and unchanged text-only DashScope payloads.

### Stage 9: Kling video start-image support

- **Files modified**: `backend/app/llm/adapters/video/kling.py`, `backend/app/llm/adapters/kling_client.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Branch from `/v1/videos/text2video` to the documented image-to-video endpoint when `start_image` is present.
  - Send the selected image in the documented image field as provider-compatible base64.
  - Update status polling so it uses the matching text-to-video or image-to-video task path.
- **Validation**: Unit test create/status path selection, image base64 payloads, and text-to-video regression behavior.

### Stage 10: Luma video start-image support

- **Files modified**: `backend/app/llm/adapters/video/luma.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Treat direct Luma as URL-only because its current API requires CDN image URLs for keyframes.
  - Do not send base64 chat uploads directly to Luma.
  - Add support only when a selected image can be converted to an approved public asset URL; otherwise keep the localized unsupported failure.
- **Validation**: Unit test that base64-only chat uploads still fail clearly, and that a supported public URL path builds `keyframes.frame0` when the prerequisite asset flow exists.

### Stage 11: Pika video start-image support

- **Files modified**: `backend/app/llm/adapters/video/pika.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Send `start_image` as a provider-safe data URI in the direct Pika `image_url` field by default.
  - Allow `config.start_image_field` to override the field name for deployments whose Pika-compatible endpoint expects a different key.
  - Keep text-to-video payloads unchanged when no `start_image` is present.
- **Validation**: Unit tests assert default `image_url` payload construction and configured field override behavior.

### Stage 12: Volcengine video start-image support

- **Files modified**: `backend/app/llm/adapters/video/volcengine.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - Use the existing Volcengine content-array request shape for Seedance-style multimodal input.
  - Add the selected image as an `image_url` content item with a provider-safe data URI.
  - Keep existing text content payloads unchanged.
- **Validation**: Unit test the image content payload and unchanged text-only Volcengine payloads.

## Testing Strategy

Happy path:

- One selected uploaded data URL becomes one base64 `ImageContent`.
- Multiple selected indexes preserve user order after deduplication.
- Text-only image generation still sends no references.
- Existing explicit `images` input still works.

Error path:

- Both explicit `images` and `reference_image_indexes` are rejected.
- Out-of-range reference indexes are rejected.
- Indexes without current uploaded images are rejected.
- Invalid uploaded image data is rejected.

Regression scope:

- Existing chat vision messages still include image content.
- Existing media tool result rendering is unchanged.
- Existing video generation behavior is unchanged.

## Risks & Mitigation

- The LLM may still omit indexes. Mitigation: add clear image labels and tool parameter guidance; do not auto-inject all images.
- Some image providers ignore `request.images`. Mitigation: keep provider scope unchanged and rely on existing Google/SiliconFlow support first.
- Base64 references can be large. Mitigation: pass only selected indexes, not every uploaded image.
- Video references are provider-specific. Mitigation: do not enable them until the video request schema and adapters support explicit semantics.

Rollback plan:

- Remove `reference_image_indexes` from `generate_image` schema/signature.
- Stop forwarding `current_images` from chat execution.
- Revert image labels and MIME format preservation in `build_vision_content()`.
