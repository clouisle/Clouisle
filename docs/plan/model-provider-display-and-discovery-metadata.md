# Model Provider Display and Discovery Metadata Design Document

## Background & Goals

The persisted `provider` field is a controlled adapter identifier such as `custom`; it cannot identify an organization-specific OpenAI-compatible gateway. Remote model-list responses also expose useful configuration metadata that the discovery flow currently discards.

Success criteria:

- Keep `provider` as the adapter selector and add an optional, user-facing provider display name.
- Show a configured display name in Model Management while retaining a clear OpenAI-compatible fallback for legacy records.
- Normalize only trustworthy remote metadata: context length, maximum output tokens, and the existing capability flags.
- Selecting a discovered model prefills only metadata explicitly returned by the provider.
- Existing models and external API clients remain compatible.

## High-Level Design

`models.provider_display_name` is a nullable display-only column. The existing `provider` enum and all runtime adapter dispatch continue unchanged. A startup migration adds the column before Tortoise schema generation for existing PostgreSQL deployments.

The discovery endpoint converts common provider payload aliases into a normalized `ModelDiscoveryItem`. The frontend uses that optional metadata to populate the existing context and capability controls after a result is selected. Unknown or malformed remote fields are ignored rather than persisted.

## Implementation Plan

### Stage 1: Persist display-only provider identity

- **Files modified**: `backend/app/models/model.py`, `backend/app/schemas/model.py`, `backend/app/core/init_data.py`, `backend/app/main.py`
- **Specific logic**: Add nullable `provider_display_name`, expose it from create/update/read schemas, normalize blank submissions to `null`, and add an idempotent startup migration for existing `models` tables.
- **Validation**: Exercise absent-table, existing-column, and add-column migration paths; verify create/update payloads persist the supplied display name.

### Stage 2: Normalize remote model metadata

- **Files modified**: `backend/app/api/v1/admin/endpoints/models.py`, `backend/app/schemas/model.py`, `backend/tests/api/test_admin_model_discovery.py`
- **Specific logic**: Extract bounded positive token limits and supported capability flags from documented/common response aliases. Preserve no unknown fields and do not infer unsupported capability values.
- **Validation**: Cover OpenAI-compatible and Google-shaped payload metadata, malformed metadata, capability aliases, and response-size constraints.

### Stage 3: Surface metadata in the model UI

- **Files modified**: `frontend/lib/api/models.ts`, `frontend/lib/api/admin/models.ts`, `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, `frontend/app/(dashboard)/models/_components/models-client.tsx`, locale catalogs and tests.
- **Specific logic**: Add a custom-provider display-name input, show it in the list, and populate the existing context/capability controls when a discovered model supplies those values.
- **Validation**: Verify custom-display persistence payloads and discovered metadata prefill behavior without overwriting fields absent from the remote response.

### Stage 4: Propagate additive model display metadata

- **Files modified**: model brief response paths and their type definitions.
- **Specific logic**: Include the optional display name in model brief payloads so consumers can use it without changing adapter selection.
- **Validation**: Verify explicit brief response builders retain the new field and legacy records remain valid.

## Testing Strategy

- Backend unit tests for schema normalization, model discovery metadata parsing, model CRUD persistence, and startup migration idempotence.
- Frontend API and dialog tests for outgoing display-name payloads and metadata prefill.
- Backend coverage gate and frontend isolated tests/build.

## Risks & Mitigation

- **Untrusted provider metadata**: Parse only known keys, bounded positive integer token limits, and boolean capability flags. Ignore all other fields.
- **Existing PostgreSQL databases**: Run the idempotent column migration before schema generation; nullable storage preserves legacy rows.
- **Adapter dispatch regression**: Do not alter `provider`, `ModelProvider`, or model-manager routing.
- **Partial remote metadata**: Only update fields present in the discovery result, preserving dialog defaults and manual input for omitted values.

## Rollback Plan

The display column is additive and nullable. The UI can ignore it safely, while `provider` remains authoritative for all runtime behavior. Rolling back application code leaves the added nullable column inert.

## Completion Evidence

- Backend focused regressions: 220 passed. Full backend suite: 6,746 passed and 3 skipped; line coverage 97.45% and branch coverage 95.04% passed the 95% gates.
- Frontend focused regressions: 57 passed. Full isolated suite with coverage disabled: 2,092 passed across 504 files; the repository's existing coverage-enabled Bun run reproduced its `WriteFailed` reporter failure before printing a test summary.
- Backend Ruff format/check, Babel catalog checks, legacy-catalog synchronization, frontend ESLint, and translation lint passed.
- The Next.js production build completed successfully, including TypeScript validation and all 41 static pages.