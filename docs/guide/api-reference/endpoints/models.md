# Models API

This document describes the API endpoints for LLM model management.

## Overview

The Models API allows you to:

- **List models**: Get all available LLM models
- **Get model details**: Retrieve model information
- **Add models**: Configure new LLM models (admin only)
- **Update models**: Modify model settings (admin only)
- **Delete models**: Remove models (admin only)
- **Test models**: Test model connectivity

**Base URL**: `/api/v1/models`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `model:read` - View model information
- `model:manage` - Manage models (admin only)

## List Models

Get a list of all available LLM models.

### Endpoint

```
GET /api/v1/models
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `provider` | string | No | - | Filter by provider: openai, anthropic, azure, etc. |
| `is_active` | boolean | No | - | Filter by active status |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "model-123",
        "name": "GPT-4 Turbo",
        "model_id": "gpt-4-turbo-preview",
        "provider": "openai",
        "type": "chat",
        "is_active": true,
        "capabilities": {
          "streaming": true,
          "function_calling": true,
          "vision": false,
          "max_tokens": 128000
        },
        "pricing": {
          "input_per_1k": 0.01,
          "output_per_1k": 0.03,
          "currency": "USD"
        },
        "created_at": "2026-01-15T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      },
      {
        "id": "model-456",
        "name": "Claude 3.5 Sonnet",
        "model_id": "claude-3-5-sonnet-20240620",
        "provider": "anthropic",
        "type": "chat",
        "is_active": true,
        "capabilities": {
          "streaming": true,
          "function_calling": true,
          "vision": true,
          "max_tokens": 200000
        },
        "pricing": {
          "input_per_1k": 0.003,
          "output_per_1k": 0.015,
          "currency": "USD"
        },
        "created_at": "2026-01-20T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  },
  "msg": "success"
}
```

## Get Model

Get details of a specific model.

### Endpoint

```
GET /api/v1/models/{model_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/model-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "model-123",
    "name": "GPT-4 Turbo",
    "model_id": "gpt-4-turbo-preview",
    "provider": "openai",
    "type": "chat",
    "is_active": true,
    "description": "Most capable GPT-4 model with 128K context",
    "capabilities": {
      "streaming": true,
      "function_calling": true,
      "vision": false,
      "max_tokens": 128000,
      "supports_system_message": true,
      "supports_temperature": true,
      "supports_top_p": true
    },
    "pricing": {
      "input_per_1k": 0.01,
      "output_per_1k": 0.03,
      "currency": "USD"
    },
    "config": {
      "api_base": "https://api.openai.com/v1",
      "api_version": null,
      "default_temperature": 0.7,
      "default_max_tokens": 4096
    },
    "usage_stats": {
      "total_requests": 12345,
      "total_tokens": 45678901,
      "total_cost": 456.78
    },
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
  },
  "msg": "success"
}
```

## Create Model

Add a new LLM model (admin only).

### Endpoint

```
POST /api/v1/models
```

### Request Body

```json
{
  "name": "GPT-4 Turbo",
  "model_id": "gpt-4-turbo-preview",
  "provider": "openai",
  "type": "chat",
  "description": "Most capable GPT-4 model with 128K context",
  "is_active": true,
  "capabilities": {
    "streaming": true,
    "function_calling": true,
    "vision": false,
    "max_tokens": 128000
  },
  "pricing": {
    "input_per_1k": 0.01,
    "output_per_1k": 0.03,
    "currency": "USD"
  },
  "config": {
    "api_key": "sk-...",
    "api_base": "https://api.openai.com/v1",
    "default_temperature": 0.7,
    "default_max_tokens": 4096
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name |
| `model_id` | string | Yes | Model identifier (e.g., gpt-4-turbo-preview) |
| `provider` | string | Yes | Provider: openai, anthropic, azure, etc. |
| `type` | string | Yes | Model type: chat, completion, embedding |
| `description` | string | No | Model description |
| `is_active` | boolean | No | Active status (default: true) |
| `capabilities` | object | No | Model capabilities |
| `pricing` | object | No | Pricing information |
| `config` | object | Yes | Provider-specific configuration |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/models" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GPT-4 Turbo",
    "model_id": "gpt-4-turbo-preview",
    "provider": "openai",
    "type": "chat",
    "config": {
      "api_key": "sk-...",
      "api_base": "https://api.openai.com/v1"
    }
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "model-789",
    "name": "GPT-4 Turbo",
    "model_id": "gpt-4-turbo-preview",
    "provider": "openai",
    "type": "chat",
    "is_active": true,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Model created successfully"
}
```

