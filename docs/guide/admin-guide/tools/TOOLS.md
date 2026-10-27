# Tools Guide

This guide explains how to use the Tools feature in Clouisle to extend Agent capabilities.

---

## Table of Contents

- [Overview](#overview)
- [Tool Types](#tool-types)
  - [Builtin Tools](#builtin-tools)
  - [HTTP Tools](#http-tools)
  - [Code Tools](#code-tools)
  - [Database Tools](#database-tools)
  - [MCP Tools](#mcp-tools)
- [Code Sandbox](#code-sandbox)
  - [Available Modules](#available-modules)
  - [Writing Code](#writing-code)
  - [Limitations](#limitations)
- [Creating Tools](#creating-tools)
- [Testing Tools](#testing-tools)
- [Using Tools in Agents](#using-tools-in-agents)

---

## Overview

Tools allow Agents to perform actions beyond text generation, such as:

- Searching the web
- Calling external APIs
- Processing data with custom code
- Interacting with databases and file systems (via MCP)

## Tool Types

- [Builtin Tools](#builtin-tools)
- [Memory Tools](#memory-tools)
- [HTTP Tools](#http-tools)
- [Code Tools](#code-tools)
- [Database Tools](#database-tools)
- [MCP Tools](#mcp-tools)

### Builtin Tools

System-provided tools that are ready to use without configuration.

| Tool | Description | Category |
|------|-------------|----------|
| `get_current_time` | Get current time in specified timezone | Time |
| `format_datetime` | Format date/time strings | Time |
| `calculate` | Evaluate mathematical expressions | Math |
| `unit_convert` | Convert between units | Math |
| `web_search` | Site-managed web search (Tavily, Bocha or DeepSeek API key, or configured SearXNG instance) | Search |
| `fetch_webpage` | Fetch and extract webpage content | Web |
| `rss_feed_reader` | Fetch and parse RSS or Atom feeds into a structured article list | Web |

### Memory Tools

When an Agent has memory enabled, the model can use read and write tools for the user's memory graph. Read tools remain available when automatic extraction is disabled; write tools are gated by the Agent's memory configuration.

| Tool | Purpose | Limits and behavior |
|------|---------|---------------------|
| `search_memory` | Find relevant user memory entities | Supports `top_k` (clamped to 1-10), an optional time window, and an entity-type filter |
| `get_memory_subgraph` | Read relationships connected to search results | Accepts at most 5 seed IDs or exact names, traverses 1-3 levels, follows `incoming`, `outgoing`, or `both` directions (default `both`), and can filter relation types |

Use `search_memory` first, then `get_memory_subgraph` only when the answer depends on relationships. Treat returned relationships as the source of truth; do not infer edges that were not returned.

### HTTP Tools

Call external REST APIs with configurable requests.

**Features:**
- Support GET, POST, PUT, PATCH, DELETE methods
- Variable substitution in the URL path or URL string, query parameters, headers, and request body templates; candidates are tool parameters and declared connection fields
- URL templates are rendered before the request is sent and the final URL passes SSRF validation
- Secure credential storage
- Response path extraction

**Example Configuration:**

```json
{
  "method": "POST",
  "url": "https://api.example.com/translate",
  "headers": {
    "Authorization": "Bearer {{api_key}}",
    "Content-Type": "application/json"
  },
  "body_template": "{\"text\": \"{{input}}\", \"target\": \"{{language}}\"}",
  "timeout": 30,
  "response_path": "data.translation"
}
```
> **Important:** The URL field supports `{{variable}}` placeholders. They are rendered from tool parameters and declared connection fields before the request is sent, and the final rendered URL is validated against SSRF protections. Every placeholder must resolve to a value; a missing value fails the call instead of silently dropping the path or query segment. Values are inserted verbatim, so URL-encode path/query values that may contain reserved characters. The editor suggests available names after typing `{{`.

### Code Tools

Execute custom JavaScript or Python code in a secure sandbox.

**Features:**
- JavaScript (Node.js) and Python support
- Access to standard library modules
- Parameter injection via `params` object
- Selected personal/team connection fields via the per-execution `credentials` mapping
- Console/print output capture
- 30-second timeout protection

The code editor's **Run** is a connectionless snippet preview. Save the tool and use **Test** in the capabilities list to select a connection and verify credential-dependent behavior. Code can intentionally return or print the credentials it receives; outputs are not automatically scrubbed.

### Database Tools

Use the builtin `postgresql_query`, `mysql_query`, `redis_query`, or `mongodb_query` to inspect schemas and run read-only operations. Select a personal or team connection for each Agent attachment or workflow node; no custom database tool is created.

Database addresses, accounts, query timeouts and row limits are encrypted connection fields, not model arguments or tool-definition settings. Internal targets must be allowed by the site's network policy.

### MCP Tools

Connect to external tool servers via [Model Context Protocol](https://modelcontextprotocol.io/).

For identity connections, OAuth, approvals and live resource subscriptions, see
[MCP Connections and Approvals](mcp-connections-and-approvals.md).

MCP HTTP/SSE header values and stdio environment values accept `{{field_name}}` references to declared connection fields. Type `{{` to select a field name; the editor never displays its stored value. URL, command and arguments do not support these references. Store actual credentials in a connection, not in the tool definition.

**Supported Transports:**

| Transport | Description | Use Case |
|-----------|-------------|----------|
| `stdio` | Launch subprocess, communicate via stdin/stdout | Local MCP servers |
| `sse` | Server-Sent Events | Remote servers |
| `http` | Streamable HTTP | Remote servers |

**Popular MCP Servers:**

| Server | Command | Description |
|--------|---------|-------------|
| Filesystem | `npx -y @modelcontextprotocol/server-filesystem /path` | File operations |
| SQLite | `uvx mcp-server-sqlite --db-path /path/db.sqlite` | Database queries |
| GitHub | `npx -y @modelcontextprotocol/server-github` | GitHub API access |
| Slack | `npx -y @modelcontextprotocol/server-slack` | Slack integration |

---

## Code Sandbox

The code sandbox provides a secure environment for executing custom code.

### Available Modules

#### Python

All Python standard library modules are available:

| Module | Purpose |
|--------|---------|
| `json` | JSON parsing/serialization |
| `re` | Regular expressions |
| `math` | Mathematical functions |
| `datetime` | Date and time handling |
| `collections` | Data structures (Counter, defaultdict, etc.) |
| `itertools` | Iterator utilities |
| `functools` | Function utilities |
| `random` | Random number generation |
| `string` | String constants and templates |
| `base64` | Base64 encoding/decoding |
| `hashlib` | Hash algorithms (MD5, SHA, etc.) |
| `urllib.parse` | URL parsing |
| `csv` | CSV file handling |
| `uuid` | UUID generation |
| `statistics` | Statistical calculations |
| `decimal` | Precise decimal arithmetic |
| `html` | HTML escaping |
| `textwrap` | Text wrapping |
| `difflib` | Difference comparison |

**Not Available by default:** `requests`, `numpy`, `pandas`, `httpx`, or other third-party packages. However, code tools may declare third-party dependencies (`python_packages` for Python, `js_packages` for JavaScript), which the sandbox installs into an isolated, cached environment. Each package must be pinned to an exact version (e.g. `requests==2.32.3`), and custom package index / npm registry URLs must be plain `http(s)://` URLs without embedded credentials.

#### JavaScript

Built-in objects (no require needed):

| Object | Purpose |
|--------|---------|
| `JSON` | JSON parsing/serialization |
| `Math` | Mathematical functions |
| `Date` | Date and time handling |
| `Array` | Array methods |
| `Object` | Object methods |
| `String` | String methods |
| `RegExp` | Regular expressions |
| `Promise` | Async handling |
| `Map` / `Set` | Collection data structures |
| `Buffer` | Binary data handling |

Node.js core modules (require needed):

| Module | Purpose |
|--------|---------|
| `crypto` | Cryptographic functions |
| `url` | URL parsing |
| `path` | Path manipulation |
| `querystring` | Query string parsing |
| `util` | Utility functions |
| `http` / `https` | HTTP requests |

**Not available by default:** `axios`, `lodash`, `moment`, `dayjs`, or other npm packages. As with Python, `js_packages` may list npm packages pinned to an exact version (e.g. `axios@1.7.9`), which are installed into an isolated, cached environment for the execution.

### Writing Code

#### Basic Rules

1. **Use `return` to output results** - The return value becomes the tool output
2. **Access parameters via `params`** - Input arguments are available in the `params` object
3. **Use `console.log` / `print` for logging** - Output is captured and shown in logs

#### Python Examples

```python
# Simple calculation
result = params['a'] + params['b']
return result
```

```python
# Data processing
import json
from collections import Counter

data = json.loads(params['json_string'])
words = data['text'].split()
counts = Counter(words)
return dict(counts.most_common(10))
```

```python
# Date calculation
from datetime import datetime, timedelta

start = datetime.fromisoformat(params['start_date'])
end = start + timedelta(days=int(params['days']))
return end.isoformat()
```

```python
# Generate UUID
import uuid
return str(uuid.uuid4())
```

#### JavaScript Examples

```javascript
// Simple calculation
const result = params.a + params.b;
return result;
```

```javascript
// Data processing
const data = JSON.parse(params.json_string);
const words = data.text.split(/\s+/);
const counts = words.reduce((acc, word) => {
  acc[word] = (acc[word] || 0) + 1;
  return acc;
}, {});
return Object.entries(counts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 10);
```

```javascript
// Date calculation
const start = new Date(params.start_date);
start.setDate(start.getDate() + parseInt(params.days));
return start.toISOString();
```

```javascript
// Async operation with crypto
const crypto = require('crypto');
const hash = crypto.createHash('sha256')
  .update(params.text)
  .digest('hex');
return hash;
```

### Limitations

| Limitation | Details |
|------------|---------|
| **Timeout** | 30 seconds maximum execution time |
| **Third-party packages** | Optional; must be pinned to an exact version (`requests==2.32.3`, `axios@1.7.9`) and are installed into an isolated, cached environment |
| **File system access** | Confined to the job's `/workspace` directory. The platform's built-in `bash`, `read`, `write`, `edit`, and `artifact` tools operate on `/workspace` only; files written outside `/workspace` are rejected |
| **No persistent state** | Each execution is isolated; workspaces are temporary and cleaned up after the run |
| **Limited environment** | Minimal environment variables (PATH, HOME, LANG) |

---

## Creating Tools

### Via Web UI

1. Navigate to the **Tools** page in your team
2. Click **Create Tool**
3. Choose tool type:
   - **HTTP Tool**: Configure API endpoint and request format
   - **Code Tool**: Write JavaScript or Python code
   - **MCP Tool**: Configure MCP server connection
4. Define parameters that the tool accepts
5. Test the tool with sample inputs
6. Save the tool

### HTTP Tool Configuration

| Field | Description |
|-------|-------------|
| Method | HTTP method (GET, POST, PUT, PATCH, DELETE) |
| URL | Endpoint URL; supports `{{variable}}` placeholders from tool parameters and connection fields, rendered before SSRF validation |
| Headers | Request headers, supports `{{variable}}` substitution |
| Query Params | URL query parameters |
| Body Template | Request body for POST/PUT/PATCH |
| Timeout | Request timeout in seconds |
| Response Path | JSON path to extract from response (e.g., `data.result`) |

### Code Tool Configuration

| Field | Description |
|-------|-------------|
| Language | `javascript` or `python` |
| Code | The code to execute |
| Parameters | Input parameter definitions |

### Database Tool Configuration

Choose the engine's builtin tool, then create/select its connection. The following fields belong to that connection; URL and host/port are alternative forms. Use the saved-tool Test action to verify connectivity with a read-only schema operation.

| Field | Description |
|-------|-------------|
| Engine | Fixed by the selected builtin tool |
| Host / Port | Server address (`url` instead for Redis/MongoDB) |
| Database | Database name (`db` index for Redis, `auth_source` for MongoDB) |
| Username / Password | Connection credentials |
| SSL | TLS configuration |
| Timeout | Query timeout in seconds (default 15) |
| Max Limit | Maximum returned rows (default 100) |

### MCP Tool Configuration

| Field | Description |
|-------|-------------|
| Transport | `stdio`, `sse`, or `http` |
| Command | Command to run (stdio only) |
| Args | Command arguments (stdio only) |
| URL | Server URL (sse/http only) |
| Headers | HTTP headers (sse/http only) |
| Env | Environment variables |

---

## Testing Tools

Before using tools in Agents, test them to ensure they work correctly.

### Test Panel

1. Open the tool details
2. Click **Test** tab
3. Enter test parameter values
4. Click **Run**
5. View results, logs, and execution time

### Code Playground

For code tools, use the **Code Editor** page:

1. Navigate to **Tools > Code Editor**
2. Select language (JavaScript or Python)
3. Write your code
4. Define test parameters in the right panel
5. Click **Run** to execute
6. View results and logs
7. Click **Save as Tool** when ready

---

## Using Tools in Agents

### Assigning Tools

1. Open Agent settings
2. Go to **Tools** section
3. Select tools to enable for this Agent
4. Save changes

### How Agents Use Tools

When an Agent needs to perform an action:

1. Agent decides which tool to call based on the task
2. Agent generates the required parameters
3. System executes the tool
4. Tool result is returned to the Agent
5. Agent incorporates the result into its response

### Best Practices

- **Clear descriptions**: Write clear tool descriptions so the Agent knows when to use them
- **Specific parameters**: Define parameters with clear names and descriptions
- **Error handling**: Tools should return meaningful error messages
- **Test thoroughly**: Test tools with various inputs before production use

### Custom Tool Naming Conventions & Chat Status Visibility

When an Agent calls tools during reasoning, the top **Chain of Thought header** automatically surfaces the action without requiring users to expand the collapsible panel. Follow these naming conventions to ensure the most intuitive status display:

#### 1. Recommended Verb Prefixes

| Action Type | Recommended Prefix / Keywords | CoT Header Display |
| :--- | :--- | :--- |
| **Query / Retrieval** | `query_`, `fetch_`, `get_`, `search_`, `find_`, `check_` | `Querying {tool}...` |
| **Sending / Notifications** | `send_`, `post_`, `push_`, `notify_`, `mail_` | `Sending {tool}...` |
| **Creation** | `create_`, `add_`, `insert_`, `new_`, `build_` | `Creating {tool}...` |
| **External API / Requests** | `api_`, `http_`, `rest_`, `request_`, or input has `url`/`endpoint` | `Requesting {tool}...` |
| **Computation / Analysis** | `calc_`, `math_`, `count_`, `analyze_`, `stat_` | `Calculating...` |
| **Artifacts & Downloads** | `artifact`, `artifacts`, contains `Create Download Link` | `Collecting artifacts...` |
| **Files / Documents** | `read_`, `write_`, `open_file`, `save_file` | `Reading / Editing file...` |
#### 2. Display Name Tips

- **Provide a friendly Display Name**: If configured (e.g., `Fetch Stock Quotes` or `Send Slack Notification`), the CoT header directly uses this name for status rendering.
- **Automatic Identifier Beautification**: Raw identifiers like `fetch_user_orders` or `syncCrmAccount` are automatically converted to clean phrases (e.g., `Querying Fetch User Orders...`).
- **Parallel Call Aggregation**: When multiple tools execute simultaneously, the header aggregates them into `Calling {N} tools in parallel...` to preserve clean UI presentation.
