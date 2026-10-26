# Tool Management

This guide covers how to manage tools and integrations as an administrator.

## Overview

As an administrator, you can:

- **View all tools**: Access all available tools
- **Add tools**: Configure new tools
- **Update tools**: Modify tool settings
- **Test tools**: Verify tool functionality
- **Share tools**: Share custom tools with other teams

## Accessing Tool Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Capabilities** and open the **Tools** tab (route `/capabilities`); there is no separate Tools sidebar item
3. View tool management interface

### Tool List View

The tool list shows:

- **Tool name**
- **Type** (Builtin, Custom — HTTP, Code, or Database, MCP)
- **Category** (Time, Math, Search, Web, File, Code, Sandbox, API, Data, etc.)
- **Status** (Enabled / Disabled)

**Filters:**
- Type
- Category
- Status

**Search:**
- Search by tool name or description

## Built-in Tools

### Available Built-in Tools

**Time Tools:**
- **Get Current Time**: Get current time in a timezone
- **Format Datetime**: Format date/time strings

**Math Tools:**
- **Calculate**: Evaluate mathematical expressions
- **Unit Convert**: Convert between units

**Search / Web Tools:**
- **Web Search**: Search the web (requires Tavily API key)
- **Fetch Webpage**: Fetch and extract webpage content
- **RSS Feed Reader**: Fetch and parse RSS or Atom feeds into a structured article list

**File Tools:**
- **MarkItDown**: Parse PDF, Word, Excel, PowerPoint, and text files
**Generation Tools:**
- **Generate Image**: Generate images
- **Generate Video**: Generate videos

**Sandbox Tools:**
- **Bash**: Run commands in the code sandbox
- **Read / Write / Edit**: File operations inside the sandbox workspace
- **Artifact**: Collect files from the sandbox workspace

> **Note:** Knowledge base retrieval is not a built-in tool; it is configured per agent as RAG.
>
> **Note:** Image generation, video generation, and interactive questions (`ask_user`) are not shown in this catalog. They are enabled per agent through their dedicated feature switches (`enable_image_generation`, `enable_video_generation`, `enable_user_input_request`) and injected automatically — not attachable through `tools_config`.

### Configure Built-in Tools

**Web Search Tool:**
```yaml
Tool: Web Search
Type: Builtin
Category: Search
Status: Enabled

Site Configuration:
  default_engine: tavily
  tavily_enabled: true
  bocha_enabled: false
  deepseek_enabled: false
  tavily_api_key: ... # write-only
```

Site administrators manage search from the **Configure search** button on the platform **Capabilities** page, or from **Capabilities → Tools → Web Search → Configure** in the dashboard, without selecting a team. Enable a provider and explicitly choose the site default. Secrets are encrypted; the form shows whether a key is configured but never reads it back. Leave a secret unchanged to preserve it, replace it to rotate, or clear it explicitly. Agents only choose an enabled provider or inherit the site default; they cannot store search keys or override endpoints. Missing/disabled providers and provider failures are explicit errors, with no fallback to another account.

Agent orchestration and workflow `web_search` tool nodes share an enabled-only engine selector. **Auto** inherits the site default. Disabled providers are not offered; an existing saved selection is retained rather than silently changed. Execution rechecks the site configuration, so disabling a provider also blocks previously saved selections.

**Update Configuration:**
1. Open Web Search configuration in the administrator dashboard.
2. Enable Tavily, Bocha or DeepSeek and enter its API key, or enable the administrator-configured SearXNG instance.
3. Choose the site default and save changes.
4. Test the saved configuration with a representative query and inspect relevance, not merely nonempty results.

> **Note:** Tavily, Bocha and DeepSeek require API credentials. SearXNG requires a configured instance, not a random public fallback. There are no per-tool limits (calls per day/agent/minute) or timeout settings for built-in tools.

On upgrade, existing global search keys remain global and are encrypted. Legacy Agent/team keys are archived encrypted, not activated site-wide. Administrators must configure the intended shared account; the configuration response signals archived credentials without exposing them. `TAVILY_API_KEY` is imported only on the first migration when no global key exists, not read on each request.

#### DeepSeek Search

