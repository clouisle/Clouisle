# 工具指南

本指南介绍如何使用 Clouisle 的工具功能来扩展 Agent 能力。

---

## 目录

- [概述](#概述)
- [工具类型](#工具类型)
  - [内置工具](#内置工具)
  - [HTTP 工具](#http-工具)
  - [代码工具](#代码工具)
  - [MCP 工具](#mcp-工具)
- [代码沙箱](#代码沙箱)
  - [可用模块](#可用模块)
  - [编写代码](#编写代码)
  - [限制说明](#限制说明)
- [创建工具](#创建工具)
- [测试工具](#测试工具)
- [在 Agent 中使用工具](#在-agent-中使用工具)

---

## 概述

工具允许 Agent 执行文本生成之外的操作，例如：

- 搜索网页
- 调用外部 API
- 使用自定义代码处理数据
- 与数据库和文件系统交互（通过 MCP）

## 工具类型

### 内置工具

系统预置的工具，无需配置即可使用。

| 工具 | 描述 | 分类 |
|------|------|------|
| `get_current_time` | 获取指定时区的当前时间 | 时间 |
| `format_datetime` | 格式化日期时间字符串 | 时间 |
| `calculate` | 计算数学表达式 | 数学 |
| `unit_convert` | 单位转换 | 数学 |
| `web_search` | 网页搜索（需要 Tavily API 密钥） | 搜索 |
| `fetch_webpage` | 获取并提取网页内容 | 网页 |

### HTTP 工具

调用外部 REST API，支持灵活配置请求。

**功能特性：**
- 支持 GET、POST、PUT、PATCH、DELETE 方法
- URL、请求头、查询参数、请求体中支持变量替换
- 安全的凭证存储
- 响应路径提取

**配置示例：**

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

### 代码工具

在安全沙箱中执行自定义 JavaScript 或 Python 代码。

**功能特性：**
- 支持 JavaScript (Node.js) 和 Python
- 可访问标准库模块
- 通过 `params` 对象注入参数
- 捕获 console.log/print 输出
- 30 秒超时保护

### MCP 工具

通过 [Model Context Protocol](https://modelcontextprotocol.io/) 连接外部工具服务器。

**支持的传输协议：**

| 协议 | 描述 | 使用场景 |
|------|------|----------|
| `stdio` | 启动子进程，通过 stdin/stdout 通信 | 本地 MCP 服务器 |
| `sse` | Server-Sent Events | 远程服务器 |
| `http` | Streamable HTTP | 远程服务器 |

**常用 MCP 服务器：**

| 服务器 | 命令 | 描述 |
|--------|------|------|
| Filesystem | `npx -y @modelcontextprotocol/server-filesystem /path` | 文件操作 |
| SQLite | `uvx mcp-server-sqlite --db-path /path/db.sqlite` | 数据库查询 |
| GitHub | `npx -y @modelcontextprotocol/server-github` | GitHub API 访问 |
| Slack | `npx -y @modelcontextprotocol/server-slack` | Slack 集成 |

---

## 代码沙箱

代码沙箱提供安全的代码执行环境。

### 可用模块

#### Python

所有 Python 标准库模块均可使用：

| 模块 | 用途 |
|------|------|
| `json` | JSON 解析/序列化 |
| `re` | 正则表达式 |
| `math` | 数学函数 |
| `datetime` | 日期时间处理 |
| `collections` | 数据结构（Counter、defaultdict 等） |
| `itertools` | 迭代器工具 |
| `functools` | 函数工具 |
| `random` | 随机数生成 |
| `string` | 字符串常量和模板 |
| `base64` | Base64 编解码 |
| `hashlib` | 哈希算法（MD5、SHA 等） |
| `urllib.parse` | URL 解析 |
| `csv` | CSV 文件处理 |
| `uuid` | UUID 生成 |
| `statistics` | 统计计算 |
| `decimal` | 精确小数运算 |
| `html` | HTML 转义 |
| `textwrap` | 文本换行 |
| `difflib` | 差异比较 |

**不可用：** `requests`、`numpy`、`pandas`、`httpx` 或任何第三方包。

#### JavaScript

内置对象（无需 require）：

| 对象 | 用途 |
|------|------|
| `JSON` | JSON 解析/序列化 |
| `Math` | 数学函数 |
| `Date` | 日期时间处理 |
| `Array` | 数组方法 |
| `Object` | 对象方法 |
| `String` | 字符串方法 |
| `RegExp` | 正则表达式 |
| `Promise` | 异步处理 |
| `Map` / `Set` | 集合数据结构 |
| `Buffer` | 二进制数据处理 |

Node.js 核心模块（需要 require）：

| 模块 | 用途 |
|------|------|
| `crypto` | 加密函数 |
| `url` | URL 解析 |
| `path` | 路径操作 |
| `querystring` | 查询字符串解析 |
| `util` | 工具函数 |
| `http` / `https` | HTTP 请求 |

**不可用：** `axios`、`lodash`、`moment`、`dayjs` 或任何 npm 包。

### 编写代码

#### 基本规则

1. **使用 `return` 输出结果** - 返回值将成为工具输出
2. **通过 `params` 访问参数** - 输入参数在 `params` 对象中
3. **使用 `console.log` / `print` 记录日志** - 输出会被捕获并显示在日志中

#### Python 示例

```python
# 简单计算
result = params['a'] + params['b']
return result
```

```python
# 数据处理
import json
from collections import Counter

data = json.loads(params['json_string'])
words = data['text'].split()
counts = Counter(words)
return dict(counts.most_common(10))
```

```python
# 日期计算
from datetime import datetime, timedelta

start = datetime.fromisoformat(params['start_date'])
end = start + timedelta(days=int(params['days']))
return end.isoformat()
```

```python
# 生成 UUID
import uuid
return str(uuid.uuid4())
```

#### JavaScript 示例

```javascript
// 简单计算
const result = params.a + params.b;
return result;
```

```javascript
// 数据处理
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
// 日期计算
const start = new Date(params.start_date);
start.setDate(start.getDate() + parseInt(params.days));
return start.toISOString();
```

```javascript
// 使用 crypto 的异步操作
const crypto = require('crypto');
const hash = crypto.createHash('sha256')
  .update(params.text)
  .digest('hex');
return hash;
```

### 限制说明

| 限制 | 详情 |
|------|------|
| **超时** | 最长执行时间 30 秒 |
| **无第三方包** | 仅可使用标准库模块 |
| **无文件系统访问** | 无法读写文件 |
| **无持久状态** | 每次执行相互隔离 |
| **受限环境** | 仅有最小环境变量（PATH、HOME、LANG） |

---

## 创建工具

### 通过 Web 界面

1. 进入团队工作区的**工具**页面
2. 点击**创建工具**
3. 选择工具类型：
   - **HTTP 工具**：配置 API 端点和请求格式
   - **代码工具**：编写 JavaScript 或 Python 代码
   - **MCP 工具**：配置 MCP 服务器连接
4. 定义工具接受的参数
5. 使用示例输入测试工具
6. 保存工具

### HTTP 工具配置

| 字段 | 描述 |
|------|------|
| 方法 | HTTP 方法（GET、POST、PUT、PATCH、DELETE） |
| URL | 端点 URL，支持 `{{variable}}` 替换 |
| 请求头 | 请求头，支持 `{{variable}}` 替换 |
| 查询参数 | URL 查询参数 |
| 请求体模板 | POST/PUT/PATCH 的请求体 |
| 超时 | 请求超时时间（秒） |
| 响应路径 | 从响应中提取的 JSON 路径（如 `data.result`） |

### 代码工具配置

| 字段 | 描述 |
|------|------|
| 语言 | `javascript` 或 `python` |
| 代码 | 要执行的代码 |
| 参数 | 输入参数定义 |

### MCP 工具配置

| 字段 | 描述 |
|------|------|
| 传输协议 | `stdio`、`sse` 或 `http` |
| 命令 | 要运行的命令（仅 stdio） |
| 参数 | 命令参数（仅 stdio） |
| URL | 服务器 URL（仅 sse/http） |
| 请求头 | HTTP 请求头（仅 sse/http） |
| 环境变量 | 环境变量 |

---

## 测试工具

在 Agent 中使用工具之前，先测试确保其正常工作。

### 测试面板

1. 打开工具详情
2. 点击**测试**标签
3. 输入测试参数值
4. 点击**运行**
5. 查看结果、日志和执行时间

### 代码编辑器

对于代码工具，可使用**代码编辑器**页面：

1. 进入**工具 > 代码编辑器**
2. 选择语言（JavaScript 或 Python）
3. 编写代码
4. 在右侧面板定义测试参数
5. 点击**运行**执行
6. 查看结果和日志
7. 准备好后点击**保存为工具**

---

## 在 Agent 中使用工具

### 分配工具

1. 打开 Agent 设置
2. 进入**工具**部分
3. 选择要为此 Agent 启用的工具
4. 保存更改

### Agent 如何使用工具

当 Agent 需要执行操作时：

1. Agent 根据任务决定调用哪个工具
2. Agent 生成所需的参数
3. 系统执行工具
4. 工具结果返回给 Agent
5. Agent 将结果整合到回复中

### 最佳实践

- **清晰的描述**：编写清晰的工具描述，让 Agent 知道何时使用
- **明确的参数**：定义具有清晰名称和描述的参数
- **错误处理**：工具应返回有意义的错误信息
- **充分测试**：在生产使用前用各种输入测试工具
