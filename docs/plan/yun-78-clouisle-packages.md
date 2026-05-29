# YUN-78 Clouisle Packages Design Document

## Background & Goals

- Support export/import for Tool, Agent, Workflow, and Knowledge Base assets so teams can migrate, reuse, back up, and restore core configuration without manual rebuilding.
- Use a `.clouisle` ZIP package with `manifest.json`, resource payload, checksums, dependencies, and optional documents/assets.
- Import must preview and validate before writing business data; invalid files, unsupported versions, checksum mismatches, missing dependencies, permission failures, and name conflicts must produce clear errors without dirty writes.
- Exported packages must not contain plaintext secrets.

## High-Level Design

- Add a unified backend `/packages` API for export, import preview, and import install.
- Add a shared package service for ZIP structure validation, manifest parsing, checksum validation, path safety, secret scanning, temporary session storage, and audit metadata sanitization.
- Add lightweight resource adapters for Tool, Agent, Workflow, and Knowledge Base to handle resource-specific serialization, dependency extraction, permission checks, conflict resolution, and install logic.
- Add a frontend `packagesApi` and reusable import dialog, then wire export/import actions into existing resource pages.
- Knowledge Base v1 exports base settings and reconstructable document content when available, but not raw vector embeddings.

## Package Format

```text
*.clouisle
├── manifest.json
├── resources/
│   └── resource.json
├── assets/
│   └── ... optional static assets
├── documents/
│   └── ... optional KB documents
└── checksums.json
```

`manifest.json` fields:

- `format_version`: `1`
- `app_version`
- `package_id`
- `exported_at`
- `resource_type`: `tool`, `agent`, `workflow`, or `knowledge_base`
- `resource_name`
- `resource_id`
- `dependencies`
- `checksums`

The importer trusts only package contents, not the uploaded filename or frontend-selected resource type.

## Implementation Plan

### Stage 1: Planning docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-78-clouisle-packages.md`
- **Specific logic**: Register this complex task and keep implementation stages visible.
- **Validation**: Confirm the index links to this detailed plan and stage statuses match implementation progress.

### Stage 2: Backend schemas, session model, and migration

- **Files modified**: `backend/app/schemas/clouisle_package.py`, `backend/app/models/package_import.py`, backend model registration, migration files.
- **Specific logic**:
  - Define manifest, dependency, preview, conflict, install request/result, and export option schemas.
  - Add `ClouisleImportSession` with parsed manifest/resource payload, preview result, temp path, status, team, creator, and expiry.
- **Validation**: Run backend import/type checks and migration generation/checks.

### Stage 3: Shared package service

- **Files modified**: `backend/app/services/clouisle_package.py`
- **Specific logic**:
  - Validate `.clouisle` extension.
  - Safely read ZIP contents and reject Zip Slip, missing required files, unsupported format versions, oversized files, and checksum mismatches.
  - Parse `manifest.json` and `resources/resource.json`.
  - Include checked `assets/` and `documents/` binary entries in package checksums, and stage them during preview for install.
  - Recursively reject plaintext sensitive fields and values.
  - Create preview sessions and load sessions for install.
- **Validation**: Unit tests for invalid extension, broken ZIP, missing manifest/resource, unsupported version, checksum mismatch, path traversal, and secret detection.

### Stage 4: Resource adapters

- **Files modified**: `backend/app/services/clouisle_package_resources.py`
- **Specific logic**:
  - Tool adapter exports safe tool config, excludes credentials, detects name conflicts, carries local uploaded icon assets, and installs as disabled by default unless updating.
  - Agent adapter exports prompts, model config, tools config, KB associations, variables, and media/RAG settings; excludes `tools_credentials`; carries local uploaded icon/avatar assets; maps model/tool/KB dependencies on import.
  - Workflow adapter exports definition, variables, trigger config, and embed config; excludes webhook tokens and run/version history; carries local uploaded icon assets; rewrites node dependency IDs on import.
  - Knowledge Base adapter exports base config and document content/metadata when available; excludes raw vectors; carries local uploaded icon assets and uploaded document files; imports documents as pending/reprocessable content with new target-system file paths instead of source-system URLs/paths.
- **Validation**: Integration tests for export/preview/install per resource type, conflict rename/update, dependency missing, and install rollback.

