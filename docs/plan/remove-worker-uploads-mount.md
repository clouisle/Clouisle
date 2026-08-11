# Remove Worker Uploads Mount Dependency

## Background & Goals

### Problem
`worker` (Celery: `default,knowledge,workflow`) and `sandbox-worker` must run without an `uploads` PVC / volume at `/app/uploads` in every deployment manifest (`deploy/k8s/clouisle.yaml`,
`deploy/helm/clouisle/templates/*`, `deploy/docker-compose.yml`). In a distributed deployment without
distributed/object storage the worker pod may land on a node that cannot attach the uploads volume,
or no RWX-capable StorageClass exists. The goal is to remove the uploads mount from both worker roles
while keeping the **api** process as the sole owner of the local uploads directory.

### Success criteria
- `worker` and `sandbox-worker` run without any `uploads` volume in all storage modes (`local` and `object`/`s3`).
- `api` remains the only process that mounts the local uploads directory.
- No regression in knowledge-base ingestion, workflow file handling, upload/download, sandbox attachments, or sandbox artifacts.
- Worker file reads and writes use the authenticated internal gateway; api remains the sole owner of the selected `UploadStorageBackend`.

## Current State (verified 2026-08-10)

File I/O already routed through `UploadStorageBackend` (`backend/app/services/upload_storage.py`,
`get_upload_storage_backend(root)`, backend selected by SiteSetting `upload_storage_backend`
= `local` | `object` | `s3`; `LocalUploadStorage` and `ObjectUploadStorage` implementations):

- `upload.py::save_generated_upload` (user uploads, sandbox artifacts) — `storage.save`
- `document_processor` `save_file` / `read_file` / `delete_file` / `extract_text` — `storage.*`
- `skill_import.py` package save/delete — `storage.*`
- `chat_tools.py::read_asset`, `llm/tools/builtin/media.py`, `sandbox/manager.py` input files — `storage.*`

The worker-only local-path dependencies were removed. `sandbox-worker` stages authorized attachments through the internal upload gateway when `UPLOAD_STORAGE_MODE=remote`; this preserves the mount-free deployment contract.

## High-Level Design

Two layered changes, both keeping `api` as the storage owner:

1. **Stage 1 — media assets move onto `UploadStorageBackend`.** Adds a `list(prefix)` capability to
   the backend interface, then converts the three media-asset code paths (write, delete, serve).
   Result: in `object`/`s3` mode the worker already has zero local storage dependency.

2. **Stage 2 — worker talks to api through explicit internal HTTP endpoints.** New private
   endpoints under `/internal/uploads/*` on `api`, authenticated with `INTERNAL_API_TOKEN`.
   `document_processor` branches on `UPLOAD_STORAGE_MODE`: the api process (mode `local`) uses
   `LocalUploadStorage` directly; the worker (mode `remote`) issues explicit HTTP calls to api for
   every file operation (read document bytes, save media asset, delete media assets, delete file).
   No new storage abstraction class — the worker's calls are explicit and visible.

```
┌──────────────┐  uploads  ┌──────────────┐
│  api (server)│ ◄────────►│ local dir    │  (only process that mounts the volume)
│  + internal  │           │ /app/uploads │
│  file router │           └──────────────┘
└──────┬───────┘
       │ GET/PUT/DELETE /internal/uploads/*  (INTERNAL_API_TOKEN)
┌──────▼───────┐
│ worker       │  document and media operations → api (no volume)
│ sandbox-     │  authorized attachment reads → api (no volume)
│ worker       │  artifacts upload → api
└──────────────┘
```

Process role selection is explicit via env (`UPLOAD_STORAGE_MODE`), not inferred from argv.

## Implementation Plan

### Stage 1: Media assets on UploadStorageBackend

- **Files modified**: `backend/app/services/upload_storage.py`,
  `backend/app/services/document_processor.py`,
  `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/tests/...`
