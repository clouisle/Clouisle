# 审计日志 API

**文件**: `backend/app/api/v1/endpoints/audit_logs.py`
**路径前缀**: `/api/v1/audit-logs`

## 概述

审计日志记录系统中的所有关键操作，用于安全审计和问题追踪。

## 接口列表

### GET /

获取审计日志列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取审计日志列表，支持多种筛选条件 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `user_id`: 用户 ID
- `team_id`: 团队 ID
- `action`: 操作类型
- `resource_type`: 资源类型
- `status`: 状态（success, failed）
- `start_date`: 开始日期
- `end_date`: 结束日期
- `search`: 搜索关键词

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "user": {
          "id": "uuid",
          "username": "string"
        },
        "team": {
          "id": "uuid",
          "name": "string"
        },
        "action": "create_agent",
        "resource_type": "agent",
        "resource_id": "uuid",
        "resource_name": "string",
        "operation": "create",
        "status": "success",
        "ip_address": "192.168.1.1",
        "user_agent": "string",
        "changes": {
          "before": null,
          "after": {...}
        },
        "metadata": {...},
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 1000
  }
}
```

---

### GET /stats

获取审计日志统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取审计日志统计数据 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "total": 10000,
    "today": 100,
    "failed": 50,
    "active_users_today": 30,
    "top_actions": [
      {"action": "login_success", "count": 500},
      {"action": "create_agent", "count": 200}
    ],
    "top_users": [
      {"user_id": "uuid", "username": "admin", "count": 100}
    ]
  }
}
```

---

### GET /stats/retention

获取保留统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取审计日志保留和归档统计 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "retention_days": 90,
    "total_logs": 10000,
    "logs_to_archive": 500,
    "archived_logs": 5000,
    "last_archive_at": "2024-01-01T00:00:00Z"
  }
}
```

---

### POST /archive

触发归档

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 手动触发审计日志归档 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "archived_count": 500,
    "message": "Archive completed"
  }
}
```

---

### GET /export

导出审计日志

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 导出审计日志为 CSV 或 JSON |

**查询参数**:
- `format`: 导出格式（csv, json）
- `user_id`: 用户 ID
- `action`: 操作类型
- `start_date`: 开始日期
- `end_date`: 结束日期

**响应**: 文件下载

---

## 审计操作类型

### 认证相关

| 操作 | 说明 |
|------|------|
| `login_success` | 登录成功 |
| `login_failed` | 登录失败 |
| `logout` | 登出 |
| `register` | 注册 |
| `change_password` | 修改密码 |
| `reset_password` | 重置密码 |

### 用户管理

| 操作 | 说明 |
|------|------|
| `create_user` | 创建用户 |
| `update_user` | 更新用户 |
| `delete_user` | 删除用户 |
| `activate_user` | 激活用户 |
| `deactivate_user` | 停用用户 |

### 团队管理

| 操作 | 说明 |
|------|------|
| `create_team` | 创建团队 |
| `update_team` | 更新团队 |
| `delete_team` | 删除团队 |
| `add_team_member` | 添加成员 |
| `remove_team_member` | 移除成员 |

### Agent 管理

| 操作 | 说明 |
|------|------|
| `create_agent` | 创建 Agent |
| `update_agent` | 更新 Agent |
| `delete_agent` | 删除 Agent |
| `publish_agent` | 发布 Agent |
| `unpublish_agent` | 取消发布 |

### API Key 管理

| 操作 | 说明 |
|------|------|
| `create_api_key` | 创建 API Key |
| `update_api_key` | 更新 API Key |
| `delete_api_key` | 删除 API Key |
| `activate_api_key` | 激活 API Key |
| `deactivate_api_key` | 停用 API Key |

### 站点设置

| 操作 | 说明 |
|------|------|
| `update_site_setting` | 更新设置 |
| `bulk_update_site_settings` | 批量更新设置 |
| `reset_site_settings` | 重置设置 |
| `trigger_audit_log_archive` | 触发归档 |

---

## 日志字段说明

| 字段 | 说明 |
|------|------|
| `action` | 操作类型 |
| `resource_type` | 资源类型（user, team, agent 等） |
| `resource_id` | 资源 ID |
| `resource_name` | 资源名称 |
| `operation` | 操作（create, update, delete） |
| `status` | 状态（success, failed） |
| `ip_address` | 客户端 IP |
| `user_agent` | 客户端 User-Agent |
| `changes` | 变更内容（before/after） |
| `metadata` | 额外元数据 |