Enable DeepSeek and paste a DeepSeek API key. Clouisle calls DeepSeek's own Search API (`https://api.deepseek.com/v1/tools/search`) with that key; it does not route searches through a DeepSeek chat model. Searches are billed by DeepSeek per successful request, independently of the number of returned results, and share the account-level Search QPS limit. Result text uses DeepSeek's long `summary` so the model receives useful snippets without downloading full pages.

#### SearXNG instance

In the same site dialog, enter the instance root **Base URL**, for example `https://search.example.com` or `https://example.com/searxng/`. The server appends `/search`, preserving the reverse-proxy prefix. Do not include `/search`, query parameters, fragments or embedded username/password. An optional gateway bearer token is stored encrypted and requires HTTPS; no token is needed for an unauthenticated instance.

Enable JSON output in the instance's `settings.yml`:

```yaml
search:
  formats:
    - html
    - json
```

The instance must be reachable from API and task-worker processes that execute searches. With SSRF protection enabled (the default), private IPs/internal hostnames must be explicitly approved through the SSRF allowed-target settings; cloud metadata targets remain blocked. Use a resolvable internal FQDN or explicitly allowlist the private IP; a bare Docker service name cannot be added as a hostname rule by the existing allowlist validator. Disabling **Enable SSRF protection** in Security settings removes destination restrictions, including cloud metadata blocking; this is unsafe for untrusted users. Search requests recheck the current policy and do not follow redirects.

SearXNG uses a 30-second HTTPX timeout for connection/read/write/pool operations, not a strict total-duration deadline. Requests are not retried and do not fall back to another provider.

The tool test page exposes a search-engine selector for `web_search`; it lists only enabled providers plus the site default and submits the choice as `search_engine`.

Save first, then test with `上海天气 今天`, a multiword technical query and a `site:` query. Inspect result relevance as well as connectivity. A 403 may mean JSON output is disabled or the gateway rejected access. SearXNG engine availability/relevance depends on the instance's upstream engines; Clouisle does not promise that every query/operator is supported.


## Custom Tools

### Create Custom Tool

1. Click **Add Tool** button
2. Select **Custom Tool**
3. Fill in tool details:
   - **Name**: Tool display name
   - **Description**: Tool purpose
   - **Category**: Tool category
   - **Icon**: Tool icon

4. Configure tool:
   - **Endpoint**: API endpoint URL
   - **Method**: HTTP method (GET, POST, etc.)
   - **Authentication**: Auth method
   - **Headers**: Custom headers
   - **Parameters**: Input parameters
   - **Response**: Response format

5. Test tool
6. Save tool

**Custom Tool Example:**
```yaml
Name: CRM Lookup
Description: Look up customer information in CRM
Category: Data
Type: Custom

Endpoint Configuration:
  URL: https://api.crm.example.com/customers
  Method: GET
  Authentication: API Key
  API Key Header: X-API-Key
  API Key: crm_...
  Query Parameters:
    customer_id: "{{customer_id}}"
  Timeout: 30 seconds

Input Parameters:
  - name: customer_id
    type: string
    required: true
    description: Customer ID to lookup

Response Format:
  type: json
  schema:
    customer_id: string
    name: string
    email: string
    phone: string
    status: string

Example Request:
  GET https://api.crm.example.com/customers?customer_id=12345
  Headers:
    X-API-Key: crm_...

Example Response:
  {
    "customer_id": "12345",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-0123",
    "status": "active"
  }
```
> **Important:** Custom HTTP tools do not support `{{variable}}` substitution in the URL path or URL string. Keep the endpoint URL static and pass variables through `Query Parameters`, request `Headers`, or `Body Template` fields.

> **Note:** A custom tool can also be a **Database** tool (`type: database`) that runs a SQL query against a configured connection (PostgreSQL, MySQL, Redis, or MongoDB), configured with host/port/database/credentials, a query timeout, and a maximum row limit. Verify connectivity with `POST /api/v1/tools/database/test-connection` (requires `tool:create`).

### Custom Tool with POST

