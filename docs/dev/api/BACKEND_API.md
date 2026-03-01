# Clouisle Backend API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **API Prefix**: `/api/v1`
- **认证方式**: Bearer Token (JWT)

---

## 多语言支持 (i18n)

API 支持多语言响应消息。通过请求头指定语言：

### 请求头

| Header | 说明 | 示例 |
|--------|------|------|
| `X-Language` | 首选语言（优先级高） | `zh`, `en` |
| `Accept-Language` | 标准语言头 | `zh-CN,zh;q=0.9,en;q=0.8` |

### 支持的语言

| 代码 | 语言 |
|------|------|
| `en` | English (默认) |
| `zh` | 中文 |

### 示例

**请求（中文）**:
```bash
curl -X POST "http://localhost:8000/api/v1/login/access-token" \
  -H "X-Language: zh" \
  -d "username=admin&password=admin123"
```

**响应**:
```json
{
  "code": 0,
  "data": {...},
  "msg": "登录成功"
}
```

**请求（英文）**:
```bash
curl -X POST "http://localhost:8000/api/v1/login/access-token" \
  -H "X-Language: en" \
  -d "username=admin&password=admin123"
```

**响应**:
```json
{
  "code": 0,
  "data": {...},
  "msg": "Login successful"
}
```

---

## 统一响应格式

所有接口返回统一格式：

```json
{
  "code": 0,        // 0=成功, 非0=错误码
  "data": {...},    // 响应数据
  "msg": "success"  // 消息
}
```

### 分页响应

```json
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

### 表单验证错误响应

当请求参数验证失败时（如格式错误、必填字段缺失等），返回字段级别的错误信息：

**HTTP 状态码**: `422`

```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": "value is not a valid email address: The part after the @-sign is not valid.",
      "username": "String should have at least 3 characters"
    }
  },
  "msg": "验证错误"
}
```

**字段说明**:
- `code`: 固定为 `1001` (VALIDATION_ERROR)
- `data.errors`: 字段名到错误消息的映射对象
  - key: 字段名（嵌套字段使用点号分隔，如 `user.email`）
  - value: 错误描述字符串，或错误描述数组（同一字段多个错误时）
- `msg`: 多语言提示消息

**前端处理建议**:
- 遍历 `data.errors` 对象
- 将错误消息显示在对应的表单输入框下方
- 支持显示多个字段的错误

### 业务错误响应

业务逻辑错误（如用户名已存在、权限不足等）：

**HTTP 状态码**: `400` / `401` / `403` / `404`

```json
{
  "code": 5001,
  "data": null,
  "msg": "用户名已被注册"
}
```
```

---

## 认证接口 (Auth)

### 登录

获取访问令牌。

- **URL**: `POST /api/v1/login/access-token`
- **Content-Type**: `application/x-www-form-urlencoded`
- **认证**: 不需要

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码 |

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/login/access-token" \
  -d "username=admin&password=admin123"
```

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  },
  "msg": "Login successful"
}
```

---

### 注册

注册新用户。新注册用户默认处于禁用状态，需要管理员审核激活后才能登录。

- **URL**: `POST /api/v1/register`
- **Content-Type**: `application/json`
- **认证**: 不需要

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| email | string | 是 | 邮箱 |
| password | string | 是 | 密码 |

**请求示例**:
```json
{
  "username": "newuser",
  "email": "newuser@example.com",
  "password": "password123"
}
```

**响应示例（普通用户注册）**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "newuser",
    "email": "newuser@example.com",
    "is_active": false,
    "is_superuser": false,
    "roles": []
  },
  "msg": "Registration successful. Your account is pending admin approval."
}
```

**特殊说明**: 
- 新注册用户 `is_active=false`，需要管理员通过激活接口审核
- 第一个注册的用户例外：自动获得 `is_active=true`、`is_superuser=true` 和 `Super Admin` 角色

---

## 用户接口 (Users)

> **注意**：用户管理接口（CRUD、激活/停用等）已迁移至管理侧路径 `/api/v1/admin/users/`。
> 以下自身操作接口保留在平台侧 `/api/v1/users/`。

### 获取当前用户信息

- **URL**: `GET /api/v1/users/me`
- **认证**: 需要

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "admin",
    "email": "admin@example.com",
    "is_active": true,
    "is_superuser": true,
    "created_at": "2025-12-22T10:00:00Z",
    "roles": [
      {
        "id": "...",
        "name": "Super Admin",
        "permissions": [
          {"id": "...", "code": "*", "scope": "system"}
        ]
      }
    ]
  },
  "msg": "success"
}
```

