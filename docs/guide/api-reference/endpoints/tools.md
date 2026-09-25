# Tools API

This document describes the API endpoints for tool management and execution.

## Overview

The Tools API allows you to:

- **List tools**: Get all available tools
- **Get tool details**: Retrieve tool information
- **Test tools**: Execute a tool once with arguments
- **Execute code**: Run code directly in the sandbox
- **Manage custom tools**: Create and configure tools
- **Toggle & duplicate tools**: Enable/disable or copy a tool
- **Tool configuration**: Store tool credentials globally or per team
- **Share tools**: Share a tool across teams and manage its shares

**Base URL**: `/api/v1/tools`

## Authentication

All endpoints require an authenticated JWT user session. API-key authentication is not accepted by these management and execution routes.

**Required permissions:**
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
        "database_config": null,
        "mcp_config": null,
        "team_id": null,
        "created_by_id": null,
        "created_by_name": null,
        "visibility": "private",
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

## List Tool Filter Options

Get the filter option lists (types, categories, statuses, teams, creators) for the current user's accessible tools.

### Endpoint

```
GET /api/v1/tools/filters
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "types": [
      { "value": "builtin", "label": "builtin" },
      { "value": "custom", "label": "custom" },
      { "value": "mcp", "label": "mcp" }
    ],
    "categories": [
      { "value": "search", "label": "search" }
    ],
    "statuses": [
      { "value": "enabled", "label": "enabled" },
      { "value": "disabled", "label": "disabled" }
    ],
    "teams": [
      { "value": "team-123", "label": "Engineering" }
    ],
    "creators": [
      { "value": "alice", "label": "alice" }
    ]
  },
  "msg": "success"
}
```

`categories` contains every defined tool category plus any custom category present on accessible tools. `teams` lists the teams the user can access, and `creators` the distinct creator names of accessible tools.

## List Legacy Team Tools

Legacy compatibility endpoint returning a team's tools grouped by kind. Prefer [List Tools](#list-tools) for new integrations.

### Endpoint

```
GET /api/v1/tools/legacy?team_id={team_id}
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | Yes | - | Team UUID |
| `include_shared` | boolean | No | true | Include tools shared with the team by other teams |

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "builtin": [],
    "custom": [
      {
        "id": "tool-789",
        "name": "crm_lookup",
        "display_name": "CRM Lookup",
        "description": "Look up customer information in CRM",
        "type": "custom",
        "category": "data",
        "icon": "👤",
        "parameters": [],
        "is_enabled": true,
        "requires_config": false,
        "config_fields": [],
        "custom_type": "http",
        "team_id": "team-123",
        "created_by_id": "user-1",
        "created_by_name": "alice",
        "visibility": "private",
        "is_owned": true,
        "owner_team_id": "team-123",
        "owner_team_name": null,
        "share_permission": null,
        "shared_with_count": 0
      }
    ],
    "mcp": []
  },
  "msg": "success"
}
```

`builtin` always contains the full builtin tool list; `custom` and `mcp` contain the team's own tools (excluding other members' private tools) and, when `include_shared` is true, tools shared with the team.

## List Builtin Tools

Get every builtin tool (including the sandbox tools `artifact`, `bash`, `edit`, `read`, `write`).

### Endpoint

```
GET /api/v1/tools/builtin
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "id": null,
      "name": "web_search",
      "display_name": "Web Search",
      "description": "Search the internet for information",
      "type": "builtin",
      "category": "search",
      "icon": "🔍",
      "parameters": [],
      "is_enabled": true,
      "requires_config": true,
      "config_fields": ["TAVILY_API_KEY"],
      "custom_type": null,
      "is_owned": true,
      "visibility": "private"
    }
  ],
  "msg": "success"
}
```

## List File Parsers

Get the tools usable as document parsers for file uploads: builtin parsers (such as `markitdown`) plus the team's enabled custom tools with `category=file`.

### Endpoint

