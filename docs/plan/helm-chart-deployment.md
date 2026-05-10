# Helm Chart Deployment Design Document

## Background & Goals

- Kubernetes deployment currently relies on a large single-file manifest at `deploy/k8s/clouisle.yaml`.
- The current runtime model includes `api`, `worker`, `sandbox-worker`, `beat`, `frontend`, PostgreSQL, Redis, Qdrant, shared uploads, and Ingress.
- Editing raw YAML for each environment is cumbersome and error-prone.

Success criteria:
- Add a Helm Chart that deploys the current runtime model from `values.yaml`.
- Support production usage with `existingSecret`, custom images, ingress, and RWX uploads storage.
- Keep the single-file manifest as a fallback.

## High-Level Design

- New chart path: `deploy/helm/clouisle`.
- Default service names remain stable: `api`, `worker`, `sandbox-worker`, `beat`, `frontend`, `postgres`, `redis`, `qdrant`.
- Internal URLs default to `http://api:8000`, `http://frontend:3000`, and `http://qdrant:6333`.
- Built-in PostgreSQL, Redis, and Qdrant are enabled by default for simple installs and can be disabled for external services.
- Secrets can be chart-created for trials or referenced via an existing Kubernetes Secret for production.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/helm-chart-deployment.md`
- **Specific logic**: Track the Helm workstream and document values, templates, validation, and risks.
- **Validation**: Confirm the implementation index links to this document.

### Stage 2: Chart scaffold and values schema
- **Files modified**: `deploy/helm/clouisle/Chart.yaml`, `deploy/helm/clouisle/values.yaml`, `deploy/helm/clouisle/values-production.yaml`, `deploy/helm/clouisle/templates/_helpers.tpl`, `deploy/helm/clouisle/templates/NOTES.txt`
- **Specific logic**: Define chart metadata, images, config, secrets, service settings, persistence, ingress, and infrastructure toggles.
- **Validation**: `helm lint deploy/helm/clouisle` after templates are added.

### Stage 3: Application service templates
- **Files modified**: `deploy/helm/clouisle/templates/configmap.yaml`, `secret.yaml`, `serviceaccount.yaml`, `uploads-pvc.yaml`, `api-*`, `worker-deployment.yaml`, `sandbox-worker-deployment.yaml`, `beat-deployment.yaml`, `frontend-*`, `ingress.yaml`
- **Specific logic**: Render application workloads with shared env, stable service names, uploads PVC, and `/api` ingress routing.
- **Validation**: `helm template` default, production, and existingSecret modes.

### Stage 4: Built-in infrastructure templates
- **Files modified**: `deploy/helm/clouisle/templates/postgres-*`, `redis-*`, `qdrant-*`
- **Specific logic**: Render internal PostgreSQL/Redis/Qdrant when enabled; use external values in ConfigMap when disabled.
- **Validation**: Render with all infrastructure disabled and external hosts set.

### Stage 5: Documentation and validation
- **Files modified**: `deploy/README.md`, `deploy/helm/clouisle/README.md`, `docs/guide/deployment/kubernetes.md`, `docs/guide/deployment/DEPLOYMENT.md`, `docs/guide/deployment/DEPLOYMENT_zh-CN.md`
- **Specific logic**: Make Helm the recommended K8s deployment path while keeping the single-file manifest as fallback.
- **Validation**: `helm lint`, `helm template`, and `kubectl apply --dry-run=client` on rendered manifests.

## Testing Strategy

- `helm lint deploy/helm/clouisle`
- `helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace`
- `helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace -f deploy/helm/clouisle/values-production.yaml`
- `helm template clouisle deploy/helm/clouisle --namespace clouisle --set secrets.create=false --set secrets.existingSecret=clouisle-secret`
- `helm template clouisle deploy/helm/clouisle --namespace clouisle --set postgresql.enabled=false --set postgresql.external.host=postgres.example.internal --set redis.enabled=false --set redis.external.host=redis.example.internal --set qdrant.enabled=false --set qdrant.external.url=https://qdrant.example.internal`
- `helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace | kubectl apply --dry-run=client -f -`

## Current Validation Status

- Static stale-reference checks passed for old `clouisle-api`, Nginx frontend, and `backend` service references in deployment docs.
- `git diff --check` passed.
- Helm validation is pending because `helm` is not installed in the local environment (`command not found: helm`).

## Risks & Mitigation

- Stable service names do not support multiple releases in one namespace.
  - **Mitigation**: Document one release per namespace for the first chart version.
- `ReadWriteMany` uploads PVC may not be supported by every cluster.
  - **Mitigation**: Document single-replica or external shared storage alternatives.
- Default chart-created secrets are not production-safe.
  - **Mitigation**: Provide production values using `existingSecret`.
- Built-in PostgreSQL/Redis/Qdrant are not HA.
  - **Mitigation**: Support disabling built-ins and using external services.