- **Specific logic**:
  - Add `async def list(self, prefix: str) -> list[str]` to `UploadStorageBackend`.
    - `LocalUploadStorage.list`: scan `self.root.joinpath(*prefix.split("/"))`, return relative keys.
    - `ObjectUploadStorage.list`: `list_objects_v2` with `Prefix=prefix` (paginated).
  - `document_processor._save_media_asset`: build the stable key
    `documents/{kb_id}/media/{doc_id}/{filename}`, persist it through `storage.save` when absent,
    and return that relative key as `path`; the API media URL remains the storage-independent public reference.
  - `document_processor.delete_media_assets`: `keys = await storage.list(f"documents/{kb_id}/media/{doc_id}/")`,
    then `storage.delete` each; drop `shutil.rmtree`.
  - `knowledge_bases.py::get_document_media`: `storage = get_upload_storage_backend(...)`,
    `storage_key = f"documents/{kb_id}/media/{doc_id}/{filename}"`, return `await storage.response(key, ...)`.
    Preserve a local fallback for media assets created before the object-storage cutover.
- **Validation**: unit tests for `list()` on both backends, media write/delete/serve through
  backend; full `uv run pytest` + `check_coverage.py` (95% line + branch).

### Stage 2: Worker file access through explicit api endpoints

- **Files modified**: `backend/app/core/config.py`, `backend/app/services/document_processor.py`,
  new `backend/app/api/v1/endpoints/internal_uploads.py`, `backend/app/main.py`,
  `backend/app/services/workflow/executors/subworkflow.py`, `backend/tests/...`
- **Specific logic**:
  - Config: `INTERNAL_API_TOKEN: str = ""`, `API_INTERNAL_BASE_URL: str = ""`,
    `UPLOAD_STORAGE_MODE: str = "local"` (`local` | `remote`).
  - New internal router mounted at `/internal` on the app (NOT under `/api`, NOT exposed by
    Ingress — Ingress only routes `/api` and `/`; the worker reaches it via the api ClusterIP
    service directly):
    - `GET /internal/uploads/read?key=...` → file bytes
    - `PUT /internal/uploads/save?key=...` → body bytes, returns storage path
    - `HEAD /internal/uploads/exists?key=...` → 200/404
    - `DELETE /internal/uploads/delete?key=...` → 204
    - `PUT /internal/uploads/media/{kb_id}/{doc_id}` → save the request bytes using the content type;
      the API determines the content-addressed filename and returns `{url, filename, ...}`.
    - `DELETE /internal/uploads/media/{kb_id}/{doc_id}` → delete all media assets of the document
    - Every handler requires `Authorization: Bearer {INTERNAL_API_TOKEN}` (constant-time compare);
      token empty ⇒ router returns 404 (fail closed).
  - `document_processor`: branch on `settings.UPLOAD_STORAGE_MODE == "remote"`:
    - `read_file` → `GET /internal/uploads/read?key=...`
    - `_save_media_asset` → `PUT /internal/uploads/media/{kb}/{doc}?filename=...` with bytes
    - `delete_media_assets` → `DELETE /internal/uploads/media/{kb}/{doc}`
    - `delete_file` → `DELETE /internal/uploads/delete?key=...`
    - local mode (`api`) keeps the current storage-backend path. Callers (knowledge tasks) are
      unchanged.
  - Fix `FileToURLNodeExecutor` (subworkflow.py): the workflow file parameter value IS the upload
    URL (`onChange(result.url)` in the frontend), so URL outputs never read local worker files.
    Apply `ensureAbsolute` only with configured `PUBLIC_API_URL`, and support both
    `fileToUrlConfig.inputs[]` (frontend) and legacy `config.inputVariable/inputType` shapes.
    The legacy `path` → `base64` mode remains supported through the internal gateway, never a local path.
- **Validation**: unit tests for internal router auth and endpoints, `document_processor` remote
  branches against mocked HTTP, file_to_url URL-only behavior; full suite + coverage gate.

### Stage 3: Deployment manifests

- **Files modified**: `deploy/k8s/clouisle.yaml`, `deploy/helm/clouisle/templates/{api,worker,sandbox-worker}-deployment.yaml`,
  `deploy/helm/clouisle/values.yaml`, `deploy/helm/clouisle/values-production.yaml`,
  `deploy/helm/clouisle/templates/{secret,configmap}.yaml`, `deploy/docker-compose.yml`,
  `deploy/install.sh`, `main.py`, deployment docs.
