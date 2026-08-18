# Kubernetes Deployment

This guide covers deploying Clouisle on Kubernetes.

> **Note**: The example snippets below are representative summaries. The authoritative files are `deploy/helm/clouisle/` (Helm chart) and `deploy/k8s/clouisle.yaml` (single-file manifest) — always use those when in doubt.

## Overview

Kubernetes deployment provides:

- **High availability**: Multiple replicas and rolling updates
- **Load balancing**: Automatic traffic distribution
- **Self-healing**: Automatic pod restart on failure
- **Resource management**: CPU and memory limits
- **Secrets management**: Secure credential storage

## Recommended Helm Deployment

Helm is the recommended Kubernetes deployment method for Clouisle. It keeps the large manifest behind templates and lets each environment maintain a small values file.

```bash
# Lint only: this token is a non-production placeholder used to satisfy the chart's required key.
helm lint deploy/helm/clouisle \
  --set-string secrets.values.INTERNAL_API_TOKEN=lint-only-token

# Demo only. Do not expose this install; set every production secret or use an existing Secret.
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  --set-string secrets.values.SECRET_KEY="$(openssl rand -hex 32)" \
  --set-string secrets.values.POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --set-string secrets.values.REDIS_PASSWORD="$(openssl rand -hex 16)" \
  --set-string secrets.values.QDRANT_API_KEY="$(openssl rand -hex 16)" \
  --set-string secrets.values.INTERNAL_API_TOKEN="$(openssl rand -hex 32)"
```

The chart requires a non-empty `INTERNAL_API_TOKEN` when it creates a Secret; the same token is shared by API, worker, and sandbox-worker. For production, create `clouisle-secret` with all required values (including `INTERNAL_API_TOKEN`) and use `values-production.yaml`, which references that existing Secret:

```bash
kubectl create namespace clouisle --dry-run=client -o yaml | kubectl apply -f -
kubectl -n clouisle create secret generic clouisle-secret \
  --from-literal=SECRET_KEY='replace-with-strong-random-key' \
  --from-literal=POSTGRES_PASSWORD='replace-with-postgres-password' \
  --from-literal=REDIS_PASSWORD='replace-with-redis-password' \
  --from-literal=QDRANT_API_KEY='replace-with-qdrant-api-key' \
  --from-literal=SANDBOX_ARTIFACT_UPLOAD_API_KEY='replace-with-sandbox-artifact-key' \
  --from-literal=INTERNAL_API_TOKEN="$(openssl rand -base64 32)"

helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

The single-file manifest `deploy/k8s/clouisle.yaml` is available as a fallback for non-Helm environments. `deploy/install.sh` (`CLOUISLE_DEPLOYMENT=k8s`) generates a separate, secret-filled copy (mode `0600`) for review and manual application.


## Prerequisites

### Requirements

**Kubernetes Cluster:**
- Kubernetes 1.25+
- kubectl configured
- Helm 3.0+ (only for the Helm chart option)
- An Ingress controller (e.g. ingress-nginx)

**Resources:**
- Minimum: 4 CPU, 16GB RAM
- Recommended: 8 CPU, 32GB RAM
- Storage: 100GB+ persistent volumes

**External Services:**
- PostgreSQL 17+ with pg_search 0.24.3 installed and `pg_search,pg_stat_statements` preloaded (or use in-cluster — the supplied `clouisle-postgres-pg-search` image provides this)
- Redis 6+ (or use in-cluster)
- Qdrant 1.7+ (or use in-cluster)

### Install kubectl

```bash
# macOS
brew install kubectl

# Linux
# Select the release architecture: amd64 for x86_64, arm64 for aarch64/arm64.
ARCH="$(uname -m)"
case "$ARCH" in x86_64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;; *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; esac
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${ARCH}/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Verify installation
kubectl version --client
```

### Install Helm (Optional)

```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify installation
helm version
```

## Architecture

### Kubernetes Components

```
┌─────────────────────────────────────────────────┐
│                   Ingress                       │
│            (nginx-ingress-controller)           │
│        /api → api:8000    / → frontend:3000     │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
┌───────▼────────┐         ┌────────▼───────┐
│   Frontend     │         │      API       │
│   (Next.js)    │         │    (FastAPI)   │
│   Deployment   │         │   Deployment   │
│   2 replicas   │         │   2 replicas   │
└────────────────┘         └────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────▼────────┐      ┌──────────▼─────────┐    ┌─────────▼────────┐
│   PostgreSQL   │      │       Redis        │    │      Qdrant      │
│   StatefulSet  │      │    Deployment      │    │   StatefulSet    │
│   1 replica    │      │     1 replica      │    │    1 replica     │
└────────────────┘      └────────────────────┘    └──────────────────┘
        │                          │                          │
