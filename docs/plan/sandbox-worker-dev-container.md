# Sandbox Worker Dev Container Design Document

## Background & Goals

The sandbox worker currently runs as a Celery worker on the `sandbox` queue, but local development does not provide a simple, isolated way to run it with a complete Python/Node toolchain. Shell command allowlists have also made Agent-driven sandbox work fragile.

Goals:

- Keep the existing Celery sandbox worker execution model.
- Add a local dev mode that builds current code into a Docker image and runs the sandbox worker in a temporary container.
- Never bind mount the local project directory into the sandbox worker container.
- Ensure `-c/--concurrency` controls the sandbox Celery worker in both normal and local dev modes.
- Install backend dependencies, Python/pip, Node/npm, and common shell tools in the sandbox worker image.
- Remove shell command allowlist restrictions while keeping resource limits, workspace/session isolation, environment cleanup, and artifact path checks.

## High-Level Design

- `main.py` remains the single service entrypoint.
- `python main.py sandbox-worker -c N` keeps the current direct Celery worker behavior.
- `python main.py sandbox-worker --local-dev -c N` builds `deploy/dockerfiles/sandbox-worker.Dockerfile` from the repository root, then runs a temporary Docker container that executes `python main.py sandbox-worker -c N`.
- The Docker build uses the repository root `.dockerignore`, so local `.venv`, `node_modules`, caches, and `.env` files are excluded.
- Shell jobs still execute through `SandboxGateway -> Celery task -> SandboxManager -> SandboxProcessLauncher`, but shell command semantic allowlists are no longer applied.

## Implementation Plan

### Stage 1: Planning Docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/sandbox-worker-dev-container.md`
- **Specific logic**: Track this work as a complex task with stages and verification commands.
- **Validation**: Confirm the implementation index links to this document.

### Stage 2: Sandbox Worker Dockerfile

- **Files modified**: `deploy/dockerfiles/sandbox-worker.Dockerfile`
- **Specific logic**:
  - Convert the Dockerfile to a builder/runtime pattern matching `deploy/dockerfiles/backend.Dockerfile`.
  - Run `uv sync --frozen --no-dev --no-editable` in the builder.
  - Copy `.venv`, `backend/`, and root `main.py` into runtime.
  - Install Node.js 22, npm, and common command-line tools.
  - Run as non-root user `clouisle`.
- **Validation**: `docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker:dev .`

### Stage 3: Local Dev CLI Mode

- **Files modified**: `main.py`, `backend/tests/test_main_sandbox_worker.py`
- **Specific logic**:
  - Add `build_sandbox_worker_image()`.
  - Add `start_sandbox_worker_container()`.
  - Add `--local-dev`, `--no-cache`, and `--image-tag` to `sandbox-worker` CLI.
  - Pass through relevant DB/Redis/Qdrant/sandbox env vars.
  - Default `REDIS_HOST` and `POSTGRES_SERVER` to `host.docker.internal` in local dev mode if unset.
  - Ensure Docker run command has no bind mount flags.
- **Validation**: Unit tests assert Docker build/run command construction and concurrency passthrough.

### Stage 4: Shell Policy Relaxation

- **Files modified**: `backend/app/llm/tools/bash.py`, `backend/app/services/sandbox/policies.py`, `backend/tests/llm/test_bash_tool.py`, `backend/tests/services/test_sandbox_gateway.py`
- **Specific logic**:
  - Stop pre-validating Bash tool commands with shell AST allowlists.
  - Let shell jobs pass through sandbox policy without `_validate_shell_command()`.
  - Keep `/workspace` path mapping and `pip install` normalization in the Bash tool.
  - Keep artifact path and disk limit checks in sandbox policy.
- **Validation**: Tests cover `python3 -c`, `npm run`, and arbitrary shell scripts being submitted/accepted, while artifact paths outside `/workspace` remain rejected.

### Stage 5: Compose and Developer Docs

- **Files modified**: `deploy/docker-compose.yml`, `docs/dev/backend/celery-and-async-jobs.md`
- **Specific logic**:
  - Add a `sandbox-worker` service to production compose with configurable `SANDBOX_WORKER_CONCURRENCY`.
  - Document normal and local dev sandbox worker startup.
  - Emphasize that local dev mode copies code into the image and does not bind mount source.
- **Validation**: `docker compose -f deploy/docker-compose.yml config` if Docker is available.

## Testing Strategy

- Unit tests for `main.py` command construction and CLI dispatch.
- Unit tests for Bash tool pass-through, path mapping, and pip normalization.
- Policy tests for unrestricted shell command acceptance and retained artifact checks.
- Targeted sandbox manager regression tests.
- Docker build smoke test for the sandbox worker image.

## Risks & Mitigation

- **Worker-level isolation, not per-job isolation**: acceptable for this iteration; per-job containers can be a future hardening step.
- **No bind mount means rebuild on code change**: intentional to avoid Agent mutations of local source.
- **Host API + container worker artifact visibility**: avoid solving with source bind mounts; use object storage or a dedicated non-source volume later if needed.
- **Shell command restrictions removed**: rely on container isolation, non-root user, workspace/session isolation, resource limits, and env cleanup.
