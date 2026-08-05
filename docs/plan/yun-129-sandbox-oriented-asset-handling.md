# YUN-129 Sandbox-Oriented Asset Handling Design Document

## Background & Goals

Chat uploads are stored as raw files, but context preparation later assumes document URLs should be parsed and injected as Markdown. Images use a separate URL and positional-index mechanism, while Sandbox input uses repeated base64 payloads and Sandbox artifacts are not reusable through the image-reference path. These parallel representations prevent one file from being safely reused across understanding, generation, parsing, Sandbox operations, and workflow boundaries.

This change introduces one durable Asset abstraction above the existing upload storage backend. Raw content remains authoritative; parsing and other projections happen only when needed. Agent Chat and its conversation Sandbox are the first integration target. Workflow execution receives a compatible `AssetRef` contract but broad node migration is deferred.

### Success criteria

- Uploaded, generated, and Sandbox-exported content is represented by authorized durable Assets.
- Uploading a document no longer automatically parses it into the prompt.
- The model uses stable four-character lowercase hexadecimal references scoped to a conversation; users continue to use filenames, natural language, and UI selection.
- Non-Sandbox Agents can inspect, read, or parse supported Assets on demand.
- Sandbox Agents can materialize authorized Assets without repeated base64 staging and export reusable Assets.
- Uploaded, generated, and Sandbox-created images can move between vision, generation reference, Sandbox, and display paths.
- Legacy `images`, `file_urls`, and `reference_image_indexes` remain compatible during rollout.

## High-Level Design

### Asset identity and persistence

A normalized Asset stores an internal UUID, owner/team scope, storage key, original/display filename, MIME type, size, SHA-256, source kind, availability status, retention timestamps, provenance, and optional parent Asset. Message/conversation relations record when an Asset was attached or produced. A durable scope binding maps an Asset to a unique four-character model reference within one conversation or workflow run.

The UUID is authoritative, SHA-256 validates content and keys parser caches, URL is a presentation/download projection, and Sandbox path is an execution projection. The four-character reference is neither a global identifier nor a security token. Resolution always combines scope, caller authorization, status, and requested capability.

### Relevant Asset Manifest

Each Agent turn receives only a bounded manifest assembled from current attachments, explicit UI selections, recent generated/Sandbox outputs, exact filename candidates, and a small recent-active set. Entries contain the four-character reference, short filename/type/size/origin context, and capability flags. URLs, UUIDs, raw content, and full historical inventories are excluded.

The model maps phrases such as “the image I just uploaded” to a visible manifest entry, then invokes tools with its exact reference. Tools never fuzzy-match names. Ambiguous candidates cause a clarification request.

### On-demand projections

File upload enables trusted `inspect_asset`, `read_asset`, and `parse_asset` tools. They accept exact scoped references, enforce authorization and bounded output, and reuse `FileParserService` only when called. A parsed representation is derived/cacheable data and never replaces the raw Asset.

An explicit Agent Sandbox capability controls broad file support. Authorized Assets are streamed/copied from `UploadStorageBackend` into paths resolved by `SandboxWorkspaceManager`, with checksum, quota, symlink, escape, overwrite, and partial-file protections. Conversation workspaces retain an Asset/path binding manifest for reuse and rehydration. Sandbox artifacts and generated media are registered through the same Asset service.

### Image lifecycle

Uploaded image Assets can project to model vision or image-generation inputs. The generation tool prefers `reference_image_refs` and temporarily supports positional indexes as a deprecated adapter. Generated media normalization and Sandbox artifact collection register image Assets with lineage and structured display/model outputs, closing the loop for later vision, generation, or Sandbox use.

## Implementation Plan

### Stage 1: Durable Asset Domain and Scoped References

- **Files modified**: new Asset models and migration, new Asset service/repository and schemas, `backend/app/models/agent.py`, upload-storage/media helpers.
- **Specific logic**:
  - Add Asset, message/conversation association, lineage, and scoped-reference records.
  - Add uniqueness constraints for scope/reference and scope/Asset mappings.
  - Generate lowercase four-hex references, detect collisions, and retry while preserving four characters.
  - Implement register, authorize, resolve, read/stream, derive, expire, and delete boundaries above `UploadStorageBackend`.
  - Define reusable `AssetRef` and capability metadata schemas.
