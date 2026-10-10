# 监控与可观测性

Clouisle 的监控设置。

## 健康检查端点

- `/api/v1/health` — 基础健康检查（无需认证；用于容器健康检查）。
- `/api/v1/admin/observability/infrastructure` — 有界基础设施快照、依赖健康状态和安全显示的 `pg_stat_statements` 查询（需要 `admin:dashboard:access`）。缺失的探针显示为 `unknown`；不可用的统计不会伪装成零。

## 管理端可观测性

可观测性 API 根路径为 `/api/v1/admin/observability`。读取端点需要 `admin:dashboard:access`；确认告警、静默告警和更新规则需要 `admin:observability:manage`。

- `GET /summary?period=15m|1h|24h|7d&team_id=...` — 紧凑的运行汇总与趋势。样本不足时，百分位数和成功率为 `null`。
- `GET /runs` — 仅返回摘要的游标分页运行列表（`limit` 为 1–50）；单次运行详情通过 `GET /runs/{agent|workflow}/{run_id}` 单独获取。
- `GET /dependencies` — 在已记录遥测支持时返回模型、工具和检索聚合。
- `GET /queues` 和 `GET /infrastructure` — 有界的当前队列与基础设施快照。
- `GET /alerts`、`GET /alerts/rules`；`POST /alerts/{id}/acknowledge`、`POST /alerts/{id}/silence?duration_seconds=...`；`PUT /alerts/rules/{id}`。

运行摘要保存在紧凑索引记录中，保留 30 天。仅记录白名单中的时序、状态、模型名称、Token 数量、资源/团队标识符和错误代码；不会保存提示词、消息正文、工具参数/结果、凭据或 traceback。没有提交时间的历史运行不会回填。新的 Agent 记录包含模型聚合和安全的运行根 span；不会采集工具/检索子 span 及其聚合，API 会将这些数据标记为不可用，不会推断数值。告警规则在读取告警时评估，因此评估依赖 API 可用；定时清理任务使用现有的 `default` Celery 队列。

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