---

### 获取用户列表

- **URL**: `GET /api/v1/admin/users/`
- **认证**: 需要
- **权限**: `user:read`

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 |

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 50,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

---

### 获取指定用户

- **URL**: `GET /api/v1/admin/users/{user_id}`
- **认证**: 需要
- **权限**: `user:read`

---

### 创建用户

- **URL**: `POST /api/v1/admin/users/`
- **认证**: 需要
- **权限**: `user:create`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| email | string | 是 | 邮箱 |
| password | string | 是 | 密码 |
| is_active | bool | 否 | 是否激活，默认 true |
| is_superuser | bool | 否 | 是否超管，默认 false |

---

### 更新用户

- **URL**: `PUT /api/v1/admin/users/{user_id}`
- **认证**: 需要
- **权限**: `user:update`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 否 | 邮箱 |
| password | string | 否 | 新密码 |
| is_active | bool | 否 | 是否激活 |
| roles | string[] | 否 | 角色名称列表 |

---

### 激活用户

管理员审核通过新注册用户，激活账户。

- **URL**: `POST /api/v1/admin/users/{user_id}/activate`
- **认证**: 需要
- **权限**: `user:update`

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "newuser",
    "email": "newuser@example.com",
    "is_active": true,
    "is_superuser": false,
    "roles": []
  },
  "msg": "User activated successfully"
}
```

**错误响应**:
- `404`: 用户不存在
- `400`: 用户已经是激活状态

---

### 禁用用户

禁用用户账户，禁用后用户无法登录。

- **URL**: `POST /api/v1/admin/users/{user_id}/deactivate`
- **认证**: 需要
- **权限**: `user:update`

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "someuser",
    "email": "someuser@example.com",
    "is_active": false,
    "is_superuser": false,
    "roles": []
  },
  "msg": "User deactivated successfully"
}
```

**错误响应**:
- `404`: 用户不存在
- `400`: 用户已经是禁用状态
- `400`: 超级管理员不能被禁用

---

### 删除用户

- **URL**: `DELETE /api/v1/admin/users/{user_id}`
- **认证**: 需要
- **权限**: `user:delete`

**限制**: 超级管理员用户不可删除

---

## 角色接口 (Roles)

> 角色管理接口已迁移至管理侧路径 `/api/v1/admin/roles/`。

### 获取角色列表

- **URL**: `GET /api/v1/admin/roles/`
- **认证**: 需要

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 50 | 每页数量 |

---

### 获取指定角色

- **URL**: `GET /api/v1/admin/roles/{role_id}`
- **认证**: 需要

---

### 创建角色

- **URL**: `POST /api/v1/admin/roles/`
- **认证**: 需要
- **权限**: `user:manage`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 角色名称 |
| description | string | 否 | 描述 |
| permissions | string[] | 否 | 权限代码列表 |

**请求示例**:
```json
{
  "name": "Editor",
  "description": "Can edit content",
  "permissions": ["user:read", "user:update"]
}
```

---

### 更新角色

- **URL**: `PUT /api/v1/admin/roles/{role_id}`
- **认证**: 需要
- **权限**: `user:manage`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 角色名称 |
| description | string | 否 | 描述 |

**限制**: 系统角色不可修改

---

### 更新角色权限

- **URL**: `PUT /api/v1/admin/roles/{role_id}/permissions`
- **认证**: 需要
- **权限**: `user:manage`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| permissions | string[] | 是 | 权限代码列表（全量替换） |

