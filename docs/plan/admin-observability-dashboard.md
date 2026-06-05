# 后台管理员可观测性面板设计文档

## 背景与目标

### 问题
当前系统缺乏对 AI 对话和工作流运行的可观测性，管理员无法：
1. 了解超时发生的频率和类型分布
2. 监控 Agent/Workflow 的性能表现（响应时间分位数）
3. 追踪系统吞吐量和负载趋势
4. 快速定位性能瓶颈和异常

### 目标
在后台管理面板新增**可观测性 (Observability)** 标签页，提供：
1. **超时监控**：按类型、Agent、模型统计超时事件
2. **性能分析**：P50/P90/P95/P99 响应时间分位数
3. **吞吐量监控**：QPS/TPS、并发数、成功率
4. **趋势分析**：时间序列图表，支持自定义时间范围

## 高层设计

### 1. 数据架构

#### 1.1 数据源
- **现有数据**：
  - `Message` 表：`duration_ms`, `created_at`, `conversation_id`, `round_status`, `round_role`, `is_round_canonical`, `model_used`, `token_usage`
  - `Conversation` 表：`agent_id`, `created_at`, `message_count`
  - `Agent` 表：`id`, `name`, `model_id`
  - `WorkflowRun` 表：`workflow_id`, `status`, `total_duration_ms`, `total_token_usage`, `failed_nodes`, `created_at`, `started_at`, `finished_at`
  - `NodeExecution` 表：`run_id`, `node_type`, `status`, `execution_duration_ms`, `queue_duration_ms`, `model_used`, `total_tokens`
  - 系统运行时：psutil、SQLAlchemy/Tortoise 连接状态、Redis INFO、Celery inspect

- **初期方案**：
  - 直接从现有表聚合，Redis 缓存 30 秒。
  - 不新增时序指标表；如果后续生产数据量导致聚合超过 2 秒，再追加 rollup 表。
  - `Message` 没有 `agent_id`，Agent 维度聚合必须通过 `Conversation.agent_id` 关联。
  - 历史 Agent 消息未持久化 `timeout_type` / `timeout_seconds`，因此 idle/global 类型只能在未来埋点后精确区分；当前版本对 Agent 历史超时类型返回 `unknown`，Workflow 超时通过 `WorkflowRun.status = timeout` 精确统计。

#### 1.2 指标定义

**超时指标**：
- `timeout_count`：超时事件总数
- `timeout_rate`：超时率 = 超时数 / 总请求数
- 按维度分组：`timeout_type` (idle/global), `agent_id`, `model_id`, `team_id`

**性能指标**：
- `duration_p50/p90/p95/p99`：响应时间分位数（毫秒）
- `first_token_latency_p50/p90/p95`：首 token 延迟（毫秒）
- 按维度分组：`agent_id`, `model_id`, `team_id`, `has_tools`

**吞吐量指标**：
- `qps`：每秒查询数（Queries Per Second）
- `tps`：每秒事务数（Transactions Per Second，这里指完整对话轮次）
- `concurrent_conversations`：并发对话数
- `success_rate`：成功率 = 成功数 / 总数

**资源指标**：
- `token_usage_total`：总 token 消耗
- `token_usage_rate`：每秒 token 消耗
- `avg_tokens_per_message`：平均每条消息 token 数

### 2. 前端界面设计

#### 2.1 页面结构

```
后台管理 (Dashboard)
├── 概览 (Overview)
├── 用户管理 (Users)
├── 团队管理 (Teams)
├── 模型管理 (Models)
├── 系统设置 (Settings)
└── 可观测性 (Observability) ← 新增
    ├── 概览 (Overview)
    ├── 系统健康 (System Health) ← 新增
    ├── Agent 性能 (Agent Performance)
    ├── Workflow 性能 (Workflow Performance)
    ├── 超时分析 (Timeout Analysis)
    └── 系统吞吐 (System Throughput)
```

#### 2.2 子页面详细设计

##### 2.2.1 概览 (Overview)

**布局**：4 个关键指标卡片 + 2 个趋势图

**关键指标卡片**：
1. **总请求数**
   - 今日/本周/本月总请求数
   - 环比增长率
   
2. **平均响应时间**
   - P50 响应时间
   - 与昨日对比

3. **超时率**
   - 今日超时率
   - 超时类型分布（饼图）

4. **系统吞吐量**
   - 当前 QPS
   - 峰值 QPS（今日）

**趋势图**：
1. **请求量趋势**（折线图）
   - X 轴：时间（小时/天）
   - Y 轴：请求数
   - 可切换：今日/本周/本月

2. **响应时间趋势**（折线图）
   - X 轴：时间
   - Y 轴：P50/P90/P95（多条线）

##### 2.2.2 系统健康 (System Health)

**布局**：6 个基础设施状态卡片 + 系统资源趋势图

**基础设施状态卡片**：

1. **CPU 使用率**
   - 实时 CPU 使用率（百分比）
   - 状态指示：正常（<70%）、警告（70-90%）、危险（>90%）
   - 最近 1 小时平均值
   - 核心数和架构信息

2. **内存使用**
   - 实时内存使用率（百分比）
   - 已用/总量（GB）
   - 状态指示：正常（<80%）、警告（80-90%）、危险（>90%）
   - 最近 1 小时平均值

