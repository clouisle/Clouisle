# 升级 Clouisle

升级应安排维护窗口。提供的 Compose 文件引用预构建镜像且没有 `build:` 段，不保证滚动更新。生产环境应使用不可变 image tag 或 digest，不要依赖 `latest`。

## 升级前检查清单

- [ ] 备份 PostgreSQL、Qdrant 快照和上传文件；决定是否需要保留 Redis 队列状态。
- [ ] 查看发布说明中的破坏性变更和配置变更。
- [ ] 在 staging 用完全相同的 image tag 测试。
- [ ] 确认回滚 image tag/digest 和可用的备份恢复路径。
- [ ] 安排并通知维护窗口。

## Docker Compose 升级

在包含当前 `docker-compose.yml` 和 `.env` 的安装目录执行（安装器默认目录为 `/opt/clouisle`）。以下命令不会本地构建镜像；请先在 Compose/环境配置中替换为已发布的 `IMAGE_TAG`。

```bash
cd /opt/clouisle  # 替换为实际安装目录
git pull          # 仅源代码 checkout 需要；安装器部署可能没有 Git 仓库

# 拉取固定版本并重建服务。这是停止/重建操作，不是滚动重启。
docker compose pull
docker compose up -d --force-recreate

# 验证所有服务和 API 健康检查
docker compose ps
docker compose logs --tail=50 api worker sandbox-worker beat frontend
curl --fail http://localhost:8000/api/v1/health
```

如果自行构建镜像，必须从**仓库根目录**构建，给三个镜像使用同一个不可变 release tag 并推送，然后更新 Compose 中的镜像引用，再执行 `docker compose pull`：

```bash
# 从仓库根目录执行；REGISTRY 和 IMAGE_TAG 是需替换的示例。
REGISTRY=registry.example.com/clouisle
IMAGE_TAG=vX.Y.Z
docker build -f deploy/dockerfiles/backend.Dockerfile -t "$REGISTRY/clouisle-backend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t "$REGISTRY/clouisle-frontend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG" .
docker push "$REGISTRY/clouisle-backend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-frontend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"
```

## Kubernetes 升级

提供的 Kubernetes 部署使用 `clouisle` 命名空间，并分别运行 `api`、`worker`、`sandbox-worker`、`beat` 和 `frontend` Deployment。从仓库根目录构建并发布不可变 tag，更新所有应用工作负载，再逐一观察 rollout：

```bash
# 通用 registry/tag 示例：替换为实际值。
REGISTRY=registry.example.com/clouisle
IMAGE_TAG=vX.Y.Z
docker build -f deploy/dockerfiles/backend.Dockerfile -t "$REGISTRY/clouisle-backend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t "$REGISTRY/clouisle-frontend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG" .
docker push "$REGISTRY/clouisle-backend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-frontend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"

kubectl -n clouisle set image deployment/api api="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/worker worker="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/sandbox-worker sandbox-worker="$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"
kubectl -n clouisle set image deployment/beat beat="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/frontend frontend="$REGISTRY/clouisle-frontend:$IMAGE_TAG"

kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle rollout status deployment/worker
kubectl -n clouisle rollout status deployment/sandbox-worker
kubectl -n clouisle rollout status deployment/beat
kubectl -n clouisle rollout status deployment/frontend
```

使用 Helm 时，在 values 文件中更新 backend、sandbox-worker 和 frontend tag，并带 `--namespace clouisle` 执行 `helm upgrade`；保留现有 Secret 及全部必需 key。不要执行常规 Alembic 命令：Clouisle 在 backend 启动时通过 Tortoise ORM（`init_db`）初始化/更新 schema。

## 回滚

```bash
# Compose：在当前配置中恢复上一版本 tag/digest，然后重建。
docker compose pull
docker compose up -d --force-recreate

# Kubernetes：在 clouisle 命名空间回滚每个应用 Deployment。
kubectl -n clouisle rollout undo deployment/api
kubectl -n clouisle rollout undo deployment/worker
kubectl -n clouisle rollout undo deployment/sandbox-worker
kubectl -n clouisle rollout undo deployment/beat
kubectl -n clouisle rollout undo deployment/frontend
```

如果数据/schema 发生不兼容变更，不要在未遵循该版本发布说明恢复流程的情况下回滚应用代码。

## 升级后验证

- [ ] 所有基础设施和应用服务正常运行。
- [ ] 通过公网代理访问 `GET /api/v1/health` 成功。
- [ ] 登录、Agent 对话/流式响应、文件上传、知识库检索和工作流执行正常。
- [ ] worker、sandbox-worker、beat 日志无启动错误；beat 始终只有 1 个副本。
- [ ] 备份与监控任务仍在运行。
