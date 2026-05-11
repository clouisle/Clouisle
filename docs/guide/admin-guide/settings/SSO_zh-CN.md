# SSO 配置指南

本指南介绍如何在 Clouisle 中配置单点登录（SSO），并以 GitHub 为例进行详细说明。

---

## 目录

- [概述](#概述)
- [支持的协议](#支持的协议)
- [前置条件](#前置条件)
- [第一步：启用 SSO](#第一步启用-sso)
- [第二步：创建 SSO 提供商](#第二步创建-sso-提供商)
  - [示例：GitHub OAuth](#示例github-oauth)
- [第三步：测试连接](#第三步测试连接)
- [第四步：验证登录](#第四步验证登录)
- [提供商配置参考](#提供商配置参考)
  - [OAuth2 / OIDC](#oauth2--oidc)
  - [SAML 2.0](#saml-20)
  - [CAS](#cas)
- [属性映射](#属性映射)
  - [点号路径](#点号路径)
  - [JSONPath](#jsonpath)
- [站点设置](#站点设置)
- [API 参考](#api-参考)
- [常见问题](#常见问题)

---

## 概述

Clouisle 支持 SSO 认证，允许用户通过 GitHub、Google、Azure AD、Okta 等外部身份提供商登录。SSO 可以与密码登录并存，也可以作为唯一的登录方式。

登录流程如下：

1. 用户在登录页面点击 SSO 提供商按钮
2. 浏览器跳转到提供商的授权页面
3. 用户在提供商处完成认证
4. 提供商携带授权码回调到 Clouisle
5. Clouisle 用授权码换取用户信息
6. 用户登录成功（或自动创建新账号）

## 支持的协议

| 协议 | 适用场景 | 示例 |
|------|----------|------|
| OAuth2 / OIDC | 大多数现代提供商 | GitHub、Google、Azure AD、Okta、Auth0 |
| SAML 2.0 | 企业身份提供商 | Azure AD、Okta、OneLogin、ADFS |
| CAS | 高校 / 机构 SSO | Apereo CAS |

## 前置条件

- Clouisle 已部署并可通过公网 URL 访问（SSO 需要提供商能够回调到你的服务）
- `API_BASE_URL` 和 `FRONTEND_URL` 环境变量已设置为实际域名（如 `https://example.com`）
- 拥有超级管理员权限的账号

---

## 第一步：启用 SSO

1. 以管理员身份登录，进入 **站点设置** -> **安全**
2. 在 **SSO 设置** 区域，开启 **启用 SSO**
3. 配置全局 SSO 行为：

| 设置 | 默认值 | 说明 |
|------|--------|------|
| 允许密码登录 | 开启 | SSO 启用后仍保留密码登录 |
| 自动创建用户 | 开启 | 首次 SSO 登录时自动创建账号 |
| 需要审批 | 关闭 | 新 SSO 用户需要管理员审批 |
| 邮箱匹配 | 开启 | 通过邮箱将 SSO 账号关联到已有用户 |

4. 点击 **保存**

**注意**：如果关闭 **允许密码登录**，至少需要一个超级管理员已绑定 SSO 账号，以防止所有管理员被锁定在系统外。

---

## 第二步：创建 SSO 提供商

### 示例：GitHub OAuth

#### 2.1 在 GitHub 注册 OAuth 应用

1. 进入 GitHub：**Settings** -> **Developer settings** -> **OAuth Apps** -> **New OAuth App**
2. 填写表单：

| 字段 | 值 |
|------|-----|
| Application name | `Clouisle`（或任意名称） |
| Homepage URL | `https://your-domain.com` |
| Authorization callback URL | `https://your-domain.com/api/v1/sso/callback/github` |

> 回调 URL 格式为 `{API_BASE_URL}/api/v1/sso/callback/{provider_name}`，其中 `provider_name` 必须与你在 Clouisle 中设置的提供商名称一致（见下一步）。

3. 点击 **Register application**
4. 复制 **Client ID**
5. 点击 **Generate a new client secret** 并复制 **Client Secret**

#### 2.2 在 Clouisle 中添加提供商

1. 进入 **站点设置** -> **SSO**
2. 点击 **添加提供商**
3. 在 **基本信息** 标签页中填写：

| 字段 | 值 |
|------|-----|
| 提供商名称 | `github` |
| 协议 | `OAuth2/OIDC` |
| 显示名称 | `GitHub` |
| 按钮文本 | `使用 GitHub 登录` |
| 图标 URL | `https://github.githubassets.com/favicons/favicon-dark.svg` |
| 启用 | 开启 |
| 允许注册 | 开启 |

4. 切换到 **配置** 标签页，输入：

```json
{
  "client_id": "你的-github-client-id",
  "client_secret": "你的-github-client-secret",
  "authorization_url": "https://github.com/login/oauth/authorize",
  "token_url": "https://github.com/login/oauth/access_token",
  "userinfo_url": "https://api.github.com/user",
  "scopes": "read:user user:email"
}
```

5. 切换到 **属性映射** 标签页，输入：

```json
{
  "email": "email",
  "username": "login",
  "avatar_url": "avatar_url"
}
```

> GitHub 使用 `login` 作为用户名字段，`avatar_url` 作为头像字段。默认映射使用的 `name` 和 `picture`（OIDC 标准声明）不适用于 GitHub 的响应格式。

6. 点击 **保存**

---

## 第三步：测试连接

1. 在 **SSO** 设置页面，找到 GitHub 提供商
2. 点击 **测试连接** 按钮（烧瓶图标）
3. 显示成功消息表示配置有效

测试会验证 Clouisle 能否使用提供的配置构建有效的授权 URL，但不会执行完整的登录流程。

---

## 第四步：验证登录

1. 打开新的浏览器或无痕窗口
2. 访问登录页面
3. 密码表单下方应出现 **使用 GitHub 登录** 按钮
4. 点击按钮并完成 GitHub 授权
5. 授权完成后自动跳转回 Clouisle 并登录成功

如果启用了 **自动创建用户**，首次登录时会自动创建新账号。如果启用了 **邮箱匹配** 且已有相同邮箱的用户，SSO 账号会自动关联到已有用户。

---

## 提供商配置参考

### OAuth2 / OIDC

| 字段 | 必填 | 说明 |
|------|------|------|
| `client_id` | 是 | 提供商的 OAuth2 Client ID |
| `client_secret` | 是 | 提供商的 OAuth2 Client Secret |
| `authorization_url` | 是 | 提供商的授权端点 |
| `token_url` | 是 | 提供商的令牌交换端点 |
| `userinfo_url` | 是 | 提供商的用户信息端点 |
| `scopes` | 否 | 空格分隔的权限范围（默认：`openid email profile`） |

**常见提供商 URL：**

| 提供商 | authorization_url | token_url | userinfo_url |
|--------|-------------------|-----------|--------------|
| GitHub | `https://github.com/login/oauth/authorize` | `https://github.com/login/oauth/access_token` | `https://api.github.com/user` |
| Google | `https://accounts.google.com/o/oauth2/v2/auth` | `https://oauth2.googleapis.com/token` | `https://openidconnect.googleapis.com/v1/userinfo` |
| GitLab | `https://gitlab.com/oauth/authorize` | `https://gitlab.com/oauth/token` | `https://gitlab.com/api/v4/user` |

### SAML 2.0

| 字段 | 必填 | 说明 |
|------|------|------|
| `sp_entity_id` | 是 | 服务提供商实体 ID（你的 Clouisle 实例标识） |
| `idp_entity_id` | 是 | 身份提供商实体 ID |
| `sso_url` | 是 | IdP 单点登录 URL |
| `x509_cert` | 是 | IdP X.509 证书（PEM 格式，不含头尾标记） |
| `acs_url` | 是 | 断言消费服务 URL（`{API_BASE_URL}/api/v1/sso/callback/{provider_name}`） |
| `slo_url` | 否 | SP 单点登出 URL |
| `idp_slo_url` | 否 | IdP 单点登出 URL |
| `name_id_format` | 否 | NameID 格式（默认：`urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified`） |

### CAS

| 字段 | 必填 | 说明 |
|------|------|------|
| `server_url` | 是 | CAS 服务器基础 URL |
| `service_url` | 是 | CAS 验证的服务 URL |
| `version` | 否 | CAS 协议版本：`1`、`2` 或 `3`（默认：`3`） |

---

## 属性映射

属性映射定义了提供商用户数据字段如何映射到 Clouisle 用户字段。支持的 Clouisle 字段：

| Clouisle 字段 | 说明 |
|---------------|------|
| `email` | 用户邮箱 |
| `username` | 用户名 |
| `avatar_url` | 头像 URL |

### 点号路径

对于简单的嵌套对象，使用点号分隔的路径：

```json
{
  "email": "email",
  "username": "profile.name",
  "avatar_url": "profile.picture"
}
```

这会从提供商响应中提取 `data["profile"]["name"]`。

### JSONPath

对于复杂的数据结构（数组、嵌套），使用以 `$` 开头的 JSONPath 表达式：

```json
{
  "email": "$.emails[0].value",
  "username": "$.name.givenName",
  "avatar_url": "$.photos[0].value"
}
```

当提供商返回如下结构的数据时，JSONPath 非常有用：

```json
{
  "emails": [
    {"value": "user@example.com", "primary": true},
    {"value": "alias@example.com", "primary": false}
  ],
  "name": {"givenName": "John", "familyName": "Doe"},
  "photos": [{"value": "https://example.com/photo.jpg"}]
}
```

当 JSONPath 表达式匹配到多个值时，取第一个匹配结果。

**注意**：不以 `$` 开头的路径按点号路径处理，完全向后兼容。已有的映射如 `{"email": "email"}` 无需修改。

---

## 站点设置

以下全局设置控制所有提供商的 SSO 行为，在 **站点设置** -> **安全** 中配置。

| 设置 | 默认值 | 说明 |
|------|--------|------|
| `sso_enabled` | `false` | SSO 总开关。关闭时登录页面不显示 SSO 按钮。 |
| `sso_allow_password_login` | `true` | SSO 启用后是否允许密码登录。关闭后 SSO 成为唯一登录方式。 |
| `sso_auto_create_users` | `true` | 首次 SSO 登录时是否自动创建用户账号。 |
| `sso_require_approval` | `false` | 新 SSO 用户是否需要管理员审批。 |
| `sso_match_by_email` | `true` | 是否通过邮箱将 SSO 用户匹配到已有账号。 |

每个提供商还有独立的 **允许注册** 和 **需要审批** 设置，可以覆盖全局默认值。

---

## API 参考

### 公开接口

```http
GET /api/v1/sso/providers
```

返回已启用的 SSO 提供商列表（用于渲染登录按钮）。

```http
GET /api/v1/sso/login/{provider_name}?redirect=/dashboard
```

发起 SSO 登录流程，浏览器跳转到提供商的授权页面。

```http
GET /api/v1/sso/callback/{provider_name}
```

处理提供商回调。此 URL 在提供商注册应用时用作回调地址。

### 管理接口

所有管理接口需要超级管理员认证。

```http
GET    /api/v1/sso/admin/providers
POST   /api/v1/sso/admin/providers
PUT    /api/v1/sso/admin/providers/{provider_id}
DELETE /api/v1/sso/admin/providers/{provider_id}
POST   /api/v1/sso/admin/providers/{provider_id}/test
```

### 创建提供商示例

```http
POST /api/v1/sso/admin/providers
Content-Type: application/json

{
  "name": "github",
  "protocol": "oidc",
  "display_name": "GitHub",
  "button_text": "使用 GitHub 登录",
  "icon_url": "https://github.githubassets.com/favicons/favicon-dark.svg",
  "config": {
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "authorization_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "userinfo_url": "https://api.github.com/user",
    "scopes": "read:user user:email"
  },
  "attribute_mapping": {
    "email": "email",
    "username": "login",
    "avatar_url": "avatar_url"
  },
  "is_enabled": true,
  "allow_signup": true,
  "require_approval": false
}
```

响应：

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "github",
    "protocol": "oidc",
    "display_name": "GitHub",
    "is_enabled": true,
    "created_at": "2026/02/09 10:00"
  },
  "msg": "success"
}
```

---

## 常见问题

### 登录页面没有出现 SSO 按钮

- 确认 **站点设置** -> **安全** 中已开启 **启用 SSO**
- 确认提供商的 **启用** 开关已打开
- 检查 `FRONTEND_URL` 和 `API_BASE_URL` 环境变量是否正确设置

### 回调 URL 不匹配错误

在提供商处注册的回调 URL 必须与以下格式完全一致：

```
{API_BASE_URL}/api/v1/sso/callback/{provider_name}
```

- `API_BASE_URL` 是后端 URL（如果前端代理了 `/api/*` 到后端，则为 `https://example.com`；如果后端有独立域名，则为 `https://api.example.com`）
- `provider_name` 是你在 Clouisle 中创建提供商时设置的名称（如 `github`）

### SSO 登录后跳转到错误页面

查看后端日志获取详细信息：

```bash
# Docker Compose
docker compose logs api | grep sso

# Kubernetes
kubectl -n clouisle logs deployment/api | grep sso
```

常见原因：
- **SSO 会话过期**：用户在 10 分钟内未完成认证，请重试。
- **Client Secret 错误**：提供商配置中的 `client_secret` 不正确。
- **权限范围未授权**：请求的 scopes 未在提供商的 OAuth 应用设置中启用。

### 用户创建成功但邮箱为空

提供商可能未在预期字段中返回邮箱。请查阅提供商的 API 文档并更新属性映射。对于 GitHub，确保 scopes 中包含 `read:user user:email`，并注意如果用户将邮箱设为私密，GitHub 可能返回 `null`。

### "无法解除唯一的认证方式"

通过 SSO 登录且未设置密码的用户无法解除 SSO 关联，否则将无法登录。请先通过管理面板为用户设置密码，再解除 SSO 关联。