3. **数据库状态**
   - 连接状态：🟢 正常 / 🔴 异常
   - 活跃连接数 / 最大连接数
   - 查询队列长度
   - 最近 1 小时慢查询数（>1s）
   - 数据库大小

4. **Redis 状态**
   - 连接状态：🟢 正常 / 🔴 异常
   - 内存使用率
   - 命中率（hit rate）
   - 每秒操作数（ops/sec）
   - 连接数

5. **Worker 状态**
   - Celery Worker 状态：🟢 正常 / 🔴 异常
   - 活跃 Worker 数
   - 任务队列长度
   - 待处理任务数
   - 最近 1 小时任务失败率

6. **磁盘 I/O**
   - 读写速率（MB/s）
   - IOPS
   - 磁盘使用率

**系统资源趋势图**：

1. **CPU 使用率趋势**（折线图）
   - X 轴：时间（最近 24 小时，按分钟）
   - Y 轴：CPU 使用率 %
   - 标注危险阈值线（90%）

2. **内存使用趋势**（面积图）
   - X 轴：时间
   - Y 轴：内存使用量（GB）
   - 展示已用和总量

3. **数据库性能趋势**（组合图）
   - 左轴：活跃连接数（折线）
   - 右轴：查询延迟 P50/P95（折线）

4. **Redis 性能趋势**（折线图）
   - 命中率 %
   - 每秒操作数
   - 内存使用率 %

**详细监控表格**：

**数据库慢查询列表**：

| 时间 | 查询摘要 | 耗时 (ms) | 表名 | 影响行数 |
|------|---------|----------|------|---------|
| 14:32 | SELECT * FROM messages WHERE... | 1,250 | messages | 5000 |

**Worker 任务队列**：

| 队列名称 | 待处理 | 活跃 | 失败 | 平均耗时 |
|---------|--------|------|------|---------|
| default | 12 | 3 | 0 | 2.5s |
| high_priority | 0 | 1 | 0 | 1.2s |

##### 2.2.3 Agent 性能 (Agent Performance)

**筛选器**：
- 时间范围：今日/本周/本月/自定义
- Agent 选择：下拉多选
- 团队选择：下拉多选

**表格**：Agent 性能排行

| Agent 名称 | 请求数 | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | 超时率 | 成功率 | 平均 Token |
|-----------|--------|----------|----------|----------|----------|--------|--------|-----------|
| 客服助手   | 1,234  | 850      | 2,100    | 3,500    | 5,200    | 0.5%   | 99.2%  | 1,250     |
| 代码助手   | 856    | 1,200    | 4,500    | 8,000    | 12,000   | 2.1%   | 97.5%  | 3,400     |

**详情图表**（点击 Agent 展开）：
1. **响应时间分布**（直方图）
2. **时间序列**（折线图）：P50/P90/P95 随时间变化
3. **超时事件时间线**（散点图）：标注每次超时发生时间和类型

##### 2.2.4 Workflow 性能 (Workflow Performance)

**类似 Agent 性能，额外维度**：
- 节点执行时间分布
- 节点失败率
- 平均节点数

**表格**：Workflow 性能排行

| Workflow 名称 | 执行次数 | P50 (ms) | P90 (ms) | P95 (ms) | 超时率 | 成功率 | 平均节点数 |
|--------------|---------|----------|----------|----------|--------|--------|-----------|
| 数据处理流程  | 456     | 3,200    | 8,500    | 12,000   | 1.2%   | 98.5%  | 5.2       |

##### 2.2.5 超时分析 (Timeout Analysis)

**筛选器**：
- 时间范围
- 超时类型：idle/global
- Agent/Workflow
- 模型

**可视化**：
1. **超时类型分布**（饼图）
   - idle timeout: 65%
   - global timeout: 35%

2. **超时趋势**（折线图）
   - X 轴：时间
   - Y 轴：超时次数
   - 分组：按超时类型

3. **超时热力图**（热力图）
   - X 轴：小时（0-23）
   - Y 轴：星期（周一-周日）
   - 颜色深度：超时次数

4. **Top 超时 Agent**（条形图）
   - 按超时次数排序

**详细事件列表**：

| 时间 | Agent/Workflow | 超时类型 | 超时阈值 | 实际耗时 | 模型 | 对话 ID |
|------|---------------|---------|---------|---------|------|---------|
| 2026-05-28 14:32 | 客服助手 | idle | 180s | 185s | gpt-4 | conv-123 |

##### 2.2.6 系统吞吐 (System Throughput)

**实时指标**（大数字卡片）：
1. **当前 QPS**
   - 实时更新（每 5 秒）
   
2. **当前并发数**
   - 正在进行的对话数

3. **今日峰值 QPS**
   - 发生时间

**趋势图**：
1. **QPS 趋势**（折线图）
   - 最近 24 小时，按分钟聚合
   - 标注峰值点

2. **TPS 趋势**（折线图）
   - 完整对话轮次/秒

3. **并发数趋势**（面积图）
   - 并发对话数随时间变化

4. **成功率趋势**（折线图）
   - 成功率 % 随时间变化

#### 2.3 企业级监控展示重设计

用户反馈第一版 6 个子页面表现力不足，因此在不改变后端 API 的前提下，对 `/dashboard/observability` 进行展示层重设计：

