# 工作流管理 API

**文件**: `backend/app/api/v1/endpoints/workflows.py`
**路径前缀**: `/api/v1/workflows`

## 概述

工作流是可视化的自动化流程，由节点和边组成。支持多种触发方式和节点类型。

## 工作流状态

| 状态 | 说明 |
|------|------|
| `DRAFT` | 草稿 |
| `PUBLISHED` | 已发布 |
| `ARCHIVED` | 已归档 |

## 运行状态

| 状态 | 说明 |
|------|------|
| `PENDING` | 待执行 |
| `RUNNING` | 执行中 |
| `SUCCESS` | 成功 |
| `FAILED` | 失败 |
| `CANCELLED` | 已取消 |

## 触发类型

| 类型 | 说明 |
|------|------|
| `MANUAL` | 手动触发 |
| `SCHEDULED` | 定时触发 |
| `WEBHOOK` | Webhook 触发 |
| `API` | API 触发 |

## 接口列表

### GET /

获取工作流列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` |
| 说明 | 获取用户可访问的工作流列表 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词
- `team_id`: 团队 ID
- `status`: 状态筛选

---

### POST /

创建工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:create` |
| 说明 | 创建新工作流 |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)",
  "team_id": "uuid",
  "nodes": [...],
  "edges": [...],
  "variables": [...],
  "trigger_type": "MANUAL",
  "trigger_config": {}
}
```

---

### GET /{workflow_id}

获取工作流详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取工作流详细配置 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### PUT /{workflow_id}

更新工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:update` + 团队成员 |
| 说明 | 更新工作流配置 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### DELETE /{workflow_id}

删除工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:delete` + 团队成员 |
| 说明 | 删除工作流及其运行记录 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/publish

发布工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:publish` + 团队成员 |
| 说明 | 发布工作流 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/unpublish

取消发布

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:publish` + 团队成员 |
| 说明 | 取消发布工作流 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/duplicate

复制工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:create` + 团队成员 |
| 说明 | 复制工作流 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/run

运行工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:run` + 团队成员 |
| 说明 | 手动触发工作流运行 |

**路径参数**:
- `workflow_id`: 工作流 UUID

**请求体**:
```json
{
  "inputs": {
    "key": "value"
  }
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "run_id": "uuid",
    "status": "PENDING"
  }
}
```

---

### POST /{workflow_id}/debug

调试工作流

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:run` + 团队成员 |
| 说明 | 以调试模式运行工作流 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/regenerate-webhook-token

重新生成 Webhook Token

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:update` + 团队成员 |
| 说明 | 重新生成工作流的 Webhook Token |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

## 运行记录

### GET /{workflow_id}/runs

获取运行记录列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取工作流的运行记录 |

**路径参数**:
- `workflow_id`: 工作流 UUID

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `status`: 状态筛选

---

### GET /runs

获取所有运行记录（全局）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` |
| 说明 | 获取所有工作流的运行记录 |

---

### GET /runs/stats

获取运行统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` |
| 说明 | 获取工作流运行统计数据 |

---

### GET /runs/{run_id}

获取运行详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取运行详细信息 |

**路径参数**:
- `run_id`: 运行记录 UUID

---

### GET /runs/{run_id}/nodes

获取节点执行记录

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取运行中各节点的执行情况 |

**路径参数**:
- `run_id`: 运行记录 UUID

---

### POST /runs/{run_id}/cancel

取消运行

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:run` + 团队成员 |
| 说明 | 取消正在运行的工作流 |

**路径参数**:
- `run_id`: 运行记录 UUID

---

### DELETE /runs/{run_id}

删除运行记录

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:delete` + 团队成员 |
| 说明 | 删除指定运行记录 |

**路径参数**:
- `run_id`: 运行记录 UUID

---

### GET /runs/{run_id}/stream

流式获取运行事件

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | SSE 流式获取运行事件 |

**路径参数**:
- `run_id`: 运行记录 UUID

**响应**: Server-Sent Events

---

## 版本管理

### GET /{workflow_id}/versions

获取版本列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取工作流的版本历史 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### GET /{workflow_id}/versions/{version}

获取指定版本

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:read` + 团队成员 |
| 说明 | 获取工作流的指定版本 |

**路径参数**:
- `workflow_id`: 工作流 UUID
- `version`: 版本号

---

### POST /{workflow_id}/versions

创建版本

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:update` + 团队成员 |
| 说明 | 保存当前配置为新版本 |

**路径参数**:
- `workflow_id`: 工作流 UUID

---

### POST /{workflow_id}/versions/{version}/restore

恢复版本

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `workflow:update` + 团队成员 |
| 说明 | 恢复到指定版本 |

**路径参数**:
- `workflow_id`: 工作流 UUID
- `version`: 版本号

---

## Webhook API（公开）

### POST /webhook/{webhook_token}

Webhook 触发

| 属性 | 值 |
|------|-----|
| 认证 | API Key (Authorization Header) |
| 权限 | 有效的 API Key |
| 说明 | 通过 Webhook 触发工作流执行 |

**路径参数**:
- `webhook_token`: 工作流的 Webhook Token

**请求体**:
```json
{
  "inputs": {
    "key": "value"
  }
}
```

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `workflow:read` | 查看工作流列表、详情和运行记录 |
| `workflow:create` | 创建新工作流 |
| `workflow:update` | 更新工作流配置、创建版本 |
| `workflow:delete` | 删除工作流和运行记录 |
| `workflow:publish` | 发布/取消发布工作流 |
| `workflow:run` | 运行工作流、取消运行 |

---

## 节点类型

| 类型 | 说明 |
|------|------|
| `START` | 开始节点 |
| `END` | 结束节点 |
| `LLM` | LLM 调用节点 |
| `CODE` | 代码执行节点 |
| `HTTP` | HTTP 请求节点 |
| `CONDITION` | 条件分支节点 |
| `LOOP` | 循环节点 |
| `VARIABLE` | 变量操作节点 |
| `KNOWLEDGE` | 知识库检索节点 |
| `TOOL` | 工具调用节点 |
