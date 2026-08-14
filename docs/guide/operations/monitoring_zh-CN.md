# 监控与可观测性

Clouisle 的监控设置。

## 健康检查端点

- `/api/v1/health` - 基础健康检查（无需认证；用于容器健康检查）
- `/api/v1/admin/observability/system/health` - 详细系统健康状态：CPU、内存、磁盘、数据库、Redis 和 Celery Workers（需要 `admin:dashboard:access` 权限）

## 管理端可观测性

> **Note:** Clouisle 没有 Prometheus 风格的 `/metrics` 端点。可观测性数据由 `/api/v1/admin/observability/*` 管理端 API 和前端可观测性仪表盘（`/dashboard/observability`）提供。所有端点都需要 `admin:dashboard:access` 权限，并接受 `7d`、`30d`、`90d` 或 `all` 的 `time_range` 参数。

- `/overview` - 所选时间范围内的汇总统计
- `/agents`、`/agent/{agent_id}` - Agent 请求数、延迟百分位（p50/p95）、成功率、Token 用量
- `/workflows`、`/workflow/{workflow_id}` - 工作流运行统计、失败率、Token 用量
- `/timeouts`、`/throughput`、`/tokens` - 超时事件、请求吞吐量、按模型统计的 Token 消耗
- `/system/health`、`/system/trend`、`/system/slow-queries`、`/system/workers` - 系统健康快照、Celery 队列长度与 Worker 统计、慢数据库查询

## 日志

### 应用日志

```bash
# Docker Compose
docker compose logs -f api
docker compose logs -f worker

# Kubernetes
kubectl logs -f deployment/api
kubectl logs -f deployment/worker
```

### 访问日志

- Gunicorn 访问日志（api）
- 前端容器直接运行 `node server.js`；nginx 不属于部署的一部分。如需反向代理访问日志，请在前端之外自行部署 nginx。

## 与监控工具的集成

> **Note:** 未实现 / 路线图。Clouisle 不提供 `/metrics` 端点，也没有内置的 Prometheus、Grafana、Datadog 或 ELK 集成。如需外部监控，请收集应用与访问日志，并轮询健康检查端点和管理端可观测性 API。
