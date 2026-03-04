# Kubernetes Deployment

This guide covers deploying Clouisle on Kubernetes.

## Overview

Kubernetes deployment provides:

- **High availability**: Multiple replicas and auto-scaling
- **Load balancing**: Automatic traffic distribution
- **Rolling updates**: Zero-downtime deployments
- **Self-healing**: Automatic pod restart on failure
- **Resource management**: CPU and memory limits
- **Secrets management**: Secure credential storage

## Prerequisites

### Requirements

**Kubernetes Cluster:**
- Kubernetes 1.24+
- kubectl configured
- Helm 3.0+ (optional)

**Resources:**
- Minimum: 4 CPU, 16GB RAM
- Recommended: 8 CPU, 32GB RAM
- Storage: 100GB+ persistent volumes

**External Services:**
- PostgreSQL 14+ (or use in-cluster)
- Redis 6+ (or use in-cluster)
- Qdrant 1.7+ (or use in-cluster)

### Install kubectl

```bash
# macOS
brew install kubectl

# Linux
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
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
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
┌───────▼────────┐         ┌────────▼───────┐
│   Frontend     │         │    Backend     │
│   (Next.js)    │         │   (FastAPI)    │
│   Deployment   │         │   Deployment   │
│   3 replicas   │         │   3 replicas   │
└────────────────┘         └────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────▼────────┐      ┌──────────▼─────────┐    ┌─────────▼────────┐
│   PostgreSQL   │      │       Redis        │    │      Qdrant      │
│   StatefulSet  │      │    StatefulSet     │    │   StatefulSet    │
│   1 replica    │      │     1 replica      │    │    1 replica     │
└────────────────┘      └────────────────────┘    └──────────────────┘
        │                          │                          │
┌───────▼────────┐      ┌──────────▼─────────┐    ┌─────────▼────────┐
│  PVC (100GB)   │      │    PVC (10GB)      │    │   PVC (50GB)     │
└────────────────┘      └────────────────────┘    └──────────────────┘
```

## Namespace Setup

### Create Namespace

```bash
# Create namespace
kubectl create namespace clouisle

# Set as default namespace
kubectl config set-context --current --namespace=clouisle
```

### Create Namespace YAML

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: clouisle
  labels:
    name: clouisle
    environment: production
```

```bash
kubectl apply -f namespace.yaml
```

## Secrets Management

### Create Secrets

**Database Credentials:**

```bash
kubectl create secret generic postgres-secret \
  --from-literal=username=clouisle \
  --from-literal=password=your-secure-password \
  --from-literal=database=clouisle \
  -n clouisle
```

**Redis Password:**

```bash
kubectl create secret generic redis-secret \
  --from-literal=password=your-redis-password \
  -n clouisle
```

**Application Secrets:**

```bash
kubectl create secret generic app-secret \
  --from-literal=secret-key=your-secret-key \
  --from-literal=jwt-secret=your-jwt-secret \
  --from-literal=openai-api-key=sk-... \
  --from-literal=anthropic-api-key=sk-ant-... \
  -n clouisle
```

**Secrets YAML:**

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: clouisle
type: Opaque
stringData:
  username: clouisle
  password: your-secure-password
  database: clouisle
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-secret
  namespace: clouisle
type: Opaque
stringData:
  password: your-redis-password
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secret
  namespace: clouisle
type: Opaque
stringData:
  secret-key: your-secret-key
  jwt-secret: your-jwt-secret
  openai-api-key: sk-...
  anthropic-api-key: sk-ant-...
```

```bash
kubectl apply -f secrets.yaml
```

## ConfigMap

### Application Configuration

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: clouisle
data:
  # Site Configuration
  SITE_NAME: "Clouisle"
  SITE_URL: "https://your-domain.com"
  FRONTEND_URL: "https://your-domain.com"

  # Database Configuration
  POSTGRES_HOST: "postgres-service"
  POSTGRES_PORT: "5432"

  # Redis Configuration
  REDIS_HOST: "redis-service"
  REDIS_PORT: "6379"

  # Qdrant Configuration
  QDRANT_HOST: "qdrant-service"
  QDRANT_PORT: "6333"

  # Feature Flags
  ENABLE_REGISTRATION: "true"
  ENABLE_SSO: "true"

  # CORS
  CORS_ORIGINS: "https://your-domain.com"
```

```bash
kubectl apply -f configmap.yaml
```

## Persistent Volumes

### Storage Class

```yaml
# storage-class.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: clouisle-storage
provisioner: kubernetes.io/aws-ebs  # Change based on cloud provider
parameters:
  type: gp3
  fsType: ext4
