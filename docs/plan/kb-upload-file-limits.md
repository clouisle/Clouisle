# Knowledge Base Upload File Limits Design Document

## Background & Goals
- Knowledge base document uploads need enforced file restrictions on both frontend and backend.
- The maximum upload size should be configurable by administrators instead of hardcoded.
- Success criteria: upload dialogs show and pre-validate the configured limit; backend rejects oversized uploads before saving; admin storage settings can update the limit.

## High-Level Design
- Store `kb_document_max_upload_size_mb` in `SiteSetting` under the existing `storage` category.
- Expose the value through the existing public site settings response because upload-capable users need it for UI validation.
- Enforce the configured value in the KB upload endpoint after reading bytes and before saving the document.
- Reuse the existing admin storage settings page to edit the value.

## Implementation Plan

### Stage 1: Site setting and backend enforcement
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/schemas/site_setting.py`, `backend/app/api/v1/endpoints/site_settings.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`
- **Specific logic**: Add default MB setting, return it from public settings, read it in `upload_document`, reject files larger than configured MB with `file_too_large`.
- **Validation**: Check default setting key exists and backend type checks pass.

### Stage 2: Admin storage UI
- **Files modified**: `frontend/app/(dashboard)/site-settings/storage/page.tsx`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`
- **Specific logic**: Add numeric input for KB upload limit, validate allowed MB range, save via existing bulk settings API.
- **Validation**: Lint affected frontend code and confirm invalid values are blocked locally.

### Stage 3: Upload dialogs
- **Files modified**: `frontend/lib/api/site-settings.ts`, `frontend/lib/constants.ts`, `frontend/app/(dashboard)/knowledge-bases/[id]/_components/upload-document-dialog.tsx`, `frontend/app/(platform)/app/kb/[id]/_components/upload-document-dialog.tsx`
- **Specific logic**: Fetch public setting for max MB, derive bytes/label, validate selected files and revalidate before upload.
- **Validation**: Confirm unsupported extensions and oversized files are rejected before upload, and backend remains authoritative.

## Testing Strategy
- Happy path: allowed file below configured MB can be selected and uploaded.
- Error path: unsupported extension and file exceeding configured MB are rejected in UI; direct API upload over limit is rejected by backend.
- Regression scope: existing audit storage settings continue loading/saving; public site settings still include existing fields.

## Risks & Mitigation
- Public settings expansion could expose a non-sensitive operational limit; acceptable because the UI needs this value.
- Existing databases may not have the new key until defaults initialize; backend and frontend both keep a 50 MB fallback.
- Rollback: remove the setting key usage and return to the previous constant limit.
