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

系统预置的工具，通过 `tool_registry` 注册，无需用户配置即可使用
（注册入口 `backend/app/llm/tools/builtin/__init__.py:18-28`，元数据见
`backend/app/schemas/tool.py` 的 `BUILTIN_TOOLS_METADATA`）。

| 工具名 | 功能 | 分类 |
|--------|------|------|
| `get_current_time` | 获取当前时间 | time |
| `format_datetime` | 格式化日期时间 | time |
| `calculate` | 数学计算 | math |
| `unit_convert` | 单位转换 | math |
| `web_search` | 网页搜索 | search |
| `fetch_webpage` | 获取网页内容 | web |
| `rss_feed_reader` | 读取 RSS/Atom 订阅 | web |
| `markitdown` | 文档转 Markdown（文件解析器） | file |
| `generate_image` | 文生图 | other |
| `generate_video` | 文/图生视频 | other |
| `bash` | 沙箱内执行 Shell 命令 | sandbox |
| `read` | 读取沙箱文件 | sandbox |
| `write` | 写入沙箱文件 | sandbox |
| `edit` | 编辑沙箱文件 | sandbox |
| `artifact` | 保存 / 导出产物 | sandbox |
| `ask_user` | 向用户追问（需 Agent 开启 `enable_user_input_request`） | interaction |

数据库连接器（PostgreSQL / MySQL / MongoDB / Redis）位于同一包下
（`backend/app/llm/tools/builtin/{postgresql,mysql_db,mongo_db,redis_db}.py`），
但不走内置工具注册表，而是作为 `custom` 工具的 `database` 子类型由
`db_executor.py` 执行。

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

代码工具通过 Sandbox Runtime 提交执行任务；API/Agent 进程不再直接运行用户代码，也不提供进程内 legacy 执行回退。

### 实现位置

- `backend/app/llm/tools/sandbox.py`：代码工具入口，将 Python/JavaScript snippet 编译成 `SandboxJob`。
- `backend/app/services/sandbox/gateway.py`：结果轮询、session 绑定及 Celery 队列路由。
- `backend/app/tasks/sandbox.py`：worker 侧任务检查与状态持久化。
- `backend/app/services/sandbox/manager.py`：工作区、依赖环境、进程执行和结果收集。
- `backend/app/services/sandbox/process_launcher.py`、`egress_proxy.py`：隔离进程启动和受控出网。

### 任务路由与执行流程

1. `execute_code()` 检查 `SANDBOX_RUNTIME_ENABLED`，编译 snippet 并调用 `SandboxGateway`；运行时关闭或任务失败时直接返回失败，不在调用进程执行代码。
2. Gateway 先写入 queued result，再派发 Celery 任务。无 session 的任务使用共享 `sandbox` 队列；session 任务先等待一个已就绪 worker 并确认其物理工作区已创建，然后路由到 `sandbox.worker.<sha256(worker_id)>`。
3. Redis binding 记录 session 的 worker、process instance、node、storage、workspace 和 generation。后续 session 任务都投递到该 worker 的专属队列，并携带 binding。
4. Worker 在执行前校验当前身份、Redis lease 和 binding。过期 generation 或错误 worker 上的消息以 obsolete 失败结束，不转发，也不自动重放。
5. `SandboxManager` 准备独立工作区、按需构建 Python/Node 依赖环境、运行包装后的脚本并解析结果标记；标准输出、错误输出和被代理拦截的主机诊断会写入执行结果。

### 进程隔离与出网