allowVolumeExpansion: true
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
```

### Persistent Volume Claims

```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: clouisle
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: clouisle-storage
  resources:
    requests:
      storage: 100Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  namespace: clouisle
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: clouisle-storage
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qdrant-pvc
  namespace: clouisle
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: clouisle-storage
  resources:
    requests:
      storage: 50Gi
```

```bash
kubectl apply -f storage-class.yaml
kubectl apply -f pvc.yaml
```

## Database Deployment

### PostgreSQL StatefulSet

```yaml
# postgres.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: clouisle
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
  clusterIP: None
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: clouisle
spec:
  serviceName: postgres-service
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
        image: postgres:14
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: database
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - clouisle
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - clouisle
          initialDelaySeconds: 5
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: clouisle-storage
      resources:
        requests:
          storage: 100Gi
```

```bash
kubectl apply -f postgres.yaml
```

## Redis Deployment

### Redis StatefulSet

```yaml
# redis.yaml
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: clouisle
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
  clusterIP: None
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: clouisle
spec:
  serviceName: redis-service
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
        ports:
        - containerPort: 6379
        command:
        - redis-server
        - --requirepass
        - $(REDIS_PASSWORD)
        - --appendonly
        - "yes"
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: password
        volumeMounts:
        - name: redis-storage
          mountPath: /data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: redis-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: clouisle-storage
      resources:
        requests:
          storage: 10Gi
```

```bash
kubectl apply -f redis.yaml
```

## Qdrant Deployment

### Qdrant StatefulSet

```yaml
# qdrant.yaml
apiVersion: v1
kind: Service
metadata:
  name: qdrant-service
  namespace: clouisle
spec:
  selector:
    app: qdrant
  ports:
    - name: http
      port: 6333
      targetPort: 6333
    - name: grpc
      port: 6334
      targetPort: 6334
  clusterIP: None
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  namespace: clouisle
spec:
  serviceName: qdrant-service
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
        image: qdrant/qdrant:v1.7.4
        ports:
        - containerPort: 6333
          name: http
        - containerPort: 6334
          name: grpc
        volumeMounts:
        - name: qdrant-storage
          mountPath: /qdrant/storage
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /
            port: 6333
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 6333
          initialDelaySeconds: 5
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: qdrant-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: clouisle-storage
      resources:
        requests:
          storage: 50Gi
```

```bash
kubectl apply -f qdrant.yaml
```

## Backend Deployment

### Backend Deployment and Service

```yaml
# backend.yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: clouisle
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: clouisle
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      initContainers:
      - name: wait-for-postgres
        image: busybox:1.35
        command: ['sh', '-c', 'until nc -z postgres-service 5432; do echo waiting for postgres; sleep 2; done;']
      - name: run-migrations
        image: your-registry/clouisle-backend:latest
        command: ['alembic', 'upgrade', 'head']
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: secret-key
      containers:
      - name: backend
        image: your-registry/clouisle-backend:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: password
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: secret-key
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: jwt-secret
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: openai-api-key
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: anthropic-api-key
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

```bash
kubectl apply -f backend.yaml
```

## Frontend Deployment

### Frontend Deployment and Service

```yaml
# frontend.yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend-service
  namespace: clouisle
spec:
  selector:
    app: frontend
  ports:
    - port: 3000
      targetPort: 3000
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: clouisle
spec:
  replicas: 3
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
        image: your-registry/clouisle-frontend:latest
        ports:
        - containerPort: 3000
        env:
        - name: NEXT_PUBLIC_API_URL
          value: "https://your-domain.com/api"
        - name: NEXT_PUBLIC_SITE_URL
          value: "https://your-domain.com"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
```

```bash
kubectl apply -f frontend.yaml
```

## Celery Workers

### Celery Worker Deployment

```yaml
# celery-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
  namespace: clouisle
spec:
  replicas: 2
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
      - name: celery-worker
        image: your-registry/clouisle-backend:latest
        command: ['celery', '-A', 'app.core.celery', 'worker', '--loglevel=info']
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: password
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: secret-key
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: openai-api-key
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-beat
  namespace: clouisle
spec:
  replicas: 1
  selector:
    matchLabels:
      app: celery-beat
  template:
    metadata:
      labels:
        app: celery-beat
    spec:
      containers:
      - name: celery-beat
        image: your-registry/clouisle-backend:latest
        command: ['celery', '-A', 'app.core.celery', 'beat', '--loglevel=info']
        envFrom:
        - configMapRef:
            name: app-config
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: password
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "200m"
```

