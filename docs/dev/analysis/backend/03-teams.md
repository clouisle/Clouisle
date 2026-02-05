# 团队管理 API

**文件**: `backend/app/api/v1/endpoints/teams.py`
**路径前缀**: `/api/v1/teams`

## 概述

团队是 Clouisle 的核心多租户单元。资源（Agent、知识库、工作流等）都归属于团队，访问控制基于团队成员身份。

## 团队角色

| 角色 | 说明 |
|------|------|
| `OWNER` | 团队所有者，拥有全部权限，可转让所有权 |
| `ADMIN` | 团队管理员，可管理成员和资源 |
| `MEMBER` | 普通成员，可使用团队资源 |

## 接口列表

### GET /

获取团队列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:read` |
| 说明 | 获取所有团队列表（管理员）或用户所属团队 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词

---

### POST /

创建团队

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:create` |
| 说明 | 创建新团队，创建者自动成为所有者 |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)"
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "name": "string",
    "description": "string",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

**审计日志**: `create_team`

---

### GET /my

获取当前用户的团队

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:read` |
| 说明 | 获取当前用户所属的所有团队及其角色 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "string",
      "role": "OWNER",
      "joined_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

---

### GET /{team_id}

获取团队详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:read` + 团队成员 |
| 说明 | 获取团队详情及成员列表 |

**路径参数**:
- `team_id`: 团队 UUID

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "name": "string",
    "description": "string",
    "members": [
      {
        "user_id": "uuid",
        "username": "string",
        "role": "OWNER",
        "joined_at": "2024-01-01T00:00:00Z"
      }
    ],
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

---

### PUT /{team_id}

更新团队信息

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:update` + 团队所有者或管理员 |
| 说明 | 更新团队名称和描述 |

**路径参数**:
- `team_id`: 团队 UUID

**请求体**:
```json
{
  "name": "string (可选)",
  "description": "string (可选)"
}
```

**审计日志**: `update_team`

---

### DELETE /{team_id}

删除团队

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:delete` + 团队所有者 |
| 说明 | 删除团队及其所有资源 |

**路径参数**:
- `team_id`: 团队 UUID

**限制**:
- 不能删除默认团队

**审计日志**: `delete_team`

---

### POST /{team_id}/members

添加团队成员

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:manage` + 团队所有者或管理员 |
| 说明 | 添加用户到团队 |

**路径参数**:
- `team_id`: 团队 UUID

**请求体**:
```json
{
  "user_id": "uuid",
  "role": "MEMBER"
}
```

**错误码**:
- `5100`: 用户已是团队成员

**审计日志**: `add_team_member`

---

### PUT /{team_id}/members/{user_id}

更新成员角色

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:manage` + 团队所有者 |
| 说明 | 更新团队成员的角色 |

**路径参数**:
- `team_id`: 团队 UUID
- `user_id`: 用户 UUID

**请求体**:
```json
{
  "role": "ADMIN"
}
```

**限制**:
- 不能修改所有者的角色
- 不能将成员提升为所有者

---

### DELETE /{team_id}/members/{user_id}

移除团队成员

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:manage` + 团队所有者或管理员 |
| 说明 | 从团队中移除成员 |

**路径参数**:
- `team_id`: 团队 UUID
- `user_id`: 用户 UUID

**限制**:
- 不能移除所有者
- 管理员不能移除其他管理员

**审计日志**: `remove_team_member`

---

### POST /{team_id}/leave

离开团队

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:read` + 团队成员 |
| 说明 | 当前用户离开团队 |

**路径参数**:
- `team_id`: 团队 UUID

**限制**:
- 所有者不能离开团队（需先转让所有权）

---

### POST /{team_id}/transfer-ownership

转让所有权

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `team:manage` + 团队所有者 |
| 说明 | 将团队所有权转让给其他成员 |

**路径参数**:
- `team_id`: 团队 UUID

**请求体**:
```json
{
  "new_owner_id": "uuid"
}
```

**效果**:
- 新所有者角色变为 `OWNER`
- 原所有者角色变为 `ADMIN`

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `team:read` | 查看团队列表和详情 |
| `team:create` | 创建新团队 |
| `team:update` | 更新团队信息 |
| `team:delete` | 删除团队 |
| `team:manage` | 管理团队成员 |

---

## 访问控制矩阵

| 操作 | OWNER | ADMIN | MEMBER |
|------|-------|-------|--------|
| 查看团队 | ✓ | ✓ | ✓ |
| 更新团队 | ✓ | ✓ | ✗ |
| 删除团队 | ✓ | ✗ | ✗ |
| 添加成员 | ✓ | ✓ | ✗ |
| 移除成员 | ✓ | ✓* | ✗ |
| 更新成员角色 | ✓ | ✗ | ✗ |
| 转让所有权 | ✓ | ✗ | ✗ |
| 离开团队 | ✗** | ✓ | ✓ |

*管理员不能操作其他管理员或所有者
**所有者需先转让所有权才能离开
