# API Key 管理 API

**文件**: `backend/app/api/v1/endpoints/api_keys.py`
**路径前缀**: `/api/v1/api-keys`

## 概述

API Key 用于外部系统调用 Agent 和工作流 API。支持关联多个 Agent 和工作流。

## 接口列表

### GET /

获取 API Key 列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:read` |
| 说明 | 管理员查看所有 Key，普通用户查看自己的 Key |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词
- `is_active`: 是否激活

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "string",
        "prefix": "sk-xxx",
        "is_active": true,
        "last_used_at": "2024-01-01T00:00:00Z",
        "expires_at": "2025-01-01T00:00:00Z",
        "agents": [...],
        "workflows": [...],
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 10
  }
}
```

---

### GET /stats

获取 API Key 统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:read` |
| 说明 | 获取 API Key 统计数据 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "total": 10,
    "active": 8,
    "inactive": 2,
    "expired": 1
  }
}
```

---

### POST /

创建 API Key

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:create` |
| 说明 | 创建新 API Key |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)",
  "expires_at": "2025-01-01T00:00:00Z (可选)",
  "agent_ids": ["uuid"],
  "workflow_ids": ["uuid"]
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "name": "string",
    "key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "prefix": "sk-xxx"
  }
}
```

**注意**: `key` 字段仅在创建时返回一次，之后无法再次获取。

**审计日志**: `create_api_key`

---

### GET /{api_key_id}

获取 API Key 详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:read` |
| 说明 | 获取 API Key 详细信息 |

**路径参数**:
- `api_key_id`: API Key UUID

---

### PUT /{api_key_id}

更新 API Key

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:update` |
| 说明 | 更新 API Key 信息 |

**路径参数**:
- `api_key_id`: API Key UUID

**请求体**:
```json
{
  "name": "string (可选)",
  "description": "string (可选)",
  "expires_at": "2025-01-01T00:00:00Z (可选)",
  "agent_ids": ["uuid"],
  "workflow_ids": ["uuid"]
}
```

**审计日志**: `update_api_key`

---

### DELETE /{api_key_id}

删除 API Key

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:delete` |
| 说明 | 删除 API Key |

**路径参数**:
- `api_key_id`: API Key UUID

**审计日志**: `delete_api_key`

---

### POST /{api_key_id}/activate

激活 API Key

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:update` |
| 说明 | 激活已停用的 API Key |

**路径参数**:
- `api_key_id`: API Key UUID

**审计日志**: `activate_api_key`

---

### POST /{api_key_id}/deactivate

停用 API Key

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `apikey:update` |
| 说明 | 停用 API Key |

**路径参数**:
- `api_key_id`: API Key UUID

**审计日志**: `deactivate_api_key`

---

## API Key 格式

- 前缀: `sk-`
- 长度: 32 字符（不含前缀）
- 存储: 仅存储哈希值，原始 Key 不可恢复

## 使用方式

在 API 请求中通过 Header 传递：

```
Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 权限说明

| 权限 | 说明 |
|------|------|
| `apikey:read` | 查看 API Key 列表和详情 |
| `apikey:create` | 创建新 API Key |
| `apikey:update` | 更新、激活、停用 API Key |
| `apikey:delete` | 删除 API Key |
