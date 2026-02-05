# Clouisle 项目分析文档

本目录包含 Clouisle 项目的详细分析文档。

## 目录结构

```
docs/analysis/
├── README.md                 # 本文件
├── backend/                  # 后端 API 分析
│   ├── 00-overview.md       # 后端概述
│   ├── 01-login.md          # 登录认证
│   ├── 02-users.md          # 用户管理
│   ├── 03-teams.md          # 团队管理
│   ├── 04-roles.md          # 角色管理
│   ├── 05-permissions.md    # 权限管理
│   ├── 06-agents.md         # Agent 管理
│   ├── 07-models.md         # 模型管理
│   ├── 08-knowledge-bases.md # 知识库管理
│   ├── 09-tools.md          # 工具管理
│   ├── 10-workflows.md      # 工作流管理
│   ├── 11-api-keys.md       # API Key 管理
│   ├── 12-chat.md           # 聊天接口
│   ├── 13-notifications.md  # 通知管理
│   ├── 14-sso.md            # SSO 单点登录
│   ├── 15-site-settings.md  # 站点设置
│   ├── 16-dashboard.md      # 仪表盘统计
│   ├── 17-audit-logs.md     # 审计日志
│   ├── 18-prompt-generator.md # 提示词生成
│   └── 19-conversations.md  # 对话管理（管理端）
└── frontend/                 # 前端页面分析
    ├── 00-overview.md       # 前端概述
    ├── 01-auth.md           # 认证页面
    ├── 02-dashboard.md      # 管理后台页面
    ├── 03-platform.md       # 用户平台页面
    └── 04-chat.md           # 聊天页面
```

## 后端 API 分析

后端基于 Python FastAPI 构建，采用以下技术栈：
- ORM: Tortoise ORM + AsyncPG
- 向量数据库: Qdrant
- LLM 框架: LangChain + LangGraph
- 任务队列: Celery + Redis

### 认证模式

| 模式 | 说明 |
|------|------|
| 无认证 | 公开接口，如登录、注册、SSO 回调等 |
| 活跃用户 | `get_current_active_user` - 需要登录且账户激活 |
| 权限检查 | `PermissionChecker("scope:action")` - 细粒度权限控制 |
| 超级管理员 | `get_current_active_superuser` - 仅管理员可访问 |

### 权限字符串

系统使用 `scope:action` 格式的权限字符串进行细粒度访问控制：

| 资源 | 权限 | 说明 |
|------|------|------|
| team | `team:read`, `team:create`, `team:update`, `team:delete`, `team:manage` | 团队管理 |
| agent | `agent:read`, `agent:create`, `agent:update`, `agent:delete`, `agent:publish`, `agent:chat` | Agent 管理 |
| workflow | `workflow:read`, `workflow:create`, `workflow:update`, `workflow:delete`, `workflow:publish`, `workflow:run` | 工作流管理 |
| kb | `kb:read`, `kb:create`, `kb:update`, `kb:delete` | 知识库管理 |
| tool | `tool:read`, `tool:create`, `tool:update`, `tool:delete`, `tool:execute` | 工具管理 |
| conversation | `conversation:read`, `conversation:delete` | 对话管理 |
| apikey | `apikey:read`, `apikey:create`, `apikey:update`, `apikey:delete` | API Key 管理 |
| user | `user:read`, `user:create`, `user:update`, `user:delete` | 用户管理 |
| model | `model:read`, `model:create`, `model:update`, `model:delete` | 模型管理 |
| role | `role:read`, `role:create`, `role:update`, `role:delete` | 角色管理 |
| audit_log | `audit_log:read`, `audit_log:export` | 审计日志 |
| site_setting | `site_setting:read`, `site_setting:update` | 站点设置 |

### 系统角色

| 角色 | 说明 |
|------|------|
| Super Admin | 超级管理员，拥有所有权限 |
| Member | 普通成员，拥有资源操作权限（team, agent, workflow, kb, tool, apikey, conversation） |
| Viewer | 只读用户，仅有读取权限 |

### 响应格式

所有 API 响应使用统一格式：
```json
{
  "code": 0,
  "data": {...},
  "msg": "success"
}
```

## 前端页面分析

前端基于 Next.js 16 构建，采用以下技术栈：
- 包管理: Bun
- UI 组件: shadcn/ui
- 状态管理: React Query
- 国际化: next-intl

### 路由分组

| 分组 | 路径前缀 | 说明 |
|------|----------|------|
| (auth) | `/login`, `/register` 等 | 认证相关页面 |
| (dashboard) | `/dashboard`, `/users` 等 | 管理后台（侧边栏布局） |
| (platform) | `/app/*` | 用户平台（顶部导航布局） |
| (chat) | `/chat/*` | 聊天界面 |

## 快速导航

- [后端 API 概述](./backend/00-overview.md)
- [前端页面概述](./frontend/00-overview.md)
