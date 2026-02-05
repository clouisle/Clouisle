# 角色管理 API

**文件**: `backend/app/api/v1/endpoints/roles.py`
**路径前缀**: `/api/v1/roles`

## 接口列表

### GET /

获取角色列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取所有角色列表 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "string",
      "description": "string",
      "is_system": true,
      "permissions": ["user:read", "agent:create"],
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

---

### POST /

创建角色

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 创建新角色 |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)",
  "permissions": ["user:read", "agent:create"]
}
```

---

### GET /{role_id}

获取角色详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取指定角色的详细信息 |

**路径参数**:
- `role_id`: 角色 UUID

---

### PUT /{role_id}

更新角色

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 更新角色信息 |

**路径参数**:
- `role_id`: 角色 UUID

**请求体**:
```json
{
  "name": "string (可选)",
  "description": "string (可选)"
}
```

**限制**:
- 不能修改系统角色

---

### PUT /{role_id}/permissions

更新角色权限

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 更新角色的权限列表 |

**路径参数**:
- `role_id`: 角色 UUID

**请求体**:
```json
{
  "permissions": ["user:read", "user:create", "agent:read"]
}
```

**限制**:
- 不能修改系统角色的权限

---

### DELETE /{role_id}

删除角色

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 删除指定角色 |

**路径参数**:
- `role_id`: 角色 UUID

**限制**:
- 不能删除系统角色
- 不能删除正在使用的角色

---

## 系统角色

系统预置角色（`is_system: true`）不可修改或删除：

| 角色 | 说明 |
|------|------|
| Admin | 管理员，拥有所有权限 |
| User | 普通用户，基础权限 |

## 权限格式

权限采用 `scope:action` 格式：

| 范围 | 可用操作 |
|------|----------|
| `user` | `read`, `create`, `update`, `delete`, `manage` |
| `model` | `read`, `create`, `update`, `delete` |
| `agent` | `read`, `create`, `update`, `delete` |
| `apikey` | `read`, `create`, `update`, `delete` |
| `*` | 通配符，表示所有权限 |
