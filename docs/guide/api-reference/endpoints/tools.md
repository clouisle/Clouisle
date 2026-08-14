# Tools API

This document describes the API endpoints for tool management and execution.

## Overview

The Tools API allows you to:

- **List tools**: Get all available tools
- **Get tool details**: Retrieve tool information
- **Test tools**: Execute a tool once with arguments
- **Execute code**: Run code directly in the sandbox
- **Manage custom tools**: Create and configure tools

**Base URL**: `/api/v1/tools`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `tool:read` - View tools
- `tool:create` - Create tools
- `tool:update` - Update tools
- `tool:delete` - Delete tools
- `tool:execute` - Execute/test tools

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
| `page_size` | integer | No | 10 | Items per page (max: 100) |
| `search` | string | No | - | Search by name or display name |
| `type` | array | No | - | Filter by type: `builtin`, `custom`, `mcp` (repeatable) |
| `category` | array | No | - | Filter by category (repeatable) |
| `status` | array | No | - | Filter by enabled status (repeatable) |
| `team_id` | array | No | - | Filter by owning team (repeatable) |
| `creator` | array | No | - | Filter by creator (repeatable) |

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
        "name": "web_search",
        "display_name": "Web Search",
        "description": "Search the internet for information",
        "type": "builtin",
        "category": "search",
        "icon": "🔍",
        "parameters": [
          {
            "name": "query",
            "type": "string",
            "description": "Search query",
            "required": true
          },
          {
            "name": "max_results",
            "type": "integer",
            "description": "Maximum number of results",
            "required": false,
            "default": 5
          }
        ],
        "is_enabled": true,
        "requires_config": false,
        "config_fields": [],
        "custom_type": null,
        "http_config": null,
        "code_config": null,
        "mcp_config": null,
        "team_id": null,
        "created_by_id": null,
        "created_by_name": null,
        "is_owned": true,
        "owner_team_id": null,
        "owner_team_name": null,
        "share_permission": null,
        "shared_with_count": 0
      }
    ],
    "total": 15,
    "page": 1,
    "page_size": 10
  },
  "msg": "success"
}
```

## Get Tool

Get details of a specific tool.

### Endpoints

```
GET /api/v1/tools/id/{tool_id}
GET /api/v1/tools/name/{tool_name}?team_id={team_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID (for `GET /id/{tool_id}`) |
| `tool_name` | string | Yes | Tool name (for `GET /name/{tool_name}`) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/tools/id/tool-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-123",
    "name": "web_search",
    "display_name": "Web Search",
    "description": "Search the internet for information",
    "type": "builtin",
    "category": "search",
    "icon": "🔍",
    "parameters": [
      {
        "name": "query",
        "type": "string",
        "description": "Search query",
        "required": true
      },
      {
        "name": "max_results",
        "type": "integer",
        "description": "Maximum number of results",
        "required": false,
        "default": 5
      }
    ],
    "is_enabled": true,
    "requires_config": false,
    "config_fields": [],
    "custom_type": null,
    "http_config": null,
    "code_config": null,
    "mcp_config": null,
    "team_id": null,
    "created_by_id": null,
    "created_by_name": null,
    "is_owned": true,
    "owner_team_id": null,
    "owner_team_name": null,
    "share_permission": null,
    "shared_with_count": 0,
    "created_at": null,
    "updated_at": null
  },
  "msg": "success"
}
```

## Test Tool

Execute a tool once by name with arguments. There is no standalone `POST /tools/{tool_id}/execute` endpoint.

### Endpoint

```
POST /api/v1/tools/test
```

### Request Body

```json
{
  "name": "web_search",
  "arguments": {
    "query": "artificial intelligence",
    "max_results": 5
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tool name |
| `arguments` | object | No | Tool arguments |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/test" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web_search",
    "arguments": {
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
    "name": "web_search",
    "success": true,
    "result": {
      "results": [
        {
          "title": "Artificial Intelligence - Wikipedia",
          "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
          "snippet": "Artificial intelligence (AI) is intelligence demonstrated by machines..."
        }
      ]
    },
    "error": null,
    "logs": null,
    "artifacts": [],
    "duration_ms": 1200
  },
  "msg": "success"
}
```

**Error (400 Bad Request):**

```json
{
  "code": 1001,
  "data": {
    "field": "arguments.query",
    "error": "Query is required"
  },
  "msg": "Validation failed"
}
```

## Execute Code

Run JavaScript/Python code directly in the sandbox without saving a tool.

### Endpoint

```
POST /api/v1/tools/execute-code
```

### Request Body

```json
{
  "language": "python",
  "code": "print(1 + 1)",
  "params": {},
  "timeout": 30,
  "python_packages": ["requests"]
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `language` | string | Yes | Code language: `javascript`, `python` |
| `code` | string | Yes | Code content |
| `params` | object | No | Input parameters |
| `timeout` | number | No | Timeout in seconds (1-60, default: 30) |
| `command` | array | No | Custom command (argv array) |
| `python_packages` | array | No | Python packages to install |
| `js_packages` | array | No | JavaScript packages to install |
| `python_package_index_url` | string | No | Python package mirror URL |
| `node_package_registry_url` | string | No | JavaScript package registry URL |
| `artifacts` | array | No | Sandbox artifact configuration |
| `limits` | object | No | Resource limits (timeout_seconds, disk_mb, max_stdout_kb, max_stderr_kb) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/execute-code" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "language": "python",
    "code": "print(1 + 1)"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": "2\n",
    "error": null,
    "logs": null,
    "artifacts": [],
    "duration_ms": 350
  },
  "msg": "success"
}
```

## Create Custom Tool

Create a custom tool. `team_id` is a required query parameter.

### Endpoint

```
POST /api/v1/tools?team_id={team_id}
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID that owns the tool |