**请求示例**:
```json
{
  "permissions": ["user:read", "user:create", "user:update"]
}
```

**限制**: 系统角色权限不可修改

---

### 删除角色

- **URL**: `DELETE /api/v1/admin/roles/{role_id}`
- **认证**: 需要
- **权限**: `user:manage`

**限制**: 
- 系统角色不可删除
- 已分配给用户的角色不可删除

---

## 权限接口 (Permissions)

> 权限管理接口已迁移至管理侧路径 `/api/v1/admin/permissions/`。

### 获取权限列表

- **URL**: `GET /api/v1/admin/permissions/`
- **认证**: 需要

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 50 | 每页数量 |
| scope | string | - | 按 scope 筛选 |

---

### 获取指定权限

- **URL**: `GET /api/v1/admin/permissions/{permission_id}`
- **认证**: 需要

---

### 创建权限

- **URL**: `POST /api/v1/admin/permissions/`
- **认证**: 需要
- **权限**: `user:manage`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 权限代码，格式: `scope:action` |
| scope | string | 是 | 权限范围 |
| description | string | 否 | 描述 |

**请求示例**:
```json
{
  "code": "kb:create",
  "scope": "kb",
  "description": "Create knowledge base"
}
```

---

### 更新权限

- **URL**: `PUT /api/v1/admin/permissions/{permission_id}`
- **认证**: 需要
- **权限**: `user:manage`

---

### 删除权限

- **URL**: `DELETE /api/v1/admin/permissions/{permission_id}`
- **认证**: 需要
- **权限**: `user:manage`

**限制**: 通配符权限 `*` 不可删除

---

## 团队接口 (Teams)

团队是资源隔离和协作的基本单位。每个团队有独立的成员和角色体系。

> **路由说明**：
> - 全量列表、创建、删除团队 → 管理侧 `/api/v1/admin/teams/`
> - 我的团队、团队详情、成员管理、离开、转让 → 平台侧 `/api/v1/teams/`

### 成员角色

| 角色 | 说明 |
|------|------|
| `owner` | 所有者，拥有团队全部权限，可删除团队、转让所有权 |
| `admin` | 管理员，可管理成员 |
| `member` | 普通成员 |
| `viewer` | 只读成员 |

---

### 获取所有团队（管理员）

- **URL**: `GET /api/v1/admin/teams/`
- **认证**: 需要
- **权限**: `team:read`

返回系统中所有团队（不限成员关系）。

---

### 创建团队（管理员）

- **URL**: `POST /api/v1/admin/teams/`
- **认证**: 需要
- **权限**: `team:create`

创建者自动成为团队 `owner`。

---

### 删除团队（管理员）

- **URL**: `DELETE /api/v1/admin/teams/{team_id}`
- **认证**: 需要
- **权限**: `team:delete`

**限制**: 默认团队不可删除

---

### 获取我的团队

- **URL**: `GET /api/v1/teams/my`
- **认证**: 需要

返回当前用户所属的所有团队及其角色。

**响应示例**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "My Team",
      "description": "Team description",
      "avatar_url": null,
      "role": "owner",
      "joined_at": "2025-12-22T10:00:00Z"
    }
  ],
  "msg": "success"
}
```

---

### 创建团队

- **URL**: `POST /api/v1/teams/`
- **认证**: 需要

创建者自动成为团队 `owner`。

> **注意**：此接口为平台侧，创建者成为 owner。管理员批量管理请使用 `/api/v1/admin/teams/`。

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 团队名称（唯一） |
| description | string | 否 | 团队描述 |
| avatar_url | string | 否 | 团队头像 URL |

**请求示例**:
```json
{
  "name": "Development Team",
  "description": "Core development team"
}
```

---

### 获取团队详情

- **URL**: `GET /api/v1/teams/{team_id}`
- **认证**: 需要
- **权限**: 需为团队成员

返回团队详情及成员列表。

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Development Team",
    "description": "Core development team",
    "avatar_url": null,
    "is_default": false,
    "owner": {
      "id": "...",
      "username": "admin",
      "email": "admin@example.com"
    },
    "created_at": "2025-12-22T10:00:00Z",
    "updated_at": "2025-12-22T10:00:00Z",
    "members": [
      {
        "id": "...",
        "user_id": "...",
        "username": "admin",
        "email": "admin@example.com",
        "role": "owner",
        "joined_at": "2025-12-22T10:00:00Z"
      }
    ]
  },
  "msg": "success"
}
```

