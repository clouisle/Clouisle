# SSO 单点登录 API

**文件**: `backend/app/api/v1/endpoints/sso.py`
**路径前缀**: `/api/v1/sso`

## 概述

SSO 支持多种协议，允许用户通过第三方身份提供商登录。

## 支持的协议

| 协议 | 说明 |
|------|------|
| `OAUTH2` | OAuth 2.0 |
| `OIDC` | OpenID Connect |
| `SAML2` | SAML 2.0 |
| `CAS` | CAS 协议 |

## 公开接口

### GET /providers

获取 SSO 提供商列表

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 获取已启用的 SSO 提供商列表（用于登录页面） |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "Google",
      "protocol": "OIDC",
      "icon": "google.svg"
    }
  ]
}
```

---

### GET /login/{provider_id}

发起 SSO 登录

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 重定向到 SSO 提供商进行认证 |

**路径参数**:
- `provider_id`: 提供商 UUID

**查询参数**:
- `redirect_uri`: 登录成功后的回调地址

**响应**: 302 重定向到 SSO 提供商

---

### GET /callback/{provider_id}

SSO 回调

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 处理 SSO 提供商的回调 |

**路径参数**:
- `provider_id`: 提供商 UUID

**查询参数**:
- `code`: 授权码（OAuth2/OIDC）
- `state`: 状态参数
- `SAMLResponse`: SAML 响应（SAML2）

**响应**: 302 重定向到前端，携带 JWT Token

**流程**:
1. 验证 state/nonce
2. 获取用户信息
3. 查找或创建用户
4. 生成 JWT Token
5. 重定向到前端

---

## 管理员接口

### GET /admin/providers

获取所有提供商（管理员）

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取所有 SSO 提供商配置 |

---

### POST /admin/providers

创建提供商

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 创建新 SSO 提供商 |

**请求体**:
```json
{
  "name": "string",
  "protocol": "OIDC",
  "is_enabled": true,
  "config": {
    "client_id": "string",
    "client_secret": "string",
    "authorization_url": "string",
    "token_url": "string",
    "userinfo_url": "string",
    "scopes": ["openid", "profile", "email"]
  },
  "attribute_mapping": {
    "id": "sub",
    "email": "email",
    "name": "name"
  }
}
```

---

### PUT /admin/providers/{provider_id}

更新提供商

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 更新 SSO 提供商配置 |

**路径参数**:
- `provider_id`: 提供商 UUID

---

### DELETE /admin/providers/{provider_id}

删除提供商

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 删除 SSO 提供商 |

**路径参数**:
- `provider_id`: 提供商 UUID

---

### POST /admin/providers/{provider_id}/test

测试连接

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 测试 SSO 提供商连接 |

**路径参数**:
- `provider_id`: 提供商 UUID

---

## 用户 SSO 连接

### GET /connections

获取当前用户的 SSO 连接

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 获取当前用户绑定的 SSO 账户 |

---

### DELETE /connections/{connection_id}

断开 SSO 连接

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 断开与 SSO 提供商的绑定 |

**路径参数**:
- `connection_id`: 连接 UUID

---

## 协议配置示例

### OIDC (OpenID Connect)

```json
{
  "client_id": "xxx",
  "client_secret": "xxx",
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
  "token_url": "https://oauth2.googleapis.com/token",
  "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
  "scopes": ["openid", "profile", "email"]
}
```

### SAML2

```json
{
  "entity_id": "https://your-app.com/saml",
  "sso_url": "https://idp.example.com/sso",
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "name_id_format": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
}
```

---

## 安全机制

1. **State 参数**: 防止 CSRF 攻击
2. **Nonce 参数**: 防止重放攻击（OIDC）
3. **会话管理**: SSO 会话与本地会话关联
4. **安全检查**: 禁用密码登录前确保有超级管理员绑定 SSO
