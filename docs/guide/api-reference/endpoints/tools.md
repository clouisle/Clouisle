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
- **Saved MCP servers**: Negotiate capabilities and use tools, resources, resource templates, prompts, completion and live resource subscriptions through a stored MCP definition
- **External identity**: Manage encrypted personal/team/site connections and MCP OAuth
- **Approvals**: Inspect executions, decide approval gates, preview effective policies and answer server-initiated interactions

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
      "requires_config": false,
      "config_fields": [],
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

## Tool Identity and Credentials

The legacy plaintext tool configuration endpoints (`/tools/config`,
`/tools/config/{tool_name}`, and their `/admin/tools/config` equivalents) have
been removed. Tool credentials are no longer readable or writable through a
generic configuration API.

Built-in and custom tools declare an identity policy (`none`, `team_only`,
`personal_only`, `selectable`) plus secret connection fields on their tool
definition. Users attach encrypted personal or team connections through the
tool connection API, and execution resolves the chosen/default connection. The
tool definition response exposes `identity_policy`, `connection_fields`,
`approval_policy` and stable built-in definition identity; no response ever
returns secret values.

Tools whose identity policy is `none` need no connection. A tool that requires
an identity but has no usable connection fails execution explicitly
(`tool_connection_required` or `tool_connection_inactive`) instead of falling
back to a team or global plaintext credential.

Site-wide web search remains the one intentionally site-owned configuration and
uses the dedicated administrator endpoints below.

### Upgrading Legacy Plaintext Configuration

Startup migrates legacy `ToolConfig` rows into encrypted connections and then
deletes each migrated non-web-search row. A legacy global row
(`team_id = NULL`) has no team of its own, so startup fails closed instead of
silently picking one. Assign it explicitly to the team that should own the
credential before upgrading:

```bash
python -m app.core.tool_secret_migration \
  --tool-name <tool_name> --target-team <team-uuid>
```

The command rewrites the row into a team connection and removes the plaintext
row in one transaction; it never prints secret values. Re-run startup after it
succeeds.

## Site-managed Web Search

`GET /api/v1/admin/tools/web-search/config` requires `admin:capability:read`. It returns `default_engine`, provider enable flags, `searxng_base_url`, and configured-secret booleans (`tavily_api_key_configured`, `bocha_api_key_configured`, `deepseek_api_key_configured`, `searxng_auth_token_configured`), never raw secrets.

`PUT /api/v1/admin/tools/web-search/config` requires `admin:capability:update`. Set `default_engine` to `tavily`, `bocha`, `searxng` or `deepseek`, provider enable flags (`tavily_enabled`, `bocha_enabled`, `searxng_enabled`, `deepseek_enabled`), and `searxng_base_url`. Optional secrets are `tavily_api_key`, `bocha_api_key`, `deepseek_api_key` and `searxng_auth_token`. Omitted or null secrets preserve the saved value; empty strings clear it; nonempty strings replace it. Configuration is global and takes no `team_id`. SearXNG Base URL preserves subpaths, rejects query/fragment/userinfo and a `/search` suffix, and is checked against SSRF policy; bearer authentication requires HTTPS. Enable JSON format on the SearXNG instance. No request redirects are followed.

DeepSeek uses the DeepSeek Search API (`POST https://api.deepseek.com/v1/tools/search`) with the saved site key as a Bearer token. `count` follows the requested result limit (1–50), `need_content` is `false`, and each result uses `summary` (or `snippet` when empty) as its text. The endpoint bills successful requests per call.

`POST /api/v1/admin/tools/web-search/test` requires `admin:capability:execute` and accepts `{"query":"Shanghai weather", "engine":"auto"}`. It tests saved site settings and returns normalized search results. `auto` uses the explicit site default; disabled/unconfigured providers fail without fallback.

Existing global search credentials are encrypted during migration. Agent/team credentials are archived encrypted and cease to apply; `legacy_credentials_present` signals that administrator action may be needed. No private account is automatically promoted to a site account.

### Available Engines

`GET /api/v1/tools/web-search/engines` requires `tool:read` and does not require an administrator role. It returns only the provider identifiers the site has enabled so agent and workflow configuration forms can offer valid choices.

```json
{
  "code": 0,
  "data": ["tavily", "searxng"],
  "msg": "success"
}
```