┌───────▼────────┐      ┌──────────▼─────────┐    ┌─────────▼────────┐
│ PVC 10Gi       │      │   emptyDir         │    │  PVC 10Gi        │
└────────────────┘      └────────────────────┘    └──────────────────┘
```

Additional workloads not shown: `worker` (Deployment, 2 replicas), `sandbox-worker` (Deployment, 1 replica), `beat` (Deployment, exactly 1 replica, `Recreate` strategy), and the `uploads-data` PVC (10Gi, `ReadWriteMany`, mounted only by `api`).

## Single-File Manifest

All resources are defined in a single file: `deploy/k8s/clouisle.yaml`.

```bash
# 1. Edit the manifest — replace secret placeholders and set your domain
vi deploy/k8s/clouisle.yaml

# 2. Apply everything. Backend workloads use wait-for-postgres init
#    containers to handle PostgreSQL startup; Redis and Qdrant readiness
#    still must be checked before application use.
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Wait for infrastructure
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s

# 4. Verify all pods
kubectl -n clouisle get pods
```

### Manifest Sections

The manifest contains 13 resource sections. It does **not** use YAML anchors — each section is written out explicitly:

| # | Resource | Kind | Notes |
|---|----------|------|-------|
| 1 | Namespace | Namespace | `clouisle` |
| 2 | ConfigMap | ConfigMap | `clouisle-config`, non-sensitive configuration |
| 3 | Secret | Secret | `clouisle-secret`, 6 keys (**must edit/generate**) |
| 4 | PostgreSQL | StatefulSet + Service + PVC | Headless Service, `postgres-data` 10Gi |
| 5 | Redis | Deployment + Service | |
| 6 | Qdrant | StatefulSet + Service + PVC | Headless Service, `qdrant-data` 10Gi |
| 7 | Uploads | PVC | `uploads-data` 10Gi, ReadWriteMany |
| 8 | API | Deployment + Service | 2 replicas, port 8000 |
| 9 | Worker | Deployment | 2 replicas, no Service |
| 10 | Sandbox Worker | Deployment | 1 replica, no Service |
| 11 | Beat | Deployment | 1 replica, `Recreate` strategy |
| 12 | Frontend | Deployment + Service | 2 replicas, port 3000 |
| 13 | Ingress | Ingress | `/api` → api:8000, `/` → frontend:3000 |

## Secrets Management

### Create Secrets

The manifest uses a **single Secret** `clouisle-secret` with 6 keys:

```bash
kubectl create secret generic clouisle-secret -n clouisle \
  --from-literal=SECRET_KEY='your-secret-key' \
  --from-literal=POSTGRES_PASSWORD='your-postgres-password' \
  --from-literal=REDIS_PASSWORD='your-redis-password' \
  --from-literal=QDRANT_API_KEY='your-qdrant-api-key' \
  --from-literal=SANDBOX_ARTIFACT_UPLOAD_API_KEY='your-sandbox-artifact-key' \
  --from-literal=INTERNAL_API_TOKEN='your-internal-gateway-token'
```

> **Note**: `INTERNAL_API_TOKEN` is required and shared by the api, worker, and sandbox-worker workloads (mounted via `INTERNAL_API_TOKEN_FILE`). `SANDBOX_ARTIFACT_UPLOAD_API_KEY` is used for sandbox artifact upload authentication.

When editing the manifest template directly, base64-encode each value:

```bash
echo -n 'your-strong-secret-key' | base64
```

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: clouisle-secret
  namespace: clouisle
type: Opaque
data:
  SECRET_KEY: <paste-base64-here>
  POSTGRES_PASSWORD: <paste-base64-here>
  REDIS_PASSWORD: <paste-base64-here>
  QDRANT_API_KEY: <paste-base64-here>
  SANDBOX_ARTIFACT_UPLOAD_API_KEY: <paste-base64-here>
  INTERNAL_API_TOKEN: <paste-base64-here>
```

