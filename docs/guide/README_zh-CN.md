<p align="center">
  <img src="../../imgs/clouisle-light.svg" alt="Clouisle Logo" width="200" />
</p>

# <p align="center">Clouisle（云屿）</p>

<p align="center"><b>企业级 AI Agent 与知识库平台</b></p>

<p align="center">
构建、部署和管理智能 AI Agent，实现高级知识检索与工作流自动化。
</p>

<p align="center">
<img src="https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white" />
<img src="https://img.shields.io/badge/Bun-1.0-orange?logo=bun&logoColor=white" />
<img src="https://img.shields.io/badge/License-GPLv3-blue.svg" />
<a href="https://github.com/yunhai-dev/Clouisle/actions/workflows/ci.yml">
  <img src="https://github.com/yunhai-dev/Clouisle/actions/workflows/ci.yml/badge.svg" />
</a>
</p>

<p align="center">
<a href="https://clouisle.asia">官方网站</a> ·
<a href="../../README.md">English</a> ·
<a href="#功能特性">功能特性</a> ·
<a href="#快速开始">快速开始</a> ·
<a href="#系统架构">系统架构</a> ·
<a href="#文档">文档</a>
</p>

---

## 目录

- [为什么选择 Clouisle](#为什么选择-clouisle)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [配置说明](#配置说明)
- [使用场景](#使用场景)
- [路线图](#路线图)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

---

## 为什么选择 Clouisle？

现代企业面临一个共同挑战：**数据碎片化、低复用性和零智能执行**。知识分散在文档、数据库、Wiki 和内部工具中——但当需要做出决策时，这些知识仍然是静态且无法执行的。

**Clouisle 改变这一现状**，提供：

- **智能知识管理**：不仅仅是存储，而是理解和推理您的数据
- **原生 Agent 架构**：AI Agent 能够检索、推理和执行——而不仅仅是回答问题
- **企业级安全**：多租户、RBAC、SSO、审计日志和合规就绪功能
- **灵活集成**：支持 15+ LLM 提供商和可扩展的工具系统

> 将 Clouisle 视为一个与您的业务共同演进的**智能层**。

---

## 功能特性

### AI Agent 管理

- **多模型支持**：使用不同的 LLM 提供商和参数配置 Agent
- **RAG 集成**：三种检索模式——禁用、引用和重写
- **知识库绑定**：将 Agent 连接到特定知识库以获取上下文感知响应
- **工具集成**：使用内置和自定义工具扩展 Agent 能力
- **可见性控制**：私有、团队或公开访问级别
- **对话管理**：多轮对话，支持历史记录、版本控制和 Token 追踪

### 可视化工作流构建器

- **无代码界面**：拖拽式工作流创建
- **15+ 节点类型**：包括 LLM、条件、代码执行、HTTP 请求、工具、子工作流等
- **执行模式**：手动、定时、Webhook 或 API 触发
- **实时监控**：流式执行，实时状态更新
- **调试模式**：部署前测试工作流

### 知识库系统

- **多格式支持**：通过 MarkItDown 支持 PDF、DOCX、XLSX 等格式
- **智能分块**：可配置的分块策略，支持预览和编辑
- **向量搜索**：基于 Qdrant 的相似度搜索，可配置阈值
- **异步处理**：通过 Celery 进行后台文档处理

### LLM 提供商支持

开箱即用支持 15+ 提供商：

| 提供商 | 模型 |
|--------|------|
| OpenAI | GPT-4o、GPT-4、GPT-3.5 |
| Anthropic | Claude 3.5 Sonnet、Opus、Haiku（支持思考模式） |
| Google | Gemini Pro、Flash |
| xAI | Grok |
| DeepSeek | DeepSeek-V3、R1 |
| Azure OpenAI | 所有 Azure 托管模型 |
| Moonshot | Kimi |
| 智谱 | GLM-4 |
| 通义千问 | 阿里巴巴千问系列 |
| Ollama | 本地模型 |
| 自定义 | 任何 OpenAI 兼容端点 |

### 企业功能

- **多租户**：基于团队的资源隔离和管理
- **RBAC**：细粒度权限系统，支持自定义角色
- **SSO**：支持 OIDC、OAuth2、SAML 2.0 和 CAS
- **审计日志**：全面的操作追踪，包含变更前后快照
- **通知系统**：应用内、邮件、钉钉、企业微信、飞书、Slack 和 Webhook 渠道
- **API 密钥管理**：带有过期时间和使用追踪的作用域访问

### 工具系统

- **内置工具**：时间/日期、计算器、网页搜索（Tavily）、文件解析器
- **自定义工具**：支持认证的 HTTP API 工具
- **MCP 集成**：模型上下文协议，实现高级工具能力
- **沙箱执行**：安全的代码执行环境

---

## 快速开始

### 前置条件

- Docker 和 Docker Compose
- Python 3.13+ 以及 [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh/) 1.0+

### 1. 启动基础设施

```bash
# 启动 PostgreSQL、Redis 和 Qdrant
docker-compose -f deploy/docker-compose.dev.yml up -d
```

### 2. 配置环境变量

```bash
# 复制环境变量文件
cp .env.example .env

# 生成安全密码并更新 .env
# 重要：请为以下字段设置强随机值：
#   - SECRET_KEY
#   - POSTGRES_PASSWORD
#   - REDIS_PASSWORD
#   - QDRANT_API_KEY
```

### 3. 启动后端

```bash
cd backend

# 安装依赖
uv sync

# 启动 API 服务器（首次运行时数据库会自动初始化）
uv run uvicorn app.main:app --reload

# 在单独的终端中启动 Celery workers
uv run celery -A app.core.celery:celery_app worker --loglevel=info
uv run celery -A app.core.celery:celery_app beat --loglevel=info
```

### 4. 启动前端

```bash
cd frontend

# 安装依赖
bun install

# 启动开发服务器
bun dev
```

### 5. 访问应用

- **前端**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs
- **默认管理员**：查看 `.env` 获取初始凭据

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Next.js 16)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  管理后台 │  │  用户平台 │  │   聊天   │  │  认证 (SSO/登录) │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Agent   │  │  工作流  │  │  知识库  │  │   用户与团队     │ │
│  │   引擎   │  │   引擎   │  │         │  │     管理        │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │   LLM    │  │   工具   │  │  审计    │  │     通知        │ │
│  │  适配器  │  │   系统   │  │   日志   │  │     服务        │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
             ┌──────────┐  ┌──────────┐  ┌──────────┐
             │PostgreSQL│  │  Redis   │  │  Qdrant  │
             │  (数据库) │  │  (缓存)  │  │ (向量库) │
             └──────────┘  └──────────┘  └──────────┘
```

### 技术栈

**后端**
- 框架：FastAPI (Python 3.13)
- ORM：Tortoise ORM + AsyncPG
- 任务队列：Celery + Redis
- 向量数据库：Qdrant
- LLM 框架：LangChain + LangGraph

**前端**
- 框架：Next.js 16 (App Router)
- 运行时：Bun
- UI：shadcn/ui + Tailwind CSS
- 语言：TypeScript

---

## 配置说明

### 环境变量

关键配置选项（完整列表请查看 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 |
| `REDIS_URL` | Redis 连接字符串 |
| `QDRANT_URL` | Qdrant 向量数据库 URL |
| `SECRET_KEY` | JWT 签名密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥（可选） |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥（可选） |

### 站点设置

通过管理后台配置：

- **通用**：站点名称、描述、品牌
- **安全**：密码策略、会话超时、登录限制
- **注册**：启用/禁用、需要审批、邮箱验证
- **邮件**：通知的 SMTP 配置
- **SSO**：配置身份提供商
- **通知**：自动通知规则和渠道

---

## 使用场景

| 使用场景 | 说明 |
|----------|------|
| **企业问答** | 部署基于内部知识的 AI Agent，提供准确、上下文感知的答案 |
| **工作流自动化** | 构建结合 LLM 推理和 API 集成的无代码工作流 |
| **工程生产力** | 通过即时访问文档和团队知识加速新人入职 |
| **合规与风险** | 自动化合同、政策和监管要求的文档分析 |
| **客户支持** | 创建可访问产品文档的智能支持 Agent |

---

## 路线图

- [x] 多提供商 LLM 支持（15+ 提供商）
- [x] 可视化工作流构建器
- [x] 带 RAG 的知识库
- [x] 企业 SSO（OIDC、SAML、OAuth2）
- [x] 多渠道通知
- [x] 全面的审计日志
- [ ] 行业特定 Agent 模板
- [ ] 高级分析仪表板
- [ ] 插件市场
- [ ] 移动应用

---

## 参与贡献

我们欢迎贡献！请查看 [贡献指南](../CONTRIBUTING.md) 了解详情。

### 开发命令

**后端**
```bash
uv run ruff check .          # 代码检查
uv run ruff format .         # 代码格式化
uv run mypy app/             # 类型检查
uv run pytest                # 测试
```

**前端**
```bash
bun run lint                 # 代码检查
bun run build                # 构建
```

---

## 许可证

Clouisle 采用 [GPL v3](../LICENSE) 许可证开源。

---

## 致谢

基于以下优秀的开源项目构建：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [Next.js](https://nextjs.org/) - 生产级 React 框架
- [LangChain](https://langchain.com/) - LLM 应用框架
- [Qdrant](https://qdrant.tech/) - 向量相似度搜索引擎
- [shadcn/ui](https://ui.shadcn.com/) - UI 组件库

---

<p align="center">
<b>在 GitHub 上给我们 Star</b> 支持项目<br>
欢迎 PR · 一起构建企业 AI 的未来
</p>
