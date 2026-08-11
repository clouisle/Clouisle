# Kubernetes Manifest Installer and Startup Readiness Design Document

## Background & Goals

### Problem

`deploy/install.sh` currently supports only Docker Compose and Helm. The plain
`deploy/k8s/clouisle.yaml` must be edited manually to replace embedded Secret
placeholders. It is easy to apply an insecure manifest accidentally.

Kubernetes schedules the PostgreSQL StatefulSet and backend workloads
independently. The raw manifest has no dependency gate, so the API, Celery
worker, sandbox worker, and beat can start before PostgreSQL accepts
connections. Those processes may exit and enter a restart loop instead of
remaining pending until their database dependency is ready.

### Success Criteria

- The guided installer offers a third `k8s` target that creates a separate,
  secure single-file manifest without mutating the repository template.
- The generated manifest contains independent strong values for `SECRET_KEY`,
  `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`,
  `SANDBOX_ARTIFACT_UPLOAD_API_KEY`, and `INTERNAL_API_TOKEN`.
- The generated manifest is mode `0600`, never overwrites an existing output,
  and is not applied automatically.
- Every raw-manifest backend workload waits for PostgreSQL readiness before its
  application container starts.
- Documentation explains the new route, the generated file's sensitivity, and
  remaining cluster-specific settings.

## High-Level Design

The installer adds a third deployment choice:

```text
Docker Compose  -> install and start services
Helm            -> create/reuse cluster Secret and install chart
Kubernetes YAML -> generate a secret-filled manifest; operator reviews/applies it
```

`install_k8s_manifest` copies the repository/downloaded template into a caller
selected output path (`CLOUISLE_K8S_MANIFEST`, default
`./clouisle-k8s.yaml`). It creates six random values with the existing
`random_secret` helper, base64-encodes each value, and replaces only the known
`Secret.data` key lines. It creates the output directory when necessary,
refuses to overwrite an existing file, sets mode `0600`, and prints the exact
`kubectl apply -f` command. It does not require cluster access and never edits
`deploy/k8s/clouisle.yaml` or Helm values.

The raw manifest receives the same `wait-for-postgres` init container in the
API, worker, sandbox-worker, and beat pod specs. It uses the published
PostgreSQL image, reads the host/user/database fields from the ConfigMap, and
loops on `pg_isready`. Kubernetes therefore holds each workload in
`Init:0/1` until the database is accepting connections, instead of restarting
application containers.

## Implementation Plan

### Stage 1: Add the secure manifest-generation installer route

- **Files modified**: `deploy/install.sh`, `deploy/k8s/clouisle.yaml`,
  `backend/tests/test_deploy_install_script.py`
- **Specific logic**:
  - Extend the deployment selector and non-interactive validation with `k8s`.
  - Add source-template acquisition for local source and curl-piped installs.
  - Add a base64 helper and exact-key replacement helper; never perform a
    blanket placeholder replacement.
  - Generate the six Secret values into a new output only, apply `chmod 600`,
    and print the explicit apply command.
  - Add the optional sandbox artifact upload API key to the raw Secret so the
    generated document has the same secret contract as Docker/Helm.
- **Validation**: execute the installer against a temporary output via
  `CLOUISLE_SOURCE_DIR`; parse the result and decode every generated value.
  Confirm the source template remains unchanged and reusing an output fails.

### Stage 2: Gate raw backend workloads on PostgreSQL readiness

- **Files modified**: `deploy/k8s/clouisle.yaml`,
  `backend/tests/test_deploy_install_script.py`
- **Specific logic**:
  - Add `wait-for-postgres` init containers to `api`, `worker`,
    `sandbox-worker`, and `beat`.
  - Read PostgreSQL endpoint/user/database from `clouisle-config` and loop on
    `pg_isready` with a short retry interval.
  - Keep existing application readiness/liveness probes unchanged: the init
    container solves dependency ordering; probes retain runtime health checks.
- **Validation**: parse the manifest and assert each backend pod has the
  expected init container and no unrelated pod is changed.

### Stage 3: Document and verify deployment behavior

- **Files modified**: `README.md`, `deploy/README.md`,
  `docs/IMPLEMENTATION_PLAN.md`, this document
- **Specific logic**:
  - Document the third installer choice, output path environment variable,
    generated-secret security boundary, and explicit apply step.
  - Distinguish `kubectl` requirements for the raw-manifest path from Helm
    requirements for the chart path.
- **Validation**: `bash -n deploy/install.sh`, `uv run ruff check tests/test_deploy_install_script.py`, and `uv run pytest tests/test_deploy_install_script.py -q` passed. `kubectl apply --dry-run=client --validate=false -f deploy/k8s/clouisle.yaml` accepted all 20 documents. Full backend regression passed: 6692 passed, 3 skipped; line coverage 97.44% and branch coverage 95.01% (both above the 95% gate). Helm validation was not run because `helm` is not installed in the environment.

## Testing Strategy

- **Happy path**: non-interactive `CLOUISLE_DEPLOYMENT=k8s` creates a new
  parseable manifest whose required Secret entries decode to six distinct
  non-placeholder values.
- **Failure path**: existing output is rejected before any secret rotation or
  overwrite occurs.
- **Startup ordering**: static manifest assertions require PostgreSQL wait
  init containers for all database-dependent backend workloads.
- **Regression scope**: existing Docker and Helm installer routes retain their
  selection values and secret generation behavior; raw deployment YAML remains
  valid Kubernetes YAML.

## Risks & Mitigation

- **Generated file leaks**: it contains base64-encoded secrets, not encryption.
  Default/new output only and `0600` permissions reduce accidental exposure;
  docs require operators to store it securely.
- **Bad database configuration**: the init container intentionally waits rather
  than restarting application containers. Its pod logs reveal the failed
  `pg_isready` check; operators must correct ConfigMap/Secret values.
- **Template drift**: replacements are keyed to the known Secret names and
  fail if a key is absent, preventing silent insecure output.
- **No implicit cluster mutation**: generation never calls `kubectl apply`, so
  review and application stay under the operator's control.
