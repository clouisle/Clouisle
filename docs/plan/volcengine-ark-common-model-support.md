# Volcengine Ark Common Model Support Design Document

## Background & Goals

Clouisle already identifies Volcengine Ark with provider code `volcengine` and supports OpenAI-compatible chat plus Seedance task APIs. The model-management UI does not expose the provider across its supported categories, text embeddings reject it, Seedream has no adapter, and the Seedance adapter uses an outdated request/response shape.

Success criteria:

- the provider appears as **火山方舟 / Volcengine Ark** for chat, text embedding, rerank, image, and video models;
- administrators configure a current Ark Model ID or `ep-...` Endpoint ID, Ark API key, and optional base URL without a hard-coded catalog;
- chat and rerank keep their existing OpenAI-compatible implementations;
- text embeddings use Ark's OpenAI-compatible `/embeddings` API;
- Seedream images and Seedance videos use their documented Ark request/response contracts;
- generated temporary URLs continue through the existing durable media normalization pipeline.

## High-Level Design

Keep the existing `volcengine` provider, default base URL `https://ark.cn-beijing.volces.com/api/v3`, generic credential schema, and shared model-management form. Add only the missing capability routes:

1. `OpenAIEmbeddings` for text embedding.
2. A dedicated Seedream image adapter backed by the shared `VolcengineClient`.
3. Current Seedance top-level parameters and compatible response parsing in the existing video adapter.

Chat continues through `OpenAICompatibleAdapter(provider_hint="volcengine")`; rerank remains the existing LLM-based reranker. Multimodal embeddings are out of scope because the current embedding abstraction accepts text strings only.

## Data Flow

- Model administration stores `provider=volcengine`, Model ID/Endpoint ID, API key, optional base URL, and provider defaults.
- Chat, embedding, image, and video factories select the adapter based on model type.
- Seedream returns shared `ImageGenerationResponse` objects and Seedance returns shared `VideoGenerationResponse` objects.
- Existing media normalization copies URL/base64 output into configured application storage before Agent or Workflow callers consume it.

## Implementation Plan

### Stage 1: Provider exposure and naming

- **Files modified**: `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, `frontend/i18n/en/models.json`, `frontend/i18n/zh/models.json`
- Add `volcengine` to the domestic group and the text, rerank, image, and video allowlists, excluding audio.
- Display `火山方舟` and `Volcengine Ark` while retaining the internal provider code.
- Preserve Seedream named sizes (`1K` to `4K`) in `default_params.size`; numeric sizes continue to use width/height defaults for other adapters.
- **Validation**: translation lint, frontend lint, production build.

### Stage 2: Text embedding support

- **Files modified**: `backend/app/llm/adapters/embedding/factory.py`, focused backend tests
- Route Volcengine through the existing `OpenAIEmbeddings` branch with Ark's default base URL and explicit-base-URL override.
- Keep `check_embedding_ctx_length=False` and text-only inputs.
- **Validation**: factory tests for default and custom URLs and existing compatible-provider regressions.

### Stage 3: Seedream image generation

- **Files modified**: `backend/app/llm/adapters/image/volcengine.py`, image factory, shared Volcengine client, media-adapter tests, locale catalogs when a new error key is necessary
- POST to `/images/generations` with bearer authentication.
- Map prompt, Model ID/Endpoint ID, named size, seed, reference image(s), output settings, watermark, and optional sequential-generation controls.
- Parameter precedence is explicit request field, request `extra_params`, model defaults, then adapter fallback.
- Parse URL and base64 `data[]` items into shared image types; fail on empty or unusable output.
- **Validation**: mocked request payloads, reference inputs, URL/base64 outputs, sequential controls, invalid inputs, provider errors.

### Stage 4: Seedance compatibility

- **Files modified**: `backend/app/llm/adapters/video/volcengine.py`, media-adapter tests
- Send `ratio`, `duration`, and `seed` at the top level rather than under `parameters`.
- Keep start-image content and allow supported extras without permitting overrides of `model` or generated `content`.
- Parse the current object-shaped `content.video_url` and retain legacy list/object variants.
- Map failed, cancelled, and expired terminal states; never treat completed-without-URL as a valid result.
- **Validation**: current/legacy response shapes, top-level payloads, precedence, references, terminal errors.

### Stage 5: Final checks and documentation

- **Files modified**: this document and `docs/IMPLEMENTATION_PLAN.md`
- Confirm generic model connection-test dispatch reaches all new adapters without a new endpoint or schema.
- Run focused backend tests, backend lint/format/type checks, frontend translation/lint/build checks, and `git diff --check`.
- Do not use browser automation.

## Request Mapping

### Seedream

| Clouisle input | Ark field |
|---|---|
| configured model ID | `model` |
| prompt | `prompt` |
| default/extra named resolution | `size` |
| request seed | `seed` |
| reference images | `image` |
| output format | `output_format` |
| watermark option | `watermark` |
| sequential mode/options | `sequential_image_generation`, `sequential_image_generation_options` |

### Seedance

| Clouisle input | Ark field |
|---|---|
| configured model ID | `model` |
| prompt and optional start image | `content[]` |
| aspect ratio | `ratio` |
| duration | `duration` |
| seed | `seed` |
| supported provider extras | top-level fields |

## Testing Strategy

- Happy paths: chat regression, text embedding, text-to-image, reference-to-image, text-to-video, image-to-video, URL/base64 image outputs, current and legacy video results.
- Error paths: invalid credentials through existing provider errors, malformed image options, empty image output, failed/cancelled/expired video tasks, completed video without URL.
- Regression scope: other OpenAI-compatible providers, other image/video adapters, model create/edit/test flows, and media persistence.

## Risks & Mitigation

- **Model-version option differences**: accept administrator-entered model IDs and provider JSON instead of maintaining a catalog.
- **Temporary media URLs**: reuse existing immediate storage normalization.
- **Changing Ark response shapes**: support the documented shape first and narrowly retain historical variants.
- **Rollback**: remove frontend allowlist entries and the new factory branches, then restore the previous Seedance mapper; no schema rollback is required.

## Deliberate Exclusions

- Multimodal embeddings, sparse vectors, and embedding instructions.
- Native Ark rerank API.
- Model presets/catalogs and Access Key request signing.
- New provider identifiers, migrations, dependencies, or credential forms.
