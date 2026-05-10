# Deploy Config Refresh Design Document

## Background & Goals

- Current deployment files lag behind the runtime model in `main.py`.
- The API process is named `backend` in deployment files, while the backend image also runs workers and scheduler processes.
- Docker Compose has `sandbox-worker`, but K8s does not.
- Frontend deployment docs still describe an Nginx-based container, while the current Dockerfile runs Next.js standalone with `node server.js`.
- Sandbox artifact upload needs an internal API URL that is valid inside Compose/K8s networks.

Success criteria:
- Compose, K8s, CI image build, env examples, and deploy docs all describe the same services.
- API service is named `api`; backend image name remains `clouisle-backend`.
- Sandbox worker uses a dedicated `clouisle-sandbox-worker` image.
- Sandbox artifact upload explicitly targets `http://api:8000` in containerized deployment.

## High-Level Design

- Docker Compose runs infrastructure (`db`, `redis`, `qdrant`) plus application services (`api`, `worker`, `sandbox-worker`, `beat`, `frontend`).
- K8s runs matching Deployments/Services and adds a shared uploads PVC for API/worker/sandbox-worker file access.
- CI builds three images: backend, sandbox-worker, and frontend.
- Env examples split defaults by context: root `.env.example` for local development, `deploy/.env.example` for container deployment.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/deploy-config-refresh.md`
- **Specific logic**: Add this workstream and track the deployment refresh stages.
- **Validation**: Confirm the implementation index links to this document.

### Stage 2: Docker Compose and env examples
- **Files modified**: `deploy/docker-compose.yml`, `deploy/.env.example`, `.env.example`
- **Specific logic**:
  - Rename Compose service `backend` to `api`.
  - Add `build` blocks for backend, sandbox-worker, and frontend images.
  - Use `env_file: .env` from the `deploy` directory.
  - Set `SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://api:8000`.
  - Add sandbox and frontend build variables to env examples.
- **Validation**: Run `docker compose -f deploy/docker-compose.yml config`.

### Stage 3: K8s manifest and CI
- **Files modified**: `deploy/k8s/clouisle.yaml`, `.github/workflows/build-images.yml`
- **Specific logic**:
  - Rename K8s API resources from `backend` to `api`.
  - Add `sandbox-worker` Deployment.
  - Add shared `uploads-data` PVC and mount it in API, worker, and sandbox-worker.
  - Update Redis probes to support password auth.
  - Add CI build for `clouisle-sandbox-worker`.
- **Validation**: Run `kubectl apply --dry-run=client -f deploy/k8s/clouisle.yaml` when `kubectl` is available.

### Stage 4: Deployment docs and examples
- **Files modified**: `deploy/README.md`, `deploy/nginx/default.conf`, `deploy/dockerfiles/sandbox-worker.Dockerfile`
- **Specific logic**:
  - Rewrite deployment docs around `api`, `worker`, `sandbox-worker`, `beat`, and `frontend`.
  - Document current frontend standalone runtime and mark Nginx as optional external example.
  - Update Nginx example proxy target from `backend` to `api`.
  - Add sandbox-worker virtualenv `PATH`.
- **Validation**: Search for stale `http://backend:8000`, `logs -f backend`, and `Next.js + Nginx` references.

## Testing Strategy

- Compose static validation: `docker compose -f deploy/docker-compose.yml config`.
- Docker image validation:
  - `docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend:local .`
  - `docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker:local .`
  - `docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend:local .`
- K8s static validation: `kubectl apply --dry-run=client -f deploy/k8s/clouisle.yaml`.
- Stale-reference check: grep deployment docs and manifests for old `backend` service URLs.

## Risks & Mitigation

- Existing scripts using `docker compose logs backend` will break.
  - Mitigation: document migration to `api`.
- K8s `ReadWriteMany` PVC requires compatible storage.
  - Mitigation: document single-replica or object-storage alternatives when RWX is unavailable.
- Sandbox artifact code still has a legacy fallback URL.
  - Mitigation: explicitly set `SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://api:8000` in deploy configs.