## Update Model

Update model configuration (admin only).

### Endpoint

```
PATCH /api/v1/models/{model_id}
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
  "is_active": true,
  "pricing": {
    "input_per_1k": 0.01,
    "output_per_1k": 0.03
  },
  "config": {
    "default_temperature": 0.8
  }
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/models/model-123" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_active": true,
    "pricing": {
      "input_per_1k": 0.01,
      "output_per_1k": 0.03
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "model-123",
    "name": "GPT-4 Turbo (Updated)",
    "is_active": true,
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Model updated successfully"
}
```

## Delete Model

Delete a model permanently (admin only).

### Endpoint

```
DELETE /api/v1/models/{model_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/models/model-123" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Model deleted successfully"
}
```

## Test Model

Test model connectivity and configuration.

### Endpoint

```
POST /api/v1/models/{model_id}/test
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Request Body

```json
{
  "prompt": "Hello, how are you?",
  "temperature": 0.7,
  "max_tokens": 100
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/models/model-123/test" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello, how are you?",
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "response": "Hello! I'm doing well, thank you for asking. How can I help you today?",
    "tokens_used": {
      "prompt": 6,
      "completion": 18,
      "total": 24
    },
    "response_time": 1.2,
    "model_info": {
      "model": "gpt-4-turbo-preview",
      "provider": "openai"
    }
  },
  "msg": "Model test successful"
}
```

**Error (500 Internal Server Error):**

```json
{
  "code": 6100,
  "data": {
    "error": "Invalid API key",
    "provider": "openai"
  },
  "msg": "Model test failed"
}
```

## Get Model Usage

Get usage statistics for a model (admin only).

### Endpoint

```
GET /api/v1/models/{model_id}/usage
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_id` | string | Yes | Model UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |
| `group_by` | string | No | day | Group by: hour, day, week, month |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/model-123/usage?start_date=2026-01-01&end_date=2026-02-11" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "model_id": "model-123",
    "model_name": "GPT-4 Turbo",
    "period": {
      "start": "2026-01-01T00:00:00Z",
      "end": "2026-02-11T23:59:59Z"
    },
    "summary": {
      "total_requests": 12345,
      "total_tokens": 45678901,
      "total_cost": 456.78,
      "avg_tokens_per_request": 3700,
      "avg_response_time": 2.3
    },
    "daily_stats": [
      {
        "date": "2026-02-11",
        "requests": 234,
        "tokens": 865200,
        "cost": 8.65,
        "avg_response_time": 2.1
      },
      {
        "date": "2026-02-10",
        "requests": 198,
        "tokens": 732600,
        "cost": 7.33,
        "avg_response_time": 2.4
      }
    ]
  },
  "msg": "success"
}
```

## List Providers

Get a list of supported LLM providers.

### Endpoint

