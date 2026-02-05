# 权限管理 API

**文件**: `backend/app/api/v1/endpoints/permissions.py`
**路径前缀**: `/api/v1/permissions`

## 接口列表

### GET /

获取权限列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取所有可用权限 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "code": "user:read",
      "name": "Read Users",
      "description": "View user list and details",
      "scope": "user"
    }
  ]
}
```

---

### POST /

创建权限

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 创建新权限 |

**请求体**:
```json
{
  "code": "string",
  "name": "string",
  "description": "string (可选)",
  "scope": "string"
}
```

---

### GET /{permission_id}

获取权限详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取指定权限的详细信息 |

**路径参数**:
- `permission_id`: 权限 UUID

---

### PUT /{permission_id}

更新权限

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 更新权限信息 |

**路径参数**:
- `permission_id`: 权限 UUID

**请求体**:
```json
{
  "name": "string (可选)",
  "description": "string (可选)"
}
```

---

### DELETE /{permission_id}

删除权限

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `user:manage` |
| 说明 | 删除指定权限 |

**路径参数**:
- `permission_id`: 权限 UUID

**限制**:
- 不能删除通配符权限 (`*`)

---

## 权限范围

| 范围 | 说明 |
|------|------|
| `user` | 用户管理相关 |
| `model` | 模型管理相关 |
| `agent` | Agent 管理相关 |
| `apikey` | API Key 管理相关 |
| `team` | 团队管理相关 |
| `*` | 通配符，匹配所有 |