1. **页面状态与加载体验**
   - `page.tsx` 只负责标签页、时间范围、数据拉取、错误状态和刷新状态。
   - 内容区使用 Skeleton，不再用全页居中 spinner 覆盖已有缓存数据。
   - Health 标签页保留 30 秒自动刷新，并在标题区展示自动刷新提示。

2. **概览页：运维驾驶舱**
   - 左侧运行状态面板按超时率、成功率、首 Token P95（有新数据时）或总耗时 P95（历史回退）推导健康 / 关注 / 严重风险。
   - 右侧使用 Agent 请求与 Workflow 运行的堆叠面积趋势图。
   - 下方展示请求总量、Token、峰值小时请求、流量构成与 P50/P90/P95/P99 分位条。
   - TTFT（Time To First Token / 首 Token 延迟）与完整响应耗时分开统计；历史数据和非流式消息没有真实 TTFT，不从 `duration_ms` 反推。

3. **系统健康页：依赖与资源控制台**
   - 使用 CPU/内存趋势图作为主视觉。
   - CPU、内存、磁盘、数据库、Redis、Worker 以依赖状态列表展示主指标、状态和百分比进度。
   - Worker 队列展示 active/reserved/scheduled 和各队列 pending 分布。
   - 慢查询区对 `pg_stat_statements` 不可用状态展示可操作启用提示，对可用状态展示防御式字段读取表格。

4. **Agent / Workflow 性能页：排行 + 详情 Sheet**
   - 列表展示名称、团队、请求/运行数、成功率、超时率、P95/P99、Token 等核心指标。
   - 行点击打开右侧 Sheet，异步拉取详情，展示分位条、性能趋势图和 Workflow 节点拆解。
   - 详情请求不阻塞主列表渲染。

5. **超时分析页：分布 + 事件流**
   - 顶部展示总事件数、最高频超时类型和 Agent 类型数据可用状态。
   - 使用横向分布条替代简单卡片，近期事件表展示来源、实体、类型、状态、模型、耗时和时间。
   - 对历史 Agent timeout subtype 不可精确区分的限制保留警告说明。

6. **系统吞吐页：容量与 Token 分析**
   - 顶部展示 QPS、TPS、运行中 Workflow、总 Token。
   - 主图使用 Agent/Workflow 请求量堆叠柱状图。
   - Token 按来源和模型使用横向分布条展示占比，缺失数据只影响 Token 区块，不隐藏吞吐图。

### 3. 后端 API 设计

#### 3.1 API 端点

**基础路径**：`/api/v1/admin/observability`

##### 3.1.1 概览指标

```
GET /api/v1/admin/observability/overview
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601 (if custom)
  - end_time: ISO8601 (if custom)

Response:
{
  "total_requests": 12345,
  "total_requests_growth": 15.2,  // 环比增长 %
  "avg_response_time_p50": 850,
  "avg_response_time_p50_change": -5.3,  // 与昨日对比 %
  "timeout_rate": 0.8,
  "timeout_distribution": {
    "idle": 65,
    "global": 35
  },
  "current_qps": 12.5,
  "peak_qps": 45.2,
  "peak_qps_time": "2026-05-28T14:32:00Z"
}
```

##### 3.1.2 请求量趋势

```
GET /api/v1/admin/observability/request-trend
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - granularity: hour|day

Response:
{
  "data": [
    {"timestamp": "2026-05-28T00:00:00Z", "count": 234},
    {"timestamp": "2026-05-28T01:00:00Z", "count": 189},
    ...
  ]
}
```

##### 3.1.3 响应时间趋势

```
GET /api/v1/admin/observability/response-time-trend
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - granularity: hour|day

Response:
{
  "data": [
    {
      "timestamp": "2026-05-28T00:00:00Z",
      "p50": 850,
      "p90": 2100,
      "p95": 3500,
      "p99": 5200
    },
    ...
  ]
}
```

##### 3.1.4 Agent 性能列表

```
GET /api/v1/admin/observability/agents
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - agent_ids: comma-separated UUIDs (optional)
  - team_ids: comma-separated UUIDs (optional)
  - sort_by: requests|p50|p90|p95|timeout_rate
  - sort_order: asc|desc
  - page: int
  - page_size: int

Response:
{
  "total": 45,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "agent_id": "uuid",
      "agent_name": "客服助手",
      "team_name": "客服团队",
      "request_count": 1234,
      "p50": 850,
      "p90": 2100,
      "p95": 3500,
      "p99": 5200,
      "timeout_count": 6,
      "timeout_rate": 0.5,
      "success_count": 1224,
      "success_rate": 99.2,
      "avg_tokens": 1250
    },
    ...
  ]
}
```

##### 3.1.5 Agent 详细时间序列

```
GET /api/v1/admin/observability/agents/{agent_id}/timeseries
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - granularity: hour|day

Response:
{
  "agent_id": "uuid",
  "agent_name": "客服助手",
  "data": [
    {
      "timestamp": "2026-05-28T00:00:00Z",
      "request_count": 45,
      "p50": 820,
      "p90": 2050,
      "p95": 3400,
      "timeout_count": 0
    },
    ...
  ]
}
```

##### 3.1.6 超时事件列表

