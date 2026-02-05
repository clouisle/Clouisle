# 通知管理 API

**文件**: `backend/app/api/v1/endpoints/notifications.py`
**路径前缀**: `/api/v1/notifications`

## 概述

通知系统支持多种通知范围和投递渠道。

## 通知范围

| 范围 | 说明 |
|------|------|
| `GLOBAL` | 全局通知，所有用户可见 |
| `TEAM` | 团队通知，团队成员可见 |
| `USER` | 用户通知，指定用户可见 |

## 投递渠道

| 渠道 | 说明 |
|------|------|
| `EMAIL` | 邮件 |
| `DINGTALK` | 钉钉 |
| `WECHAT` | 企业微信 |
| `FEISHU` | 飞书 |
| `SLACK` | Slack |
| `WEBHOOK` | Webhook |

## 用户接口

### GET /

获取通知列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取当前用户的通知列表 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `is_read`: 是否已读

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "title": "string",
        "content": "string",
        "type": "info",
        "is_read": false,
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 10
  }
}
```

---

### GET /unread-count

获取未读数量

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取当前用户的未读通知数量 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "count": 5
  }
}
```

---

### POST /read

标记已读

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 标记通知为已读 |

**请求体**:
```json
{
  "notification_ids": ["uuid", "uuid"],
  "all": false
}
```

---

## 管理员接口

### GET /admin

获取所有通知（管理员）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取系统所有通知 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `scope`: 通知范围
- `search`: 搜索关键词

---

### POST /admin

创建通知（管理员）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 创建新通知 |

**请求体**:
```json
{
  "title": "string",
  "content": "string",
  "type": "info",
  "scope": "GLOBAL",
  "team_id": "uuid (TEAM 范围时必填)",
  "user_ids": ["uuid"] (USER 范围时必填),
  "channels": ["EMAIL", "DINGTALK"],
  "scheduled_at": "2024-01-01T00:00:00Z (可选)"
}
```

**通知类型**:
- `info`: 信息
- `warning`: 警告
- `error`: 错误
- `success`: 成功

---

### DELETE /admin/{notification_id}

删除通知（管理员）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 删除指定通知 |

**路径参数**:
- `notification_id`: 通知 UUID

---

## 投递机制

通知创建后通过 Celery 异步任务投递：

1. 站内通知：直接创建通知记录
2. 外部渠道：根据配置调用对应 API

### 投递状态

| 状态 | 说明 |
|------|------|
| `PENDING` | 待投递 |
| `SENT` | 已发送 |
| `FAILED` | 发送失败 |

---

## 权限说明

| 操作 | 普通用户 | 团队管理员 | 超级管理员 |
|------|----------|------------|------------|
| 查看自己的通知 | ✓ | ✓ | ✓ |
| 标记已读 | ✓ | ✓ | ✓ |
| 查看所有通知 | ✗ | ✗ | ✓ |
| 创建通知 | ✗ | ✗ | ✓ |
| 删除通知 | ✗ | ✗ | ✓ |