```
GET /api/v1/models/providers
```

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/models/providers" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "providers": [
      {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI GPT models",
        "supported_types": ["chat", "completion", "embedding"],
        "config_fields": [
          {
            "name": "api_key",
            "type": "string",
            "required": true,
            "description": "OpenAI API key"
          },
          {
            "name": "api_base",
            "type": "string",
            "required": false,
            "description": "Custom API base URL"
          }
        ]
      },
      {
        "id": "anthropic",
        "name": "Anthropic",
        "description": "Anthropic Claude models",
        "supported_types": ["chat"],
        "config_fields": [
          {
            "name": "api_key",
            "type": "string",
            "required": true,
            "description": "Anthropic API key"
          }
        ]
      },
      {
        "id": "azure",
        "name": "Azure OpenAI",
        "description": "Azure OpenAI Service",
        "supported_types": ["chat", "completion", "embedding"],
        "config_fields": [
          {
            "name": "api_key",
            "type": "string",
            "required": true,
            "description": "Azure API key"
          },
          {
            "name": "api_base",
            "type": "string",
            "required": true,
            "description": "Azure endpoint URL"
          },
          {
            "name": "api_version",
            "type": "string",
            "required": true,
            "description": "API version"
          },
          {
            "name": "deployment_name",
            "type": "string",
            "required": true,
            "description": "Deployment name"
          }
        ]
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
| `6101` | Model test failed | Model connectivity test failed |
| `6102` | Invalid model config | Model configuration is invalid |
| `6103` | Provider not supported | LLM provider is not supported |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5100` | Model already exists | Model with this ID already exists |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/models` | 100/minute |
| `GET /api/v1/models/{id}` | 100/minute |
| `POST /api/v1/models` | 10/minute (admin) |
| `PATCH /api/v1/models/{id}` | 30/minute (admin) |
| `DELETE /api/v1/models/{id}` | 10/minute (admin) |
| `POST /api/v1/models/{id}/test` | 10/minute (admin) |

## Best Practices

### Model Configuration

**✅ Do:**
- Test models after configuration
- Set appropriate pricing information
- Use descriptive model names
- Keep API keys secure
- Monitor model usage and costs
- Set reasonable default parameters

**❌ Don't:**
- Expose API keys in logs
- Use production keys in development
- Forget to update pricing
- Enable untested models
- Ignore usage alerts

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
- Forget about rate limits
- Skip cost analysis

## Code Examples

### Python

```python
import requests

def list_models(token):
    """List all available models."""
    url = "https://your-domain.com/api/v1/models"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']['items']
    else:
        raise Exception(f"Error: {result['msg']}")

def create_model(token, name, model_id, provider, config):
    """Create a new model."""
    url = "https://your-domain.com/api/v1/models"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "model_id": model_id,
        "provider": provider,
        "type": "chat",
        "config": config
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

def test_model(token, model_id, prompt):
    """Test a model."""
    url = f"https://your-domain.com/api/v1/models/{model_id}/test"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 100
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
models = list_models("YOUR_TOKEN")
for model in models:
    print(f"Model: {model['name']} ({model['provider']})")

# Create model
new_model = create_model(
    "YOUR_ADMIN_TOKEN",
    "GPT-4 Turbo",
    "gpt-4-turbo-preview",
    "openai",
    {"api_key": "sk-..."}
)
print(f"Created model: {new_model['id']}")

# Test model
test_result = test_model(
    "YOUR_ADMIN_TOKEN",
    "model-123",
    "Hello, how are you?"
)
print(f"Test response: {test_result['response']}")
```

### JavaScript

```javascript
async function listModels(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/models',
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data.items;
  } else {
    throw new Error(result.msg);
  }
}

async function createModel(token, name, modelId, provider, config) {
  const response = await fetch(
    'https://your-domain.com/api/v1/models',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: name,
        model_id: modelId,
        provider: provider,
        type: 'chat',
        config: config,
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

async function testModel(token, modelId, prompt) {
  const response = await fetch(
    `https://your-domain.com/api/v1/models/${modelId}/test`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: prompt,
        temperature: 0.7,
        max_tokens: 100,
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
const models = await listModels('YOUR_TOKEN');
models.forEach(model => {
  console.log(`Model: ${model.name} (${model.provider})`);
});

// Create model
const newModel = await createModel(
  'YOUR_ADMIN_TOKEN',
  'GPT-4 Turbo',
  'gpt-4-turbo-preview',
  'openai',
  { api_key: 'sk-...' }
);
console.log('Created model:', newModel.id);

// Test model
const testResult = await testModel(
  'YOUR_ADMIN_TOKEN',
  'model-123',
  'Hello, how are you?'
);
console.log('Test response:', testResult.response);
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Model Management](../../admin-guide/models/model-management.md) - Admin guide
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using models with agents

---

**Last Updated**: 2026-02-11