`data` is an ordered array containing only `tavily`, `bocha`, `searxng` and/or `deepseek`. `auto` is never included: clients offer it separately as the explicit site-default routing choice. Credentials, secret-configured flags and the SearXNG base URL are never returned. A site with no configuration, or with every provider disabled, returns `[]`. Availability is informational only — execution still re-validates the selected provider's enable flag and credentials.

## Get Tool Usage

> **Note:** Not implemented / Roadmap. There is no per-tool usage statistics endpoint.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Not found | Tool or tool share does not exist |
| `4004` | Team not found | Target team for a share does not exist |
| `3000` | Permission denied | Insufficient permissions, or private tool access denied |
| `3002` | Not a team member | A requested `team_id` filter refers to a team the user cannot access |
| `1001` | Validation failed | Invalid request data |
| `1002` | Bad request | Private tool cannot be shared, share target is the owning team, or database connection failed |
| `1003` | Internal error | MCP server connection failed |
| `5001` | Already exists | A tool with the same name already exists in the team |
| `5104` | Duplicate name | Tool is already shared with that team |

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

> **Scratch configuration only.** This route accepts a client-supplied
> `mcp_config` so an unsaved server can be probed while editing a tool
> definition. It is scheduled for removal from saved-tool configuration
> dialogs. For a saved MCP tool, use the authenticated saved-server route
> `GET /api/v1/tools/{tool_id}/mcp/tools` above, which resolves the stored
> connection and never accepts credentials from the client.

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

## Saved MCP Server Protocol

These routes operate a **stored** MCP tool definition. The server transport,
URL, command, headers and environment are read from the saved tool; clients
never send `mcp_config`, headers or credentials, and no response returns
connection secrets or server configuration. The tool is always resolved by
`tool_id`, then authorized for the **consuming** `team_id`: the owning team uses
normal tool access, another team must hold an explicit tool share, and private
tools are never shared.

`team_id` is a required query parameter on every route. Identity selection is
optional unless the tool is `selectable`:

| Parameter | Location | Description |
|-----------|----------|-------------|
| `team_id` | query | Consuming team context |
| `connection_mode` | query/body | `personal` or `team`; mandatory for `selectable`, must not contradict an explicit connection |
| `connection_id` | query/body | Explicit stored connection, re-validated against the team and tool |
| `execution_id` | query/body | Resume one previously returned pending execution |

Permissions are `tool:read` for metadata and `tool:execute` for operations,
subscriptions and `prompts/get`/`completion`.

### Operation Envelope

Metadata and operations share one envelope. `status` describes **this HTTP
request**, not the external result:

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "status": "completed",
    "operation": "list:tools",
    "execution_id": null,
    "result": {},
    "pending_approval": null
  }
}
```

These direct capability-browser routes do not trigger execution approval, even
when the MCP definition has an operation approval rule. They still authorize
the actor and consuming team and resolve the selected connection.

MCP operation approval rules apply when the Agent invokes the child tool during
interactive chat. Chat exposes the pending execution through its run interaction
and shows an inline approval card. After approval, the durable worker resumes
the original operation once with its bound parameters and identity. Tool testing,
discovery, workflows and background entrypoints do not request confirmation.

### Operation Namespaces

Approval policies address operations by exact key:

| Operation | Key |
|-----------|-----|
| `tools/call` | `tool:<server tool name>` |
| `resources/read` | `read:resource` |
| Resource subscription | `subscribe:resource` |
| `prompts/get` | `prompt:<prompt name>` |
| Prompt completion | `complete:prompt` |
| Resource-template completion | `complete:resource_template` |
| Discovery | `list:capabilities`, `list:tools`, `list:resources`, `list:resource-templates`, `list:prompts` |

Tool, resource and prompt keys are namespaced so identical server names never
collide. For chat child-tool policies use `tool:<server tool name>`, not the
model-facing `mcp_<server>_<tool>` alias. An Agent's **Require Confirmation**
switch cannot be relaxed by a child's `allow` override.

### Capabilities

```http
GET /api/v1/tools/{tool_id}/mcp/capabilities?team_id={team_id}
```

Returns `Response[McpOperationOut[McpCapabilitiesOut]]`. The result reports the
negotiated protocol version and only the capabilities the server advertised:

```json
{
  "protocol_version": "2026-07-28",
  "server_name": "orders",
  "server_version": "1.2.0",
  "instructions": "…",
  "tools": true,
  "tools_list_changed": false,
  "resources": true,
  "resources_subscribe": false,
  "resources_list_changed": false,
  "resource_templates": true,
  "prompts": true,
  "prompts_list_changed": false,
  "completions": true,
  "logging": false,
  "experimental": false
}
```

Instructions are untrusted server text for display, never system policy. An
operation the server did not advertise fails with `mcp_capability_unavailable`
(`409`) instead of a fabricated success.

### List Tools, Resources, Resource Templates and Prompts

```http
GET /api/v1/tools/{tool_id}/mcp/tools
GET /api/v1/tools/{tool_id}/mcp/resources
GET /api/v1/tools/{tool_id}/mcp/resource-templates
GET /api/v1/tools/{tool_id}/mcp/prompts
```

Shared query parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_items` | `200` | 1–500 maximum items for this request |
| `cursor` | – | Opaque `next_cursor` from a truncated listing |
| `execution_id` | – | Resume a pending metadata approval |

