<p align="center">
  <img src="../../imgs/clouisle-light.svg" alt="Clouisle Logo" width="200" />
</p>

# <p align="center">Clouisle（云屿）</p>

<p align="center"><b>开源 AI Agent 平台 · 工作流自动化 · 知识管理</b></p>

<p align="center">
构建、部署和管理智能 AI Agent，支持 RAG 知识检索、可视化工作流自动化与企业级安全。
</p>

<p align="center">
<img src="https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white" />
<img src="https://img.shields.io/badge/Bun-1.0-orange?logo=bun&logoColor=white" />
<img src="https://img.shields.io/badge/License-GPLv3-blue.svg" />
<a href="https://github.com/clouisle/Clouisle/actions/workflows/ci.yml">
  <img src="https://github.com/clouisle/Clouisle/actions/workflows/ci.yml/badge.svg" />
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
- [贡献者](#贡献者)
- [许可证](#许可证)

---

## 为什么选择 Clouisle？

现代企业面临一个共同挑战：**数据碎片化、低复用性和零智能执行**。知识分散在文档、数据库、Wiki 和内部工具中——但当需要做出决策时，这些知识仍然是静态且无法执行的。

**Clouisle 改变这一现状**，提供：

- **智能知识管理**：混合搜索（向量 + 全文）+ 重排序，可配置分块策略，多格式文档处理
- **原生 Agent 架构**：AI Agent 能够检索、推理、执行工具和生成媒体——支持流式输出、思考/推理模式和对话记忆
- **可视化工作流自动化**：拖拽式工作流构建器，15+ 节点类型，版本管理，多种执行触发方式
- **企业级安全**：多租户、RBAC、SSO（OIDC/SAML/CAS）、TOTP 双因素认证、全面审计日志
- **灵活集成**：24+ LLM 提供商、MCP 工具协议、沙箱代码执行、API 密钥管理

> 将 Clouisle 视为一个与您的业务共同演进的**智能层**。

---

## 功能特性

### AI Agent 管理

- **多模型支持**：使用不同的 LLM 提供商、参数和思考/推理模式配置 Agent
- **RAG 集成**：多种检索模式——禁用、引用和重写——支持知识库绑定
- **流式与思考**：实时流式响应，支持推理/思考内容展示
- **对话管理**：多轮对话，支持分支、手动停止、Token 用量追踪和会话记忆
- **媒体生成**：对话中内置文本生图、视频和音频生成能力
- **工具系统**：内置工具（网页搜索、计算器、文件解析器）、自定义 HTTP API 工具和 MCP 协议集成
- **上下文压缩**：自动压缩长会话的对话上下文
- **可见性控制**：私有、团队或公开访问级别，受 RBAC 约束

### 可视化工作流构建器

- **无代码界面**：拖拽式工作流创建，实时节点配置
- **15+ 节点类型**：LLM、Agent、条件、代码执行（Python）、知识检索、HTTP 请求、工具、子工作流、媒体生成、迭代等
- **执行触发方式**：手动、定时（Cron）、Webhook 或 API——灵活适用于各种场景
- **版本管理**：草稿/发布生命周期，支持版本历史和回滚
- **实时监控**：流式执行，节点级实时状态更新
- **调试模式**：逐步测试，部署前查看变量状态
- **子工作流**：将工作流嵌套复用为子工作流节点
- **性能分析**：执行性能分析，包含每节点延迟和成本追踪

### 知识库系统

- **多格式支持**：通过 MarkItDown 支持 PDF、DOCX、XLSX、Markdown 等格式
- **混合搜索**：向量相似度（Qdrant）+ BM25 全文检索（pg_search），支持 Reciprocal Rank Fusion 融合排序
- **可配置分块**：自定义分块大小、重叠和分隔符，支持预览
- **重排序**：可选的重排序管道，提升检索准确度
- **嵌入管理**：可配置的嵌入模型和向量维度
- **异步处理**：通过 Celery 后台处理文档，支持状态追踪
- **全文检索**：基于 PostgreSQL 的全文搜索，支持中文分词（jieba）
- **搜索模式**：仅向量、仅全文或混合模式，支持权重调节

### LLM 提供商支持

开箱即用支持 24+ 提供商，以及任何 OpenAI 兼容端点。

**对话与补全**

| 提供商 | 代表性模型 |
|--------|-----------|
| OpenAI | GPT-5.6 Sol、GPT-5.6 Terra、GPT-5.6 Luna |
| Anthropic | Claude Opus 5、Fable 5、Mythos 5、Sonnet 5 |
| Google | Gemini 3.6 Flash、Gemini 3.5 Flash-Lite、Gemini 3.1 Pro |
| xAI | Grok 4.5、Grok 4.6（即将发布）、Grok 4.7（即将发布） |
| Azure OpenAI | GPT-5.6 Sol、GPT-5.6 Luna、GPT-5.4 系列 |
| DeepSeek | DeepSeek-V4、DeepSeek-V4-Flash |
| Moonshot | Kimi K3（2.8T 参数，开源） |
| 智谱 | GLM-5.2、GLM-4.7 |
| 通义千问 | Qwen3.8-Max、Qwen3.7-Flash |
| 百川 | Baichuan-M4 |
| MiniMax | MiniMax-M3（100 万上下文，多模态） |
| 火山引擎 | 豆包 2.1 Pro / Turbo |
| SiliconFlow | GLM-5.2、MiniMax-M3、Nex-N2-Pro 等开源模型 |
| Ollama | 本地模型 |
| 自定义 | 任何 OpenAI 兼容端点 |

**图像、视频与音频**

| 提供商 | 最新模型 | 模态 |
|--------|---------|------|
| OpenAI | GPT image-2、GPT image-1.5 | 文生图 |
| Stability AI | Stable Diffusion 3.5 Large、Stable Audio 3.0 | 图像、音频 |
| Midjourney | V8.2、V8.1 | 文生图（代理） |
| Google | Imagen 4、Imagen 3 | 文生图 |
| Runway | Gen-4.5、Aleph 2.0 | 文生视频 |
| Pika | Pika 2.5、PikaStream 1.0 | 文生视频 |
| Luma | Ray3.2、Uni-1.1 | 图像、视频 |
| Kling | Kling 3.0、Kling IMAGE 3.0 Omni | 图像、视频（原生 4K） |
| MiniMax | H3、M3 | 图像、视频、TTS、音频 |
| 火山引擎 | Seedance 2.5、豆包 2.1 Pro | 图像、视频、TTS、音频 |
| SiliconFlow | FLUX 1.1 Pro、Wan2.2、CosyVoice2、Fish-Speech | 图像、视频、音频 |

### 模型管理

- **多提供商**：集中管理 24+ 提供商的模型配置，标准化接口
- **模型注册**：注册和管理对话、嵌入、重排序、TTS、STT、图像和视频模型
- **团队授权**：细粒度的按团队模型访问控制，支持日/月 Token 和请求配额
- **连接测试**：部署前内置模型连通性测试
- **默认参数**：可配置的模型级默认参数（温度、top_p、max_tokens、思考模式等）
- **能力标记**：标记模型能力（视觉、函数调用、流式等）
- **加密凭据**：API 密钥加密存储

### 企业功能

- **多租户**：基于团队的资源隔离，精细的模型授权和配额追踪
- **RBAC**：基于角色的权限系统，支持自定义角色和权限预设
- **SSO**：支持 OIDC、OAuth2、SAML 2.0 和 CAS 单点登录
- **双因素认证**：TOTP 双因素认证，增强账户安全
- **审计日志**：全面的操作追踪，包含变更前后快照和用户归属
- **通知系统**：应用内、邮件、钉钉、企业微信、飞书、Slack 和 Webhook 渠道
- **API 密钥管理**：作用域 API 密钥，支持过期时间、用量追踪和团队访问控制
- **站点设置**：可配置的站点设置，支持本地化（英文/中文）
- **密码策略**：可配置的密码过期、历史记录和复杂度要求

### 工具系统

- **内置工具**：时间/日期、计算器、网页搜索（Tavily）、文件解析器、Python 代码解释器
- **自定义工具**：可配置的 HTTP API 工具，支持多种认证方式（API Key、Bearer、Basic）和变量映射
- **MCP 集成**：模型上下文协议，实现标准化的工具能力和资源访问
- **沙箱执行**：安全隔离的 Python 代码执行环境，带资源限制
- **工具注册中心**：集中式工具管理，支持凭据注入和生命周期钩子

---

## 快速开始

### 前置条件

- Docker 和 Docker Compose

### 1. 配置环境变量

```bash
# 复制 Docker 部署环境变量文件
cp deploy/.env.example deploy/.env

# 编辑 deploy/.env，为以下字段设置强随机值：
#   SECRET_KEY、POSTGRES_PASSWORD、REDIS_PASSWORD、QDRANT_API_KEY
```

### 2. 启动 Clouisle

```bash
cd deploy
docker compose --env-file .env up -d
```

### 3. 访问应用

- **前端**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs

> 如需从源码搭建本地开发环境（后端 + 前端），请参考 [开发指南](getting-started/development_zh-CN.md)。

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
| `DATABASE_URL` | PostgreSQL 连接字符串（未设置时由各字段自动拼接） |
| `POSTGRES_SERVER` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | PostgreSQL 连接信息 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | Redis 连接 |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant 向量数据库 |
| `SECRET_KEY` | JWT 签名密钥 |
| `VECTOR_BACKEND` | 向量数据库后端（默认：qdrant） |
| `API_BASE_URL` | 后端公开 API URL |
| `FRONTEND_URL` | 前端 URL（CORS 和重定向用） |
| `NEXT_PUBLIC_API_URL` | 前端使用的 API URL |
| `TAVILY_API_KEY` | 网页搜索 API 密钥（可选） |
| `SANDBOX_RUNTIME_ENABLED` | 启用沙箱代码执行 |

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
| **企业问答** | 部署基于内部知识的 AI Agent，通过混合搜索和重排序提供准确的上下文感知答案 |
| **工作流自动化** | 构建结合 LLM 推理、API 集成、代码执行和条件分支的无代码工作流 |
| **客户支持** | 创建支持知识库访问、对话记忆和升级工作流的智能支持 Agent |
| **内容生成** | 通过 Agent 和媒体生成节点自动执行文本、图像、视频和音频生成流程 |
| **数据分析** | 将 Agent 连接到内部数据库和 API，实现自然语言数据查询和报表生成 |
| **合规与风险** | 自动化合同、政策和监管要求的文档分析，附带审计追踪 |
| **工程生产力** | 通过 RAG Agent 即时访问文档和团队知识，加速新人入职

---

## 路线图

- [x] 多提供商 LLM 支持（24+ 提供商）
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

开发环境搭建和命令（代码检查、测试、构建等）请参考 [开发指南](getting-started/development_zh-CN.md)。

## 贡献者

感谢所有为 Clouisle 做出贡献的人：

<a href="https://github.com/clouisle/Clouisle/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=clouisle/Clouisle" />
</a>


---

## 许可证

Clouisle 采用 [GPL v3](../LICENSE) 许可证开源。

---

## 致谢

Clouisle 基于许多优秀的开源项目构建——从后端的 FastAPI、LangChain，到前端的 Next.js、shadcn/ui，再到 PostgreSQL、Redis、Qdrant 等基础设施支柱。

查看 [ACKNOWLEDGMENTS.md](../../ACKNOWLEDGMENTS.md) 获取完整列表。

---

## Star 历史

<a href="https://star-history.com/#clouisle/Clouisle&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=clouisle/Clouisle&type=Date&theme=dark" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=clouisle/Clouisle&type=Date" />
  </picture>
</a>

---

<p align="center">
<b>在 GitHub 上给我们 Star</b> 支持项目<br>
欢迎 PR · 一起构建企业 AI 的未来
</p>