### Request Body

```json
{
  "name": "crm_lookup",
  "display_name": "CRM Lookup",
  "description": "Look up customer information in CRM",
  "category": "data",
  "type": "custom",
  "custom_type": "http",
  "icon": "👤",
  "parameters": [
    {
      "name": "customer_id",
      "type": "string",
      "required": true,
      "description": "Customer ID to lookup"
    }
  ],
  "http_config": {
    "method": "GET",
    "url": "https://api.crm.example.com/customers/{customer_id}",
    "headers": {
      "X-API-Key": "crm_..."
    },
    "timeout": 30
  },
  "credentials": {},
  "is_enabled": true
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tool name (unique identifier, max 100 chars) |
| `display_name` | string | Yes | Display name (max 100 chars) |
| `description` | string | No | Tool description |
| `icon` | string | No | Icon (emoji or URL, max 100 chars) |
| `category` | string | No | Tool category (default: `other`) |
| `type` | string | No | Tool type: `builtin`, `custom`, `mcp` (default: `custom`) |
| `custom_type` | string | No | Custom tool type: `http`, `code`, `mcp` (only for `type=custom`) |
| `parameters` | array | No | Parameter definitions (`name`, `type`, `description`, `required`, `enum`, `default`) |
| `http_config` | object | No | HTTP config (`method`, `url`, `headers`, `query_params`, `body_template`, `content_type`, `form_fields`, `timeout`, `response_path`) |
| `code_config` | object | No | Code config (`language`, `code`, `command`, `python_packages`, `js_packages`, `artifacts`, `limits`) |
| `mcp_config` | object | No | MCP Server config (`transport`, `command`, `args`, `env`, `url`, `headers`) |
| `credentials` | object | No | Tool credentials |
| `is_enabled` | boolean | No | Enabled status (default: true) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools?team_id=team-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "crm_lookup",
    "display_name": "CRM Lookup",
    "description": "Look up customer information in CRM",
    "category": "data",
    "type": "custom",
    "custom_type": "http",
    "parameters": [
      {
        "name": "customer_id",
        "type": "string",
        "required": true
      }
    ],
    "http_config": {
      "method": "GET",
      "url": "https://api.crm.example.com/customers/{customer_id}"
    }
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-789",
    "name": "crm_lookup",
    "display_name": "CRM Lookup",
    "description": "Look up customer information in CRM",
    "type": "custom",
    "category": "data",
    "custom_type": "http",
    "is_enabled": true,
    "team_id": "team-123",
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z",
    "created_by_name": "alice"
  },
  "msg": "Tool created successfully"
}
```

## Update Tool

Update tool configuration.

### Endpoint

```
PUT /api/v1/tools/{tool_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "display_name": "CRM Lookup (Updated)",
  "is_enabled": true,
  "http_config": {
    "timeout": 60
  }
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/tools/tool-789" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "CRM Lookup (Updated)",
    "is_enabled": true
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-789",
    "name": "crm_lookup",
    "display_name": "CRM Lookup (Updated)",
    "type": "custom",
    "is_enabled": true,
    "team_id": "team-123",
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:05:00Z",
    "created_by_name": "alice"
  },
  "msg": "Tool updated successfully"
}
```

## Delete Tool

Delete a custom tool.

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
  -H "Authorization: Bearer YOUR_TOKEN"
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

## Get Tool Usage

> **Note:** Not implemented / Roadmap. There is no per-tool usage statistics endpoint.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Not found | Tool does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints. (Codes `6300`-`6306` are reserved for SSO errors and are not used by the Tools API.)

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

def test_tool(token, name, arguments):
    """Execute a tool once."""
    url = "https://your-domain.com/api/v1/tools/test"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "arguments": arguments
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
    print(f"Tool: {tool['display_name']} ({tool['category']})")

# Execute web search
result = test_tool(
    "YOUR_TOKEN",
    "web_search",
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

async function testTool(token, name, arguments) {
  const response = await fetch(
    'https://your-domain.com/api/v1/tools/test',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: name,
        arguments: arguments,
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
  console.log(`Tool: ${tool.display_name} (${tool.category})`);
});

// Execute web search
const result = await testTool(
  'YOUR_TOKEN',
  'web_search',
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
