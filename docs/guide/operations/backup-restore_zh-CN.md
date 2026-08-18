# 备份与恢复

请备份包含应用状态的各数据存储，并在依赖备份前实际验证恢复流程。

## 需要备份的内容

1. **PostgreSQL**：用户、团队、Agent、工作流、知识库元数据、会话和设置。
2. **Qdrant**：向量集合及其快照。
3. **上传文件**：Compose `api` 服务的 `/app/uploads` 卷，或 Kubernetes 的 `uploads-data` PVC。
4. **Redis**：可选的缓存和队列状态。计划内恢复时可保留 Redis dump，但排队任务也可以重新提交。
5. **配置与密钥**：单独、安全地保存 `.env`/密钥管理器记录；不要把明文密钥放进可广泛访问的备份归档。

## Docker Compose 备份

在包含提供的 `docker-compose.yml` 和 `.env` 的目录执行。cron 或非交互运行必须使用 `-T`。

```bash
# 这是在线、尽力而为的多存储备份，不是事务一致的完整快照；
# 如果必须跨存储严格一致，请另行安排停机窗口。
docker compose stop worker sandbox-worker beat

# PostgreSQL 自定义格式 dump
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" -Fc "${POSTGRES_DB:-clouisle}" > "postgres_$(date +%Y%m%d_%H%M%S).dump"

# Redis 可选；设置 REDIS_PASSWORD 时必须鉴权。
docker compose exec -T redis sh -c 'redis-cli ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} --rdb -' > "redis_$(date +%Y%m%d_%H%M%S).rdb"

# 上传文件只挂载到 api；通过容器流式备份，不假定 Docker 卷名。
docker compose exec -T api tar -czf - -C /app uploads > "uploads_$(date +%Y%m%d_%H%M%S).tar.gz"
```

Qdrant 需要对每个现有 collection 通过 API 创建和下载快照。提供的 Compose 镜像为 `qdrant/qdrant:v1.18.3`；恢复时请使用快照 API 语义兼容的 Qdrant 版本。启用鉴权时，运行任何 Qdrant API 命令前，先从受保护的部署 `.env` 或 Kubernetes Secret 将 `QDRANT_API_KEY` 导出到当前 shell；Docker Compose 不会把 `.env` 中的值自动导出到 shell。

代码片段默认使用 `http://localhost:6333`，只有在 Qdrant 发布了主机端口时才可用。如果生产环境按安全建议移除了该端口映射，请临时将 Qdrant 绑定到 `127.0.0.1:6333:6333` 并重新创建服务，或从连接 Compose 网络的辅助容器执行命令；完成后移除临时主机映射。

```bash
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_AUTH=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  QDRANT_AUTH=(--header "api-key: $QDRANT_API_KEY")
fi

# 列出所有当前 collection。将 COLLECTION 设为其中一个名称，然后对每个名称
# 重复创建、列出和下载快照的命令。
curl --fail "${QDRANT_URL}/collections" "${QDRANT_AUTH[@]}"
COLLECTION='replace-with-a-name-returned-above'

# 创建 collection 快照。
curl --fail --request POST "${QDRANT_URL}/collections/${COLLECTION}/snapshots" \
  "${QDRANT_AUTH[@]}"
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots" \
  "${QDRANT_AUTH[@]}"
SNAPSHOT_NAME='replace-with-the-name-returned-above'
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_NAME}" \
  "${QDRANT_AUTH[@]}" \
  --output "${COLLECTION}_${SNAPSHOT_NAME}.snapshot"
```
对每个返回的 collection 重复此流程。Clouisle 在使用相应功能时通常会创建知识库向量 collection `kb_dim_<dimension>`，以及记忆向量 collection `memory_entities_dim_<dimension>`。


备份结束后启动已停止的 Worker：

```bash
docker compose start worker sandbox-worker beat
```

## Kubernetes 备份