```
GET /api/v1/tools/file-parsers?team_id={team_id}
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID whose custom file parsers are included |

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "id": null,
      "name": "markitdown",
      "display_name": "MarkItDown",
      "description": "Convert documents to Markdown",
      "type": "builtin",
      "category": "file",
      "icon": null,
      "parameters": [],
      "is_enabled": true
    }
  ],
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
    "database_config": null,
    "mcp_config": null,
    "team_id": null,
    "created_by_id": null,
    "created_by_name": null,
    "visibility": "private",
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

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | No | Team UUID used to resolve custom tools and look up tool credentials (team configuration first, then global) |

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
| `custom_type` | string | No | Custom tool type: `http`, `code`, `database`, `mcp` (only for `type=custom`) |
| `visibility` | string | No | Tool visibility: `private`, `team` (default: `private`) |
| `parameters` | array | No | Parameter definitions (`name`, `type`, `description`, `required`, `enum`, `default`) |
| `http_config` | object | No | HTTP config (`method`, `url`, `headers`, `query_params`, `body_template`, `content_type`, `form_fields`, `timeout`, `response_path`) |
| `code_config` | object | No | Code config (`language`, `code`, `command`, `python_packages`, `js_packages`, `python_package_index_url`, `node_package_registry_url`, `artifacts`, `limits`) |
| `database_config` | object | No | Database config (`db_type`, `host`, `port`, `database`, `username`, `password`, `ssl`, `url`, `db`, `auth_source`, `timeout`, `max_limit`) |
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

**Success (200 OK):**

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

## Toggle Tool

Flip a tool's enabled state. There is no request body.

### Endpoint

```
POST /api/v1/tools/{tool_id}/toggle
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/tool-789/toggle" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-789",
    "name": "crm_lookup",
    "display_name": "CRM Lookup",
    "type": "custom",
    "is_enabled": false,
    "team_id": "team-123",
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:05:00Z",
    "created_by_name": "alice"
  },
  "msg": "Tool updated successfully"
}
```

The tool creator or a team admin/owner can toggle a tool. Only custom and MCP tools (database-backed) can be toggled; builtin tools are always enabled.

## Duplicate Tool

Copy a database-backed tool within its owning team.

### Endpoint

```
POST /api/v1/tools/{tool_id}/duplicate
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_id` | string | Yes | Tool UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/tools/tool-789/duplicate" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "tool-790",
    "name": "crm_lookup_copy",
    "display_name": "CRM Lookup (Copy)",
    "type": "custom",
    "custom_type": "http",
    "is_enabled": false,
    "team_id": "team-123",
    "created_at": "2026-02-11T16:10:00Z",
    "updated_at": "2026-02-11T16:10:00Z",
    "created_by_name": "alice"
  },
  "msg": "Tool duplicated successfully"
}
```

The copy is created in the same team with visibility `private` and `is_enabled=false`. The name gets a `_copy` suffix (`_copy_1`, `_copy_2`, … when that name is already taken) and the display name gets a `(Copy)` suffix. Requires the `tool:create` permission and team admin rights.

## Tool Configuration

Store credentials (API keys, tokens) for builtin or database tools, either globally (superuser only) or per team.

### List Tool Configurations

```
GET /api/v1/tools/config?team_id={team_id}
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | No | Team UUID. Omit to list global configurations (superuser only) |

### Get Tool Configuration

```
GET /api/v1/tools/config/{tool_name}?team_id={team_id}
```

### Create Tool Configuration

```
POST /api/v1/tools/config?team_id={team_id}
```

```json
{
  "tool_name": "web_search",
  "credentials": {
    "TAVILY_API_KEY": "tvly-..."
  }
}
```

### Update Tool Configuration

```
PUT /api/v1/tools/config/{tool_name}?team_id={team_id}
```

```json
{
  "credentials": {
    "TAVILY_API_KEY": "tvly-updated"
  }
}
```

### Delete Tool Configuration

```
DELETE /api/v1/tools/config/{tool_name}?team_id={team_id}
```

### Path & Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_name` | string | Yes | Tool name (path parameter), e.g. `web_search` |
| `team_id` | string | No | Team UUID query parameter. Omit for the global configuration |

With `team_id`, team admin rights are required for create/update/delete and team membership for read; without `team_id`, only superusers may read or write the global configuration. Reading a team configuration for a known builtin tool name creates an empty configuration automatically; an unknown name returns 404.

### Response

