# Models API

This document describes the API endpoints for LLM model discovery and management.

## Overview

The Models API allows you to:

- **List providers**: Get supported LLM providers
- **List model types**: Get supported model types
- **List available models**: Get enabled models for dropdown selection
- **Get default model**: Get the default model for a type
- **Manage models**: Configure LLM models (admin only)
- **Test models**: Test model connectivity (admin only)

**Base URLs**:
- Public catalog metadata: `/api/v1/models/providers`, `/api/v1/models/types`, `/api/v1/models/available`, and `/api/v1/models/default/{model_type}`
- Admin management and listing: `/api/v1/admin/models`

## Authentication

- `GET /api/v1/models/providers` and `GET /api/v1/models/types` require no authentication.
- `GET /api/v1/models/available` and `GET /api/v1/models/default/{model_type}` require an authenticated JWT user session.
- Admin endpoints require an authenticated JWT user with the appropriate scope.

**Required scopes (admin):**
- `admin:model:read` - List and view models
- `admin:model:create` - Create and test-new models
- `admin:model:update` - Update models, set defaults, test saved models
- `admin:model:delete` - Delete models

## List Providers

Get the list of supported LLM providers.

### Endpoint

```
GET /api/v1/models/providers
```

No authentication required.

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/providers"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "code": "openai",
      "name": "OpenAI",
      "base_url": "https://api.openai.com/v1",
      "icon": "openai"
    },
    {
      "code": "anthropic",
      "name": "Anthropic",
      "base_url": "https://api.anthropic.com",
      "icon": "anthropic"
    },
    {
      "code": "azure",
      "name": "Azure OpenAI",
      "base_url": null,
      "icon": "azure"
    }
  ],
  "msg": "success"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Provider identifier |
| `name` | string | Display name |
| `base_url` | string | Default API base URL (`null` if none) |
| `icon` | string | Icon identifier |

## List Model Types

Get the list of supported model types.

### Endpoint

```
GET /api/v1/models/types
```

No authentication required.

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/types"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "code": "chat",
      "name": "Chat",
      "description": "对话模型"
    },
    {
      "code": "embedding",
      "name": "Embedding",
      "description": "嵌入模型"
    },
    {
      "code": "rerank",
      "name": "Rerank",
      "description": "重排序模型"
    },
    {
      "code": "tts",
      "name": "TTS",
      "description": "语音合成"
    },
    {
      "code": "stt",
      "name": "STT",
      "description": "语音识别"
    },
    {
      "code": "audio_generation",
      "name": "Audio Generation",
      "description": "音频生成"
    },
    {
      "code": "text_to_image",
      "name": "Text to Image",
      "description": "文生图"
    },
    {
      "code": "text_to_video",
      "name": "Text to Video",
      "description": "文生视频"
    }
  ],
  "msg": "success"
}
```

## List Available Models

Get enabled models for dropdown selection, optionally filtered by type.

### Endpoint

```
GET /api/v1/models/available
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `model_type` | string | No | - | Filter by model type (e.g. `chat`, `embedding`) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/available?model_type=chat" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "GPT-4 Turbo",
      "provider": "openai",
      "provider_display_name": null,
      "model_id": "gpt-4-turbo-preview",
      "model_type": "chat",
      "capabilities": {
        "streaming": true,
        "function_calling": true
      }
    }
  ],
  "msg": "success"
}
```

## Get Default Model

Get the default enabled model for a specific type.

### Endpoint

```
GET /api/v1/models/default/{model_type}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_type` | string | Yes | Model type (e.g. `chat`, `embedding`) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/default/chat" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

Returns a single `ModelBrief` object (same shape as list items above), or `null` if no default exists.

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "GPT-4 Turbo",
    "provider": "openai",
    "provider_display_name": null,
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "capabilities": {
      "streaming": true,
      "function_calling": true
    }
  },
  "msg": "success"
}
```

## List Models (admin)

Get a paginated list of all configured models.

### Endpoint