Each returns `Response[McpOperationOut[McpEnumerationOut[…]]]`. The listing
result is bounded and reports truncation explicitly:

```json
{
  "items": [
    {
      "name": "query_orders",
      "title": "Query orders",
      "description": "Query the orders database",
      "parameters": { "type": "object", "properties": {} },
      "output_schema": null,
      "annotations": { "readOnlyHint": true },
      "meta": null
    }
  ],
  "pages_fetched": 1,
  "truncated": false,
  "truncation_reason": null,
  "next_cursor": null,
  "total_items": 1
}
```

`truncation_reason` is one of `max_items`, `max_pages`, `cursor_loop` or
`deadline`. `next_cursor` is resumable with `cursor`; a page cut **mid-page**
reports `next_cursor: null` because MCP has no offset to resume from. Pagination
never silently returns a partial list.

Item shapes:

- Tools: `name`, `title`, `description`, `parameters` (input schema),
  `output_schema`, `annotations`, `meta`.
- Resources: `uri`, `name`, `title`, `description`, `mime_type`, `size`,
  `annotations`, `meta`.
- Resource templates: `uri_template`, `name`, `title`, `description`,
  `mime_type`, `annotations`, `meta`.
- Prompts: `name`, `title`, `description`, `arguments[]`
  (`name`/`description`/`required`), `meta`.

Resource templates are a separate listing; never assume `resources` enumerates
every template-addressed URI.

**Metadata policy.** Discovery defaults to `allow` even when the tool's
operation default is `deny` or `require_approval`. An explicit
`operation_overrides["list:<kind>"]` on the tool policy is honored in full
(allow, deny or require approval); site, team and entrypoint layers still apply
and can never be relaxed. A malformed stored policy is rejected with `409` and
code `6510`, never silently ignored. `max_items` and `cursor` are bound into the
approval parameters, so an approved page cannot be widened or swapped.

### Call a Tool

```http
POST /api/v1/tools/{tool_id}/mcp/tools/call?team_id={team_id}
Content-Type: application/json

{
  "name": "query_orders",
  "arguments": { "status": "open" },
  "connection_mode": "personal"
}
```

The result is `McpToolResultOut`; `success`/`is_error` describe the external
outcome, independently of the envelope's `completed` status:

```json
{
  "success": true,
  "result": { "rows": [] },
  "error": null,
  "is_error": false,
  "content": [{ "type": "text", "text": "…" }],
  "structured_content": { "rows": [] },
  "input_required": null
}
```

`content` preserves text, media, resource links and resources; `structured_content`
and `input_required` are preserved rather than flattened. A result that exceeds
the content budget returns a failure result, not a truncated payload.

### Read a Resource

```http
POST /api/v1/tools/{tool_id}/mcp/resources/read?team_id={team_id}
Content-Type: application/json

{ "uri": "file:///reports/today.md" }
```

The URI is forwarded verbatim to the MCP server; the backend performs no local
download or URI rewriting. Result: `McpResourceContentsOut[]` with `uri`,
`mime_type`, `text` or `blob`, and `meta`. Treat contents as untrusted context.
Content limits are 1,000,000 bytes per block and 4,000,000 bytes total by
default; exceeding them fails explicitly.

