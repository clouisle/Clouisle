# YUN-106 Object Storage Switch Design Document

## Background & Goals
- Problem to solve: uploads currently assume local filesystem storage only, which prevents deployments from using S3-compatible object storage.
- Success criteria:
  - Default local storage behavior remains compatible.
  - Admins configure upload storage backend and object storage values through system/site settings, not environment variables.
  - Upload/read/delete flows work through the selected backend.
  - Object storage mode fails clearly when selected with missing or invalid settings.

## High-Level Design
- Store upload storage configuration in existing `SiteSetting` records under the `storage` category.
- Keep `upload_storage_backend=local` as the default system setting.
- Add a small storage adapter module for local and S3-compatible object storage.
- Keep existing public upload URLs unchanged: `/api/v1/upload/files/{category}/{year}/{month}/{filename}`.
- Resolve the selected backend at runtime from system settings so changes do not require environment changes.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-106-object-storage-switch.md`
- **Specific logic**: Register the feature and capture implementation/validation steps.
- **Validation**: Confirm the docs exist before code changes.

### Stage 2: Backend settings and storage adapter
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`, `backend/app/services/upload_storage.py`, `backend/pyproject.toml`
- **Specific logic**: Add storage-category system settings; validate admin updates; implement local storage and object storage methods for save, read response, delete, existence checks, and validation.
- **Validation**: Unit tests cover default local settings, invalid backend/settings failures, and mocked object storage calls.

### Stage 3: Upload endpoint integration
- **Files modified**: `backend/app/api/v1/endpoints/upload.py`, `backend/app/main.py`
- **Specific logic**: Replace direct filesystem save/read/delete with adapter calls while preserving response metadata and URLs. Validate selected storage after database/default settings initialization.
- **Validation**: Existing upload endpoint tests still pass; new tests assert local and object-storage flows.

### Stage 4: Admin settings UI
- **Files modified**: `frontend/app/(dashboard)/site-settings/storage/page.tsx`, `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`
- **Specific logic**: Expose upload backend and object storage fields in the existing storage settings page.
- **Validation**: Frontend lint/type checks verify the page compiles without browser testing.

### Stage 5: Tests and checks
- **Files modified**: `backend/tests/services/test_upload_storage.py`, existing upload endpoint tests if needed
- **Specific logic**: Cover local write/read/delete, settings-driven backend selection, missing object settings, mocked object storage upload/read/delete, and missing object existence checks.
- **Validation**: Run targeted pytest, ruff, and mypy for touched backend code; run frontend lint/build if feasible without installing dependencies.

## Testing Strategy
- Happy path tests:
  - Local storage remains the default when no storage settings exist.
  - Object storage saves bytes with the expected object key and returns the existing public URL shape.
  - Object storage read/delete call the underlying client.
- Error path tests:
  - Invalid storage backend is rejected.
  - Missing object storage endpoint, bucket, access key, or secret key fails validation when object storage is selected.
  - Missing object returns the existing file-not-found behavior.
- Regression scope:
  - Existing `/api/v1/upload/sandbox-artifact` metadata behavior.
  - Local filesystem upload path compatibility.
  - Admin storage settings save/load behavior.

## Risks & Mitigation
- Possible side effect: runtime storage backend resolution reads settings for each upload operation. Mitigation: keeps changes simple and ensures settings changes take effect immediately; caching can be added later only if needed.
- Possible side effect: public object-storage files still proxy through backend instead of direct bucket URLs. Mitigation: preserves existing URL compatibility and avoids unrelated frontend consumers changing.
- Rollback plan: set `upload_storage_backend` back to `local` or revert adapter wiring to return to direct filesystem storage.