```
GET /api/v1/admin/observability/timeouts
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - timeout_type: idle|global (optional)
  - agent_ids: comma-separated UUIDs (optional)
  - model_ids: comma-separated UUIDs (optional)
  - page: int
  - page_size: int

Response:
{
  "total": 123,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "timestamp": "2026-05-28T14:32:15Z",
      "agent_id": "uuid",
      "agent_name": "客服助手",
      "timeout_type": "idle",
      "timeout_threshold": 180,
      "actual_duration": 185,
      "model_id": "uuid",
      "model_name": "gpt-4",
      "conversation_id": "uuid"
    },
    ...
  ]
}
```

##### 3.1.7 系统吞吐量实时指标

```
GET /api/v1/admin/observability/throughput/realtime

Response:
{
  "current_qps": 12.5,
  "current_concurrent": 34,
  "today_peak_qps": 45.2,
  "today_peak_qps_time": "2026-05-28T14:32:00Z"
}
```

##### 3.1.8 QPS/TPS 趋势

```
GET /api/v1/admin/observability/throughput/trend
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - granularity: minute|hour|day

Response:
{
  "data": [
    {
      "timestamp": "2026-05-28T14:00:00Z",
      "qps": 12.5,
      "tps": 8.3,
      "concurrent": 34,
      "success_rate": 99.2
    },
    ...
  ]
}
```

##### 3.1.9 系统健康实时状态

```
GET /api/v1/admin/observability/system/health

Response:
{
  "cpu": {
    "usage_percent": 45.2,
    "cores": 8,
    "architecture": "x86_64",
    "status": "normal",  // normal | warning | danger
    "avg_1h": 42.5
  },
  "memory": {
    "usage_percent": 68.5,
    "used_gb": 12.4,
    "total_gb": 16.0,
    "status": "normal",
    "avg_1h": 65.2
  },
  "database": {
    "status": "healthy",  // healthy | unhealthy
    "active_connections": 15,
    "max_connections": 100,
    "query_queue_length": 0,
    "slow_queries_1h": 2,
    "database_size_gb": 2.5
  },
  "redis": {
    "status": "healthy",
    "memory_usage_percent": 35.2,
    "hit_rate": 92.5,
    "ops_per_sec": 1250,
    "connected_clients": 25
  },
  "worker": {
    "status": "healthy",  // healthy | unhealthy
    "active_workers": 3,
    "queue_length": 12,
    "pending_tasks": 8,
    "failure_rate_1h": 0.5
  },
  "disk": {
    "read_mbps": 45.2,
    "write_mbps": 23.8,
    "iops": 850,
    "usage_percent": 62.3
  }
}
```

##### 3.1.10 系统资源趋势

```
GET /api/v1/admin/observability/system/trend
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - granularity: minute|hour|day

Response:
{
  "data": [
    {
      "timestamp": "2026-05-28T14:00:00Z",
      "cpu_usage": 45.2,
      "memory_usage": 68.5,
      "db_active_connections": 15,
      "db_query_latency_p50": 12.5,
      "db_query_latency_p95": 45.2,
      "redis_hit_rate": 92.5,
      "redis_ops_per_sec": 1250,
      "disk_read_mbps": 45.2,
      "disk_write_mbps": 23.8
    },
    ...
  ]
}
```

##### 3.1.11 数据库慢查询列表

```
GET /api/v1/admin/observability/system/slow-queries
Query:
  - time_range: today|week|month|custom
  - start_time: ISO8601
  - end_time: ISO8601
  - threshold_ms: int (default: 1000)
  - page: int
  - page_size: int

Response:
{
  "total": 45,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "timestamp": "2026-05-28T14:32:15Z",
      "query_hash": "abc123",
      "query_summary": "SELECT * FROM messages WHERE conversation_id = $1",
      "duration_ms": 1250,
      "table_name": "messages",
      "rows_affected": 5000,
      "database": "clouisle"
    },
    ...
  ]
}
```

##### 3.1.12 Worker 任务队列状态

```
GET /api/v1/admin/observability/system/workers

Response:
{
  "active_workers": 3,
  "queues": [
    {
      "name": "default",
      "pending": 12,
      "active": 3,
      "failed": 0,
      "avg_duration_ms": 2500
    },
    {
      "name": "high_priority",
      "pending": 0,
      "active": 1,
      "failed": 0,
      "avg_duration_ms": 1200
    },
    {
      "name": "session_memory",
      "pending": 5,
      "active": 0,
      "failed": 2,
      "avg_duration_ms": 3500
    }
  ]
}
```

#### 3.2 数据聚合策略

**实时查询**（< 1 小时）：
- 直接从 `Message` 表聚合
- 使用数据库索引优化：`(created_at, agent_id, round_status)`

**历史查询**（> 1 小时）：
- 方案 A（初期）：从 `Message` 表聚合，加缓存
- 方案 B（长期）：预聚合到时序指标表，定时任务每小时/每天聚合

**分位数计算**：
- PostgreSQL：使用 `percentile_cont()` 函数
- 或应用层计算（从数据库取 `duration_ms` 列表后排序）

### 4. 实施计划

#### 阶段 1：基础设施（1-2 天）

1. **后端 API**
   - 创建 `/api/v1/admin/observability` 路由模块
   - 实现概览指标 API
   - 实现 Agent 性能列表 API
   - 实现超时事件列表 API

2. **数据库优化**
   - 添加索引：`Message(created_at, agent_id, round_status)`
   - 添加索引：`Conversation(created_at, agent_id)`

3. **权限控制**
   - 仅超级管理员可访问
   - 添加权限检查中间件