```
GET /api/v1/admin/models
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `provider` | array | No | - | Filter by provider (repeatable) |
| `model_type` | array | No | - | Filter by model type (repeatable) |
| `is_enabled` | boolean | No | - | Filter by enabled status |
| `search` | string | No | - | Search by name or model ID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/models?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "GPT-4 Turbo",
        "provider": "openai",
        "provider_display_name": null,
        "model_id": "gpt-4-turbo-preview",
        "model_type": "chat",
        "base_url": "https://api.openai.com/v1",
        "has_api_key": true,
        "context_length": 128000,
        "max_output_tokens": 4096,
        "input_price": 0.01,
        "output_price": 0.03,
        "default_params": {
          "temperature": 0.7
        },
        "capabilities": {
          "streaming": true,
          "function_calling": true,
          "vision": false
        },
        "config": {},
        "is_enabled": true,
        "is_default": true,
        "sort_order": 0,
        "created_at": "2026-01-15T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Model UUID |
| `name` | string | Display name |
| `provider` | string | Provider identifier |
| `provider_display_name` | string | Optional user-facing provider/gateway name |
| `model_id` | string | Model identifier (e.g. `gpt-4-turbo-preview`) |
| `model_type` | string | Model type: `chat`, `embedding`, `rerank`, `tts`, `stt`, `audio_generation`, `text_to_image`, `text_to_video` |
| `base_url` | string | Custom API URL |
| `has_api_key` | boolean | Whether an API key is configured (key itself is hidden) |
| `context_length` | integer | Context length |
| `max_output_tokens` | integer | Max output tokens |
| `input_price` | number | Input price per 1M tokens |
| `output_price` | number | Output price per 1M tokens |
| `default_params` | object | Default inference parameters |
| `capabilities` | object | Model capabilities (e.g. `streaming`, `function_calling`, `vision`) |
| `config` | object | Additional provider-specific configuration |
| `is_enabled` | boolean | Enabled status |
| `is_default` | boolean | Whether this is the default model for its type |
| `sort_order` | integer | Sort order |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |

## Get Model (admin)

Get details of a specific model.

### Endpoint

```
GET /api/v1/admin/models/{model_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/models/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

Returns a single `ModelResponse` object (same shape as list items above).

**Error (404 Not Found):**

```json
{
  "code": 6100,
  "data": null,
  "msg": "Model not found"
}
```

## Create Model (admin)

Add a new LLM model.

### Endpoint

```
POST /api/v1/admin/models
```

### Request Body

```json
{
  "name": "GPT-4 Turbo",
  "provider": "openai",
  "model_id": "gpt-4-turbo-preview",
  "model_type": "chat",
  "provider_display_name": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "context_length": 128000,
  "max_output_tokens": 4096,
  "input_price": 0.01,
  "output_price": 0.03,
  "default_params": {
    "temperature": 0.7
  },
  "capabilities": {
    "streaming": true,
    "function_calling": true,
    "vision": false
  },
  "config": {},
  "is_enabled": true,
  "is_default": false,
  "sort_order": 0
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name (max 100 chars) |
| `provider` | string | Yes | Provider identifier (must be a supported provider) |
| `model_id` | string | Yes | Model identifier (max 100 chars) |
| `model_type` | string | Yes | Model type |
| `provider_display_name` | string | No | Optional user-facing provider or gateway name |
| `base_url` | string | No | Custom API URL (max 512 chars) |
| `api_key` | string | No | API key (optional for local providers) |
| `context_length` | integer | No | Context length |
| `max_output_tokens` | integer | No | Max output tokens |
| `input_price` | number | No | Input price per 1M tokens |
| `output_price` | number | No | Output price per 1M tokens |
| `default_params` | object | No | Default inference parameters |
| `capabilities` | object | No | Model capabilities |
| `config` | object | No | Additional configuration |
| `is_enabled` | boolean | No | Enabled status (default: true) |
| `is_default` | boolean | No | Default model flag (default: false) |
| `sort_order` | integer | No | Sort order (default: 0) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/models" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GPT-4 Turbo",
    "provider": "openai",
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "is_enabled": true
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "GPT-4 Turbo",
    "provider": "openai",
    "provider_display_name": null,
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "base_url": "https://api.openai.com/v1",
    "has_api_key": true,
    "context_length": null,
    "max_output_tokens": null,
    "input_price": null,
    "output_price": null,
    "default_params": null,
    "capabilities": null,
    "config": null,
    "is_enabled": true,
    "is_default": false,
    "sort_order": 0,
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Model created successfully"
}
```

## Update Model (admin)

Update model configuration.

### Endpoint

```
PUT /api/v1/admin/models/{model_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "GPT-4 Turbo (Updated)",
  "is_enabled": true,
  "input_price": 0.01,
  "output_price": 0.03,
  "default_params": {
    "temperature": 0.8
  }
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/admin/models/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GPT-4 Turbo (Updated)",
    "default_params": {
      "temperature": 0.8
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "GPT-4 Turbo (Updated)",
    "provider": "openai",
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "is_enabled": true,
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Model updated successfully"
}
```

## Delete Model (admin)

Delete a model permanently.

### Endpoint

```
DELETE /api/v1/admin/models/{model_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/admin/models/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "GPT-4 Turbo (Updated)",
    "provider": "openai",
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "is_enabled": true,
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Model deleted successfully"
}
```

## Set Default Model (admin)

Set a model as the default for its type.

### Endpoint

```
POST /api/v1/admin/models/{model_id}/set-default
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/models/550e8400-e29b-41d4-a716-446655440000/set-default" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

Returns the updated `ModelResponse` with `is_default: true`.

## Test Model Connection (admin)

Test connectivity for an already-saved model.

### Endpoint

```
POST /api/v1/admin/models/{model_id}/test
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

No request body is required.

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/models/550e8400-e29b-41d4-a716-446655440000/test" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "message": "Model connection successful",
    "latency_ms": 1200
  },
  "msg": "Model test successful"
}
```

**Error (500 Internal Server Error):**

```json
{
  "code": 6100,
  "data": null,
  "msg": "Model test failed"
}
```

## Test Model Configuration (admin)

Test a provider/model configuration before saving it.

### Endpoint

```
POST /api/v1/admin/models/test
```

### Request Body

```json
{
  "provider": "openai",
  "model_id": "gpt-4-turbo-preview",
  "model_type": "chat",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "default_params": {
    "temperature": 0.7
  },
  "config": {}
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/models/test" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "api_key": "sk-..."
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "message": "Model connection successful",
    "latency_ms": 1100
  },
  "msg": "Model test successful"
}
```

## Discover Models (admin)

List models exposed by a provider without persisting the supplied key.

### Endpoint

```
POST /api/v1/admin/models/discover
```

### Request Body

```json
{
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-..."
}
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "message": "Discovered 3 models",
    "models": [
      {
        "id": "gpt-4-turbo-preview",
        "name": "GPT-4 Turbo",
        "context_length": 128000,
        "max_output_tokens": 4096,
        "capabilities": {
          "streaming": true,
          "function_calling": true
        }
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6100` | Model not found | Model does not exist |
| `6101` | Team model not found | Team model authorization does not exist |
| `6102` | Team model exists | Team model authorization already exists |
| `6103` | Model quota exceeded | Team model quota exceeded |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Best Practices

### Model Configuration

**✅ Do:**
- Test models after configuration
- Set appropriate pricing information
- Use descriptive model names
- Keep API keys secure
- Set reasonable default parameters

**❌ Don't:**
- Expose API keys in logs
- Use production keys in development
- Forget to update pricing
- Enable untested models

### Provider Selection

**✅ Do:**
- Choose models based on use case
- Consider cost vs. performance
- Test multiple providers
- Monitor model availability
- Plan for provider failover

**❌ Don't:**
- Use single provider for all tasks
- Ignore model limitations

## Code Examples

### Python

```python
import requests

def list_available_models(token, model_type="chat"):
    """List enabled models of a type."""
    url = "https://your-domain.com/api/v1/models/available"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers, params={"model_type": model_type})
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

def create_model(token, name, model_id, provider, model_type, api_key):
    """Create a new model (admin)."""
    url = "https://your-domain.com/api/v1/admin/models"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "provider": provider,
        "model_id": model_id,
        "model_type": model_type,
        "api_key": api_key
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

def test_model(token, model_id):
    """Test a saved model (admin)."""
    url = f"https://your-domain.com/api/v1/admin/models/{model_id}/test"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.post(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
models = list_available_models("YOUR_TOKEN", "chat")
for model in models:
    print(f"Model: {model['name']} ({model['provider']})")

# Create model (admin)
new_model = create_model(
    "YOUR_ADMIN_TOKEN",
    "GPT-4 Turbo",
    "gpt-4-turbo-preview",
    "openai",
    "chat",
    "sk-..."
)
print(f"Created model: {new_model['id']}")

# Test model (admin)
test_result = test_model("YOUR_ADMIN_TOKEN", new_model['id'])
print(f"Test success: {test_result['success']}")
```

### JavaScript

```javascript
async function listAvailableModels(token, modelType = 'chat') {
  const response = await fetch(
    `https://your-domain.com/api/v1/models/available?model_type=${modelType}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data;
  } else {
    throw new Error(result.msg);
  }
}

async function createModel(token, name, modelId, provider, modelType, apiKey) {
  const response = await fetch(
    'https://your-domain.com/api/v1/admin/models',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: name,
        provider: provider,
        model_id: modelId,
        model_type: modelType,
        api_key: apiKey,
      }),
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data;
  } else {
    throw new Error(result.msg);
  }
}

// Usage
const models = await listAvailableModels('YOUR_TOKEN', 'chat');
models.forEach(model => {
  console.log(`Model: ${model.name} (${model.provider})`);
});

// Create model (admin)
const newModel = await createModel(
  'YOUR_ADMIN_TOKEN',
  'GPT-4 Turbo',
  'gpt-4-turbo-preview',
  'openai',
  'chat',
  'sk-...'
);
console.log('Created model:', newModel.id);
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [Model Management](../../admin-guide/models/model-management.md) - Admin guide
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using models with agents

---

**Last Updated**: 2026-02-11