> **Tip**: For production, consider using an external secret manager (Vault, AWS Secrets Manager, etc.) with the External Secrets Operator instead of storing secrets in YAML. `deploy/install.sh` in Kubernetes mode generates a separate `0600` output file with strong values and does not apply it automatically.

## ConfigMap

### Application Configuration

The non-sensitive configuration lives in the `clouisle-config` ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: clouisle-config
  namespace: clouisle
data:
  PROJECT_NAME: "Clouisle"
  TIMEZONE: "Asia/Shanghai"
  API_BASE_URL: "http://api:8000"
  PUBLIC_API_URL: ""
  API_INTERNAL_BASE_URL: "http://api:8000"
  SANDBOX_ARTIFACT_UPLOAD_BASE_URL: "http://api:8000"
  FRONTEND_URL: "http://frontend:3000"
  BACKEND_CORS_ORIGINS: '["http://localhost:3000"]'
  POSTGRES_SERVER: "postgres"
  POSTGRES_PORT: "5432"
  POSTGRES_USER: "postgres"
  POSTGRES_DB: "clouisle"
  REDIS_HOST: "redis"
  REDIS_PORT: "6379"
  VECTOR_BACKEND: "qdrant"
  QDRANT_URL: "http://qdrant:6333"
  QDRANT_COLLECTION_PREFIX: "kb_dim"
  QDRANT_DISTANCE: "Cosine"
  RETRIEVAL_HYBRID_KILL_SWITCH: "false"
  RETRIEVAL_SHADOW_ENABLED: "false"
```

For your public domain, put the public origin into `PUBLIC_API_URL` and set `FRONTEND_URL`/`BACKEND_CORS_ORIGINS` accordingly (keep `API_BASE_URL` internal).

## Persistent Volumes

The manifest declares three PVCs directly in `deploy/k8s/clouisle.yaml` (there is no separate `storage-class.yaml`/`pvc.yaml`):

| PVC | Size | Used By | Access Mode |
|-----|------|---------|-------------|
| `postgres-data` | 10Gi | PostgreSQL | ReadWriteOnce |
| `qdrant-data` | 10Gi | Qdrant | ReadWriteOnce |
| `uploads-data` | 10Gi | API (uploads) | ReadWriteMany |

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: clouisle
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
```

To change the size or add a `storageClassName`, edit the PVC definitions in `clouisle.yaml`:

```yaml
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: your-storage-class    # Add this line
  resources:
    requests:
      storage: 50Gi                       # Adjust size
```

> **Important**: `uploads-data` (ReadWriteMany) is mounted only by the `api` Deployment at `/app/uploads`. Workers and sandbox-worker do **not** mount it — they read/write authorized documents and upload sandbox artifacts through the authenticated internal upload gateway. `ReadWriteMany` is only required when scaling `api` beyond one replica with local upload storage; with `ReadWriteOnce` keep `api` at one replica. `ReadWriteMany` requires a storage class that supports it (NFS, CephFS, EFS, etc.).

## PostgreSQL Deployment

### PostgreSQL StatefulSet

The supplied PostgreSQL image is `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1` (PostgreSQL 17 with pg_search). It runs with `shared_preload_libraries=pg_search,pg_stat_statements`. Condensed excerpt:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: clouisle
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
  clusterIP: None          # headless
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: clouisle
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
          args:
            - "-c"
            - "shared_preload_libraries=pg_search,pg_stat_statements"
            - "-c"
            - "pg_stat_statements.track=all"
          env:
            - name: POSTGRES_USER
              valueFrom:
                configMapKeyRef: { name: clouisle-config, key: POSTGRES_USER }
            - name: POSTGRES_DB
              valueFrom:
                configMapKeyRef: { name: clouisle-config, key: POSTGRES_DB }
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef: { name: clouisle-secret, key: POSTGRES_PASSWORD }
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "postgres"]
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            exec:
              command: ["pg_isready", "-U", "postgres"]
            initialDelaySeconds: 15
            periodSeconds: 20
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-data
```

See the full StatefulSet (resources, probes) in `deploy/k8s/clouisle.yaml`.

## Redis Deployment

Redis runs as a **Deployment** with an `emptyDir` data volume (a cache; data is recoverable):

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: clouisle
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: clouisle
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          command:
            - sh
            - -c
            - |
              if [ -n "$REDIS_PASSWORD" ]; then
                redis-server --requirepass "$REDIS_PASSWORD"
              else
                redis-server
              fi
          env:
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef: { name: clouisle-secret, key: REDIS_PASSWORD }
          readinessProbe:
            exec:
              command: ["sh", "-c", "redis-cli ${REDIS_PASSWORD:+-a \"$REDIS_PASSWORD\"} ping | grep -q PONG"]
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            exec:
              command: ["sh", "-c", "redis-cli ${REDIS_PASSWORD:+-a \"$REDIS_PASSWORD\"} ping | grep -q PONG"]
            initialDelaySeconds: 15
            periodSeconds: 20
      volumes:
        - name: data
          emptyDir: {}
```

