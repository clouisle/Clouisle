# 工具管理 API

**文件**: `backend/app/api/v1/endpoints/tools.py`
**路径前缀**: `/api/v1/tools`

## 概述

工具是 Agent 可以调用的功能扩展。支持内置工具、自定义工具和 MCP 工具。

## 工具类型

| 类型 | 说明 |
|------|------|
| `BUILTIN` | 内置工具，系统预置 |
| `CUSTOM` | 自定义工具，用户创建 |

## 自定义工具类型

| 类型 | 说明 |
|------|------|
| `HTTP` | HTTP 请求工具 |
| `CODE` | 代码执行工具（沙箱） |
| `MCP` | Model Context Protocol 工具 |

## 工具分类

| 分类 | 说明 |
|------|------|
| `SEARCH` | 搜索类 |
| `PRODUCTIVITY` | 生产力类 |
| `COMMUNICATION` | 通信类 |
| `DATA` | 数据处理类 |
| `DEVELOPMENT` | 开发类 |
| `OTHER` | 其他 |

## 接口列表

### GET /

获取工具列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` |
| 说明 | 获取所有可用工具（内置 + 自定义 + 共享） |

**查询参数**:
- `team_id`: 团队 ID
- `type`: 工具类型
- `category`: 工具分类

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "string",
      "description": "string",
      "type": "BUILTIN",
      "category": "SEARCH",
      "is_enabled": true,
      "config": {...}
    }
  ]
}
```

---

### POST /

创建自定义工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:create` + 团队管理员 |
| 说明 | 创建自定义工具 |

**请求体**:
```json
{
  "name": "string",
  "description": "string",
  "team_id": "uuid",
  "custom_type": "HTTP",
  "category": "DATA",
  "config": {
    "url": "string",
    "method": "POST",
    "headers": {},
    "body_template": "string"
  },
  "parameters": [
    {
      "name": "string",
      "type": "string",
      "description": "string",
      "required": true
    }
  ]
}
```

---

### GET /id/{tool_id}

获取工具详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` + 团队成员 |
| 说明 | 获取工具详细配置 |

**路径参数**:
- `tool_id`: 工具 UUID

---

### PUT /{tool_id}

更新工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` + 团队管理员 |
| 说明 | 更新自定义工具配置 |

**路径参数**:
- `tool_id`: 工具 UUID

---

### DELETE /{tool_id}

删除工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:delete` + 团队管理员 |
| 说明 | 删除自定义工具 |

**路径参数**:
- `tool_id`: 工具 UUID

---

### POST /test

测试执行工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:execute` |
| 说明 | 手动执行工具进行测试 |

**请求体**:
```json
{
  "name": "string",
  "arguments": {
    "key": "value"
  }
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": {...},
    "duration_ms": 150
  }
}
```

---

### POST /execute-code

直接执行代码

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:execute` |
| 说明 | 在沙箱中执行代码（不需要保存工具） |

**请求体**:
```json
{
  "code": "string",
  "language": "python",
  "params": {},
  "timeout": 30
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": {...},
    "logs": "string",
    "duration_ms": 100
  }
}
```

---

### POST /mcp/list-tools

列出 MCP 工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` |
| 说明 | 从 MCP 服务器获取可用工具列表 |

**请求体**:
```json
{
  "mcp_config": {
    "server_url": "string",
    "api_key": "string (可选)"
  }
}
```

---

### POST /{tool_id}/toggle

切换工具启用状态

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` + 团队管理员 |
| 说明 | 启用或禁用工具 |

**路径参数**:
- `tool_id`: 工具 UUID

---

### POST /{tool_id}/duplicate

复制工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:create` + 团队管理员 |
| 说明 | 复制工具 |

**路径参数**:
- `tool_id`: 工具 UUID

---

## 工具配置管理

### GET /config

获取工具配置列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` |
| 说明 | 获取团队或全局的工具配置 |

**查询参数**:
- `team_id`: 团队 ID（可选，不传则获取全局配置，需超级管理员）

---

### GET /config/{tool_name}

获取指定工具配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` |
| 说明 | 获取指定工具的配置 |

**路径参数**:
- `tool_name`: 工具名称

---

### POST /config

创建工具配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` |
| 说明 | 创建工具配置 |

---

### PUT /config/{tool_name}

更新工具配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` |
| 说明 | 更新工具配置 |

**路径参数**:
- `tool_name`: 工具名称

---

### DELETE /config/{tool_name}

删除工具配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:delete` |
| 说明 | 删除工具配置 |

**路径参数**:
- `tool_name`: 工具名称

---

## 工具共享

### POST /{tool_id}/share

共享工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` + 团队管理员 |
| 说明 | 将工具共享给其他团队 |

**路径参数**:
- `tool_id`: 工具 UUID

**请求体**:
```json
{
  "team_id": "uuid",
  "permission": "USE"
}
```

---

### GET /{tool_id}/shares

获取工具共享列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` + 团队成员 |
| 说明 | 获取工具的共享记录 |

**路径参数**:
- `tool_id`: 工具 UUID

---

### DELETE /{tool_id}/share/{team_id}

取消共享

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:update` + 团队管理员 |
| 说明 | 取消工具共享 |

**路径参数**:
- `tool_id`: 工具 UUID
- `team_id`: 目标团队 UUID

---

### GET /shared-with-me

获取共享给我的工具

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `tool:read` |
| 说明 | 获取共享给当前团队的工具列表 |

**查询参数**:
- `team_id`: 团队 ID

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `tool:read` | 查看工具列表和详情 |
| `tool:create` | 创建新工具 |
| `tool:update` | 更新工具配置、共享工具 |
| `tool:delete` | 删除工具 |
| `tool:execute` | 执行工具测试 |

---

## HTTP 工具配置

```json
{
  "url": "https://api.example.com/endpoint",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer {{api_key}}",
    "Content-Type": "application/json"
  },
  "body_template": "{\"query\": \"{{query}}\"}",
  "response_path": "data.result"
}
```

## 代码工具配置

```json
{
  "language": "python",
  "code": "def main(params):\n    return {'result': params['input'] * 2}",
  "timeout": 30
}
```

## MCP 工具配置

```json
{
  "server_url": "https://mcp.example.com",
  "api_key": "xxx",
  "tool_name": "search"
}
```