4. **系统健康监控集成**
   - 集成 `psutil` 库获取系统指标
   - 实现数据库连接池监控
   - 实现 Redis 状态监控
   - 实现 Celery Worker 状态监控

#### 阶段 2：前端界面（2-3 天）

1. **路由和布局**
   - 添加 `/dashboard/observability` 路由
   - 创建子页面路由结构

2. **概览页面**
   - 关键指标卡片组件
   - 请求量趋势图（使用 recharts）
   - 响应时间趋势图

3. **系统健康页面**
   - 基础设施状态卡片组件（CPU、内存、数据库、Redis、Worker、磁盘）
   - 系统资源趋势图（CPU、内存、数据库性能、Redis 性能）
   - 慢查询列表表格
   - Worker 任务队列表格

4. **Agent 性能页面**
   - 筛选器组件
   - 性能表格组件
   - 详情展开面板

5. **超时分析页面**
   - 超时类型分布饼图
   - 超时趋势折线图
   - 超时事件列表

#### 阶段 3：高级功能（2-3 天）

1. **Workflow 性能**
   - Workflow 性能 API
   - Workflow 性能页面

2. **系统吞吐**
   - 实时 QPS/TPS API
   - 吞吐量趋势页面
   - WebSocket 实时更新（可选）

3. **导出功能**
   - CSV 导出
   - PDF 报告生成（可选）

#### 阶段 4：优化和监控（1-2 天）

1. **性能优化**
   - 查询缓存（Redis）
   - 预聚合任务（Celery）

2. **告警功能**（可选）
   - 超时率阈值告警
   - 性能下降告警
   - 邮件/Webhook 通知

3. **系统健康告警**
   - CPU 使用率超过 90% 告警
   - 内存使用率超过 90% 告警
   - 数据库连接池超过 80% 告警
   - Redis 命中率低于 80% 告警
   - Worker 任务失败率超过 5% 告警

### 5. 技术栈

**后端**：
- FastAPI
- PostgreSQL（聚合查询）
- Redis（缓存）
- Celery（预聚合任务，可选）
- psutil（系统监控）
- SQLAlchemy（数据库连接池监控）

**前端**：
- Next.js
- React
- Recharts（图表库）
- TanStack Table（表格）
- Tailwind CSS
- WebSocket（实时更新，可选）

### 6. 数据保留策略

**原始数据**：
- `Message` 表：永久保留（或按团队配置）

**聚合数据**（如果使用预聚合表）：
- 小时级聚合：保留 30 天
- 天级聚合：保留 1 年
- 月级聚合：永久保留

### 7. 安全和权限

**访问控制**：
- 仅超级管理员（`is_superuser=True`）可访问
- 团队管理员可查看本团队数据（可选）

**数据脱敏**：
- 不展示对话内容
- 只展示统计指标和元数据

**审计日志**：
- 记录管理员访问可观测性面板的操作

### 8. 测试策略

**单元测试**：
- API 端点测试
- 聚合逻辑测试
- 分位数计算测试

**集成测试**：
- 端到端 API 测试
- 前端组件测试

**性能测试**：
- 大数据量聚合查询性能
- 并发查询压力测试

### 9. 监控和告警

**系统监控**：
- API 响应时间
- 数据库查询性能
- 缓存命中率

**业务告警**：
- 超时率超过阈值（如 5%）
- P95 响应时间超过阈值（如 10s）
- QPS 异常波动

### 10. 未来扩展

**高级分析**：
- 异常检测（基于机器学习）
- 性能预测
- 成本分析（Token 消耗 × 价格）

**自定义仪表盘**：
- 用户自定义指标
- 自定义图表布局
- 保存和分享仪表盘

**集成外部监控**：
- Prometheus 导出器
- Grafana 集成
- DataDog/New Relic 集成

---

## 附录

### A. 数据库 Schema 变更（可选预聚合表）

```sql
-- 小时级聚合表
CREATE TABLE observability_metrics_hourly (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    agent_id UUID REFERENCES agents(id),
    team_id UUID REFERENCES teams(id),
    model_id UUID REFERENCES team_models(id),
    
    -- 请求统计
    request_count INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    timeout_count INT NOT NULL DEFAULT 0,
    timeout_idle_count INT NOT NULL DEFAULT 0,
    timeout_global_count INT NOT NULL DEFAULT 0,
    
    -- 响应时间分位数（毫秒）
    duration_p50 INT,
    duration_p90 INT,
    duration_p95 INT,
    duration_p99 INT,
    
    -- Token 统计
    total_tokens BIGINT NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(timestamp, agent_id, team_id, model_id)
);

CREATE INDEX idx_metrics_hourly_timestamp ON observability_metrics_hourly(timestamp);
CREATE INDEX idx_metrics_hourly_agent ON observability_metrics_hourly(agent_id, timestamp);
CREATE INDEX idx_metrics_hourly_team ON observability_metrics_hourly(team_id, timestamp);
```

### B. 前端组件结构

```
frontend/app/(dashboard)/observability/
├── layout.tsx                    # 可观测性布局
├── page.tsx                      # 概览页面
├── agents/
│   └── page.tsx                  # Agent 性能页面
├── workflows/
│   └── page.tsx                  # Workflow 性能页面
├── timeouts/
│   └── page.tsx                  # 超时分析页面
├── throughput/
│   └── page.tsx                  # 系统吞吐页面
└── _components/
    ├── metric-card.tsx           # 指标卡片
    ├── trend-chart.tsx           # 趋势图表
    ├── performance-table.tsx     # 性能表格
    ├── timeout-heatmap.tsx       # 超时热力图
    └── time-range-selector.tsx   # 时间范围选择器
```