**Create Record Tool:**
```yaml
Name: Create Support Ticket
Description: Create a support ticket in ticketing system
Category: Communication
Type: Custom

Endpoint Configuration:
  URL: https://api.tickets.example.com/tickets
  Method: POST
  Authentication: Bearer Token
  Token: Bearer tk_...
  Content-Type: application/json
  Timeout: 30 seconds

Input Parameters:
  - name: title
    type: string
    required: true
    description: Ticket title

  - name: description
    type: string
    required: true
    description: Ticket description

  - name: priority
    type: enum
    required: false
    default: medium
    options: [low, medium, high, urgent]
    description: Ticket priority

  - name: assignee
    type: string
    required: false
    description: Assignee email

Response Format:
  type: json
  schema:
    ticket_id: string
    status: string
    created_at: string

Example Request:
  POST https://api.tickets.example.com/tickets
  Headers:
    Authorization: Bearer tk_...
    Content-Type: application/json
  Body:
    {
      "title": "Customer inquiry",
      "description": "Customer asking about pricing",
      "priority": "medium",
      "assignee": "support@example.com"
    }

Example Response:
  {
    "ticket_id": "TKT-12345",
    "status": "open",
    "created_at": "2026-02-11T14:30:00Z"
  }
```

### Edit Custom Tool

1. Select custom tool
2. Click **Edit**
3. Modify:
   - Tool details
   - Endpoint configuration
   - Parameters
   - Response format
4. Test tool
5. Save changes

### Delete Custom Tool

1. Select custom tool
2. Click **Delete**
3. Review impact:
   - Agents using this tool
   - Workflows using this tool
4. Confirm deletion

## Integration Tools

### Available Integrations

> **Note:** Not implemented / Roadmap. There is no "integration" tool type (Salesforce, HubSpot, Slack apps, GitHub, Jira, etc.). Tool types are limited to `builtin`, `custom` (HTTP, Code, or Database), and `mcp` (MCP server tools). External services are integrated either as HTTP custom tools, MCP servers, or through the Email and generic Webhook notification settings in Site Settings.

## Testing Tools

### Test Tool

1. Select tool
2. Click **Test** button
3. Enter test parameters
4. Click **Run Test**

**Test Results:**
```yaml
Tool: Web Search
Test Parameters:
  query: "artificial intelligence"
  max_results: 5

Status: Success
Response Time: 1.2 seconds
Results:
  - title: "Artificial Intelligence - Wikipedia"
    url: "https://en.wikipedia.org/wiki/Artificial_intelligence"
    snippet: "Artificial intelligence (AI) is intelligence..."

  - title: "What is AI? | IBM"
    url: "https://www.ibm.com/topics/artificial-intelligence"
    snippet: "Artificial intelligence leverages computers..."

  [3 more results]

Metadata:
  total_results: 5
  search_time: 0.8s
  api_calls: 1
```

### Test Custom Tool

**Test CRM Lookup:**
```yaml
Tool: CRM Lookup
Test Parameters:
  customer_id: "12345"

Status: Success
Response Time: 0.5 seconds
Response:
  {
    "customer_id": "12345",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-0123",
    "status": "active"
  }

Validation: Passed
  ✓ Response format matches schema
  ✓ All required fields present
  ✓ Data types correct
```

## Monitoring Tool Usage

### Usage Statistics

> **Note:** Not implemented / Roadmap. There is no tool usage tracking UI or API (calls, success rate, response time, error breakdowns, top users/agents, per-team reports). The tool test endpoints (`POST /api/v1/admin/tools/test`, `/execute-code`) are the only way to exercise tools from admin; runtime usage is not aggregated.

## Tool Limits

### Set Tool Limits

> **Note:** Not implemented / Roadmap. There are no global, tool-specific, per-user, per-team, or per-agent call limits (calls per minute/day, concurrency, timeout) for tools, and no rate-limit responses with `Retry-After`.

### Rate Limiting

> **Note:** Not implemented / Roadmap. Tools are not rate limited.

## Tool Status Management

### Tool Statuses

**Enabled:**
- Tool is operational
- Available for use
- Appears in tool selection

**Disabled:**
- Tool is disabled
- Cannot be used
- Hidden from users

> **Note:** Tools have a single enabled/disabled state. There are no `testing` or `deprecated` statuses. Custom tools can be toggled via `POST /api/v1/admin/tools/{tool_id}/toggle`.