- **Validation**:
  - Apply migration to empty and representative databases.
  - Verify stable mappings, forced collision retries, duplicate checksum behavior, invalid ownership, expired/deleted resolution, and unsupported capabilities.

### Stage 2: Raw Uploads, Chat Attachments, and Manifests

- **Files modified**: `backend/app/api/v1/endpoints/upload.py`, `chat.py`, `chat_tools.py`, `chat_helpers/general.py`, relevant request/response schemas, frontend upload/chat API types and `frontend/hooks/use-chat.ts`.
- **Specific logic**:
  - Register uploaded raw files and associate requested Assets with messages/conversations.
  - Return Asset attachment metadata while retaining legacy URL fields.
  - Stop implicit MarkItDown/custom-parser execution for new Asset requests and stop automatic `{{fileContent}}` injection.
  - Retain legacy request translation and explicit parse endpoints during migration.
  - Build the bounded relevant Asset Manifest and allocate references on first exposure.
- **Validation**:
  - Confirm document upload does not invoke a parser or add file content to the prompt.
  - Verify legacy `files`/`file_urls` requests and historical messages still load.
  - Reject foreign, missing, over-limit, and unavailable Asset attachments.

### Stage 3: On-Demand Asset Tools and Image References

- **Files modified**: new Asset tool module/registry, `backend/app/api/v1/endpoints/chat_helpers/tool_executor.py`, `general.py`, `backend/app/llm/tools/builtin/media.py`, tool descriptions, i18n resources.
- **Specific logic**:
  - Register trusted inspect/read/parse tools when upload capability is enabled.
  - Resolve only exact conversation references and return bounded model summaries plus structured display metadata.
  - Invoke `FileParserService` or the configured custom parser only from `parse_asset`.
  - Add preferred `reference_image_refs` handling and retain `reference_image_indexes` as a compatibility adapter.
- **Validation**:
  - Verify cross-turn ref stability and exact-scope resolution.
  - Cover malformed/unknown refs, wrong scope, deleted Assets, unsupported text/image capabilities, truncation, and custom parser errors.
  - Verify old generation calls still resolve positional indexes.

### Stage 4: Conversation Sandbox Materialization and Artifact Assets

- **Files modified**: `backend/app/services/sandbox/models.py`, `gateway.py`, `manager.py`, `workspace.py`, `artifacts.py`, `session_store.py`, `backend/app/llm/tools/sandbox_files.py`, chat session creation.
- **Specific logic**:
  - Bind ordinary chat Sandbox sessions to `conversation_id` while preserving agent/team checks.
  - Add reference-based input specifications and streaming storage materialization; retain base64 inputs for compatibility.
  - Persist Asset/path/checksum bindings and rehydrate lost workspaces from durable storage.
  - Register collected files/directories as Assets and preserve Sandbox/session/path provenance.
  - Return Asset refs and structured metadata alongside current artifact URL fields.
- **Validation**:
  - Exercise upload-to-Sandbox, repeated-turn reuse, workspace recreation, and Sandbox-output reuse.
  - Fail closed on unauthorized sources, checksum/size mismatches, path escape, symlink, quota, duplicate target, partial copy, and artifact limits.

### Stage 5: Frontend Capability and Reference UX

- **Files modified**: `frontend/lib/api/upload.ts`, `frontend/lib/api/agents.ts`, `frontend/hooks/use-chat.ts`, `frontend/components/chat/chat-input.tsx`, `types.ts`, `message.tsx`, `frontend/lib/utils/tool-result.ts`, run-page send plumbing, i18n resources and generated types.
- **Specific logic**:
  - Carry Asset attachment identity while preserving URL-based display compatibility.
  - Drive allowed file types and limits from backend capabilities rather than duplicated extension constants.
  - Render filename/source and add explicit “use as reference” selection for generated or Sandbox images.
  - Send explicit Asset selection, never guessed indexes or user-entered internal identifiers.
- **Validation**:
  - Cover upload, reference selection, generated/Sandbox image reuse, legacy messages/results, unavailable assets, mobile rendering, download, and lightbox behavior.
  - Regenerate i18n types and run translation lint.

