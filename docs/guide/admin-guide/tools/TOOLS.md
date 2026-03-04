# Tools Guide

This guide explains how to use the Tools feature in Clouisle to extend Agent capabilities.

---

## Table of Contents

- [Overview](#overview)
- [Tool Types](#tool-types)
  - [Builtin Tools](#builtin-tools)
  - [HTTP Tools](#http-tools)
  - [Code Tools](#code-tools)
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

### Builtin Tools

System-provided tools that are ready to use without configuration.

| Tool | Description | Category |
|------|-------------|----------|
| `get_current_time` | Get current time in specified timezone | Time |
| `format_datetime` | Format date/time strings | Time |
| `calculate` | Evaluate mathematical expressions | Math |
| `unit_convert` | Convert between units | Math |
| `web_search` | Search the web (requires Tavily API key) | Search |
| `fetch_webpage` | Fetch and extract webpage content | Web |

### HTTP Tools

Call external REST APIs with configurable requests.

**Features:**
- Support GET, POST, PUT, PATCH, DELETE methods
- Variable substitution in URL, headers, query params, and body
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

### Code Tools

Execute custom JavaScript or Python code in a secure sandbox.

**Features:**
- JavaScript (Node.js) and Python support
- Access to standard library modules
- Parameter injection via `params` object
- Console/print output capture
- 30-second timeout protection

### MCP Tools

Connect to external tool servers via [Model Context Protocol](https://modelcontextprotocol.io/).

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

**Not Available:** `requests`, `numpy`, `pandas`, `httpx`, or any third-party packages.

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

**Not Available:** `axios`, `lodash`, `moment`, `dayjs`, or any npm packages.

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
| **No third-party packages** | Only standard library modules available |
| **No file system access** | Cannot read/write files |
| **No persistent state** | Each execution is isolated |
| **Limited environment** | Minimal environment variables (PATH, HOME, LANG) |

---

## Creating Tools

### Via Web UI

1. Navigate to **Tools** page in your team workspace
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
| URL | Endpoint URL, supports `{{variable}}` substitution |
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
