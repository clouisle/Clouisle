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
<a href="README.md">English documentation index</a> ·
<a href="#功能特性">功能特性</a> ·
<a href="#快速开始">快速开始</a> ·
<a href="#系统架构">系统架构</a> ·
<a href="#文档">文档</a>
</p>

---

## 目录

- [为什么选择 Clouisle](#为什么选择-clouisle)
- [功能特性](#功能特性)
- [文档](#文档)
- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [配置说明](#配置说明)
- [使用场景](#使用场景)
- [路线图](#路线图)
- [参与贡献](#参与贡献)
- [贡献者](#贡献者)
- [许可证](#许可证)

---

## 文档

按主题浏览用户、管理员、部署运维和 API 文档。以下链接均指向仓库中现有页面；部分页面目前仅提供英文版本。本页同时保留中文产品概览；英文文档导航入口为 [README.md](README.md)。

### 入门
- [介绍](getting-started/introduction_zh-CN.md)
- [快速开始](getting-started/quick-start_zh-CN.md)
- [开发环境](getting-started/development_zh-CN.md)
- [基本概念](getting-started/basic-concepts_zh-CN.md)

### 用户指南
- [登录与注册](user-guide/authentication/login-register_zh-CN.md)
- [密码管理](user-guide/authentication/password-management.md)
- [单点登录](user-guide/authentication/sso-user-guide.md)
- [个人资料设置](user-guide/profile/profile-settings.md)
- [通知](user-guide/profile/notifications.md)
- [团队](user-guide/teams/joining-teams.md)
- [团队协作](user-guide/teams/team-collaboration.md)
- [团队角色](user-guide/teams/team-roles.md)
- [知识库](user-guide/knowledge-base/browsing-kb.md)
- [上传文档](user-guide/knowledge-base/uploading-documents.md)
- [文档管理](user-guide/knowledge-base/document-management.md)
- [知识库搜索](user-guide/knowledge-base/searching.md)
- [与 Agent 对话](user-guide/chat/chatting-with-agents.md)
- [会话管理](user-guide/chat/conversation-management.md)
- [聊天文件上传](user-guide/chat/file-uploads.md)
- [工作流构建器](user-guide/workflows/workflow-builder.md)
- [工作流节点](user-guide/workflows/workflow-nodes.md)
- [运行工作流](user-guide/workflows/running-workflows.md)
- [工作流历史](user-guide/workflows/workflow-history.md)
- [API 密钥管理](user-guide/api-keys/managing-api-keys.md)
- [API 密钥作用域](user-guide/api-keys/api-key-scopes.md)

### 管理指南
- [用户管理](admin-guide/users/user-management.md)
- [团队管理](admin-guide/teams/team-management.md)
- [知识库管理](admin-guide/knowledge-base/kb-management.md)
- [Agent 管理](admin-guide/agents/agent-management.md)
- [工作流管理](admin-guide/workflows/workflow-management.md)
- [模型管理](admin-guide/models/model-management.md)
- [工具管理](admin-guide/tools/tool-management.md)
- [权限](admin-guide/permissions/PERMISSIONS_zh-CN.md)
- [系统设置](admin-guide/settings/system-settings.md)
- [SSO 设置](admin-guide/settings/SSO_zh-CN.md)
- [自动通知](admin-guide/settings/AUTO_NOTIFICATIONS_zh-CN.md)
- [审计日志](admin-guide/audit-logs/audit-log-management.md)

### API 参考
- [概览](api-reference/overview.md)
- [认证](api-reference/authentication.md)
- [响应格式](api-reference/response-format.md)
- [错误码](api-reference/error-codes.md)
- [分页](api-reference/pagination.md)
- [筛选](api-reference/filtering.md)
- [速率限制](api-reference/rate-limiting.md)
- [文件上传](api-reference/file-uploads.md)
- [SSE 流式传输](api-reference/sse-streaming.md)
- [Webhook](api-reference/webhooks.md)
- [SDK 示例](api-reference/sdk-examples.md)
- [端点参考目录](api-reference/endpoints/)

### 概念
- [系统架构](concepts/architecture_zh-CN.md)
- [多租户](concepts/multi-tenancy_zh-CN.md)
- [RAG 说明](concepts/rag-explained_zh-CN.md)
- [Agent 与工作流](concepts/agent-vs-workflow_zh-CN.md)
- [代码沙箱](concepts/code-sandbox_zh-CN.md)
- [向量嵌入](concepts/vector-embeddings_zh-CN.md)

### 最佳实践
- [提示词工程](best-practices/prompt-engineering_zh-CN.md)
- [知识库优化](best-practices/kb-optimization_zh-CN.md)
- [工作流模式](best-practices/workflow-patterns_zh-CN.md)
- [性能调优](best-practices/performance-tuning_zh-CN.md)

### 部署与运维
- [部署指南](deployment/DEPLOYMENT_zh-CN.md)
- [Docker Compose](deployment/docker-compose.md)
- [Kubernetes](deployment/kubernetes.md)
- [环境变量](deployment/environment-variables.md)
- [高可用](deployment/high-availability.md)
- [扩展](deployment/scaling.md)
- [生产检查清单](deployment/production-checklist.md)
- [备份与恢复](deployment/backup-recovery.md)
- [监控](operations/monitoring_zh-CN.md)
- [升级](operations/upgrading_zh-CN.md)
- [故障排查](deployment/troubleshooting.md)
- [安全检查清单](operations/security-checklist_zh-CN.md)

### 测试
- [Agent UI 自动化](testing/agent-ui-automation.md)

---


## 为什么选择 Clouisle？

现代企业面临一个共同挑战：**数据碎片化、低复用性和零智能执行**。知识分散在文档、数据库、Wiki 和内部工具中——但当需要做出决策时，这些知识仍然是静态且无法执行的。

**Clouisle 改变这一现状**，提供：

- **智能知识管理**：混合搜索（向量 + 全文）+ 重排序，可配置分块策略，多格式文档处理
- **原生 Agent 架构**：AI Agent 能够检索、推理、执行工具和生成媒体——支持流式输出、思考/推理模式和对话记忆
- **可视化工作流自动化**：拖拽式工作流构建器，支持多种节点、版本管理和多种执行触发方式
- **企业级安全**：多租户、RBAC、SSO（OIDC/SAML/CAS）、TOTP 双因素认证、关键操作审计日志
- **灵活集成**：可配置的模型提供商与模型、MCP 工具协议、沙箱代码执行和 API 密钥管理

> 将 Clouisle 视为一个与您的业务共同演进的**智能层**。

---

## 功能特性

### AI Agent 管理

- **多模型支持**：使用已配置的 LLM 提供商、模型、参数和思考/推理模式配置 Agent
- **RAG 集成**：支持 off（关闭）、auto（自动检索）和 agentic（Agent 自主检索）模式，并可绑定知识库
- **流式与思考**：实时流式响应，支持推理/思考内容展示
- **对话管理**：多轮对话，支持分支、手动停止、Token 用量追踪和会话记忆
- **媒体生成**：对话中支持文本和图像、视频生成（具体能力取决于已配置模型）
- **工具系统**：内置工具（网页搜索、计算器、文件解析器）、自定义 HTTP API 工具和 MCP 协议集成
- **上下文压缩**：自动压缩长会话的对话上下文
- **可见性控制**：私有、团队或公开访问级别，受 RBAC 约束

### 可视化工作流构建器

- **无代码界面**：拖拽式工作流创建，实时节点配置
- **多种节点类型**：LLM/媒体生成、条件/问题分类、Iteration/Loop/Pause、代码/模板、变量聚合与赋值、参数提取、子工作流、Agent、Tool、知识检索和 Answer 等
- **执行触发方式**：手动、定时（Cron）或 Webhook
- **版本管理**：草稿/发布生命周期，支持版本历史和回滚
- **实时监控**：流式执行，节点级实时状态更新
- **调试模式**：逐步测试，部署前查看变量状态
- **子工作流**：将工作流嵌套复用为子工作流节点
- **性能分析**：执行性能和节点延迟分析，并提供可用的 Token、重试等运行指标

### 知识库系统

- **多格式支持**：通过 MarkItDown 支持 PDF、DOCX、XLSX、Markdown 等格式
- **混合搜索**：向量相似度（Qdrant）+ BM25 全文检索（pg_search），支持 Reciprocal Rank Fusion 融合排序
- **可配置分块**：自定义分块大小、重叠和分隔符，支持预览
- **重排序**：可选的重排序管道，提升检索准确度
- **嵌入管理**：可配置的嵌入模型和向量维度
- **异步处理**：通过 Celery 后台处理文档，支持状态追踪
- **全文检索**：基于 PostgreSQL 的全文搜索，支持中文分词（jieba）
- **搜索模式**：仅向量、仅全文或混合模式，支持权重调节

### 模型与提供商

模型提供商和模型由管理员在模型管理中配置。平台通过统一适配接口连接已启用的提供商，也支持 OpenAI 兼容端点；可用模型、能力和参数以当前部署配置为准，不在此固定列出供应商或模型清单。

模型配置可覆盖对话、嵌入、重排序和已启用的媒体模型。连接测试、能力标记、默认参数和加密凭据等选项也取决于具体模型配置。

### 模型管理

- **多提供商**：集中管理已配置的模型提供商和模型，使用标准化接口
- **模型注册**：注册和管理对话、嵌入、重排序和媒体模型
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
- **审计日志**：关键操作追踪，覆盖范围取决于端点；支持变更前后快照和用户归属信息
- **通知系统**：应用内、邮件、钉钉、企业微信、飞书、Slack 和 Webhook 渠道
- **API 密钥管理**：作用域 API 密钥，支持过期时间、用量追踪和团队访问控制
- **站点设置**：可配置的站点设置，支持本地化（英文/中文）
- **密码策略**：可配置的密码过期、历史记录和复杂度要求

### 工具系统

- **内置工具**：时间/日期、计算器、网页搜索（Tavily）、文件解析器、Python 代码解释器
- **自定义工具**：可配置的 HTTP API 工具，支持多种认证方式（API Key、Bearer、Basic）和变量映射
- **MCP 集成**：模型上下文协议，实现标准化的工具能力和资源访问
- **沙箱执行**：安全隔离的 Python 代码执行环境，带资源限制
- **工具管理**：集中管理工具配置、凭据和可用范围

---

## 快速开始

### 前置条件

- 单机部署需要 Docker 和 Docker Compose v2
- Kubernetes 部署需要 `kubectl` 和 Helm 3

### 1. 运行引导式安装脚本

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | bash
```

根据提示选择单机 Docker Compose、Kubernetes Helm，或 Kubernetes 单文件 manifest（仅生成）。Docker 模式会交互式选择安装目录，默认为 `/opt/clouisle`；脚本会生成必要的随机密钥，并在启动前验证部署配置。选择单文件 manifest 时，脚本默认在当前目录生成权限为 `0600` 的 `./clouisle-k8s.yaml`（可通过 `CLOUISLE_K8S_MANIFEST` 指定路径），不会自动执行 `kubectl apply`；请先审阅生成文件，再使用实际生成路径运行 `kubectl apply -f <manifest-path>`；未设置 `CLOUISLE_K8S_MANIFEST` 时使用 `./clouisle-k8s.yaml`。

### 2. 访问应用

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
- 生产运行时：Node.js standalone；Bun 用于前端依赖管理、开发和构建
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
| `API_BASE_URL` | 后端内部服务 URL，不用于对外展示 |
| `PUBLIC_API_URL` | 浏览器可访问的后端公开 URL（可选） |
| `NEXT_PUBLIC_API_URL` | 前端构建或运行时使用的 API URL（可选） |
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
| **内容生成** | 通过 Agent 和媒体生成节点自动执行文本、图像和视频生成流程 |
| **数据分析** | 将 Agent 连接到内部数据库和 API，实现自然语言数据查询和报表生成 |
| **合规与风险** | 自动化合同、政策和监管要求的文档分析，附带审计追踪 |
| **工程生产力** | 通过 RAG Agent 即时访问文档和团队知识，加速新人入职

---

## 路线图

- [x] 多提供商 LLM 支持（可配置提供商和模型）
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

我们欢迎贡献！请查看 [贡献指南](../../CONTRIBUTING.md) 了解详情。

开发环境搭建和命令（代码检查、测试、构建等）请参考 [开发指南](getting-started/development_zh-CN.md)。

## 贡献者

感谢所有为 Clouisle 做出贡献的人：

<a href="https://github.com/clouisle/Clouisle/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=clouisle/Clouisle" />
</a>


---

## 许可证

Clouisle 采用 [GPL v3](../../LICENSE) 许可证开源。

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