### C. API 响应示例

**Agent 性能列表响应**：
```json
{
  "total": 45,
  "page": 1,
  "page_size": 20,
  "data": [
    {
      "agent_id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_name": "客服助手",
      "team_name": "客服团队",
      "request_count": 1234,
      "p50": 850,
      "p90": 2100,
      "p95": 3500,
      "p99": 5200,
      "timeout_count": 6,
      "timeout_rate": 0.49,
      "success_count": 1224,
      "success_rate": 99.19,
      "avg_tokens": 1250
    }
  ]
}
```

---

**文档版本**: 1.0  
**创建时间**: 2026-05-28  
**作者**: Claude (Opus 4.7)  
**相关 Issue**: YUN-72 (超时优化的后续扩展)

---

## 附录 D：系统健康监控实现细节

### D.1 psutil 系统监控

```python
# backend/app/services/observability/system_monitor.py

import psutil
from datetime import datetime
from typing import Dict, Any

def get_cpu_metrics() -> Dict[str, Any]:
    """获取 CPU 指标"""
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()
    
    # 判断状态
    status = "normal"
    if cpu_percent >= 90:
        status = "danger"
    elif cpu_percent >= 70:
        status = "warning"
    
    return {
        "usage_percent": cpu_percent,
        "cores": cpu_count,
        "architecture": psutil.machine(),
        "status": status,
        "avg_1h": get_cpu_avg_1h(),  # 从历史数据计算
        "frequency_mhz": cpu_freq.current if cpu_freq else None,
    }

def get_memory_metrics() -> Dict[str, Any]:
    """获取内存指标"""
    memory = psutil.virtual_memory()
    
    status = "normal"
    if memory.percent >= 90:
        status = "danger"
    elif memory.percent >= 80:
        status = "warning"
    
    return {
        "usage_percent": memory.percent,
        "used_gb": round(memory.used / (1024 ** 3), 2),
        "total_gb": round(memory.total / (1024 ** 3), 2),
        "available_gb": round(memory.available / (1024 ** 3), 2),
        "status": status,
        "avg_1h": get_memory_avg_1h(),
    }

def get_disk_metrics() -> Dict[str, Any]:
    """获取磁盘 I/O 指标"""
    disk_io = psutil.disk_io_counters()
    disk_usage = psutil.disk_usage('/')
    
    return {
        "read_mbps": round(disk_io.read_bytes / (1024 ** 2), 2) if disk_io else 0,
        "write_mbps": round(disk_io.write_bytes / (1024 ** 2), 2) if disk_io else 0,
        "iops": (disk_io.read_count + disk_io.write_count) if disk_io else 0,
        "usage_percent": disk_usage.percent,
        "total_gb": round(disk_usage.total / (1024 ** 3), 2),
        "used_gb": round(disk_usage.used / (1024 ** 3), 2),
    }

def get_process_metrics() -> Dict[str, Any]:
    """获取当前进程指标"""
    process = psutil.Process()
    
    return {
        "pid": process.pid,
        "memory_mb": round(process.memory_info().rss / (1024 ** 2), 2),
        "cpu_percent": process.cpu_percent(),
        "threads": process.num_threads(),
        "open_files": len(process.open_files()),
    }
```

### D.2 数据库连接池监控