提供的 manifest 使用 `clouisle` 命名空间、`postgres` 和 `qdrant` StatefulSet，以及由 `api` 挂载的 `uploads-data` PVC。请使用集群明确提供的备份目的地（对象存储、已创建的备份 PVC 或 CSI 快照）；该 manifest **没有**声明通用的 `backup-pvc`。

```bash
# PostgreSQL；保留 stdout 以便导出 dump。
kubectl -n clouisle exec -i statefulset/postgres -- pg_dump -U postgres -Fc clouisle > postgres.dump

# 上传文件；通过 api Pod 流式导出 PVC。
kubectl -n clouisle exec -i deployment/api -- tar -czf - -C /app uploads > uploads.tar.gz

# Qdrant 镜像不保证包含 curl。在一个终端转发 Qdrant，
# 再在另一个终端使用 QDRANT_URL=http://127.0.0.1:6333 执行快照 API 命令。
kubectl -n clouisle port-forward statefulset/qdrant 6333:6333
```

## 恢复

恢复 PostgreSQL 和 Qdrant 时保持 API 与 Worker 停止。保留数据库和 Qdrant 服务运行，但两个存储都恢复完成前不要启动应用服务：

```bash
# Compose 示例
docker compose stop api worker sandbox-worker beat
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-clouisle}" --clean --if-exists < postgres.dump
```

Kubernetes 示例：

```bash
kubectl -n clouisle scale deployment api worker sandbox-worker beat --replicas=0
kubectl -n clouisle exec -i statefulset/postgres -- pg_restore -U postgres -d clouisle --clean --if-exists < postgres.dump
```

在启动 API、worker 或 beat 前，为每个已备份的 collection 恢复 Qdrant 快照。上传操作会恢复 collection，不要添加不受支持的单独 `/recover` 请求。将 `COLLECTION` 与 `SNAPSHOT_FILE` 设为匹配的一对，并对每个已备份 collection 重复上传。

```bash
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
# 将这两个变量设为一对匹配的 collection/快照；对每个 collection 重复。
COLLECTION='replace-with-a-backed-up-collection-name'
SNAPSHOT_FILE='replace-with-the-matching-snapshot.snapshot'
QDRANT_AUTH=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  QDRANT_AUTH=(--header "api-key: $QDRANT_API_KEY")
fi

curl --fail --request POST \
  "${QDRANT_URL}/collections/${COLLECTION}/snapshots/upload" \
  "${QDRANT_AUTH[@]}" \
  --form "snapshot=@${SNAPSHOT_FILE}"
```

PostgreSQL 和 Qdrant 恢复完成后，只启动 API 恢复 uploads 压缩包，再将应用工作负载恢复为原有副本数。提供的 manifest 使用 `api=2`、`worker=2`、`sandbox-worker=1` 和 `beat=1`；如果部署曾扩容，请按实际副本数调整。

```bash
# Compose
docker compose start api
docker compose exec -T api tar -xzf - -C /app < uploads.tar.gz
docker compose start worker sandbox-worker beat

# Kubernetes
kubectl -n clouisle scale deployment api --replicas=2
kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle exec -i deployment/api -- tar -xzf - -C /app < uploads.tar.gz
kubectl -n clouisle scale deployment worker --replicas=2
kubectl -n clouisle scale deployment sandbox-worker --replicas=1
kubectl -n clouisle scale deployment beat --replicas=1
```

恢复后验证 `/api/v1/health`、登录、知识库检索、文件上传和一个代表性工作流。Redis 队列状态是可选的；不恢复时，请重新提交故障时处于排队状态的任务。

## 自动备份

可用主机 cron 调度 Compose 命令，或在 Kubernetes CronJob 中执行等价命令。CronJob 必须挂载已明确创建的备份目的地，并从 Secret 读取凭据。保留加密的异地副本、定义保留期限，并定期在临时环境执行恢复测试。

详见[部署指南](../deployment/DEPLOYMENT.md)和[备份与恢复](../deployment/backup-recovery.md)。