### Get a Prompt

```http
POST /api/v1/tools/{tool_id}/mcp/prompts/get?team_id={team_id}
Content-Type: application/json

{ "name": "summarize", "arguments": { "document": "…" } }
```

Result: `messages[]` (`role`, `content` block), `description`, `meta`. Prompt
messages are untrusted server content: preview them and never treat them as
system instructions automatically.

### Complete an Argument

```http
POST /api/v1/tools/{tool_id}/mcp/completion?team_id={team_id}
Content-Type: application/json

{
  "reference": { "kind": "prompt", "name": "summarize" },
  "argument_name": "document",
  "argument_value": "rep",
  "context_arguments": { "tone": "brief" }
}
```

`reference.kind` is `prompt` (requires `name`, forbids `uri`) or
`resource_template` (requires `uri`, forbids `name`). Result: `values`, `total`,
`has_more`. Completion uses the same identity, approval and content limits as
other protocol operations.

### Subscribe to Resource Updates (SSE)

```http
GET /api/v1/tools/{tool_id}/mcp/resources/subscribe?team_id={team_id}&uri=file:///reports/today.md
Accept: text/event-stream
```

Authorization and connection resolution run first under operation
`subscribe:resource`. This direct capability-browser route does not request
execution approval. Requires `tool:execute`.

Events:

```
event: subscription_opened
data: {"subscription_id":"…","tool_id":"…","team_id":"…","uri":"…","connection_id":"…","connection_scope":"user","account_label":"…","expires_at":"…"}

event: resource_updated
data: {"subscription_id":"…","uri":"…","sequence":1,"received_at":"…"}

event: subscription_closed
data: {"subscription_id":"…","reason":"ttl_expired"}
```

Keep-alive comments (`: keep-alive`) are sent on the heartbeat interval. Close
reasons are `client_disconnected`, `ttl_expired`, `connection_lost` and
`capability_unavailable`. Restrictions:

- The subscription is **request-scoped**: there is no background listener,
  registry, daemon or durable subscription. Process death or disconnects end it;
  reconnecting creates a new subscription.
- Only explicitly configured identities may subscribe; each request is bound to
  one URI and one connection.
- At most 100 pending updates are queued; a slow client drops the oldest update
  rather than blocking the protocol loop.
- The stream lifetime is bounded by `MCP_SUBSCRIPTION_TTL_SECONDS` (default
  `300`, range 10–3600).
- Unsubscribe is read-side cleanup and never enters the approval/outcome
  machinery. Missed updates are not replayed.

## Tool Connections

A tool definition declares an identity policy (`none`, `team_only`,
`personal_only`, `selectable`) and secret field names. Users attach encrypted
connections; execution resolves and re-validates one connection every time.
Connection scopes are:

| Scope | Owner | Use |
|-------|-------|-----|
| `user` | Personal user | The owner's external account |
| `team` | Team | Shared team service account |
| `site` | Site administrator | Global account, never overridable by tool editors |

Every connection response is secret-safe: only `secret_fields` names,
`account_label`, `secret_version` and lifecycle metadata are returned. Config
values are write-only.

### Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/v1/tools/{tool_id}/connections?team_id=` | List visible connections for this tool (`include_site`, `include_revoked`) |
| `POST` | `/api/v1/tools/{tool_id}/connections` | Create a connection for the path tool |
| `GET` | `/api/v1/tool-connections?team_id=&tool_id=&builtin_tool_key=` | Generic listing (`include_site`, `include_revoked`) |
| `POST` | `/api/v1/tool-connections` | Create by `tool_id` or `builtin_tool_key` |
| `GET` | `/api/v1/tool-connections/{connection_id}` | Read one (`team_id` required for a site connection) |
| `PATCH` | `/api/v1/tool-connections/{connection_id}` | Partial update |
| `DELETE` | `/api/v1/tool-connections/{connection_id}?reason=` | Revoke (terminal, no hard delete) |

Creation body (`ToolConnectionForToolCreate` omits `tool_id`):

```json
{
  "team_id": "…",
  "scope": "user",
  "name": "Work account",
  "account_label": "me@example.com",
  "config": { "api_key": "…" },
  "is_default": true
}
```

