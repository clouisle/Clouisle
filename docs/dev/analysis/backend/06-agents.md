# Agent 管理 API

**文件**: `backend/app/api/v1/endpoints/agents.py`
**路径前缀**: `/api/v1/agents`

## 概述

Agent 是 Clouisle 的核心功能，代表一个可配置的 AI 助手。Agent 可以配置模型、提示词、工具、知识库等。

## Agent 属性

### 可见性 (Visibility)

| 值 | 说明 |
|-----|------|
| `PRIVATE` | 仅创建者可见 |
| `TEAM` | 团队成员可见 |
| `PUBLIC` | 所有登录用户可见 |

### 状态 (Status)

| 值 | 说明 |
|-----|------|
| `DRAFT` | 草稿，仅创建者可使用 |
| `PUBLISHED` | 已发布，按可见性规则可用 |

### RAG 模式

| 值 | 说明 |
|-----|------|
| `DISABLED` | 不使用知识库 |
| `SIMPLE` | 简单 RAG，直接检索 |
| `AGENTIC` | 智能 RAG，自动注入 knowledge_search 工具 |

## 接口列表

### GET /

获取 Agent 列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:read` |
| 说明 | 获取用户可访问的 Agent 列表 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词
- `team_id`: 团队 ID
- `status`: 状态筛选
- `visibility`: 可见性筛选

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "string",
        "description": "string",
        "icon": "string",
        "status": "PUBLISHED",
        "visibility": "TEAM",
        "team": {...},
        "model": {...},
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 100
  }
}
```

---

### POST /

创建 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:create` |
| 说明 | 创建新 Agent |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)",
  "icon": "string (可选)",
  "team_id": "uuid",
  "model_id": "uuid",
  "system_prompt": "string (可选)",
  "temperature": 0.7,
  "max_tokens": 4096,
  "visibility": "TEAM",
  "rag_mode": "DISABLED",
  "knowledge_base_ids": ["uuid"],
  "tool_ids": ["uuid"],
  "variables": [
    {
      "name": "string",
      "type": "string",
      "default": "string",
      "required": true
    }
  ],
  "enable_vision": false,
  "enable_file_upload": false
}
```

**审计日志**: `create_agent`

---

### GET /{agent_id}

获取 Agent 详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:read` + 可见性检查 |
| 说明 | 获取 Agent 详细配置 |

**路径参数**:
- `agent_id`: Agent UUID

**访问控制**:
- `PRIVATE`: 仅创建者
- `TEAM`: 团队成员
- `PUBLIC`: 所有登录用户
- `DRAFT` 状态: 仅创建者

---

### PUT /{agent_id}

更新 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:update` + Agent 创建者或团队管理员 |
| 说明 | 更新 Agent 配置 |

**路径参数**:
- `agent_id`: Agent UUID

**审计日志**: `update_agent`

---

### DELETE /{agent_id}

删除 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:delete` + Agent 创建者或团队管理员 |
| 说明 | 删除 Agent 及其所有对话 |

**路径参数**:
- `agent_id`: Agent UUID

**审计日志**: `delete_agent`

---

### POST /{agent_id}/publish

发布 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:publish` + Agent 创建者或团队管理员 |
| 说明 | 将 Agent 状态改为 PUBLISHED |

**路径参数**:
- `agent_id`: Agent UUID

**审计日志**: `publish_agent`

---

### POST /{agent_id}/unpublish

取消发布 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:publish` + Agent 创建者或团队管理员 |
| 说明 | 将 Agent 状态改为 DRAFT |

**路径参数**:
- `agent_id`: Agent UUID

**审计日志**: `unpublish_agent`

---

### POST /{agent_id}/duplicate

复制 Agent

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `agent:create` + 可访问该 Agent 的用户 |
| 说明 | 复制 Agent 到指定团队 |

**路径参数**:
- `agent_id`: Agent UUID

**请求体**:
```json
{
  "team_id": "uuid",
  "name": "string (可选)"
}
```

---

### GET /{agent_id}/conversations

获取 Agent 对话列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` + Agent 创建者或团队管理员 |
| 说明 | 获取该 Agent 的所有对话 |

**路径参数**:
- `agent_id`: Agent UUID

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量

---

### GET /conversations/my

获取我的对话列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` |
| 说明 | 获取当前用户的所有对话 |

---

### GET /conversations/{conversation_id}

获取对话详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` + 对话所有者 |
| 说明 | 获取对话及其消息 |

**路径参数**:
- `conversation_id`: 对话 UUID

---

### PATCH /conversations/{conversation_id}

更新对话

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:read` + 对话所有者 |
| 说明 | 更新对话标题等信息 |

**路径参数**:
- `conversation_id`: 对话 UUID

**请求体**:
```json
{
  "title": "string"
}
```

---

### DELETE /conversations/{conversation_id}

删除对话

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:delete` + 对话所有者 |
| 说明 | 删除对话及其所有消息 |

**路径参数**:
- `conversation_id`: 对话 UUID

---

### DELETE /conversations/{conversation_id}/messages/{message_id}

删除消息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `conversation:delete` + 对话所有者 |
| 说明 | 删除对话中的指定消息 |

**路径参数**:
- `conversation_id`: 对话 UUID
- `message_id`: 消息 UUID

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `agent:read` | 查看 Agent 列表和详情 |
| `agent:create` | 创建新 Agent |
| `agent:update` | 更新 Agent 配置 |
| `agent:delete` | 删除 Agent |
| `agent:publish` | 发布/取消发布 Agent |
| `agent:chat` | 与 Agent 对话 |
| `conversation:read` | 查看对话列表和详情 |
| `conversation:delete` | 删除对话和消息 |

---

## 访问控制矩阵

| 操作 | 创建者 | 团队管理员 | 团队成员 | 其他用户 |
|------|--------|------------|----------|----------|
| 查看 (PRIVATE) | ✓ | ✗ | ✗ | ✗ |
| 查看 (TEAM) | ✓ | ✓ | ✓ | ✗ |
| 查看 (PUBLIC) | ✓ | ✓ | ✓ | ✓ |
| 编辑 | ✓ | ✓ | ✗ | ✗ |
| 删除 | ✓ | ✓ | ✗ | ✗ |
| 发布/取消发布 | ✓ | ✓ | ✗ | ✗ |
| 复制 | ✓ | ✓ | ✓ | ✓* |

*仅限 PUBLIC 可见性的 Agent