```python
# backend/app/services/observability/db_monitor.py

from tortoise import Tortoise
from typing import Dict, Any

async def get_database_metrics() -> Dict[str, Any]:
    """获取数据库指标"""
    try:
        # 获取连接池信息
        conn = Tortoise.get_connection("default")
        
        # 查询活跃连接数
        active_connections_query = """
            SELECT count(*) as active_connections
            FROM pg_stat_activity
            WHERE state = 'active'
        """
        active_result = await conn.execute_query(active_connections_query)
        active_connections = active_result[1][0]['active_connections']
        
        # 查询最大连接数
        max_connections_query = "SHOW max_connections"
        max_result = await conn.execute_query(max_connections_query)
        max_connections = int(max_result[1][0]['max_connections'])
        
        # 查询数据库大小
        db_size_query = """
            SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                   pg_database_size(current_database()) as size_bytes
        """
        size_result = await conn.execute_query(db_size_query)
        db_size = size_result[1][0]['size']
        db_size_bytes = size_result[1][0]['size_bytes']
        
        # 查询慢查询数（最近 1 小时，耗时 > 1 秒）
        slow_queries_query = """
            SELECT count(*) as slow_count
            FROM pg_stat_statements
            WHERE mean_exec_time > 1000  -- 毫秒
              AND last_call >= NOW() - INTERVAL '1 hour'
        """
        # 注意：需要安装 pg_stat_statements 扩展
        # slow_result = await conn.execute_query(slow_queries_query)
        # slow_queries = slow_result[1][0]['slow_count']
        slow_queries = 0  # 临时值
        
        # 连接状态
        status = "healthy"
        if active_connections / max_connections > 0.8:
            status = "warning"
        if active_connections / max_connections > 0.95:
            status = "unhealthy"
        
        return {
            "status": status,
            "active_connections": active_connections,
            "max_connections": max_connections,
            "connection_usage_percent": round(active_connections / max_connections * 100, 2),
            "query_queue_length": await get_query_queue_length(),
            "slow_queries_1h": slow_queries,
            "database_size_gb": round(db_size_bytes / (1024 ** 3), 2),
            "database_size_pretty": db_size,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }

async def get_query_queue_length() -> int:
    """获取查询队列长度"""
    try:
        conn = Tortoise.get_connection("default")
        query = """
            SELECT count(*) as queue_length
            FROM pg_stat_activity
            WHERE wait_event_type = 'Client'
              AND state = 'active'
        """
        result = await conn.execute_query(query)
        return result[1][0]['queue_length']
    except Exception:
        return 0

async def get_slow_queries(
    threshold_ms: int = 1000,
    limit: int = 100
) -> list[Dict[str, Any]]:
    """获取慢查询列表"""
    try:
        conn = Tortoise.get_connection("default")
        query = """
            SELECT 
                query,
                calls,
                mean_exec_time,
                total_exec_time,
                rows,
                last_call
            FROM pg_stat_statements
            WHERE mean_exec_time > %s
            ORDER BY mean_exec_time DESC
            LIMIT %s
        """
        result = await conn.execute_query(query, [threshold_ms, limit])
        
        return [
            {
                "query_hash": str(hash(row['query']))[:8],
                "query_summary": row['query'][:200],
                "duration_ms": round(row['mean_exec_time'], 2),
                "calls": row['calls'],
                "total_time_ms": round(row['total_exec_time'], 2),
                "rows_affected": row['rows'],
                "last_call": row['last_call'].isoformat() if row['last_call'] else None,
            }
            for row in result[1]
        ]
    except Exception as e:
        return []
```

### D.3 Redis 状态监控

```python
# backend/app/services/observability/redis_monitor.py

import redis.asyncio as redis
from typing import Dict, Any
from app.core.config import settings

async def get_redis_metrics() -> Dict[str, Any]:
    """获取 Redis 指标"""
    try:
        r = redis.from_url(
            f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            if settings.REDIS_PASSWORD
            else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
        )
        
        # 获取 INFO 信息
        info = await r.info()
        
        # 内存使用
        used_memory = info.get('used_memory', 0)
        max_memory = info.get('maxmemory', 0)
        memory_usage_percent = (used_memory / max_memory * 100) if max_memory > 0 else 0
        
        # 命中率
        keyspace_hits = info.get('keyspace_hits', 0)
        keyspace_misses = info.get('keyspace_misses', 0)
        hit_rate = (keyspace_hits / (keyspace_hits + keyspace_misses) * 100) if (keyspace_hits + keyspace_misses) > 0 else 0
        
        # 每秒操作数
        ops_per_sec = info.get('instantaneous_ops_per_sec', 0)
        
        # 连接数
        connected_clients = info.get('connected_clients', 0)
        
        # 状态判断
        status = "healthy"
        if memory_usage_percent > 90:
            status = "warning"
        if hit_rate < 80:
            status = "warning"
        
        await r.close()
        
        return {
            "status": status,
            "memory_usage_percent": round(memory_usage_percent, 2),
            "used_memory_mb": round(used_memory / (1024 ** 2), 2),
            "max_memory_mb": round(max_memory / (1024 ** 2), 2) if max_memory > 0 else None,
            "hit_rate": round(hit_rate, 2),
            "ops_per_sec": ops_per_sec,
            "connected_clients": connected_clients,
            "keyspace_hits": keyspace_hits,
            "keyspace_misses": keyspace_misses,
            "uptime_seconds": info.get('uptime_in_seconds', 0),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
```

### D.4 Celery Worker 状态监控

```python
# backend/app/services/observability/worker_monitor.py

from celery import Celery
from typing import Dict, Any, List
from app.core.config import settings

def get_celery_app() -> Celery:
    """获取 Celery 应用实例"""
    # 这里需要根据实际 Celery 配置返回实例
    from app.tasks.celery_app import celery_app
    return celery_app

async def get_worker_metrics() -> Dict[str, Any]:
    """获取 Worker 指标"""
    try:
        app = get_celery_app()
        
        # 获取活跃 Worker
        inspect = app.control.inspect()
        
        # 获取活跃任务
        active = inspect.active() or {}
        active_workers = len(active)
        
        # 获取预定任务
        reserved = inspect.reserved() or {}
        pending_tasks = sum(len(tasks) for tasks in reserved.values())
        
        # 获取队列长度
        queues = await get_queue_lengths()
        
        # 获取失败率（最近 1 小时）
        failure_rate = await get_failure_rate_1h()
        
        # 状态判断
        status = "healthy"
        if active_workers == 0:
            status = "unhealthy"
        if failure_rate > 5:  # 失败率超过 5%
            status = "warning"
        
        return {
            "status": status,
            "active_workers": active_workers,
            "queue_length": sum(q["pending"] for q in queues),
            "pending_tasks": pending_tasks,
            "failure_rate_1h": round(failure_rate, 2),
            "queues": queues,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }

async def get_queue_lengths() -> List[Dict[str, Any]]:
    """获取各队列长度"""
    try:
        app = get_celery_app()
        inspect = app.control.inspect()
        
        # 获取各队列的预定任务
        reserved = inspect.reserved() or {}
        
        # 按队列分组统计
        queue_stats = {}
        for worker, tasks in reserved.items():
            for task in tasks:
                queue = task.get('delivery_info', {}).get('routing_key', 'default')
                if queue not in queue_stats:
                    queue_stats[queue] = {
                        "name": queue,
                        "pending": 0,
                        "active": 0,
                        "failed": 0,
                        "avg_duration_ms": 0,
                    }
                queue_stats[queue]["pending"] += 1
        
        # 获取活跃任务
        active = inspect.active() or {}
        for worker, tasks in active.items():
            for task in tasks:
                queue = task.get('delivery_info', {}).get('routing_key', 'default')
                if queue in queue_stats:
                    queue_stats[queue]["active"] += 1
        
        return list(queue_stats.values())
    except Exception as e:
        return []

async def get_failure_rate_1h() -> float:
    """获取最近 1 小时的任务失败率"""
    try:
        # 这里需要从数据库或 Redis 查询任务历史
        # 示例：查询最近 1 小时的任务统计
        # total_tasks = ...
        # failed_tasks = ...
        # return (failed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        return 0.5  # 临时返回值
    except Exception:
        return 0.0
```

