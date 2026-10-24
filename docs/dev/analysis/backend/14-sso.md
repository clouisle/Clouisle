# SSO 单点登录 API

**文件**: `backend/app/api/v1/endpoints/sso.py`
**路径前缀**: `/api/v1/sso`

管理侧见 `backend/app/api/v1/admin/endpoints/integrations.py`（登录集成实例）、
`integration_settings.py`（全局登录策略 `/login-settings`）与 `feishu.py`
（飞书应用配置与目录同步，settings 域）。
完整面向管理员与 API 消费者的说明见
[集成与 SSO 配置指南](../../../guide/admin-guide/settings/SSO.md)与
[SSO 与集成 API](../../../guide/api-reference/endpoints/sso.md)。

## 概述

SSO 支持多种协议，允许用户通过第三方身份提供商登录。
登录身份源是统一 Integration 模型中 `user_login` 能力已启用的记录，
`oauth2`/`oidc`/`saml2`/`cas` 与飞书（`feishu`，显式 opt-in）共享同一套
登录/回调端点。

## 支持的协议

| provider_type | 说明 |
|------|------|
| `oauth2` | OAuth 2.0 |
| `oidc` | OpenID Connect |
| `saml2` | SAML 2.0 |
| `cas` | CAS 协议 |
| `feishu` | 飞书网页登录（PKCE 授权码流程，需在飞书集成上显式开启 `user_login`） |

## 公开接口

### GET /integrations

获取已启用的登录集成列表（用于登录页面渲染按钮）。

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 只返回已启用且 `user_login` 在已启用能力中的集成；全局 SSO 关闭时返回空列表 |

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "name": "github",
      "display_name": "GitHub",
      "icon_url": "https://cdn.example.com/github.svg",
      "button_text": "Continue with GitHub",
      "provider_type": "oauth2"
    }
  ]
}
```

---

### GET /login/{provider_name}

发起 SSO 登录。

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 307 重定向到身份提供商授权地址 |

**路径参数**:
- `provider_name`: 集成名称（即注册回调 URL 中的 slug）

**查询参数**:
- `redirect`: 登录成功后的前端站内路径（相对路径才有效，缺失或非法回退 `/app`，与角色无关）

**响应**: 307 重定向到身份提供商；同时创建 10 分钟有效的临时 SSO 会话
（PKCE verifier、nonce 或 relay state）。

未知/禁用集成与初始化失败重定向到前端：
`{frontend}/sso-callback?error=<error_code>&redirect=<path>`
（`sso_provider_not_found`、`sso_login_failed`）。

---

### GET /callback/{provider_name}

身份提供商回调。

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 处理身份提供商的回调，成功后带 JWT 回前端 |

| 协议 | 参数 |
|------|------|
| `oauth2` / `oidc` / `feishu` | `code`、`state` |
| `cas` | `ticket`（及 `state`） |
| `saml2` | `SAMLResponse`、`RelayState` |

**响应**: 307 重定向到前端，携带 JWT Token：
`{frontend}/sso-callback?token=<access_token>&redirect=<path>`；
失败（会话过期、提供商错误、账号未激活/待审批）携带 `error` 参数
（`sso_provider_not_found`、`sso_session_expired`、`sso_login_failed`、
`pending_approval`、`inactive`）。

**流程**:
1. 验证 state/nonce（飞书用 PKCE code_verifier 换 token）
2. 获取用户信息（飞书取 `union_id`，缺失时回退 `open_id` 作为 `provider_user_id`；
   无目录邮箱时复用目录同步的确定性占位邮箱）
3. 查找或创建用户
4. 生成 JWT Token
5. 重定向到前端

---

## 管理员接口

登录集成实例管理挂在 `/api/v1/admin/integrations`（`admin:integrations:login:read/update`），
全局登录策略在 `/login-settings`（UI 入口：**站点设置 → 安全**），
飞书应用配置与目录同步在 `/feishu/*`（settings 域）。
旧 `/admin/providers` 命名空间与 `/sso/providers` 已移除，无兼容别名。

## 用户 SSO 连接

### DELETE /connections/{connection_id}

断开 SSO 连接。

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 断开自己的某条身份连接；无密码账号不能删除唯一的认证方式 |

**路径参数**:
- `connection_id`: 连接 UUID

---

## 协议配置示例

### OIDC (OpenID Connect)

`config` 放非敏感字段，secret 进 `credentials`：

```json
{
  "name": "company",
  "provider_type": "oidc",
  "is_enabled": true,
  "enabled_capabilities": ["user_login"],
  "config": {
    "client_id": "xxx",
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
    "scopes": "openid profile email"
  },
  "credentials": {"client_secret": "xxx"},
  "attribute_mapping": {"email": "email", "username": "name"},
  "login_config": {"allow_signup": true, "require_approval": false}
}
```

### SAML2

```json
{
  "config": {
    "entity_id": "https://your-app.com/saml",
    "sso_url": "https://idp.example.com/sso",
    "certificate": "-----BEGIN CERTIFICATE-----\n..."
  }
}
```

### 飞书登录

不新建集成：在飞书单例集成上把 `user_login` 加入 `enabled_capabilities`
（login 域授权），回调地址沿用该集成的
`/api/v1/sso/callback/<integration-name>`，并在飞书开放平台把该地址加入重定向白名单。
详见[配置飞书登录](../../../guide/admin-guide/settings/SSO.md#configure-feishu-sign-in)。

---

## 安全机制

1. **State 参数**: 防止 CSRF 攻击
2. **Nonce 参数**: 防止重放攻击（OIDC）；飞书用 PKCE
3. **会话管理**: 临时 SSO 会话 10 分钟过期，与本地会话关联
4. **安全检查**: 禁用密码登录前确保有超级管理员绑定 SSO
5. **凭据边界**: 管理响应只暴露 `credentials_configured` 字段名与
   `supported_capabilities`，不返回凭据明文或密文
