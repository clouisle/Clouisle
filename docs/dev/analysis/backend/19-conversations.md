# 对话管理 API（管理端）

**文件**: `backend/app/api/v1/endpoints/conversations.py`
**路径前缀**: `/api/v1/conversations`

## 概述

对话管理 API 提供管理员对所有对话的管理功能，包括查看、统计和删除对话。

## 接口列表

### GET /

获取所有对话列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` |
| 说明 | 获取所有对话列表（管理端） |

**查询参数**:
- `team_id`: 团队 ID（可选）
- `agent_id`: Agent ID（可选）
- `user_id`: 用户 ID（可选）
- `search`: 搜索标题
- `untitled_only`: 仅显示无标题对话
- `page`: 页码
- `page_size`: 每页数量

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "agent_id": "uuid",
        "agent_name": "string",
        "agent_icon": "string",
        "title": "string",
        "message_count": 10,
        "user_id": "uuid",
        "user_name": "string",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

---

### GET /stats

获取对话统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` |
| 说明 | 获取对话统计数据 |

**查询参数**:
- `team_id`: 团队 ID（可选）

**响应**:
```json
{
  "code": 0,
  "data": {
    "total_conversations": 1000,
    "total_messages": 50000,
    "conversations_by_agent": [
      {
        "agent_id": "uuid",
        "agent_name": "string",
        "agent_icon": "string",
        "count": 100
      }
    ]
  }
}
```

---

### GET /stats/trends

获取对话趋势

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` |
| 说明 | 获取对话和消息的趋势数据 |

**查询参数**:
- `team_id`: 团队 ID（可选）
- `period`: 时间周期（`7d` 或 `30d`）

**响应**:
```json
{
  "code": 0,
  "data": {
    "period": "7d",
    "data": [
      {
        "date": "01/01",
        "conversations": 50,
        "messages": 500,
        "tokens": 10000
      }
    ]
  }
}
```

---

### GET /{conversation_id}

获取对话详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` |
| 说明 | 获取对话详情及消息列表 |

**路径参数**:
- `conversation_id`: 对话 UUID

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "agent_id": "uuid",
    "agent_name": "string",
    "agent_icon": "string",
    "title": "string",
    "user_id": "uuid",
    "user_name": "string",
    "messages": [
      {
        "id": "uuid",
        "role": "user",
        "content": "string",
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
}
```

---

### DELETE /{conversation_id}

删除对话

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:delete` |
| 说明 | 删除指定对话及其所有消息 |

**路径参数**:
- `conversation_id`: 对话 UUID

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid"
  },
  "msg": "conversation_deleted"
}
```

---

### DELETE /

批量删除对话

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:delete` |
| 说明 | 批量删除多个对话 |

**查询参数**:
- `ids`: 对话 ID 列表

**响应**:
```json
{
  "code": 0,
  "data": {
    "deleted_count": 5,
    "ids": ["uuid1", "uuid2", ...]
  },
  "msg": "conversations_deleted"
}
```

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `conversation:read` | 查看对话列表、详情和统计 |
| `conversation:delete` | 删除对话 |

---

## 说明

此 API 主要用于管理后台，提供对所有对话的管理功能。普通用户的对话操作请使用 `/api/v1/agents/conversations/*` 接口。