### Stage 5: API endpoints and audit logging

- **Files modified**: `backend/app/api/v1/endpoints/packages.py`, `backend/app/api/v1/api.py`, backend i18n message files as needed.
- **Specific logic**:
  - Add `GET /packages/{resource_type}/{resource_id}/export`.
  - Add `POST /packages/import/preview`.
  - Add `POST /packages/import/{session_id}/install`.
  - Log `export_clouisle_package`, `preview_clouisle_import`, and `install_clouisle_package` without payload/secrets.
- **Validation**: API tests assert response shape, download filename, audit records, and permission failures.

### Stage 6: Frontend API and shared dialog

- **Files modified**: `frontend/lib/api/packages.ts`, `frontend/components/packages/import-package-dialog.tsx`, frontend i18n JSON files.
- **Specific logic**:
  - Add typed preview/install/export API helpers.
  - Implement file picker, preview summary, dependency status, conflict strategy, install action, and error/warning rendering.
  - Use blob download for exports and server `Content-Disposition` filename when available.
- **Validation**: `bun run lint`, `bun run build`, and manual dialog checks.

### Stage 7: Page integration

- **Files modified**:
  - `frontend/app/(dashboard)/capabilities/_components/tools-client.tsx`
  - `frontend/app/(platform)/app/apps/page.tsx`
  - `frontend/app/(platform)/app/apps/workflow/[id]/page.tsx` if needed
  - `frontend/app/(dashboard)/knowledge-bases/_components/knowledge-bases-client.tsx`
  - `frontend/app/(platform)/app/kb/page.tsx` if needed
- **Specific logic**:
  - Add import buttons to list headers where users manage resources.
  - Add export actions to resource row/card menus.
  - Refresh lists or navigate to created resources after successful install.
- **Validation**: Start the app and verify Tool, Agent, Workflow, and Knowledge Base import/export UI flows.

### Stage 8: Tests and final validation

- **Files modified**: backend tests and any frontend tests that match existing patterns.
- **Specific logic**:
  - Cover invalid packages, safe export, preview sessions, dependency mapping, conflict handling, rollback, and audit logging.
  - Regenerate frontend i18n types after translation updates.
- **Validation**:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - targeted `uv run pytest ...`
  - `node scripts/gen-i18n-types.ts`
  - `node scripts/lint-translations.ts --strict`
  - `bun run lint`
  - `bun run build`

## Testing Strategy

- Happy path: export and re-import one Tool, one Agent with Tool dependency, one Workflow with Agent/Tool dependency, and one Knowledge Base with a small document.
- Error path: non-`.clouisle`, damaged ZIP, missing manifest, unsupported format version, checksum mismatch, plaintext secret, missing dependency, permission failure, and name conflict.
- Regression scope: existing Skill ZIP import, resource duplicate actions, audit log list/export, Agent tool selection, Workflow editor loading, KB document processing.

## Validation Results

- Passed: `uv --directory "backend" run ruff check .`
- Passed: `uv --directory "backend" run ruff format --check .`
- Passed: `PYTHONPATH=. uv --directory "backend" run pytest tests/services/test_clouisle_package.py`
- Passed: `bun --cwd "frontend" i18n:gen-types`
- Passed: `bun --cwd "frontend" i18n:lint --strict`
- Passed: `bun --cwd "frontend" lint`
- Passed: `bun --cwd "frontend" build`
- Full backend pytest is currently blocked by unrelated pre-existing sandbox/workflow test failures and three unrelated collection errors in workflow/sandbox modules.
- Full backend mypy is currently blocked by unrelated pre-existing errors in `app/services/message_branching.py` and `app/llm/adapters/video/runway.py`; YUN-78 package files type-check past their own errors.
- Browser smoke reached the local Next.js login page; authenticated import/export UI verification was not possible in this session without credentials.

## Risks & Mitigation

- Cross-environment IDs are unstable: match by stable hints and require explicit dependency mapping when ambiguous.
- Workflow references are embedded in node data: implement extractor/rewriter for known node types and warn on unknown references.
- Secret leakage risk: export with resource-specific allowlists and re-scan on import.
- KB vectors are not portable: do not export raw embeddings; reprocess imported documents.
- Partial installs can create dirty data: validate first, write inside DB transactions, and keep assets staged until commit succeeds.
