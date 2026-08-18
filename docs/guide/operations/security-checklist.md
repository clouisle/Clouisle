# Security Checklist

Use this checklist before exposing a Clouisle deployment to users. Items describe operator responsibilities; a checked item is not implied by the supplied Compose or Kubernetes files.

## Secrets and Configuration

- [ ] Replace every default value in `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `QDRANT_API_KEY`.
- [ ] Set a unique non-empty `INTERNAL_API_TOKEN`; API, worker, and sandbox-worker share it for the authenticated internal upload gateway.
- [ ] Keep `.env`, Kubernetes Secret manifests, and generated installer output out of source control and restrict file permissions.
- [ ] Store production secrets in a secret manager or an externally managed Kubernetes Secret where possible; rotate them through a planned maintenance window.
- [ ] Confirm `API_BASE_URL`/`API_INTERNAL_BASE_URL` are internal service URLs, while `PUBLIC_API_URL`, `FRONTEND_URL`, and `BACKEND_CORS_ORIGINS` contain the public browser origin.

## Authentication and Access

- [ ] Register the first account only after the deployment is private; the first registered user becomes the initial superuser.
- [ ] Configure session timeout, registration, email/SSO, and other site settings in the admin UI according to policy.
- [ ] Review team membership and admin permissions regularly; remove unused API keys and integrations.
- [ ] Enable MFA/SSO only after testing the configured provider and recovery path (when those features are used).

## Network and Proxy

- [ ] Terminate HTTPS at the external reverse proxy or Kubernetes Ingress and use valid certificates.
- [ ] Expose only the frontend/reverse-proxy port publicly. Keep PostgreSQL, Redis, Qdrant, and the direct API port on private networks.
- [ ] Set exact CORS origins; do not use `*` in production.
- [ ] Configure the proxy for streaming: HTTP/1.1, `proxy_buffering off`, and read/send timeouts compatible with the supplied 1800-second example.
- [ ] Restrict Kubernetes access to namespace `clouisle` with RBAC, NetworkPolicies, and an appropriate Ingress policy.

## Data Protection and Recovery

- [ ] Encrypt PostgreSQL, Qdrant, uploads, and backup storage at rest where supported.
- [ ] Back up PostgreSQL, Qdrant snapshots, and uploads on a defined schedule; Redis backup is optional because it contains cache/queue state.
- [ ] Keep encrypted off-site copies with a documented retention policy.
- [ ] Test a full restore, including Qdrant and uploads, and record RTO/RPO results.
- [ ] Do not run `docker compose down -v` or delete PVCs except as an intentional destructive operation.

## Runtime and Sandbox

- [ ] Pin production image tags/digests instead of relying on `latest`; scan images before deployment.
- [ ] Keep sandbox filesystem isolation enabled and retain the worker's required seccomp/capability settings. Review the protected sandbox hardening guidance before changing them.
- [ ] Limit sandbox egress and resource usage at the host/cluster layer where required by the threat model.
- [ ] Keep Docker, Kubernetes, PostgreSQL, Redis, Qdrant, Bubblewrap, and the host kernel patched.

## Logging and Incident Response

- [ ] Collect and protect API, worker, beat, frontend, and proxy logs; exclude tokens and passwords.
- [ ] Poll `GET /api/v1/health` and use the admin observability endpoints/dashboard (permission `admin:dashboard:access`). There is no built-in Prometheus `/metrics` endpoint.
- [ ] Alert on failed health checks, authentication anomalies, queue backlog, disk exhaustion, and backup failures.
- [ ] Document escalation, credential rotation, isolation, restore, and post-incident review procedures.