- 提供的 sandbox-worker 部署启用 Bubblewrap。每个 payload 在新的 user/mount/network namespace 内运行；只有当前工作区和临时目录可写，依赖缓存及必要运行时目录只读，子进程收到过滤后的环境变量。
- sandbox-worker 使用 `no-new-privileges`、`SYS_ADMIN`/`SETFCAP` 进行 Bubblewrap 命名空间设置，并授予 `NET_ADMIN` 供可信 egress bridge 启用隔离网络命名空间内的 loopback；Docker 默认 seccomp 会阻止 `pivot_root`，因此部署保留 `seccomp=unconfined`。Worker 容器/Pod 仍需限制 CPU、内存和进程数。
- 无代理 payload 由 Bubblewrap 使用 `--cap-drop ALL` 启动；代理路径由可信 bridge 先启用 loopback，再设置 `no-new-privileges` 并清空其 capability 集后启动 payload。`prlimit` 为每个进程及其子进程设置虚拟地址空间、CPU 时间、单文件大小和文件描述符上限。
- 隔离进程没有直接外网路由。每个任务使用独立 egress proxy socket；代理仅接受 `SANDBOX_NETWORK_ALLOWLIST` 中的精确 HTTPS 主机名，不支持通配符或 IP 字面量。默认主机为 `pypi.org`、`files.pythonhosted.org`、`pypi.python.org` 和 `registry.npmjs.org`。
- Python/Node 依赖安装使用同一任务代理和过滤后的环境，并受 `SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS`（默认 300 秒）限制；npm lifecycle scripts 保持禁用。stdout/stderr 只保留配置上限内的字节，避免大量输出占满 Worker 内存。自定义 index/registry URL 必须使用 HTTPS 且主机在 allowlist 内；拦截的主机名会作为执行诊断返回。
- `SANDBOX_FILESYSTEM_ISOLATION_ENABLED=false` 仅适用于受控的本地开发环境；生产 sandbox-worker 应启用隔离。隔离启动条件不满足时任务失败，不降级为未隔离执行。

### Session 工作区持久化与恢复

- session 的首次任务绑定到一个已就绪 worker；后续 session 任务通过专属 Celery 队列回到同一逻辑 worker。Stateless 任务仍可由共享队列的任一 worker 执行。
- 工作区、检查点、身份、锁和依赖缓存存放在 worker 自己的持久化本地磁盘。不得让不同独立磁盘共用 `SANDBOX_WORKER_ID`，也不得把多节点工作区当作共享文件系统。
- 同一磁盘上的 Celery 进程替换会保留 worker/storage identity，但使用新的 instance ID；运行时先尝试在原存储上恢复。原节点/磁盘持续不可用时，有限恢复窗口后可按 reset 上限绑定新 workspace generation，并向 AgentRun 发出 `WORKSPACE_RESET`，要求其重新规划。
- 检查点只保存已提交轮次；worker/磁盘永久丢失时，尚未检查点的数据无法恢复。命令完成状态不确定时返回不确定结果，禁止自动重放。

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

### 工具 / 代码编辑器页面

**路由：** `/app/capabilities`、`/app/capabilities/code`、`/app/capabilities/skills/[id]`

工具与 Skill 管理、代码工具编辑器统一在 `capabilities` 模块下，**不存在**
`/app/tools` 路由。

**代码编辑器页面（`/app/capabilities/code`）功能：**
- Monaco Editor 代码编辑（`@monaco-editor/react`）
- 支持 JavaScript / Python 语法高亮
- 参数定义面板
- 即时测试执行
- 保存为工具

### 关键组件

```
frontend/app/(platform)/app/capabilities/
├── page.tsx                    # 工具 / Skill 列表
├── code/
│   └── page.tsx                # 代码工具编辑器页面
├── skills/
│   └── [id]/
│       └── page.tsx            # Skill 详情
└── _components/
    ├── tool-list.tsx           # 工具列表
    ├── tool-card.tsx
    ├── tool-test-panel.tsx     # 测试面板
    ├── tool-config-dialog.tsx
    ├── tool-category-input.tsx
    ├── tool-share-dialog.tsx
    ├── http-tool-dialog.tsx    # HTTP 工具编辑
    ├── mcp-tool-dialog.tsx     # MCP 工具编辑
    ├── database-tool-dialog.tsx # 数据库工具编辑
    └── skills-panel.tsx        # Skill 管理面板
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

1. **命名空间隔离**：提供的 sandbox-worker 部署使用 Bubblewrap 的 user、mount、network namespace；任务仅能写当前工作区和临时目录。
2. **文件与进程限制**：运行时及依赖缓存只读挂载，子进程使用过滤后的环境，并受超时、输出和磁盘限制。
3. **出网控制**：隔离任务只能通过逐任务代理访问外部 HTTPS 主机；代理按 `SANDBOX_NETWORK_ALLOWLIST` 精确匹配 DNS 主机名并返回拦截诊断。
4. **持久化边界**：session 工作区和已提交检查点保存在所属 worker 的本地磁盘；TTL 到期后清理。磁盘永久丢失时，未检查点数据不可恢复。

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

- [ ] 代码执行日志持久化
- [ ] HTTP 工具 SSRF 防护

### 中期

- [ ] MCP Server 集成
- [ ] 工具市场（分享工具模板）
- [ ] 工具版本管理

### 长期

- [ ] 自定义运行时环境
- [ ] 分布式工具执行