**Success (200 OK)** — for the list endpoint `data` is an array of the object below; for get/create/update it is the object itself:

```json
{
  "code": 0,
  "data": {
    "id": "cfg-001",
    "tool_name": "web_search",
    "team_id": "team-123",
    "credentials": {
      "TAVILY_API_KEY": "tvly-..."
    },
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Tool configuration created successfully"
}
```

**Success (200 OK)** — delete returns `data: null` with `msg: "Tool configuration deleted successfully"`.

## Get Tool Usage

> **Note:** Not implemented / Roadmap. There is no per-tool usage statistics endpoint.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Not found | Tool, tool configuration, or tool share does not exist |
| `4004` | Team not found | Target team for a share does not exist |
| `3000` | Permission denied | Insufficient permissions, or private tool access denied |
| `3002` | Not a team member | A requested `team_id` filter refers to a team the user cannot access |
| `1001` | Validation failed | Invalid request data |
| `1002` | Bad request | Private tool cannot be shared, share target is the owning team, or database connection failed |
| `1003` | Internal error | MCP server connection failed |
| `5001` | Already exists | A tool with the same name already exists in the team |
| `5104` | Duplicate name | Tool is already shared with that team, or the tool configuration already exists |

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

## Cross-Team Tool Sharing

Share custom tools with other teams across the workspace.

### Share Tool

```http
POST /api/v1/tools/{tool_id}/share HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "team_id": "target-team-uuid",
  "permission": "read_only"
}
```

### List Shares for Tool

```http
GET /api/v1/tools/{tool_id}/shares HTTP/1.1
Authorization: Bearer <token>
```

### List Tools Shared With Me

```http
GET /api/v1/tools/shared-with-me?team_id=my-team-uuid HTTP/1.1
Authorization: Bearer <token>
```

Returns a `ToolListOut` object (`builtin` is always empty here; shared tools appear in `custom` or `mcp`) where each tool has `is_owned: false`, `owner_team_id`, `owner_team_name` and `share_permission` set.

### Unshare Tool

```http
DELETE /api/v1/tools/{tool_id}/share/{team_id} HTTP/1.1
Authorization: Bearer <token>
```

Revokes a team's access to the tool. Response:

```json
{
  "code": 0,
  "data": null,
  "msg": "Tool sharing revoked successfully"
}
```

Only an admin/owner of the tool's owning team can share or unshare it, and only non-private tools can be shared. `permission` is one of `read_only` (view and use the tool) or `read_execute` (also view execution results). Workspace admins use the equivalent `DELETE /api/v1/admin/tools/{tool_id}/share/{team_id}` route under the admin API (gated by `admin:capability:update`), which is documented with the admin API rather than here.

---

## MCP & Database Tool Diagnostics

### Discover MCP Server Tools

Query and dynamically discover tool definitions from a configured MCP server. Requires the `tool:read` permission.

```http
POST /api/v1/tools/mcp/list-tools HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "mcp_config": {
    "transport": "sse",
    "url": "https://mcp.internal.example.com/sse",
    "headers": {}
  }
}
```

Response:

```json
{
  "code": 0,
  "data": {
    "tools": [
      {
        "name": "query_orders",
        "description": "Query the orders database",
        "parameters": { "type": "object", "properties": {} }
      }
    ],
    "server_name": null,
    "server_version": null
  },
  "msg": "success"
}
```

A connection failure returns code `1003` with `msg: "Failed to connect to MCP server"`.

### Test Database Tool Connection

Requires the `tool:create` permission.

```http
POST /api/v1/tools/database/test-connection HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "db_type": "postgresql",
  "host": "db.example.com",
  "port": 5432,
  "database": "analytics",
  "username": "readonly",
  "password": "secret_password"
}
```

Response:

```json
{
  "code": 0,
  "data": {
    "success": true,
    "message": "PostgreSQL connection successful",
    "ping": 1
  },
  "msg": "success"
}
```

A failed connection returns code `1002` (bad request) with the driver's error key as `msg`.

## Related Documentation

- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using tools with agents
- [Tool Management](../../admin-guide/tools/tool-management.md) - Tool admin
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details

---

**Last Updated**: 2026-09-26
