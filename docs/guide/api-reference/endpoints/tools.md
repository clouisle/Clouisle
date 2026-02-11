# Tools API

This document describes the API endpoints for tool management and execution.

## Overview

The Tools API allows you to:

- **List tools**: Get all available tools
- **Get tool details**: Retrieve tool information
- **Execute tools**: Call tools directly
- **Manage custom tools**: Create and configure tools (admin only)

**Base URL**: `/api/v1/tools`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `tool:read` - View tools
- `tool:use` - Execute tools
- `tool:manage` - Manage tools (admin only)

## List Tools

Get a list of all available tools.

### Endpoint

```
GET /api/v1/tools
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `category` | string | No | - | Filter by category |
| `type` | string | No | - | Filter by type: builtin, custom, integration |
| `is_active` | boolean | No | - | Filter by active status |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/tools?category=search" \
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
        "id": "tool-123",
        "name": "Web Search",
        "description": "Search the internet for information",
        "category": "search",
        "type": "builtin",
        "is_active": true,
        "capabilities": {
          "max_results": 10,
          "supports_filters": true
        },
        "parameters": [
          {
            "name": "query",
            "type": "string",
            "required": true,
            "description": "Search query"
          },
          {
            "name": "max_results",
            "type": "integer",
            "required": false,
            "default": 5,
            "description": "Maximum number of results"
          }
        ],
        "created_at": "2026-01-15T10:00:00Z"
      }
    ],
    "total": 15,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  },
  "msg": "success"
}
```

## Get Tool

Get details of a specific tool.

### Endpoint

```
GET /api/v1/tools/{tool_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/tools/tool-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-123",
    "name": "Web Search",
    "description": "Search the internet for information",
    "category": "search",
    "type": "builtin",
    "is_active": true,
    "icon": "🔍",
    "capabilities": {
      "max_results": 10,
      "supports_filters": true,
      "supports_pagination": true
    },
    "parameters": [
      {
        "name": "query",
        "type": "string",
        "required": true,
        "description": "Search query",
        "validation": {
          "min_length": 1,
          "max_length": 500
        }
      },
      {
        "name": "max_results",
        "type": "integer",
        "required": false,
        "default": 5,
        "description": "Maximum number of results",
        "validation": {
          "min": 1,
          "max": 10
        }
      }
    ],
    "response_schema": {
      "type": "object",
      "properties": {
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "url": {"type": "string"},
              "snippet": {"type": "string"}
            }
          }
        }
      }
    },
    "usage_stats": {
      "total_calls": 12345,
      "success_rate": 98.5,
      "avg_response_time": 1.2
    },
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
  },
  "msg": "success"
}
```

## Execute Tool

Execute a tool with given parameters.

### Endpoint