---

### 更新团队

- **URL**: `PUT /api/v1/teams/{team_id}`
- **认证**: 需要
- **权限**: `owner` 或 `admin`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 团队名称 |
| description | string | 否 | 团队描述 |
| avatar_url | string | 否 | 团队头像 URL |

---

### 删除团队

- **URL**: `DELETE /api/v1/teams/{team_id}`
- **认证**: 需要
- **权限**: `owner` 或超级管理员

**限制**: 默认团队不可删除

---

### 添加团队成员

- **URL**: `POST /api/v1/teams/{team_id}/members`
- **认证**: 需要
- **权限**: `owner` 或 `admin`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | UUID | 是 | 要添加的用户 ID |
| role | string | 否 | 成员角色，默认 `member` |

**请求示例**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "admin"
}
```

**限制**: 不能直接添加为 `owner`

---

### 更新成员角色

- **URL**: `PUT /api/v1/teams/{team_id}/members/{user_id}`
- **认证**: 需要
- **权限**: `owner`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| role | string | 是 | 新角色 (`admin`, `member`, `viewer`) |

**限制**: 
- `owner` 角色不可更改
- 不能提升为 `owner`（需使用转让所有权接口）

---

### 移除团队成员

- **URL**: `DELETE /api/v1/teams/{team_id}/members/{user_id}`
- **认证**: 需要
- **权限**: `owner`/`admin` 或自己

**限制**: `owner` 不可被移除

---

### 离开团队

- **URL**: `POST /api/v1/teams/{team_id}/leave`
- **认证**: 需要

当前用户主动离开团队。

**限制**: `owner` 不能离开，需先转让所有权或删除团队

---

### 转让所有权

- **URL**: `POST /api/v1/teams/{team_id}/transfer-ownership`
- **认证**: 需要
- **权限**: `owner`

将团队所有权转让给另一个成员。原 owner 将变为 admin。

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| new_owner_id | UUID | 是 | 新所有者的用户 ID（必须是团队成员） |

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/teams/{team_id}/transfer-ownership?new_owner_id=550e8400..." \
  -H "Authorization: Bearer <token>"
```

---

## API 密钥接口 (API Keys)

API 密钥用于程序化访问 API，支持细粒度的权限控制和速率限制。

### 安全机制

- **密钥生成**: 使用 `secrets.token_urlsafe(32)` 生成 43 字符的安全随机密钥
- **密钥存储**: 仅存储密钥哈希值（使用密码哈希算法），原始密钥不保存
- **密钥前缀**: 保存前 12 个字符作为标识，便于用户识别
- **一次性显示**: 完整密钥仅在创建时返回一次，之后无法再获取

### 密钥格式

| 字段 | 说明 |
|------|------|
| key | 完整密钥，43 字符，格式如 `sk_abc123...` |
| key_prefix | 密钥前 12 字符，用于识别 |
| key_hash | 密钥哈希值，用于验证 |

---

### 获取 API 密钥列表

- **URL**: `GET /api/v1/api-keys/`
- **认证**: 需要
- **权限**: `apikey:read`

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 |
| user_id | UUID | - | 按用户筛选（管理员可用） |

