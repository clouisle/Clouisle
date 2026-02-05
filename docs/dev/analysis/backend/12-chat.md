# 聊天接口 API

**文件**: `backend/app/api/v1/endpoints/chat.py`
**路径前缀**: `/api/v1/chat`

## 概述

聊天接口用于与 Agent 进行对话。支持流式响应、文件上传、工具调用等功能。

## 接口列表

### POST /{agent_id}/chat

发送消息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token 或 API Key |
| 权限 | 根据 Agent 可见性检查 |
| 说明 | 向 Agent 发送消息并获取回复 |

**路径参数**:
- `agent_id`: Agent UUID

**请求体**:
```json
{
  "conversation_id": "uuid (可选，新对话不传)",
  "message": "string",
  "files": [
    {
      "type": "image",
      "url": "string"
    }
  ],
  "variables": {
    "key": "value"
  },
  "stream": true
}
```

**响应（非流式）**:
```json
{
  "code": 0,
  "data": {
    "conversation_id": "uuid",
    "message_id": "uuid",
    "content": "string",
    "tool_calls": [...],
    "usage": {
      "prompt_tokens": 100,
      "completion_tokens": 50,
      "total_tokens": 150
    }
  }
}
```

**响应（流式）**: Server-Sent Events

```
event: message_start
data: {"conversation_id": "uuid", "message_id": "uuid"}

event: content_delta
data: {"delta": "Hello"}

event: content_delta
data: {"delta": " world"}

event: tool_call_start
data: {"tool_call_id": "uuid", "name": "search"}

event: tool_call_delta
data: {"delta": "{\"query\":"}

event: tool_call_end
data: {"tool_call_id": "uuid"}

event: message_end
data: {"usage": {...}}
```

---

### POST /{agent_id}/chat/upload

上传文件

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token 或 API Key |
| 权限 | 根据 Agent 可见性检查 |
| 说明 | 上传文件用于对话 |

**路径参数**:
- `agent_id`: Agent UUID

**请求体**: `multipart/form-data`
- `file`: 文件

**响应**:
```json
{
  "code": 0,
  "data": {
    "file_id": "uuid",
    "filename": "string",
    "content_type": "string",
    "size": 1024,
    "url": "string"
  }
}
```

---

### POST /{agent_id}/chat/stop

停止生成

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token 或 API Key |
| 权限 | 对话所有者 |
| 说明 | 停止正在进行的流式生成 |

**路径参数**:
- `agent_id`: Agent UUID

**请求体**:
```json
{
  "conversation_id": "uuid",
  "message_id": "uuid"
}
```

---

### POST /{agent_id}/chat/regenerate

重新生成

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token 或 API Key |
| 权限 | 对话所有者 |
| 说明 | 重新生成最后一条回复 |

**路径参数**:
- `agent_id`: Agent UUID

**请求体**:
```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "stream": true
}
```

---

## 访问控制

### Agent 可见性检查

| 可见性 | 访问规则 |
|--------|----------|
| `PRIVATE` | 仅创建者可访问 |
| `TEAM` | 团队成员可访问 |
| `PUBLIC` | 所有登录用户可访问 |

### Agent 状态检查

| 状态 | 访问规则 |
|------|----------|
| `DRAFT` | 仅创建者可访问 |
| `PUBLISHED` | 按可见性规则访问 |

### API Key 访问

使用 API Key 时：
- API Key 必须关联该 Agent
- API Key 必须处于激活状态
- API Key 不能过期

---

## RAG 模式

### AGENTIC 模式

当 Agent 配置为 AGENTIC RAG 模式时：
- 自动注入 `knowledge_search` 工具
- LLM 自主决定何时检索知识库
- 支持多轮检索

### SIMPLE 模式

当 Agent 配置为 SIMPLE RAG 模式时：
- 每次对话自动检索相关内容
- 检索结果作为上下文注入

---

## 工具调用

Agent 可以调用配置的工具：

```json
{
  "tool_calls": [
    {
      "id": "uuid",
      "name": "search",
      "arguments": "{\"query\": \"xxx\"}",
      "result": "{\"results\": [...]}"
    }
  ]
}
```

---

## 文件支持

### 图片

当 Agent 启用 Vision 时，支持图片输入：
- 支持格式: PNG, JPG, GIF, WebP
- 最大尺寸: 20MB

### 文档

当 Agent 启用文件上传时，支持文档输入：
- 支持格式: PDF, DOCX, TXT, MD
- 文档内容会被解析并作为上下文

---

## 消息版本

支持消息版本管理：
- 重新生成会创建新版本
- 可以切换到历史版本
- 版本信息包含在消息响应中