(Helm deployments use a 5Gi PVC for Redis persistence instead.)

## Qdrant Deployment

Qdrant runs as a StatefulSet with a headless Service and the `qdrant-data` PVC (10Gi):

```yaml
apiVersion: v1
kind: Service
metadata:
  name: qdrant
  namespace: clouisle
spec:
  selector:
    app: qdrant
  ports:
    - port: 6333
      targetPort: 6333
  clusterIP: None          # headless
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  namespace: clouisle
spec:
  serviceName: qdrant
  replicas: 1
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
        - name: qdrant
          image: qdrant/qdrant:v1.18.3
          env:
            - name: QDRANT__SERVICE__API_KEY
              valueFrom:
                secretKeyRef: { name: clouisle-secret, key: QDRANT_API_KEY }
          readinessProbe:
            httpGet:
              path: /healthz
              port: 6333
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 6333
            initialDelaySeconds: 15
            periodSeconds: 20
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: qdrant-data
```

## API Deployment

### API Deployment and Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: clouisle
spec:
  selector:
    app: api
  ports:
    - port: 8000
      targetPort: 8000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: clouisle
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      initContainers:
        - name: wait-for-postgres
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
          command:
            - sh
            - -ec
            - |
              until pg_isready -h "$POSTGRES_SERVER" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
                echo "Waiting for PostgreSQL at ${POSTGRES_SERVER}:${POSTGRES_PORT}..."
                sleep 2
              done
          env:
            - name: POSTGRES_SERVER
              valueFrom: { configMapKeyRef: { name: clouisle-config, key: POSTGRES_SERVER } }
            - name: POSTGRES_PORT
              valueFrom: { configMapKeyRef: { name: clouisle-config, key: POSTGRES_PORT } }
            - name: POSTGRES_USER
              valueFrom: { configMapKeyRef: { name: clouisle-config, key: POSTGRES_USER } }
            - name: POSTGRES_DB
              valueFrom: { configMapKeyRef: { name: clouisle-config, key: POSTGRES_DB } }
      containers:
        - name: api
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
          command: ["python", "main.py", "server", "-H", "0.0.0.0", "-w", "4", "--no-reload"]
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef: { name: clouisle-config }
            - secretRef: { name: clouisle-secret }
          env:
            - name: INTERNAL_API_TOKEN_FILE
              value: /var/run/secrets/clouisle/internal-api-token
          volumeMounts:
            - name: uploads
              mountPath: /app/uploads
            - name: internal-api-token
              mountPath: /var/run/secrets/clouisle
              readOnly: true
          readinessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 30
      volumes:
        - name: uploads
          persistentVolumeClaim:
            claimName: uploads-data
        - name: internal-api-token
          secret:
            secretName: clouisle-secret
            items:
              - key: INTERNAL_API_TOKEN
                path: internal-api-token
```

> **Note**: There is no Alembic migration init container — schema creation/updates run automatically at startup (Tortoise ORM). The `wait-for-postgres` init container (pg_isready) replaces the old busybox-wait pattern.

## Frontend Deployment

### Frontend Deployment and Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: clouisle
spec:
  selector:
    app: frontend
  ports:
    - port: 3000
      targetPort: 3000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: clouisle
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest
          ports:
            - containerPort: 3000
          readinessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 30
```

The frontend runs the Next.js standalone server (`node server.js`); it proxies `/api/*` to the backend via Next.js rewrites (backend URL from `BACKEND_INTERNAL_URL`, defaulting to `http://api:8000`). There is no `NEXT_PUBLIC_API_URL` runtime env in the supplied manifest (it is baked in at image build time).

## Worker and Beat Deployments

### Worker Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
  namespace: clouisle