**权限说明**:
- 超级管理员可查看所有密钥
- 普通用户只能查看自己的密钥
- 使用 `user_id` 参数筛选时，非管理员只能查看自己的密钥

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Production API Key",
        "key_prefix": "sk_abc123xyz",
        "user_id": "660e8400-e29b-41d4-a716-446655440001",
        "user": {
          "id": "660e8400-e29b-41d4-a716-446655440001",
          "username": "developer",
          "nickname": "Dev User"
        },
        "scopes": ["read", "write"],
        "rate_limit": 1000,
        "is_active": true,
        "expires_at": "2026-01-01T00:00:00Z",
        "last_used_at": "2025-01-15T10:30:00Z",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z"
      }
    ],
    "total": 10,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

---

### 获取 API 密钥统计

- **URL**: `GET /api/v1/api-keys/stats`
- **认证**: 需要
- **权限**: `apikey:read`

返回 API 密钥的统计信息。

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "total": 15,
    "active": 12,
    "inactive": 3
  },
  "msg": "success"
}
```

---

### 创建 API 密钥

- **URL**: `POST /api/v1/api-keys/`
- **认证**: 需要
- **权限**: `apikey:create`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 密钥名称（1-100 字符） |
| scopes | string[] | 否 | 权限范围列表，默认 `["read"]` |
| rate_limit | int | 否 | 速率限制（每分钟请求数），默认 `1000` |
| expires_at | datetime | 否 | 过期时间，留空表示永不过期 |

**请求示例**:
```json
{
  "name": "My API Key",
  "scopes": ["read", "write"],
  "rate_limit": 500,
  "expires_at": "2026-01-01T00:00:00Z"
}
```

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My API Key",
    "key": "sk_abc123xyz789def456ghi...",
    "key_prefix": "sk_abc123xyz7",
    "user_id": "660e8400-e29b-41d4-a716-446655440001",
    "user": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "username": "developer",
      "nickname": "Dev User"
    },
    "scopes": ["read", "write"],
    "rate_limit": 500,
    "is_active": true,
    "expires_at": "2026-01-01T00:00:00Z",
    "last_used_at": null,
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  },
  "msg": "API key created successfully"
}
```

⚠️ **重要**: 响应中的 `key` 字段包含完整密钥，**仅在创建时返回一次**，请妥善保存。

---

### 获取指定 API 密钥

- **URL**: `GET /api/v1/api-keys/{api_key_id}`
- **认证**: 需要
- **权限**: `apikey:read`

**权限说明**: 普通用户只能获取自己的密钥。

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My API Key",
    "key_prefix": "sk_abc123xyz7",
    "user_id": "660e8400-e29b-41d4-a716-446655440001",
    "user": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "username": "developer",
      "nickname": "Dev User"
    },
    "scopes": ["read", "write"],
    "rate_limit": 500,
    "is_active": true,
    "expires_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2025-01-15T10:30:00Z",
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  },
  "msg": "success"
}
```

---

### 更新 API 密钥

- **URL**: `PUT /api/v1/api-keys/{api_key_id}`
- **认证**: 需要
- **权限**: `apikey:update`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 密钥名称 |
| scopes | string[] | 否 | 权限范围列表 |
| rate_limit | int | 否 | 速率限制 |
| expires_at | datetime | 否 | 过期时间 |

**请求示例**:
```json
{
  "name": "Updated API Key Name",
  "rate_limit": 2000
}
```

**权限说明**: 普通用户只能更新自己的密钥。

---

### 删除 API 密钥

- **URL**: `DELETE /api/v1/api-keys/{api_key_id}`
- **认证**: 需要
- **权限**: `apikey:delete`

**权限说明**: 普通用户只能删除自己的密钥。

**响应示例**:
```json
{
  "code": 0,
  "data": null,
  "msg": "API key deleted successfully"
}
```

---

### 激活 API 密钥

- **URL**: `POST /api/v1/api-keys/{api_key_id}/activate`
- **认证**: 需要
- **权限**: `apikey:update`

**权限说明**: 普通用户只能激活自己的密钥。

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My API Key",
    "is_active": true,
    ...
  },
  "msg": "API key activated successfully"
}
```

**错误响应**:
- `404`: 密钥不存在
- `400`: 密钥已经是激活状态

---

### 禁用 API 密钥