```bash
kubectl apply -f celery-worker.yaml
```

## Ingress Configuration

### Nginx Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: clouisle-ingress
  namespace: clouisle
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
spec:
  tls:
  - hosts:
    - your-domain.com
    secretName: clouisle-tls
  rules:
  - host: your-domain.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: backend-service
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend-service
            port:
              number: 3000
```

```bash
kubectl apply -f ingress.yaml
```

## Horizontal Pod Autoscaler

### HPA Configuration

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
  namespace: clouisle
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: frontend-hpa
  namespace: clouisle
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: frontend
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

```bash
kubectl apply -f hpa.yaml
```

## Monitoring

### Prometheus ServiceMonitor

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: clouisle-backend
  namespace: clouisle
spec:
  selector:
    matchLabels:
      app: backend
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

## Deployment

### Deploy All Components

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create secrets
kubectl apply -f secrets.yaml

# Create configmap
kubectl apply -f configmap.yaml

# Create storage
kubectl apply -f storage-class.yaml
kubectl apply -f pvc.yaml

# Deploy databases
kubectl apply -f postgres.yaml
kubectl apply -f redis.yaml
kubectl apply -f qdrant.yaml

# Wait for databases to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n clouisle --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n clouisle --timeout=300s
kubectl wait --for=condition=ready pod -l app=qdrant -n clouisle --timeout=300s

# Deploy application
kubectl apply -f backend.yaml
kubectl apply -f frontend.yaml
kubectl apply -f celery-worker.yaml

# Deploy ingress
kubectl apply -f ingress.yaml

# Deploy HPA
kubectl apply -f hpa.yaml
```

### Verify Deployment

```bash
# Check all pods
kubectl get pods -n clouisle

# Check services
kubectl get svc -n clouisle

# Check ingress
kubectl get ingress -n clouisle

# Check HPA
kubectl get hpa -n clouisle

# View logs
kubectl logs -f deployment/backend -n clouisle
kubectl logs -f deployment/frontend -n clouisle
```

## Updates and Rollbacks

### Rolling Update

```bash
# Update backend image
kubectl set image deployment/backend backend=your-registry/clouisle-backend:v1.1.0 -n clouisle

# Update frontend image
kubectl set image deployment/frontend frontend=your-registry/clouisle-frontend:v1.1.0 -n clouisle

# Check rollout status
kubectl rollout status deployment/backend -n clouisle
kubectl rollout status deployment/frontend -n clouisle
```

### Rollback

```bash
# Rollback backend
kubectl rollout undo deployment/backend -n clouisle

# Rollback to specific revision
kubectl rollout undo deployment/backend --to-revision=2 -n clouisle

# View rollout history
kubectl rollout history deployment/backend -n clouisle
```

## Backup and Restore

### Database Backup

```bash
# Backup PostgreSQL
kubectl exec -n clouisle postgres-0 -- pg_dump -U clouisle clouisle > backup.sql

# Restore PostgreSQL
kubectl exec -i -n clouisle postgres-0 -- psql -U clouisle clouisle < backup.sql
```

### Volume Snapshots

```yaml
# volumesnapshot.yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-snapshot
  namespace: clouisle
spec:
  volumeSnapshotClassName: csi-snapclass
  source:
    persistentVolumeClaimName: postgres-pvc
```

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
kubectl exec -it postgres-0 -n clouisle -- psql -U clouisle

# Test Redis connection
kubectl exec -it redis-0 -n clouisle -- redis-cli ping

# Check service DNS
kubectl run -it --rm debug --image=busybox --restart=Never -n clouisle -- nslookup postgres-service
```

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
- Enable horizontal pod autoscaling
- Use liveness and readiness probes
- Store secrets securely
- Use persistent volumes for data
- Enable monitoring and logging
- Regular backups
- Use rolling updates

**❌ Don't:**
- Run without resource limits
- Skip health checks
- Store secrets in ConfigMaps
- Use emptyDir for data
- Ignore monitoring
- Skip backups
- Force delete pods

## Related Documentation

- [Docker Compose Deployment](./docker-compose.md) - Docker deployment
- [Environment Variables](./environment-variables.md) - Configuration
- [Troubleshooting](./troubleshooting.md) - Common issues
- [Monitoring](../operations/monitoring.md) - Monitoring guide

---

**Last Updated**: 2026-02-11