spec:
  replicas: 2
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
    spec:
      initContainers:
        - name: wait-for-postgres
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
          command: ["sh", "-ec", "until pg_isready -h \"$POSTGRES_SERVER\" -p \"$POSTGRES_PORT\" -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; do sleep 2; done"]
          env: # POSTGRES_* from clouisle-config (same as api)
      containers:
        - name: worker
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
          command: ["python", "main.py", "worker", "-c", "4", "-Q", "default,knowledge,workflow"]
          envFrom:
            - configMapRef: { name: clouisle-config }
            - secretRef: { name: clouisle-secret }
          env:
            - name: UPLOAD_STORAGE_MODE
              value: "remote"
            - name: INTERNAL_API_TOKEN_FILE
              value: /var/run/secrets/clouisle/internal-api-token
          volumeMounts:
            - name: internal-api-token
              mountPath: /var/run/secrets/clouisle
              readOnly: true
      volumes:
        - name: internal-api-token
          secret:
            secretName: clouisle-secret
            items:
              - key: INTERNAL_API_TOKEN
                path: internal-api-token
```

### Sandbox Worker Deployment

Runs 1 replica of the `clouisle-sandbox-worker` image. Because the image's non-root user has empty effective capabilities, the deployment runs it as root (`runAsUser: 0`) with `CAP_SYS_ADMIN` added, `allowPrivilegeEscalation: false`, and an unconfined seccomp profile so Bubblewrap can create user/mount namespaces:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sandbox-worker
  namespace: clouisle
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sandbox-worker
  template:
    metadata:
      labels:
        app: sandbox-worker
    spec:
      initContainers:
        - name: wait-for-postgres
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
          command: ["sh", "-ec", "until pg_isready -h \"$POSTGRES_SERVER\" -p \"$POSTGRES_PORT\" -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; do sleep 2; done"]
          env: # POSTGRES_* from clouisle-config
      containers:
        - name: sandbox-worker
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest
          command: ["sh", "-c", "python main.py sandbox-worker -c \"${SANDBOX_WORKER_CONCURRENCY:-1}\""]
          envFrom:
            - configMapRef: { name: clouisle-config }
            - secretRef: { name: clouisle-secret }
          env:
            - name: UPLOAD_STORAGE_MODE
              value: "remote"
            - name: INTERNAL_API_TOKEN_FILE
              value: /var/run/secrets/clouisle/internal-api-token
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              add:
                - SYS_ADMIN
            runAsUser: 0
            seccompProfile:
              type: Unconfined
          volumeMounts:
            - name: internal-api-token
              mountPath: /var/run/secrets/clouisle
              readOnly: true
      volumes:
        - name: internal-api-token
          secret:
            secretName: clouisle-secret
            items:
              - key: INTERNAL_API_TOKEN
                path: internal-api-token
```