### Stage 6: Workflow Boundary, Migration, and Rollout

- **Files modified**: workflow input/output schemas and adapters, `frontend/lib/api/workflows.ts`, backfill command/migration utilities, relevant developer docs.
- **Specific logic**:
  - Define workflow-run-scoped `AssetRef` inputs and explicit artifact outputs without making every node Asset-aware.
  - Backfill historical uploads/generated images using message/tool-message UUID plus ordinal when no durable identity exists.
  - Dual-read/write legacy fields until telemetry shows migration completion.
  - Add feature flags for Asset manifests, no-auto-parse behavior, tools, and Sandbox materialization.
- **Validation**:
  - Verify idempotent backfill and explicit unresolved reporting.
  - Verify old/new clients coexist, workflow Asset authorization and lineage, rollout metrics, and feature-flag rollback.

### Stage 7: One-Time Agent Attachment Capability Cutover

- **Files modified**: Agent model/schema/API/package adapters, startup migration, chat/preview/embed surfaces, orchestration UI, i18n resources, and focused tests.
- **Specific logic**:
  - Replace `enable_vision` and `enable_file_upload` with one `enable_attachments` field and replace `file_upload_config` with `attachment_config`.
  - On startup, migrate persisted values with `enable_vision OR enable_file_upload`, strip obsolete parser settings, and drop legacy columns. The API accepts and emits only the new fields.
  - Keep direct image projection conditional on the selected chat model's vision capability; the Agent attachment setting permits both images and files.
  - Remove parser selection and automatic URL parsing; Assets remain raw until the Agent invokes an explicit Asset tool.
- **Validation**:
  - Verify startup migration is idempotent and preserves every old boolean combination.
  - Verify a text-only model can use attachment Assets without receiving direct image bytes, while a vision-capable model receives them.
  - Verify the orchestration UI exposes one attachment card and the chat, preview, and embed paths use the same switch.

## Testing Strategy

### Happy paths

- Raw upload → Asset → chat manifest → on-demand parse.
- Uploaded image → vision → generation reference → generated Asset → Sandbox materialization.
- Sandbox-generated image → artifact Asset → later generation reference and display.
- Persistent conversation Sandbox reuse and workspace rehydration.
- Authorized workflow-run Asset input and explicit artifact output contract.

### Error paths

- Unknown/malformed four-character reference, reference from another scope, unavailable or unauthorized Asset.
- Collision allocation, same filename with different content, repeated upload, and checksum mismatch.
- Unsupported parser/MIME capability, parse truncation, parser failure, and expired storage object.
- Sandbox path traversal, symlink, overwrite, quota, partial stream, and artifact-size failures.
- Ambiguous natural-language reference without explicit UI selection.

### Regression scope

- Existing upload/download and parse endpoints.
- Legacy Chat `images`, `files`, and `file_urls` payloads.
- Historical messages and media tool result rendering.
- Existing positional image-reference calls.
- Base64 Sandbox input jobs and ephemeral workflow code nodes.

Run focused tests throughout, then backend `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app/`, and `uv run pytest`; frontend `node scripts/gen-i18n-types.ts`, `node scripts/lint-translations.ts --strict`, `bun run lint`, tests, and `bun run build`.

## Risks & Mitigation

- **Four-character collisions**: enforce scope uniqueness, retry generation with a nonce, and retain UUID authority.
- **Prompt growth**: cap candidate count and metadata; omit URLs, UUIDs, and content.
- **Ambiguous user language**: prioritize explicit selection/current attachment/exact filename; ask for clarification instead of tool-side guessing.
- **Authorization gaps**: resolve every ref through Asset ownership and requested capability; Sandbox session ownership alone is insufficient.
- **Large-file memory pressure**: stream storage/materialization and bound reads/parses.
- **Workspace loss**: rebuild from durable Asset/path bindings; session expiry never silently deletes durable Assets.
- **Historical identity gaps**: deterministic message-plus-ordinal backfill and explicit unresolved status.
- **Rollback**: disable new feature flags, continue legacy URL/JSON paths, preserve registered Assets and source uploads, and defer destructive cleanup until reconciliation.