```
POST /api/v1/tools/{tool_id}/execute
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Body

```json
{
  "parameters": {
    "query": "artificial intelligence",
    "max_results": 5
  },
  "context": {
    "user_id": "user-456",
    "conversation_id": "conv-789"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parameters` | object | Yes | Tool parameters |
| `context` | object | No | Execution context |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/tool-123/execute" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "query": "artificial intelligence",
      "max_results": 5
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "execution_id": "exec-456",
    "tool_id": "tool-123",
    "status": "completed",
    "result": {
      "results": [
        {
          "title": "Artificial Intelligence - Wikipedia",
          "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
          "snippet": "Artificial intelligence (AI) is intelligence demonstrated by machines..."
        },
        {
          "title": "What is AI? | IBM",
          "url": "https://www.ibm.com/topics/artificial-intelligence",
          "snippet": "Artificial intelligence leverages computers and machines..."
        }
      ],
      "total_results": 5
    },
    "metadata": {
      "execution_time": 1.2,
      "tokens_used": 0,
      "cost": 0.0
    },
    "executed_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

**Error (400 Bad Request):**

```json
{
  "code": 1001,
  "data": {
    "field": "parameters.query",
    "error": "Query is required"
  },
  "msg": "Validation failed"
}
```

## Create Custom Tool

Create a custom tool (admin only).

### Endpoint

```
POST /api/v1/tools
```

### Request Body

```json
{
  "name": "CRM Lookup",
  "description": "Look up customer information in CRM",
  "category": "data",
  "type": "custom",
  "icon": "👤",
  "endpoint": {
    "url": "https://api.crm.example.com/customers/{customer_id}",
    "method": "GET",
    "authentication": {
      "type": "api_key",
      "header": "X-API-Key",
      "value": "crm_..."
    },
    "timeout": 30
  },
  "parameters": [
    {
      "name": "customer_id",
      "type": "string",
      "required": true,
      "description": "Customer ID to lookup"
    }
  ],
  "response_schema": {
    "type": "object",
    "properties": {
      "customer_id": {"type": "string"},
      "name": {"type": "string"},
      "email": {"type": "string"}
    }
  }
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CRM Lookup",
    "description": "Look up customer information in CRM",
    "category": "data",
    "type": "custom",
    "endpoint": {
      "url": "https://api.crm.example.com/customers/{customer_id}",
      "method": "GET"
    },
    "parameters": [
      {
        "name": "customer_id",
        "type": "string",
        "required": true
      }
    ]
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-789",
    "name": "CRM Lookup",
    "type": "custom",
    "is_active": true,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Tool created successfully"
}
```

## Update Tool

Update tool configuration (admin only).

### Endpoint

```
PATCH /api/v1/tools/{tool_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "CRM Lookup (Updated)",
  "is_active": true,
  "endpoint": {
    "timeout": 60
  }
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/tools/tool-789" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_active": true
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-789",
    "name": "CRM Lookup (Updated)",
    "is_active": true,
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Tool updated successfully"
}
```

## Delete Tool

Delete a custom tool (admin only).

### Endpoint

```
DELETE /api/v1/tools/{tool_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/tools/tool-789" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Tool deleted successfully"
}
```

## Test Tool

Test tool execution (admin only).

### Endpoint

```
POST /api/v1/tools/{tool_id}/test
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Body

```json
{
  "parameters": {
    "customer_id": "12345"
  }
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/tool-789/test" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "customer_id": "12345"
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": {
      "customer_id": "12345",
      "name": "John Doe",
      "email": "john@example.com"
    },
    "execution_time": 0.5,
    "validation": {
      "passed": true,
      "schema_valid": true,
      "response_format": "valid"
    }
  },
  "msg": "Tool test successful"
}
```

## Get Tool Usage

Get usage statistics for a tool (admin only).

### Endpoint

```
GET /api/v1/tools/{tool_id}/usage
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |
| `group_by` | string | No | day | Group by: hour, day, week, month |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/tools/tool-123/usage?start_date=2026-02-01&end_date=2026-02-11" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "tool_id": "tool-123",
    "tool_name": "Web Search",
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-11T23:59:59Z"
    },
    "summary": {
      "total_calls": 5234,
      "successful_calls": 5123,
      "failed_calls": 111,
      "success_rate": 97.9,
      "avg_response_time": 1.2,
      "total_cost": 0.0
    },
    "daily_stats": [
      {
        "date": "2026-02-11",
        "calls": 567,
        "successful": 555,
        "failed": 12,
        "avg_response_time": 1.1
      },
      {
        "date": "2026-02-10",
        "calls": 489,
        "successful": 478,
        "failed": 11,
        "avg_response_time": 1.3
      }
    ],
    "top_users": [
      {
        "user_id": "user-123",
        "user_email": "john@example.com",
        "calls": 234
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6300` | Tool not found | Tool does not exist |
| `6301` | Tool execution failed | Tool execution error |
| `6302` | Invalid tool parameters | Parameters validation failed |
| `6303` | Tool timeout | Tool execution timeout |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/tools` | 100/minute |
| `GET /api/v1/tools/{id}` | 100/minute |
| `POST /api/v1/tools/{id}/execute` | 60/minute |
| `POST /api/v1/tools` | 10/minute (admin) |
| `PATCH /api/v1/tools/{id}` | 30/minute (admin) |
| `DELETE /api/v1/tools/{id}` | 10/minute (admin) |

## Code Examples

### Python

```python
import requests

def list_tools(token):
    """List all available tools."""
    url = "https://your-domain.com/api/v1/tools"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']['items']
    else:
        raise Exception(f"Error: {result['msg']}")

def execute_tool(token, tool_id, parameters):
    """Execute a tool."""
    url = f"https://your-domain.com/api/v1/tools/{tool_id}/execute"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "parameters": parameters
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']['result']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
tools = list_tools("YOUR_TOKEN")
for tool in tools:
    print(f"Tool: {tool['name']} ({tool['category']})")

# Execute web search
result = execute_tool(
    "YOUR_TOKEN",
    "tool-123",
    {"query": "artificial intelligence", "max_results": 5}
)
print(f"Search results: {result['results']}")
```

### JavaScript

```javascript
async function listTools(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/tools',
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

async function executeTool(token, toolId, parameters) {
  const response = await fetch(
    `https://your-domain.com/api/v1/tools/${toolId}/execute`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        parameters: parameters,
      }),
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data.result;
  } else {
    throw new Error(result.msg);
  }
}

// Usage
const tools = await listTools('YOUR_TOKEN');
tools.forEach(tool => {
  console.log(`Tool: ${tool.name} (${tool.category})`);
});

// Execute web search
const result = await executeTool(
  'YOUR_TOKEN',
  'tool-123',
  { query: 'artificial intelligence', max_results: 5 }
);
console.log('Search results:', result.results);
```

## Related Documentation

- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using tools with agents
- [Tool Management](../../admin-guide/tools/tool-management.md) - Tool admin
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details

---

**Last Updated**: 2026-02-11
