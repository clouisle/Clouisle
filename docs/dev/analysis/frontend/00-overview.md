# 前端页面概述

## 技术架构

- **框架**: Next.js 16 (App Router)
- **包管理**: Bun
- **UI 组件**: shadcn/ui (base-vega)
- **状态管理**: React Query (TanStack Query)
- **国际化**: next-intl
- **样式**: Tailwind CSS

## 路由分组

| 分组 | 路径 | 布局 | 说明 |
|------|------|------|------|
| `(auth)` | `/login`, `/register` 等 | 无侧边栏 | 认证相关页面 |
| `(dashboard)` | `/dashboard`, `/users` 等 | 侧边栏布局 | 管理后台 |
| `(platform)` | `/app/*` | 顶部导航布局 | 用户平台 |
| `(chat)` | `/chat/*` | 聊天布局 | 聊天界面 |

## API 客户端模块

位于 `frontend/lib/api/` 目录：

| 模块 | 说明 |
|------|------|
| `agents.ts` | Agent 管理、对话、消息、统计 |
| `knowledge-bases.ts` | 知识库、文档、分块、搜索 |
| `workflows.ts` | 工作流管理、运行、节点执行、版本 |
| `teams.ts` | 团队管理、成员、角色 |
| `users.ts` | 用户 CRUD、个人资料、密码管理 |
| `roles.ts` | 角色和权限管理 |
| `models.ts` | 模型管理、团队模型授权 |
| `tools.ts` | 工具管理（内置、自定义、MCP）、工具共享 |
| `api-keys.ts` | API Key 管理 |
| `auth.ts` | 认证、注册、SSO 连接 |
| `sso.ts` | SSO 提供商管理 |
| `site-settings.ts` | 站点配置（通用、安全、邮件、通知） |
| `audit-logs.ts` | 审计日志查看和导出 |
| `notifications.ts` | 用户和管理员通知 |
| `dashboard.ts` | 仪表盘统计和趋势 |
| `upload.ts` | 文件上传和解析 |
| `prompts.ts` | 提示词生成和优化 |

## API 客户端使用

```typescript
import { api } from '@/lib/api'

// GET 请求
const users = await api.get('/users', { params: { page: 1 } })

// POST 请求
const user = await api.post('/users', { username: 'test' })

// 错误处理
try {
  await api.post('/users', data)
} catch (error) {
  if (error instanceof ApiError) {
    // error.code - 错误码
    // error.msg - 错误消息
    // error.getFieldErrors() - 字段错误（验证错误时）
  }
}

// 静默模式（不显示 toast）
await api.post('/users', data, { silent: true })

// 文件下载
const blob = await axiosInstance.get('/export', {
  params: { format: 'csv' },
  responseType: 'blob'
})
```

## 页面统计

| 路由分组 | 页面数量 |
|----------|----------|
| (auth) | 4 |
| (dashboard) | 25+ |
| (platform) | 20+ |
| (chat) | 1 |
| **总计** | **50+** |

## 路由隔离

Dashboard 和 Platform 路由是隔离的：
- 组件位于各自的 `_components/` 目录
- 不跨路由组共享组件
- 修改共享功能时需同步两边