- **Specific logic**:
  - `worker` and `sandbox-worker`: remove `uploads` volumeMount + volume; set
    `UPLOAD_STORAGE_MODE=remote`, use `API_INTERNAL_BASE_URL`, and mount the internal token Secret file.
  - `api`: keeps uploads mount and mounts the same token file so rotations are read without process restart.
  - K8s Secret adds `INTERNAL_API_TOKEN`; the API uses `RollingUpdate` with `maxUnavailable: 0`.
  - compose: both workers drop `uploads_data`, gain gateway env, and wait for the API healthcheck.
- **Validation**: `helm lint` + `helm template` render when Helm is available, YAML parse of
  `deploy/k8s/clouisle.yaml`, `docker compose config` with placeholder env, `bash -n` on install.sh.

### Stage 4: End-to-end verification

- **Validation**:
  - `local` mode: api with uploads mount, worker/sandbox-worker without; upload document or sandbox
    attachment → knowledge ingestion and workspace staging succeed through the gateway; media URL render,
    artifact upload, and delete remove files.
  - `object`/`s3` mode (MinIO or moto): same flow with api resolving the selected object backend.
  - Workflow `file_to_url` node produces a fetchable URL; legacy path-to-base64 reads through the gateway.
  - Negative: wrong/missing `INTERNAL_API_TOKEN` → 401; `UPLOAD_STORAGE_MODE=remote` with unreachable
    api → clear error surfaced in task logs and knowledge tasks retry.

## Testing Strategy

- Happy path: media write/delete/serve through `LocalUploadStorage` and `ObjectUploadStorage`;
  internal gateway round-trip for document and sandbox attachment reads; knowledge ingestion in both storage modes.
- Error path: missing/wrong internal token, disabled internal router, backend `list` on empty prefix,
  remote backend when api is unreachable.
- Regression scope: upload/download endpoints, sandbox artifact upload, skill import package
  storage, chat `read_asset` / media tools, knowledge-base CRUD, workflow file nodes.

## Risks & Mitigation

- **Media asset compatibility**: the new key layout preserves current local files; pre-cutover media
  remains readable from the legacy local location during the object-storage transition.
- **File size over HTTP gateway**: uploads are capped at 10 MiB (`MAX_FILE_SIZE`); gateway response
  bodies stream from storage and are accumulated only where document parsing/base64 output requires bytes.
- **Internal endpoint exposure**: token auth, constant-time compare, router returns 404 when token
  unset; Ingress routes only `/api` and `/`, so `/internal` is cluster-internal. Document that
  users must not expose `/internal` publicly.
- **Availability**: token files are re-read on each request and API rolling updates use `maxUnavailable: 0`.
- **Rollback**: each stage is independently revertible; Stage 1 has no deployment impact, Stage 3
  changes are limited to manifests + env.

## Validation Evidence (2026-08-10)

- `cd backend && uv run pytest && uv run python scripts/check_coverage.py`: 6,691 passed,
  3 skipped; 97.44% line coverage and 95.01% branch coverage (both exceed the 95% gate).
- Focused gateway/media/storage suite: 81 passed; Ruff passed for the changed backend paths.
- `docker compose --env-file .env.example config --quiet` passed with temporary validation
  credentials. The rendered Compose JSON asserts that only `api` mounts `/app/uploads`; both workers
  set `UPLOAD_STORAGE_MODE=remote`. The temporary `deploy/.env` symlink was removed.
- `deploy/k8s/clouisle.yaml` parses as 20 Kubernetes documents; a static contract assertion confirms
  the api-only uploads mount and remote modes for `worker` and `sandbox-worker`. `bash -n deploy/install.sh` passed.
- Helm CLI is not installed in this environment, so `helm lint` and rendered-template validation could
  not run. Real-cluster local/object-storage validation remains Stage 4 in `docs/IMPLEMENTATION_PLAN.md`.
