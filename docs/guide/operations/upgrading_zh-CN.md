# 版本升级

版本升级程序。

## 升级前检查清单

- [ ] 备份所有数据（PostgreSQL、Qdrant、uploads）
- [ ] 查看变更日志，确认是否有破坏性变更
- [ ] 在测试环境中测试升级
- [ ] 安排维护窗口
- [ ] 通知用户停机时间

## Docker Compose 升级

Compose 文件（`deploy/docker-compose.yml`）引用预构建镜像（如 `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest`），没有 `build:` 段，因此升级通过拉取新镜像完成。

```bash
cd deploy

# 1. 拉取最新代码
git pull

# 2. 拉取新镜像
docker compose pull

# 3. 停止服务
docker compose down

# 4. 启动服务
docker compose up -d

# 5. 验证
docker compose ps
docker compose logs --tail=50 api
```

如需自行维护镜像，请使用各服务的 Dockerfile 构建并推送：

```bash
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest .
```

## Kubernetes 升级

```bash
# 1. 构建并推送新镜像
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest .
docker push registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest

# 2. 更新清单
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. 监控滚动发布
kubectl rollout status deployment/api
```

## 回滚流程

如果升级失败：

```bash
# Docker Compose
docker compose down
git checkout previous-version
docker compose up -d

# Kubernetes
kubectl rollout undo deployment/api
```

## 升级后验证

- [ ] 检查所有服务是否正常运行
- [ ] 测试登录功能
- [ ] 测试 Agent 对话
- [ ] 测试工作流执行
- [ ] 检查错误日志

---

更多信息请参阅[主文档](../README.md)。