`config` may only contain fields declared by the tool definition and is
encrypted with the deployment key. `is_default` selects the default connection
for one scope/service/owner. `ToolConnectionCreate` additionally accepts
`tool_id` **or** `builtin_tool_key` (exactly one).

Update body (partial; secret semantics are explicit):

```json
{
  "name": "Renamed",
  "account_label": "…",
  "status": "active",
  "config_set": { "api_key": "new" },
  "config_remove": ["old_field"],
  "is_default": true,
  "expected_secret_version": 3
}
```

`config_set: null` retains existing values; `config_remove` names fields to
delete; the two collections cannot overlap. `expected_secret_version` is an
optimistic concurrency guard (`409` on mismatch).

A saved Agent tool binding or workflow tool-node binding is the authorization to
use a connection. Selecting a personal connection requires ownership; the
binding is validated when the definition is created, updated, duplicated,
restored or imported. Authorized shared executions reuse the saved identity,
while execution still rejects revoked connections, team mismatches and direct
client-supplied ids for someone else's personal connection. Credentials are
never returned.

## MCP OAuth

MCP OAuth is configured on the saved tool under `mcp_config.oauth`
(`McpOAuthConfig`): optional `authorization_server`, `resource`, `scopes`,
`client_id`, `use_dcr`, `token_endpoint_auth_method`,
`extra_authorization_params` and `extra_token_params`. Client secrets are
write-only provider inputs, never part of the stored public configuration.
When `oauth` is configured, execution requires a resolved connection and adds a
fresh `Authorization: Bearer …` header; an existing case-insensitive
`authorization` header is replaced.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/tool-connections/{connection_id}/oauth/start` | Start a PKCE authorization flow |
| `GET` | `/api/v1/tool-connections/{connection_id}/oauth?team_id=` | Secret-free OAuth status |
| `POST` | `/api/v1/tool-connections/{connection_id}/oauth/disconnect` | Clear local tokens; best-effort remote revoke |
| `GET` | `/api/v1/tool-oauth/callback` | Provider/browser callback (not a client API) |

Start body (optional; `{}` is valid):

```json
{
  "redirect_path": "/app/capabilities",
  "client_secret": "…"
}
```

`redirect_path` must be an allowlisted relative frontend path.
`client_secret` is write-only, requires tool write access and is stored
encrypted; it is never returned. Response:

```json
{
  "authorization_url": "https://auth.example/authorize?…",
  "state": "…",
  "expires_at": "2026-10-26T12:00:00Z",
  "provider_kind": "mcp",
  "connection_id": "…"
}
```

Status response (`OAuthConnectionStatusOut`) reports `provider_kind`,
`provider_configured`, `authorized`, `needs_reauth`, `status`, `account_label`,
`scopes`, `expires_at` and `client_id`; never tokens. Disconnect response
(`OAuthDisconnectOut`): `local_revoked`, `remote_revocation`,
`needs_reauth`.

The flow uses PKCE S256, one-time state bound to the logged-in user and
connection, exact callback matching, minimal scopes and refresh rotation.
Authorization-server discovery, redirect and token endpoints are subject to the
central SSRF policy; HTTPS is required. `invalid_grant` marks the connection
`reauth_required`. Missing provider support or an unreachable provider fails
explicitly; it is never treated as authorized. OAuth interoperability is
portable across compliant servers but is not a guarantee for any specific
third-party provider.

## Tool Approvals and Executions

Approval policy is composed from mandatory site, team and entrypoint layers
plus the tool's own policy. `deny` wins, approval requirements union, and a
lower layer can never relax a higher mandatory layer. Each tool policy has a
default decision (`allow`, `deny`, `require_approval`), gates and
`operation_overrides` keyed by the exact operation namespace. A decision applies
to one immutable execution: changing parameters, identity or definition
invalidates it.

Gates: `caller` (the initiating user, interactive entrypoints only), `user`
(explicit user IDs) and `team_role` (roles; self-approval only when
`allow_self_approval` is true). Caller gates additionally require the approver
to be a member of the execution team; a superuser is not an implicit approver.

### Approvals

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tool-approvals?page=&page_size=` | Pending gates whose audience includes the caller |
| `GET` | `/api/v1/tool-approvals/{request_id}` | One visible gate |
| `POST` | `/api/v1/tool-approvals/{request_id}/decision` | Approve or reject; idempotent |