> **Note**: The task payload still executes inside a fresh Bubblewrap user+mount namespace. See [Code Sandbox → Host Kernel Requirements](../concepts/code-sandbox.md#host-kernel-requirements) and the deployment guide's sandbox section for details and hardening (user namespace remapping).

### Beat Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: beat
  namespace: clouisle
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: beat
  template:
    metadata:
      labels:
        app: beat
    spec:
      initContainers:
        - name: wait-for-postgres
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
          command: ["sh", "-ec", "until pg_isready -h \"$POSTGRES_SERVER\" -p \"$POSTGRES_PORT\" -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; do sleep 2; done"]
          env: # POSTGRES_* from clouisle-config
      containers:
        - name: beat
          image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
          command: ["python", "main.py", "beat"]
          envFrom:
            - configMapRef: { name: clouisle-config }
            - secretRef: { name: clouisle-secret }
```

> **Important**: Keep beat at exactly one replica — multiple beat instances cause duplicate scheduled tasks. The `Recreate` strategy ensures the old pod is fully terminated before a new one starts.

## Ingress Configuration

### Nginx Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: clouisle-ingress
  namespace: clouisle
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "1800"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "1800"
    nginx.ingress.kubernetes.io/proxy-http-version: "1.1"
    nginx.ingress.kubernetes.io/use-forwarded-headers: "true"
spec:
  ingressClassName: nginx
  rules:
    - host: clouisle.example.com    # Replace with your domain
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 3000
```

The `proxy-read-timeout`/`proxy-send-timeout` annotations (1800s) matter for long LLM streaming requests.

To enable TLS with cert-manager (automatic Let's Encrypt), add:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - clouisle.example.com
      secretName: clouisle-tls
```

## Horizontal Pod Autoscaler (optional)

The supplied manifest does **not** include HPA resources — replica counts are static. Add an HPA manually when you need CPU-based autoscaling:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: clouisle
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

## Monitoring

The supplied manifest does not expose a Prometheus `/metrics` endpoint or ServiceMonitor. Monitor the standard Kubernetes signals (`kubectl top`, logs, Ingress metrics) and Clouisle's admin observability features instead.

## Deploy All Components

```bash
# The single manifest contains everything: namespace, config, secrets, storage,
# databases, application workloads, and ingress.
kubectl apply -f deploy/k8s/clouisle.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n clouisle --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n clouisle --timeout=300s
kubectl wait --for=condition=ready pod -l app=qdrant -n clouisle --timeout=300s

# Watch application rollout
kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle rollout status deployment/worker
kubectl -n clouisle rollout status deployment/sandbox-worker
kubectl -n clouisle rollout status deployment/beat
kubectl -n clouisle rollout status deployment/frontend
```

### Verify Deployment

```bash
# Check all pods
kubectl get pods -n clouisle

# Check services
kubectl get svc -n clouisle

# Check ingress
kubectl get ingress -n clouisle

# View logs
kubectl logs -f deployment/api -n clouisle
kubectl logs -f deployment/frontend -n clouisle
```

## Updates and Rollbacks

### Rolling Update

```bash
# Update backend image
kubectl set image deployment/api api=registry.example.com/clouisle/clouisle-backend:v1.1.0 -n clouisle

# Update frontend image
kubectl set image deployment/frontend frontend=registry.example.com/clouisle/clouisle-frontend:v1.1.0 -n clouisle

# Check rollout status
kubectl rollout status deployment/api -n clouisle
kubectl rollout status deployment/frontend -n clouisle
```

### Rollback

```bash
# Rollback backend
kubectl rollout undo deployment/api -n clouisle

# Rollback to specific revision
kubectl rollout undo deployment/api --to-revision=2 -n clouisle

# View rollout history
kubectl rollout history deployment/api -n clouisle
```

## Backup and Restore

### Database Backup

```bash
# Backup PostgreSQL
kubectl exec -i -n clouisle statefulset/postgres -- pg_dump -U postgres -Fc clouisle > backup.dump

# Restore PostgreSQL
kubectl exec -i -n clouisle statefulset/postgres -- pg_restore -U postgres -d clouisle --clean --if-exists < backup.dump
```

See [Backup & Recovery](./backup-recovery.md) for the full procedures (Qdrant snapshot API, `uploads-data` PVC, Redis persistence).

## Troubleshooting

### Pod Not Starting

```bash
# Describe pod
kubectl describe pod <pod-name> -n clouisle

# View logs
kubectl logs <pod-name> -n clouisle

# Check events
kubectl get events -n clouisle --sort-by='.lastTimestamp'
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
kubectl exec -it statefulset/postgres -n clouisle -- pg_isready -U postgres

# Check service DNS
kubectl run -it --rm debug --image=busybox --restart=Never -n clouisle -- nslookup postgres
```

If application pods stay in `Init:0/1`, the `wait-for-postgres` init container is waiting — verify the `POSTGRES_*` values in `clouisle-config` match the database.

### Resource Issues

```bash
# Check resource usage
kubectl top pods -n clouisle
kubectl top nodes

# Describe node
kubectl describe node <node-name>
```

## Best Practices

**✅ Do:**
- Use resource limits and requests
- Use liveness and readiness probes
- Store secrets securely (Secret, not ConfigMap)
- Use persistent volumes for data
- Keep `beat` at exactly one replica
- Enable monitoring and logging
- Regular backups
- Use rolling updates

**❌ Don't:**
- Run without resource limits
- Skip health checks
- Store secrets in ConfigMaps
- Scale `beat` beyond 1 replica
- Ignore monitoring
- Skip backups
- Force delete pods

## Related Documentation

- [Deployment Guide](./DEPLOYMENT.md) - Full deployment guide
- [Docker Compose Deployment](./docker-compose.md) - Docker deployment
- [Environment Variables](./environment-variables.md) - Configuration
- [Troubleshooting](./troubleshooting.md) - Common issues

---

**Last Updated**: 2026-08-14