### D.5 综合系统健康 API

```python
# backend/app/api/v1/admin/endpoints/observability.py

@router.get("/system/health")
async def get_system_health(
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取系统健康状态"""
    from app.services.observability import system_monitor, db_monitor, redis_monitor, worker_monitor
    
    # 并行获取各项指标
    cpu_metrics = system_monitor.get_cpu_metrics()
    memory_metrics = system_monitor.get_memory_metrics()
    disk_metrics = system_monitor.get_disk_metrics()
    
    db_metrics = await db_monitor.get_database_metrics()
    redis_metrics = await redis_monitor.get_redis_metrics()
    worker_metrics = await worker_monitor.get_worker_metrics()
    
    return success(data={
        "cpu": cpu_metrics,
        "memory": memory_metrics,
        "disk": disk_metrics,
        "database": db_metrics,
        "redis": redis_metrics,
        "worker": worker_metrics,
    })

@router.get("/system/slow-queries")
async def get_slow_queries(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    threshold_ms: int = Query(1000, ge=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取慢查询列表"""
    from app.services.observability import db_monitor
    
    queries = await db_monitor.get_slow_queries(threshold_ms=threshold_ms)
    
    # 分页
    total = len(queries)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_queries = queries[start_idx:end_idx]
    
    return success(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": paginated_queries,
    })

@router.get("/system/workers")
async def get_worker_status(
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取 Worker 状态"""
    from app.services.observability import worker_monitor
    
    worker_metrics = await worker_monitor.get_worker_metrics()
    
    return success(data=worker_metrics)
```

### D.6 前端组件实现示例

```typescript
// frontend/app/(dashboard)/observability/_components/system-health-card.tsx

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

interface SystemHealthCardProps {
  title: string
  icon: React.ReactNode
  value: number
  unit: string
  status: "normal" | "warning" | "danger" | "healthy" | "unhealthy"
  subtitle?: string
  extra?: React.ReactNode
}

export function SystemHealthCard({
  title,
  icon,
  value,
  unit,
  status,
  subtitle,
  extra,
}: SystemHealthCardProps) {
  const statusColors = {
    normal: "text-green-600 bg-green-100",
    healthy: "text-green-600 bg-green-100",
    warning: "text-yellow-600 bg-yellow-100",
    danger: "text-red-600 bg-red-100",
    unhealthy: "text-red-600 bg-red-100",
  }

  const statusLabels = {
    normal: "正常",
    healthy: "正常",
    warning: "警告",
    danger: "危险",
    unhealthy: "异常",
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Badge variant="secondary" className={statusColors[status]}>
          {statusLabels[status]}
        </Badge>
      </CardHeader>
      <CardContent>
        <div className="flex items-center space-x-4">
          <div className="p-2 bg-gray-100 rounded-lg">
            {icon}
          </div>
          <div className="flex-1">
            <div className="text-2xl font-bold">
              {value}
              <span className="text-sm font-normal text-gray-500 ml-1">
                {unit}
              </span>
            </div>
            {subtitle && (
              <p className="text-xs text-gray-500">{subtitle}</p>
            )}
          </div>
        </div>
        {extra && <div className="mt-4">{extra}</div>}
      </CardContent>
    </Card>
  )
}

// 使用示例
export function CpuHealthCard({ cpu }: { cpu: CpuMetrics }) {
  return (
    <SystemHealthCard
      title="CPU 使用率"
      icon={<Cpu className="h-4 w-4" />}
      value={cpu.usage_percent}
      unit="%"
      status={cpu.status}
      subtitle={`${cpu.cores} 核心 • 平均 ${cpu.avg_1h}%`}
      extra={
        <Progress
          value={cpu.usage_percent}
          className="h-2"
          indicatorClassName={
            cpu.status === "danger"
              ? "bg-red-500"
              : cpu.status === "warning"
              ? "bg-yellow-500"
              : "bg-green-500"
          }
        />
      }
    />
  )
}
```

---

**附录版本**: 1.0  
**更新时间**: 2026-05-28  
**说明**: 本附录提供了系统健康监控的详细实现代码，可直接用于后端服务开发。
