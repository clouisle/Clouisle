# 仪表盘统计 API

**文件**: `backend/app/api/v1/endpoints/dashboard.py`
**路径前缀**: `/api/v1/dashboard`

## 概述

仪表盘 API 提供系统级别的统计数据，用于管理后台的数据展示。

## 接口列表

### GET /stats

获取系统统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取系统整体统计数据 |

**查询参数**:
- `period`: 时间范围（7d, 30d, 90d, all）

**响应**:
```json
{
  "code": 0,
  "data": {
    "users": {
      "total": 100,
      "active": 95,
      "new_today": 5,
      "growth_rate": 0.05
    },
    "teams": {
      "total": 20,
      "new_today": 2
    },
    "agents": {
      "total": 50,
      "published": 40,
      "draft": 10
    },
    "workflows": {
      "total": 30,
      "published": 25
    },
    "knowledge_bases": {
      "total": 15,
      "document_count": 500,
      "chunk_count": 10000
    },
    "conversations": {
      "total": 1000,
      "today": 50
    },
    "active_users": {
      "dau": 30,
      "wau": 80,
      "mau": 95
    }
  }
}
```

---

### GET /stats/trends

获取趋势数据

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取用于图表展示的趋势数据 |

**查询参数**:
- `period`: 时间范围（7d, 30d）
- `metrics`: 指标列表（users, conversations, tokens）

**响应**:
```json
{
  "code": 0,
  "data": {
    "dates": ["2024-01-01", "2024-01-02", ...],
    "users": [10, 12, 15, ...],
    "conversations": [100, 120, 150, ...],
    "tokens": [10000, 12000, 15000, ...]
  }
}
```

---

### GET /stats/agents/top

获取热门 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取使用量最高的 Agent |

**查询参数**:
- `period`: 时间范围
- `limit`: 返回数量（默认 10）
- `metric`: 排序指标（conversations, tokens, users）

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "string",
      "team": {...},
      "conversation_count": 500,
      "token_usage": 100000,
      "unique_users": 50
    }
  ]
}
```

---

### GET /stats/teams/token-usage

获取团队 Token 使用量

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取各团队的 Token 消耗排名 |

**查询参数**:
- `period`: 时间范围
- `limit`: 返回数量

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "team_id": "uuid",
      "team_name": "string",
      "total_tokens": 500000,
      "prompt_tokens": 300000,
      "completion_tokens": 200000
    }
  ]
}
```

---

### GET /stats/models/distribution

获取模型使用分布

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `admin:dashboard:access` |
| 说明 | 获取各模型的消息使用占比 |

**查询参数**:
- `time_range`: 时间范围（`7d` / `30d` / `90d` / `all`）

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "model": "gpt-4o",
      "count": 1000,
      "percentage": 35.0
    }
  ]
}
```

---

### GET /stats/workflows/summary

获取工作流统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取工作流执行统计 |

**查询参数**:
- `period`: 时间范围

**响应**:
```json
{
  "code": 0,
  "data": {
    "total_runs": 1000,
    "success_runs": 950,
    "failed_runs": 50,
    "success_rate": 0.95,
    "avg_duration_ms": 5000,
    "by_trigger_type": {
      "MANUAL": 500,
      "SCHEDULED": 300,
      "WEBHOOK": 150,
      "API": 50
    }
  }
}
```

---

## 时间范围说明

| 值 | 说明 |
|-----|------|
| `7d` | 最近 7 天 |
| `30d` | 最近 30 天 |
| `90d` | 最近 90 天 |
| `all` | 全部时间 |

## 活跃用户定义

| 指标 | 说明 |
|------|------|
| DAU | 日活跃用户（当天有操作） |
| WAU | 周活跃用户（7 天内有操作） |
| MAU | 月活跃用户（30 天内有操作） |
