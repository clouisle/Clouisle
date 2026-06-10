# 工具系统技术规范

本文档描述 Clouisle 工具系统的架构设计、实现细节和使用方式。

## 目录

- [概述](#概述)
- [工具类型](#工具类型)
- [系统架构](#系统架构)
- [代码沙箱](#代码沙箱)
- [工具注册表](#工具注册表)
- [API 接口](#api-接口)
- [数据模型](#数据模型)
- [前端集成](#前端集成)
- [安全考虑](#安全考虑)

## 概述

工具系统允许 Agent 调用外部能力来完成任务，支持三种类型的工具：

1. **内置工具 (Builtin)** - 系统预置的常用工具
2. **自定义工具 (Custom)** - 用户创建的 HTTP API 或代码工具
3. **MCP 工具 (MCP)** - 通过 Model Context Protocol 接入的外部工具

## 工具类型

### 内置工具 (Builtin)

系统预置的工具，通过 `tool_registry` 注册，无需用户配置即可使用。

| 工具名 | 功能 | 分类 |
|--------|------|------|
| `get_current_time` | 获取当前时间 | time |
| `format_datetime` | 格式化日期时间 | time |
| `calculate` | 数学计算 | math |
| `unit_convert` | 单位转换 | math |
| `web_search` | 网页搜索 | search |
| `fetch_webpage` | 获取网页内容 | web |

### 自定义工具 (Custom)

用户创建的工具，支持两种执行方式：

#### HTTP 工具

通过 HTTP 请求调用外部 API。

**配置结构 (`http_config`)：**

```json
{
  "method": "GET | POST | PUT | PATCH | DELETE",
  "url": "https://api.example.com/endpoint/{{param}}",
  "headers": {
    "Authorization": "Bearer {{api_key}}"
  },
  "query_params": {
    "key": "{{value}}"
  },
  "body_template": "{\"text\": \"{{input}}\"}",
  "timeout": 30,
  "response_path": "data.result"
}
```

**变量替换：**
- 使用 `{{variable}}` 语法在 URL、Headers、Query Params、Body 中插入变量
- 变量来源：工具参数 (`arguments`) + 凭证 (`credentials`)

#### 代码工具

在服务端沙箱中执行自定义代码，支持 JavaScript 和 Python。

**配置结构 (`code_config`)：**

```json
{
  "language": "javascript | python",
  "code": "// 代码内容\nreturn result;",
  "command": ["python"],
  "python_packages": ["requests==2.32.3"],
  "js_packages": [],
  "python_package_index_url": "https://mirror.example.com/simple",
  "node_package_registry_url": "https://registry.example.com/npm",
  "artifacts": [],
  "limits": {
    "timeout_seconds": 30,
    "disk_mb": 1024,
    "max_stdout_kb": 256,
    "max_stderr_kb": 256
  }
}
```

说明：
- `python_package_index_url` / `node_package_registry_url` 为可选字段，仅影响依赖安装阶段。
- 这两个 URL 必须是绝对 `http(s)` 地址，且不能内嵌凭证。
- 环境缓存键会包含镜像地址，因此不同镜像源不会复用同一安装缓存。

**参数定义 (`parameters`)：**

```json
[
  {
    "name": "query",
    "type": "string",
    "description": "搜索关键词",
    "required": true,
    "default": null,
    "enum": null
  }
]
```

### MCP 工具

通过 Model Context Protocol 接入外部工具服务器，支持三种传输协议。

**文件位置：** `backend/app/llm/tools/mcp_client.py`

#### 传输协议

| 协议 | 说明 | 配置示例 |
|------|------|----------|
| `stdio` | 启动子进程，通过 stdin/stdout 通信 | `npx -y @modelcontextprotocol/server-filesystem` |
| `sse` | Server-Sent Events | 连接远程 SSE 端点 |
| `http` | Streamable HTTP | 连接远程 HTTP 端点 |

#### stdio 配置

```json
{
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
  "env": {
    "API_KEY": "xxx"
  }
}
```

**常用 MCP 服务器：**

| 服务器 | 命令 | 功能 |
|--------|------|------|
| filesystem | `npx -y @modelcontextprotocol/server-filesystem /path` | 文件系统操作 |
| sqlite | `uvx mcp-server-sqlite --db-path /path/to/db.sqlite` | SQLite 数据库 |
| github | `npx -y @modelcontextprotocol/server-github` | GitHub API |
| slack | `npx -y @modelcontextprotocol/server-slack` | Slack 集成 |

#### sse/http 配置

```json
{
  "transport": "sse",
  "url": "http://localhost:3000/sse",
  "headers": {
    "Authorization": "Bearer xxx"
  }
}
```

#### 环境依赖

MCP stdio 模式需要以下运行时环境：

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Node.js | 运行 `npx` 命令 | Docker 镜像已包含 |
| uv/uvx | 运行 Python MCP 服务器 | Docker 镜像已包含 |

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Tool List   │  │ HTTP Editor │  │ Code Editor (Monaco)    │  │
│  │ Page        │  │ Dialog      │  │ + Parameter Definition  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
┌────────────────────────────▼────────────────────────────────────┐
│                      Backend (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  /api/v1/tools                            │   │
│  │  - GET     /           → list_tools (所有工具)            │   │
│  │  - GET     /builtin    → list_builtin_tools               │   │
│  │  - POST    /           → create_tool                      │   │
│  │  - GET     /id/{id}    → get_tool_by_id                   │   │
│  │  - PUT     /{id}       → update_tool                      │   │
│  │  - DELETE  /{id}       → delete_tool                      │   │
│  │  - POST    /test       → test_tool (执行工具)             │   │
│  │  - POST    /execute-code → execute_code_directly          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                             │                                    │
│  ┌──────────────────────────▼──────────────────────────────┐    │
│  │              Tool Execution Layer                        │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │    │
│  │  │ Builtin      │  │ HTTP         │  │ Code         │   │    │
│  │  │ Registry     │  │ Executor     │  │ Sandbox      │   │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │    │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    External Resources                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ HTTP APIs    │  │ Node.js      │  │ Python               │   │
│  │ (外部服务)    │  │ (JS 沙箱)    │  │ (Python 沙箱)        │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 代码沙箱

代码沙箱是工具系统的核心组件，提供安全的代码执行环境。

### 文件位置

`backend/app/llm/tools/sandbox.py`

### 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                    CodeSandbox.execute()                     │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│  JavaScript Execution    │     │    Python Execution         │
│  (_execute_javascript)   │     │    (_execute_python)        │
└────────────┬────────────┘     └────────────┬────────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Wrapper Code Generation                     │
│  1. 注入 params 变量                                         │
│  2. 捕获 console.log / print 输出                           │
│  3. 包装为异步函数                                           │
│  4. 捕获异常                                                 │
│  5. 输出结果标记 (__RESULT__....__END__)                    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  _run_subprocess()                           │
│  1. 创建子进程 (node -e / python -c)                        │
│  2. 限制环境变量 (PATH, HOME, LANG)                         │
│  3. 设置超时 (默认 30s)                                      │
│  4. 捕获 stdout/stderr                                       │
│  5. 解析结果 JSON                                            │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ExecutionResult                             │
│  {                                                           │
│    success: bool,                                            │
│    result: Any,        // 代码返回值                         │
│    error: str | null,  // 错误信息                          │
│    stdout: str,        // 日志输出                          │
│    stderr: str         // 错误输出                          │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### JavaScript 包装代码

```javascript
const params = {/* 传入的参数 */};

// 捕获 console.log 输出
const logs = [];
const originalLog = console.log;
console.log = (...args) => {
    logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
};

// 执行用户代码
async function __execute__() {
    // 用户代码插入这里
    // 必须 return 结果
}

// 运行并输出结果
(async () => {
    try {
        const result = await __execute__();
        console.log = originalLog;
        const output = { success: true, result: result, logs: logs };
        process.stdout.write('__RESULT__' + JSON.stringify(output) + '__END__');
    } catch (e) {
        console.log = originalLog;
        const output = { success: false, error: e.message || String(e), logs: logs };
        process.stdout.write('__RESULT__' + JSON.stringify(output) + '__END__');
    }
})();
```

### Python 包装代码

```python
import json
import sys
from io import StringIO

params = {# 传入的参数 #}

# 捕获 print 输出
_logs = []
_original_stdout = sys.stdout
sys.stdout = StringIO()

def __execute__():
    # 用户代码插入这里（带缩进）
    # 必须 return 结果

try:
    result = __execute__()
    _captured = sys.stdout.getvalue()
    sys.stdout = _original_stdout
    if _captured:
        _logs.extend(_captured.strip().split("\n"))
    output = { "success": True, "result": result, "logs": _logs }
    print("__RESULT__" + json.dumps(output, default=str) + "__END__")
except Exception as e:
    sys.stdout = _original_stdout
    output = { "success": False, "error": str(e), "logs": _logs }
    print("__RESULT__" + json.dumps(output, default=str) + "__END__")
```

### 代码编写规范

#### JavaScript

```javascript
// ✅ 正确：使用 return 返回结果
const result = params.a + params.b;
return result;

// ✅ 正确：支持 async/await
const response = await fetch('https://api.example.com');
const data = await response.json();
return data;

// ✅ 正确：使用 console.log 输出日志
console.log('Processing:', params.query);
return { processed: true };

// ❌ 错误：不要使用 module.exports
module.exports = result;  // 不支持

// ❌ 错误：不要使用 require（无 Node 模块系统）
const fs = require('fs');  // 不支持
```

#### Python

```python
# ✅ 正确：使用 return 返回结果
result = params['a'] + params['b']
return result

# ✅ 正确：使用 print 输出日志
print(f"Processing: {params['query']}")
return {"processed": True}

# ✅ 正确：可以使用标准库
import json
import datetime
return json.dumps({"time": str(datetime.datetime.now())})

# ❌ 错误：不要使用需要安装的第三方库
import requests  # 可能不可用
```

### 安全限制

1. **环境隔离**：子进程仅继承最小环境变量 (PATH, HOME, LANG)
2. **超时控制**：默认 30 秒，最大 60 秒
3. **无文件系统访问**：代码在临时环境执行，无持久化能力
4. **无网络限制**：JavaScript 可使用 fetch，Python 需依赖标准库

### 可用模块

#### Python 标准库

沙箱中可使用所有 Python 标准库模块：

| 模块 | 用途 |
|------|------|
| `json` | JSON 解析/序列化 |
| `re` | 正则表达式 |
| `math` | 数学运算 |
| `datetime` | 日期时间处理 |
| `collections` | 数据结构（Counter, defaultdict 等） |
| `itertools` | 迭代器工具 |
| `functools` | 函数工具 |
| `random` | 随机数 |
| `string` | 字符串常量和模板 |
| `base64` | Base64 编解码 |
| `hashlib` | 哈希算法 |
| `urllib.parse` | URL 解析 |
| `csv` | CSV 处理 |
| `io` | IO 流 |
| `os.path` | 路径操作 |
| `statistics` | 统计计算 |
| `decimal` | 精确小数运算 |
| `fractions` | 分数运算 |
| `uuid` | UUID 生成 |
| `html` | HTML 转义 |
| `textwrap` | 文本换行 |
| `difflib` | 差异比较 |

**不可用：** `requests`, `numpy`, `pandas`, `httpx` 等第三方包

#### JavaScript/Node.js

沙箱中可使用 JavaScript 内置对象和 Node.js 核心模块：

**内置对象（无需 require）：**

| 对象 | 用途 |
|------|------|
| `JSON` | JSON 解析/序列化 |
| `Math` | 数学运算 |
| `Date` | 日期时间 |
| `Array` | 数组方法 |
| `Object` | 对象方法 |
| `String` | 字符串方法 |
| `Number` | 数字方法 |
| `RegExp` | 正则表达式 |
| `Promise` | 异步处理 |
| `Map/Set` | 集合数据结构 |
| `Buffer` | 二进制数据 |

**Node.js 核心模块（需 require）：**

| 模块 | 用途 |
|------|------|
| `crypto` | 加密算法 |
| `url` | URL 解析 |
| `path` | 路径操作 |
| `querystring` | 查询字符串 |
| `util` | 工具函数 |
| `http`/`https` | HTTP 请求（内置） |

**不可用：** `axios`, `lodash`, `moment`, `dayjs` 等 npm 包

### 示例代码

#### Python 示例

```python
# 数据处理
import json
from collections import Counter

data = json.loads(params['json_string'])
word_counts = Counter(data['text'].split())
return dict(word_counts.most_common(10))
```

```python
# 日期计算
from datetime import datetime, timedelta

start = datetime.fromisoformat(params['start_date'])
end = start + timedelta(days=int(params['days']))
return end.isoformat()
```

#### JavaScript 示例

```javascript
// 数据处理
const data = JSON.parse(params.json_string);
const words = data.text.split(/\s+/);
const counts = words.reduce((acc, w) => {
  acc[w] = (acc[w] || 0) + 1;
  return acc;
}, {});
return Object.entries(counts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 10);
```

```javascript
// 日期计算
const start = new Date(params.start_date);
start.setDate(start.getDate() + parseInt(params.days));
return start.toISOString();
```

## 工具注册表

### 文件位置

`backend/app/llm/tools/registry.py`

### 核心类

#### ToolParameter

```python
class ToolParameter(BaseModel):
    name: str           # 参数名
    type: str           # 类型 (string, integer, number, boolean, array, object)
    description: str    # 描述
    required: bool      # 是否必填
    enum: list[str]     # 枚举值
    default: Any        # 默认值
```

#### ToolInfo

```python
class ToolInfo(BaseModel):
    name: str                      # 工具名称
    description: str               # 工具描述
    parameters: list[ToolParameter] # 参数列表
    handler: Callable              # 执行函数
```

#### ToolRegistry

```python
class ToolRegistry:
    def register(name, description, parameters) -> Callable  # 装饰器注册
    def register_tool(tool_info: ToolInfo)                   # 直接注册
    def get_tool(name: str) -> ToolInfo                      # 获取工具
    def get_all_tools() -> list[ToolInfo]                    # 获取全部
    def execute(name: str, arguments: dict) -> Any           # 执行工具
    def to_openai_tools(names: list) -> list[dict]           # 转 OpenAI 格式
```

### 注册内置工具示例

```python
from app.llm.tools import tool_registry, ToolParameter

@tool_registry.register(
    name="get_current_time",
    description="获取当前时间",
    parameters=[
        ToolParameter(
            name="timezone",
            type="string",
            description="时区，如 Asia/Shanghai",
            required=False,
            default="UTC"
        ),
    ]
)
async def get_current_time(timezone: str = "UTC") -> str:
    from datetime import datetime
    import pytz
    tz = pytz.timezone(timezone)
    return datetime.now(tz).isoformat()
```

## API 接口

### 工具列表

```http
GET /api/v1/tools?team_id={team_id}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "builtin": [...],  // 内置工具
    "custom": [...],   // 自定义工具
    "mcp": [...]       // MCP 工具
  }
}
```

### 创建工具

```http
POST /api/v1/tools?team_id={team_id}
Content-Type: application/json

{
  "name": "my_tool",
  "display_name": "我的工具",
  "description": "工具描述",
  "type": "custom",
  "custom_type": "code",  // "http" 或 "code"
  "category": "other",
  "parameters": [
    {
      "name": "input",
      "type": "string",
      "description": "输入参数",
      "required": true
    }
  ],
  "code_config": {
    "language": "javascript",
    "code": "return params.input.toUpperCase();"
  }
}
```

### 测试执行工具

```http
POST /api/v1/tools/test?team_id={team_id}
Content-Type: application/json

{
  "name": "my_tool",
  "arguments": {
    "input": "hello world"
  }
}
```

### 直接执行代码

```http
POST /api/v1/tools/execute-code
Content-Type: application/json

{
  "language": "javascript",
  "code": "return params.a + params.b;",
  "params": { "a": 1, "b": 2 },
  "timeout": 30
}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": 3,
    "error": null,
    "logs": "",
    "duration_ms": 45
  }
}
```

## 数据模型

### Tool 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `team_id` | UUID | 所属团队 |
| `name` | VARCHAR(100) | 工具名称（团队内唯一） |
| `display_name` | VARCHAR(100) | 显示名称 |
| `description` | TEXT | 工具描述 |
| `icon` | VARCHAR(100) | 图标 |
| `category` | ENUM | 分类 |
| `type` | ENUM | 类型 (custom/mcp) |
| `custom_type` | ENUM | 自定义类型 (http/code) |
| `http_config` | JSON | HTTP 配置 |
| `code_config` | JSON | 代码配置 |
| `mcp_config` | JSON | MCP 配置 |
| `parameters` | JSON | 参数定义 |
| `credentials` | JSON | 凭证（加密存储） |
| `is_enabled` | BOOLEAN | 是否启用 |
| `created_by` | UUID | 创建者 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

## 前端集成

### 代码编辑器页面

**路由：** `/app/tools/code`

**功能：**
- Monaco Editor 代码编辑
- 支持 JavaScript/Python 语法高亮
- 参数定义面板
- 即时测试执行
- 保存为工具

### 关键组件

```
frontend/app/(platform)/app/tools/
├── page.tsx                    # 工具列表页
├── code/
│   └── page.tsx               # 代码编辑器页面
└── _components/
    ├── tool-list.tsx          # 工具列表
    ├── tool-test-panel.tsx    # 测试面板
    ├── http-tool-dialog.tsx   # HTTP 工具编辑
    └── mcp-tool-dialog.tsx    # MCP 工具编辑
```

### API 客户端

```typescript
// frontend/lib/api/tools.ts

export const toolsApi = {
  list: (teamId: string) => api.get(`/tools?team_id=${teamId}`),
  create: (teamId: string, data: ToolCreateInput) => api.post(`/tools?team_id=${teamId}`, data),
  update: (id: string, data: ToolUpdateInput) => api.put(`/tools/${id}`, data),
  delete: (id: string) => api.delete(`/tools/${id}`),
  test: (teamId: string, name: string, args: object) => 
    api.post(`/tools/test?team_id=${teamId}`, { name, arguments: args }),
  executeCode: (data: CodeExecuteRequest) => 
    api.post('/tools/execute-code', data),
}
```

## 安全考虑

### 代码执行安全

1. **进程隔离**：代码在独立子进程中执行
2. **环境限制**：仅传递最小环境变量
3. **超时保护**：强制超时终止
4. **无持久化**：不能读写文件系统
5. **日志审计**：记录所有执行日志

### HTTP 工具安全

1. **凭证加密**：敏感信息加密存储
2. **URL 验证**：防止 SSRF 攻击（待实现）
3. **响应限制**：限制响应大小（待实现）

### 权限控制

1. **团队隔离**：工具按团队隔离
2. **角色权限**：仅 owner/admin 可创建/编辑/删除工具
3. **执行权限**：团队成员可测试执行
4. **安全边界**：不要将工具写权限放宽给普通 member。工具可调用外部系统、持有凭证或执行代码，错误配置可能破坏外部资源或共享运行环境。Skill 的创建/编辑/删除遵循同一边界，仅允许团队 owner/admin。

## 扩展规划

### 短期

- [ ] Python 第三方库支持（预安装常用库）
- [ ] 代码执行日志持久化
- [ ] HTTP 工具 SSRF 防护

### 中期

- [ ] MCP Server 集成
- [ ] 工具市场（分享工具模板）
- [ ] 工具版本管理

### 长期

- [ ] Docker 容器化沙箱
- [ ] 自定义运行时环境
- [ ] 分布式工具执行
