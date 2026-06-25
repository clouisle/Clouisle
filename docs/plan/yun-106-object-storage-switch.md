# YUN-106 Object Storage Switch Design Document

## Background & Goals
- Problem to solve: uploads currently assume local filesystem storage only, which prevents deployments from using S3-compatible object storage.
- Success criteria:
  - Default local storage behavior remains compatible.
  - Operators can switch upload storage to object storage with endpoint, bucket, region, access key, and secret key config.
  - Upload/read/delete flows work through the selected backend.
  - Object storage mode fails fast on missing or invalid config during startup validation.

## High-Level Design
- Add upload storage settings to `app.core.config.Settings` with `UPLOAD_STORAGE_BACKEND=local` by default.
- Add a small storage adapter module for local and S3-compatible object storage.
- Keep existing public upload URLs unchanged: `/api/v1/upload/files/{category}/{year}/{month}/{filename}`.
- Route existing upload save/read/delete code through the selected adapter.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-106-object-storage-switch.md`
- **Specific logic**: Register the feature and capture implementation/validation steps.
- **Validation**: Confirm the docs exist before code changes.

### Stage 2: Backend config and storage adapter
- **Files modified**: `backend/app/core/config.py`, `backend/app/services/upload_storage.py`, `backend/pyproject.toml`
- **Specific logic**: Add storage backend config; implement local storage and object storage methods for save, open/read response, delete, existence checks, and validation.
- **Validation**: Unit tests cover default local config, invalid backend/config failures, and mocked object storage calls.

### Stage 3: Upload endpoint integration
- **Files modified**: `backend/app/api/v1/endpoints/upload.py`, `backend/app/main.py`
- **Specific logic**: Replace direct filesystem save/read/delete with adapter calls while preserving response metadata and URLs. Run startup validation during app lifespan.
- **Validation**: Existing upload endpoint tests still pass; new tests assert local and object-storage flows.

### Stage 4: Tests and checks
- **Files modified**: `backend/tests/services/test_upload_storage.py`, existing upload endpoint tests if needed
- **Specific logic**: Cover local write/read/delete and mocked object storage upload/read/delete plus config validation.
- **Validation**: Run targeted pytest, ruff, and mypy for touched backend code.

## Testing Strategy
- Happy path tests:
  - Local storage saves bytes and reports compatible metadata.
  - Object storage saves bytes with the expected object key and returns the existing public URL shape.
  - Object storage read/delete call the underlying client.
- Error path tests:
  - Invalid storage backend is rejected.
  - Missing object storage endpoint, bucket, access key, or secret key fails validation.
  - Missing object returns the existing file-not-found business error.
- Regression scope:
  - Existing `/api/v1/upload/sandbox-artifact` metadata behavior.
  - Local filesystem upload path compatibility.

## Risks & Mitigation
- Possible side effect: object storage SDK dependency may affect lockfile resolution. Mitigation: use the project package manager and run targeted checks.
- Possible side effect: public object-storage files still proxy through backend instead of direct bucket URLs. Mitigation: preserves existing URL compatibility and avoids frontend changes.
- Rollback plan: revert adapter wiring and config additions to return to direct filesystem storage.
