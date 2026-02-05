# 模型管理 API

**文件**: `backend/app/api/v1/endpoints/models.py`
**路径前缀**: `/api/v1/models`

## 概述

模型管理用于配置 LLM 提供商和模型。支持多种提供商和模型类型。

## 模型提供商

| 提供商 | 说明 |
|--------|------|
| `openai` | OpenAI (GPT-4, GPT-3.5 等) |
| `anthropic` | Anthropic (Claude 系列) |
| `google` | Google (Gemini 系列) |
| `deepseek` | DeepSeek |
| `azure` | Azure OpenAI |
| `moonshot` | Moonshot AI |
| `zhipu` | 智谱 AI |
| `qwen` | 通义千问 |
| `xai` | xAI (Grok) |
| `openai_compatible` | OpenAI 兼容接口 |

## 模型类型

| 类型 | 说明 |
|------|------|
| `CHAT` | 对话模型 |
| `EMBEDDING` | 嵌入模型 |
| `TTS` | 文本转语音 |
| `STT` | 语音转文本 |
| `TEXT_TO_IMAGE` | 文生图 |

## 接口列表

### GET /providers

获取提供商列表

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 获取所有支持的模型提供商 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "openai",
      "name": "OpenAI",
      "icon": "openai.svg",
      "supported_types": ["CHAT", "EMBEDDING", "TTS", "STT"]
    }
  ]
}
```

---

### GET /types

获取模型类型列表

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 获取所有支持的模型类型 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "CHAT",
      "name": "Chat",
      "description": "对话模型"
    }
  ]
}
```

---

### GET /

获取模型列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:read` |
| 说明 | 获取所有已配置的模型 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词
- `provider`: 提供商筛选
- `type`: 类型筛选

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "GPT-4",
        "provider": "openai",
        "model_id": "gpt-4",
        "type": "CHAT",
        "is_default": true,
        "is_active": true,
        "config": {...}
      }
    ],
    "total": 10
  }
}
```

---

### POST /

创建模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:create` |
| 说明 | 添加新模型配置 |

**请求体**:
```json
{
  "name": "string",
  "provider": "openai",
  "model_id": "gpt-4",
  "type": "CHAT",
  "api_key": "string",
  "api_base": "string (可选)",
  "config": {
    "temperature": 0.7,
    "max_tokens": 4096
  }
}
```

---

### GET /{model_id}

获取模型详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:read` |
| 说明 | 获取指定模型的详细配置 |

**路径参数**:
- `model_id`: 模型 UUID

---

### PUT /{model_id}

更新模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:update` |
| 说明 | 更新模型配置 |

**路径参数**:
- `model_id`: 模型 UUID

---

### DELETE /{model_id}

删除模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:delete` |
| 说明 | 删除模型配置 |

**路径参数**:
- `model_id`: 模型 UUID

---

### POST /{model_id}/test

测试模型连接

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:read` |
| 说明 | 测试已保存模型的连接 |

**路径参数**:
- `model_id`: 模型 UUID

**响应**:
```json
{
  "code": 0,
  "data": {
    "success": true,
    "message": "Connection successful",
    "latency_ms": 150
  }
}
```

---

### POST /{model_id}/set-default

设为默认模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:update` |
| 说明 | 将模型设为该类型的默认模型 |

**路径参数**:
- `model_id`: 模型 UUID

---

### POST /test

测试模型（创建前）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `model:create` |
| 说明 | 在创建模型前测试连接 |

**请求体**:
```json
{
  "provider": "openai",
  "model_id": "gpt-4",
  "type": "CHAT",
  "api_key": "string",
  "api_base": "string (可选)"
}
```

---

### GET /available

获取可用模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取当前团队可用的模型列表 |

**查询参数**:
- `team_id`: 团队 ID
- `type`: 模型类型

---

### GET /default/{model_type}

获取默认模型

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取指定类型的默认模型 |

**路径参数**:
- `model_type`: 模型类型 (CHAT, EMBEDDING 等)

---

## 团队模型授权

模型需要授权给团队才能使用。相关 API 在团队管理中：

- `POST /teams/{team_id}/models` - 授权模型给团队
- `DELETE /teams/{team_id}/models/{model_id}` - 取消授权
- `GET /teams/{team_id}/models` - 获取团队已授权模型