Decision body:

```json
{
  "decision": "approve",
  "reason": "checked the order id",
  "idempotency_key": "decision-2026-10-26-0001"
}
```

`decision` is `approve` or `reject`; `idempotency_key` (1–128 chars) makes
retries safe. The response includes the immutable decision, `execution_status`
and `remaining_approvals`. The decision never edits the bound parameters.
Rejection, expiry, revocation and stopped runs are terminal and cannot become
approvals.

`ToolApprovalRequestOut` returns `id`, `execution_id`, `stage_index`,
`stage_key`, `gate_kind`, `approver_user_ids`, `approver_roles`,
`allow_self_approval`, `masked_display`, `status`, `expires_at`,
`resolved_at` and `created_at`. `masked_display` is already redacted.

### Executions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tool-executions?status=&tool_id=&run_kind=&run_id=&page=&page_size=` | Executions initiated by the caller |
| `GET` | `/api/v1/tool-executions/{execution_id}` | One visible execution |

`ToolExecutionOut` exposes the tool/definition version, operation, team,
entrypoint, run references, connection binding metadata,
`parameters_preview` (redacted), `parameters_digest`, `policy_hash`, `status`,
`cancel_reason`, `result_ref`, `error_code` and timestamps. Ciphertext, claim
tokens and secrets never appear.

Statuses: `awaiting_approval`, `ready`, `executing`, `succeeded`, `failed`,
`outcome_unknown`, `cancelled`. Cancel reasons: `rejected`, `expired`,
`revoked`, `cancelled`, `binding_changed`, `run_stopped`, `policy_denied`.

**No automatic retry of uncertain outcomes.** Once an external side effect was
sent, a crash or lost connection leaves `outcome_unknown`; the platform does not
silently retry. Inspect the external system, then start a **new** execution.
`failed` and `outcome_unknown` are not interchangeable, and approval decisions
never imply the side effect happened.

### Policy Layers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tool-approval-policies?team_id=&scope=&entrypoint_kind=&entrypoint_id=&tool_id=` | List layers (team view includes read-only site baseline) |
| `GET` | `/api/v1/tool-approval-policies/effective?team_id=&tool_id=&operation=&entrypoint_kind=&entrypoint_id=&entrypoint_interactive=` | Server-composed effective decision |
| `POST` | `/api/v1/tool-approval-policies` | Create a site/team/entrypoint layer |
| `PUT` | `/api/v1/tool-approval-policies/{policy_id}` | Replace policy under optimistic `expected_version` |
| `DELETE` | `/api/v1/tool-approval-policies/{policy_id}` | Delete a layer |

Create body: `scope` (`site`, `team`, `entrypoint`) plus `team_id` for team,
and `team_id`/`entrypoint_kind`/`entrypoint_id` for entrypoint; optional
`tool_id`; `policy` is the full policy object. Site layers require site
administration. The effective preview returns `decision`, `gates`, `sources`,
`policy_hash`, `configuration_error`, `entrypoint_interactive` and layer
summaries with editability; clients must not merge layers themselves. Missing
approval audience/configuration yields `6510` rather than implicit consent.

### Server-initiated Interactions

MCP sampling and elicitation requests become durable rows; only the explicit
audience can see or answer them.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/run-interactions?kind=&status=&run_id=&page=&page_size=` | Interactions visible to the caller |
| `GET` | `/api/v1/run-interactions/{interaction_id}` | One visible interaction |
| `POST` | `/api/v1/run-interactions/{interaction_id}/response` | Accept, decline or cancel |

Response body: `action` (`accept`, `decline`, `cancel`), optional `content`
(form elicitation accept only, schema-validated) and `idempotency_key`
(8–100 chars). Sampling is never auto-answered; approval uses the existing
model budget with no MCP connection and no tool access. Credential-like fields
are refused. URL elicitation only accepts exact configured hosts. Expiry or
session loss marks the interaction `connection_lost`; the outer MCP call is not
replayed.

## Related Documentation

- [MCP Connections and Approvals](../../admin-guide/tools/mcp-connections-and-approvals.md) - Operator overview of identities, OAuth, approvals and subscriptions
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using tools with agents
- [Tool Management](../../admin-guide/tools/tool-management.md) - Tool admin
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details

---

**Last Updated**: 2026-10-26