### Change Tool Status

**Enable Tool:**
```bash
1. Select tool
2. Set "Enabled" to on
3. Confirm
```

**Disable Tool:**
```bash
1. Select tool
2. Set "Enabled" to off
3. Confirm
```

## Troubleshooting

### Tool Call Failed

**Symptoms:**
- Tool returns error
- Timeout
- Invalid response

**Solutions:**

1. **Check tool configuration:**
   - Verify credentials
   - Check endpoint URL
   - Test connectivity

2. **Check audit logs:**
   - Review audit log entries for the tool's team
   - Check application logs for the tool execution

3. **Common errors:**
   - **Authentication failed**: Invalid credentials
   - **Timeout**: Increase timeout or check endpoint
   - **Rate limit**: Wait or increase limit
   - **Invalid parameters**: Check parameter format

4. **Test tool:**
   ```bash
   Select tool
   Click "Test"
   Review test results
   ```

### High Tool Costs

**Symptoms:**
- Unexpected API costs

**Solutions:**

1. **Review usage:**
   - Identify which agents use the tool and how often
2. **Optimize usage:**
   - Cache results
   - Use cheaper alternatives
   - Optimize tool calls

> **Note:** Not implemented / Roadmap: cost dashboards and cost alerts are not available.

### Slow Tool Response

**Symptoms:**
- Long response times
- Timeouts

**Solutions:**

1. **Test the tool:**
   - Use the tool test panel to measure response time
2. **Optimize tool:**
   - Increase timeout
   - Reduce data transfer
   - Optimize endpoint
3. **Check external service:**
   - Review service status
   - Check for outages
   - Contact support

## Best Practices

### Tool Configuration

**✅ Do:**
- Test tools before enabling
- Rotate credentials regularly
- Document tool purposes
- Keep tools updated
- Use error handling

**❌ Don't:**
- Enable untested tools
- Use static credentials forever
- Skip documentation
- Ignore errors

### Security

**✅ Do:**
- Use secure authentication
- Rotate API keys regularly
- Restrict tool access
- Enable audit logging
- Monitor for abuse
- Use HTTPS only
- Validate responses

**❌ Don't:**
- Use weak authentication
- Use static API keys forever
- Allow unrestricted access
- Disable audit logs
- Ignore suspicious activity
- Allow HTTP connections
- Trust responses blindly

### Performance

**✅ Do:**
- Set appropriate timeouts
- Use caching where possible
- Monitor response times
- Optimize tool calls
- Use async processing
- Handle errors gracefully

**❌ Don't:**
- Use very long timeouts
- Skip caching
- Ignore performance metrics
- Make unnecessary calls
- Use synchronous processing
- Ignore errors

## API Access

### Manage Tools via API

Admin tool endpoints live under `/api/v1/admin/tools` and require `admin:capability:*` permissions.

**List Tools:**
```python
# List tools (admin)
tools = api.get("/api/v1/admin/tools", params={"page": 1, "page_size": 20})

# Get tool filter options
filters = api.get("/api/v1/admin/tools/filters")
```

**Test Tool:**
```python
# Test a tool (builtin, custom, or MCP)
result = api.post("/api/v1/admin/tools/test", json={
    "tool_name": "web_search",
    "arguments": {"query": "artificial intelligence", "max_results": 5}
})

# Execute code directly
code_result = api.post("/api/v1/admin/tools/execute-code", json={
    "language": "python",
    "code": "return params['a'] + params['b']",
    "params": {"a": 1, "b": 2}
})
```

> **Note:** `POST /api/v1/tools/web_search/call` and `GET /api/v1/tools/web_search/usage` do not exist. Search uses dedicated `GET/PUT /api/v1/admin/tools/web-search/config` and `POST /api/v1/admin/tools/web-search/test` endpoints; generic config APIs reject `web_search`.

## Related Documentation

- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using tools with agents
- [Workflow Nodes](../../user-guide/workflows/workflow-nodes.md) - Tool nodes in workflows
- [API Reference](../../api-reference/endpoints/tools.md) - Tools API
- [Security Checklist](../../operations/security-checklist.md) - Security guidance

---

**Last Updated**: 2026-02-11
