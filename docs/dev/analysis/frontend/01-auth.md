# 认证页面

路由分组: `(auth)`

## /login - 登录页面

**文件位置**: `frontend/app/(auth)/login/page.tsx`

**页面作用**: 用户登录入口，支持用户名密码登录和 SSO 登录

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `authApi.login()` | POST `/login/access-token` | 用户名密码登录 |
| `authApi.getCaptcha()` | GET `/login/captcha` | 获取验证码（如启用） |
| `siteSettingsApi.getPublic()` | GET `/site-settings/public` | 获取公开站点设置 |
| `ssoApi.getPublicProviders()` | GET `/sso/providers` | 获取 SSO 提供商列表 |

**主要组件**:
- `LoginForm` - 登录表单组件
- 点击式人机验证（条件渲染）
- SSO 登录按钮列表

启用站点 `enable_captcha` 后，登录表单会加载一次性点击挑战；用户必须点击完成验证后才能提交。验证失败、超时或异常时，表单显示明确错误并保留刷新重试入口。

---

## /register - 注册页面

**文件位置**: `frontend/app/(auth)/register/page.tsx`

**页面作用**: 新用户注册，支持邮箱验证

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `authApi.register()` | POST `/login/register` | 用户注册 |
| `authApi.sendVerification()` | POST `/login/send-verification` | 发送验证码 |
| `authApi.verifyEmail()` | POST `/login/verify-email` | 验证邮箱 |
| `siteSettingsApi.getPublic()` | GET `/site-settings/public` | 获取公开站点设置 |

**主要功能**:
- 用户名、邮箱、密码输入
- 点击式人机验证（站点启用验证码时）
- 邮箱验证码发送和验证
- 密码强度检查（根据站点设置）

---

## /forgot-password - 忘记密码页面

**文件位置**: `frontend/app/(auth)/forgot-password/page.tsx`

**页面作用**: 密码重置流程

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `authApi.forgotPassword()` | POST `/login/forgot-password` | 发送重置邮件 |
| `authApi.resetPassword()` | POST `/login/reset-password` | 重置密码 |

**主要流程**:
1. 输入邮箱
2. 发送重置验证码
3. 输入验证码和新密码
4. 完成重置

---

## /sso-callback - SSO 回调页面

**文件位置**: `frontend/app/(auth)/sso-callback/page.tsx`

**页面作用**: 处理 SSO 认证回调

**使用的 API**: 无（从 URL 参数获取 Token）

**主要功能**:
- 从 URL 获取 JWT Token
- 存储 Token 到本地
- 重定向到目标页面

**URL 参数**:
- `token`: JWT 访问令牌
- `redirect`: 重定向目标（可选）
