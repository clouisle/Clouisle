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

运行摘要保存在紧凑索引记录中，保留 30 天，与大体积诊断内容分开存储；运行列表查询不会加载消息正文。已采集的工具/检索 span 和按需读取的工具结果可用于诊断；历史缺失数据不会使用当前资源配置重建。诊断内容可能包含用户消息、检索文档和工具结果，因此 `admin:dashboard:access` 应视为对潜在敏感运行内容的特权访问，而不只是聚合指标读取权限。告警规则在读取告警时评估，API 维护任务执行有界的保留期清理。

### 执行轨迹

从**运行诊断**打开某次运行，进入 `/dashboard/observability/runs/{agent|workflow}/{run_id}`。时间轴和有序步骤列表共用选中项；右侧检查器提供摘要、预览和原始数据，无需展开整棵执行树。可按名称、步骤类型和失败状态筛选。
执行步骤默认占满内容区整行；点击步骤后在右侧打开详情，再次点击同一步骤可收起。页面允许自然滚动；步骤与详情共用 640px、且不超过视口高度 70% 的区域高度，上下边缘对齐，标题与筛选栏固定，正文分别内部滚动。
运行列表复用通用分面筛选组件：左侧输入运行 ID，停止输入 300ms 后查询；来源和状态通过带加号的筛选按钮选择并立即生效，无需点击应用。防抖仅在此页面通过共享 useDebounce Hook 实现，不改变通用组件。来源和状态仍分别只支持单个值，清空选择表示不限。失败运行通过状态筛选，具体错误在运行记录和详情中查看。

`GET /runs/{source}/{run_id}` 返回轻量 `trajectory` 摘要；`GET /runs/{source}/{run_id}/trajectory/{entry_id}` 按需读取选中步骤的输入输出，查询限定在指定运行及来源内。两个端点都需要相同的管理员读取权限。原有 `/runs/{source}/{run_id}/tools/{tool_call_id}` 仍用于读取已记录的模型侧与展示侧工具结果。

部署后的 durable Agent 运行在调用前记录应用层归一化的模型消息、工具定义及白名单推理配置，在调用后记录实际响应和工具调用标识。它不是逐字节的供应商 HTTP 请求：适配器仍可能转换消息或补充参数。工具步骤关联到触发它的模型调用。工作流步骤展示实际节点输入、配置和输出，不伪装成聊天角色；推理内容仅展示供应商实际返回的部分。

模型输入、输出快照分别限制为 256 KiB；超限内容不保存正文并标记为部分记录，不会悄悄截断后伪装完整。每次写入采用 100 ms 超时的尽力采集，快照缺失不会使 Agent 运行失败。内容遵循 30 天遥测保留期。不采集传输层凭据和请求头，但不会自动脱敏用户正文或工具结果中包含的秘密。历史缺失上下文显示为未记录，采集仅从部署后开始。

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
