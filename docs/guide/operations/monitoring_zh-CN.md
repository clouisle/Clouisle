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

## 集成定时调度

现有 Beat 进程使用 `app.core.integration_scheduler:IntegrationScheduler`，正常情况下每两秒直接读取一次数据库中的管理员设置，不新增同步任务，也不在 Redis 另存开关副本。升级时需重启一次 Beat 加载新调度器；之后保存功能开关或同步源状态，无需重启。

- 微信任一功能启用时，调度及轮询批次进入普通 worker 消费的 `default` 队列。持久化领取仍限制全局积压并保证按到期时间公平推进，但轮询与其他任务共享执行槽位。参数见[轮询限制](../deployment/environment-variables.md#wechat-polling-limits)，切换见[升级及索引说明](upgrading_zh-CN.md#微信轮询升级切换)。
- 飞书 Agent 恢复跟随 `agent_chat`；登录、通知和手动通讯录同步不会产生周期性恢复任务。
- 飞书知识库同步不受这些能力开关控制：仅在集成启用且存在启用的同步源时派发。要暂停知识库同步，请关闭同步源。

完成同步后，关闭功能对应的条目不再存在于 Beat 活动调度表中，不会继续产生 `Task ... succeeded` 空任务日志。已经入队的任务仍可能出现，worker 会重新检查功能状态；已经开始的操作可能完成。读取设置失败时，Beat 暂停集成派发并记录 `Integration schedule refresh failed; pausing integration tasks`，其他维护任务继续运行；恢复数据库访问后自动恢复已启用的调度。Beat 必须保持单副本。

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