- **URL**: `POST /api/v1/api-keys/{api_key_id}/deactivate`
- **认证**: 需要
- **权限**: `apikey:update`

**权限说明**: 普通用户只能禁用自己的密钥。

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My API Key",
    "is_active": false,
    ...
  },
  "msg": "API key deactivated successfully"
}
```

**错误响应**:
- `404`: 密钥不存在
- `400`: 密钥已经是禁用状态

---

## 内置数据

### 系统权限

| Code | Scope | 说明 |
|------|-------|------|
| `*` | system | 所有权限（超级管理员） |
| `user:read` | user | 读取用户 |
| `user:create` | user | 创建用户 |
| `user:update` | user | 更新用户 |
| `user:delete` | user | 删除用户 |
| `user:manage` | user | 管理用户、角色、权限 |
| `apikey:read` | apikey | 读取 API 密钥 |
| `apikey:create` | apikey | 创建 API 密钥 |
| `apikey:update` | apikey | 更新 API 密钥 |
| `apikey:delete` | apikey | 删除 API 密钥 |

### 系统角色

| 名称 | 权限 | 说明 |
|------|------|------|
| Super Admin | `*` | 完全控制，拥有所有权限 |
| Viewer | `user:read` | 只读访问 |

---

## 错误响应

所有错误响应都遵循统一响应格式：

```json
{
  "code": 1001,
  "data": null,
  "msg": "Error message here"
}
```

### 错误码 (ResponseCode)

| 范围 | 类别 | 枚举值 |
|------|------|--------|
| 0 | 成功 | `SUCCESS` |
| 1000-1999 | 通用错误 | `UNKNOWN_ERROR` (1000), `VALIDATION_ERROR` (1001) |
| 2000-2999 | 认证错误 | `UNAUTHORIZED` (2000), `INVALID_TOKEN` (2001), `TOKEN_EXPIRED` (2002), `INVALID_CREDENTIALS` (2003), `INACTIVE_USER` (2004) |
| 3000-3999 | 权限错误 | `PERMISSION_DENIED` (3000), `INSUFFICIENT_PRIVILEGES` (3001) |
| 4000-4999 | 资源错误 | `NOT_FOUND` (4000), `USER_NOT_FOUND` (4001), `ROLE_NOT_FOUND` (4002), `PERMISSION_NOT_FOUND` (4003) |
| 5000-5999 | 业务逻辑错误 | `ALREADY_EXISTS` (5000), `USERNAME_EXISTS` (5001), `EMAIL_EXISTS` (5002), `CANNOT_DELETE_SYSTEM_ROLE` (5010), `ROLE_IN_USE` (5020) |

### 常见 HTTP 状态码

| 状态码 | 说明 | 响应 code 范围 |
|--------|------|----------------|
| 200 | 成功 | 0 |
| 400 | 请求错误（参数错误、业务规则违反） | 1000, 5000-5999 |
| 401 | 未认证 | 2000-2002 |
| 403 | 无权限 | 3000-3001 |
| 404 | 资源不存在 | 4000-4999 |
| 422 | 验证错误 | 1001 |
| 500 | 服务器内部错误 | 1000 |

### 错误响应示例

**验证错误 (422)**:
```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": "value is not a valid email address",
      "password": "String should have at least 6 characters"
    }
  },
  "msg": "验证错误"
}
```

**业务错误 (400)**:
```json
{
  "code": 5001,
  "data": null,
  "msg": "用户名已被注册"
}
```

**认证错误 (401)**:
```json
{
  "code": 2000,
  "data": null,
  "msg": "未授权"
}
```

**权限错误 (403)**:
```json
{
  "code": 3000,
  "data": null,
  "msg": "权限被拒绝"
}
```

**资源不存在 (404)**:
```json
{
  "code": 4001,
  "data": null,
  "msg": "用户未找到"
}
```

---

## 认证使用

在需要认证的接口中，添加 Header:

```
Authorization: Bearer <access_token>
```

示例:
```bash
curl -X GET "http://localhost:8000/api/v1/users/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```
