# 用户管理 API

**文件**: `backend/app/api/v1/endpoints/users.py`
**路径前缀**: `/api/v1/users`

## 接口列表

### GET /

获取用户列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:read` |
| 说明 | 分页获取用户列表，支持多种筛选条件 |

**查询参数**:
- `page`: 页码（默认 1）
- `page_size`: 每页数量（默认 20）
- `search`: 搜索关键词（用户名、邮箱、全名）
- `is_active`: 是否激活
- `is_superuser`: 是否超级管理员
- `role_id`: 角色 ID

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "username": "string",
        "email": "string",
        "full_name": "string",
        "is_active": true,
        "is_superuser": false,
        "role": {...},
        "sso_connections": [...]
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

---

### GET /stats

获取用户统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:read` |
| 说明 | 获取用户相关统计数据 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "total": 100,
    "active": 95,
    "inactive": 5,
    "superusers": 2,
    "pending_approval": 3
  }
}
```

---

### POST /

创建用户

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:create` |
| 说明 | 管理员创建新用户 |

**请求体**:
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "full_name": "string (可选)",
  "is_active": true,
  "is_superuser": false,
  "role_id": "uuid (可选)"
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "username": "string",
    "email": "string"
  }
}
```

**审计日志**: `create_user`

---

### POST /send-email

批量发送邮件

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:update` |
| 说明 | 向选定用户发送邮件 |

**请求体**:
```json
{
  "user_ids": ["uuid", "uuid"],
  "subject": "string",
  "content": "string"
}
```

**限流**:
- 发送者: 100 封/小时
- 每个收件人: 5 封/天

---

### GET /me

获取当前用户信息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取当前登录用户的详细信息 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "full_name": "string",
    "avatar": "string",
    "is_active": true,
    "is_superuser": false,
    "role": {...},
    "permissions": ["user:read", "agent:create"],
    "sso_connections": [
      {
        "provider_id": "uuid",
        "provider_name": "Google",
        "connected_at": "2024-01-01T00:00:00Z"
      }
    ]
  }
}
```

---

### PUT /me

更新当前用户信息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 更新当前用户的个人信息 |

**请求体**:
```json
{
  "full_name": "string (可选)",
  "avatar": "string (可选)"
}
```

**审计日志**: `update_user`

---

### POST /me/change-password

修改密码

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 修改当前用户密码 |

**请求体**:
```json
{
  "current_password": "string",
  "new_password": "string"
}
```

**错误码**:
- `2001`: 当前密码错误

**审计日志**: `change_password`

---

### DELETE /me

删除当前账户

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 用户自行删除账户（需站点设置允许） |

**请求体**:
```json
{
  "password": "string"
}
```

**错误码**:
- `5200`: 账户删除已禁用
- `2001`: 密码错误

---

### GET /{user_id}

获取指定用户信息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:read` |
| 说明 | 获取指定用户的详细信息 |

**路径参数**:
- `user_id`: 用户 UUID

---

### POST /{user_id}/activate

激活用户

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:update` |
| 说明 | 激活用户账户（管理员审批） |

**路径参数**:
- `user_id`: 用户 UUID

**审计日志**: `activate_user`

---

### POST /{user_id}/deactivate

停用用户

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:update` |
| 说明 | 停用用户账户 |

**路径参数**:
- `user_id`: 用户 UUID

**限制**:
- 不能停用超级管理员

**审计日志**: `deactivate_user`

---

### PUT /{user_id}

更新用户信息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:update` |
| 说明 | 管理员更新用户信息 |

**路径参数**:
- `user_id`: 用户 UUID

**请求体**:
```json
{
  "username": "string (可选)",
  "email": "string (可选)",
  "full_name": "string (可选)",
  "is_active": true,
  "is_superuser": false,
  "role_id": "uuid (可选)",
  "password": "string (可选，重置密码)"
}
```

**审计日志**: `update_user`

---

### DELETE /{user_id}

删除用户

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:delete` |
| 说明 | 删除指定用户 |

**路径参数**:
- `user_id`: 用户 UUID

**限制**:
- 不能删除超级管理员
- 不能删除自己

**审计日志**: `delete_user`

---

## 权限说明

| 权限 | 说明 |
|------|------|
| `user:read` | 查看用户列表和详情 |
| `user:create` | 创建新用户 |
| `user:update` | 更新用户信息、激活/停用用户 |
| `user:delete` | 删除用户 |
| `user:manage` | 管理角色和权限 |

## SSO 连接

用户响应中包含 SSO 连接信息：
- `provider_id`: SSO 提供商 ID
- `provider_name`: 提供商名称
- `connected_at`: 连接时间

用户可以通过 SSO API 断开连接。
