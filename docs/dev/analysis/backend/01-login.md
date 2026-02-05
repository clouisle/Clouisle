# 登录认证 API

**文件**: `backend/app/api/v1/endpoints/login.py`
**路径前缀**: `/api/v1/login`

## 接口列表

### GET /captcha

获取登录验证码

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 当站点设置启用验证码时，登录前需要获取验证码 |

**响应**:
```json
{
  "code": 0,
  "data": {
    "captcha_id": "uuid",
    "captcha_image": "base64_image_data"
  }
}
```

---

### POST /login/access-token

用户登录获取访问令牌

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | OAuth2 兼容的令牌登录，支持验证码验证 |

**请求体**:
```json
{
  "username": "string",
  "password": "string",
  "captcha_id": "string (可选)",
  "captcha_code": "string (可选)"
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "access_token": "jwt_token",
    "token_type": "bearer"
  }
}
```

**错误码**:
- `2001`: 用户名或密码错误
- `2002`: 账户未激活
- `5300`: 账户已锁定
- `5301`: 登录尝试次数过多
- `5302`: 验证码错误

**安全特性**:
- 登录失败次数限制
- 账户锁定机制
- 验证码支持
- 单会话模式支持（可选）
- 审计日志记录

---

### POST /logout

用户登出

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 使当前令牌失效 |

**响应**:
```json
{
  "code": 0,
  "data": null,
  "msg": "success"
}
```

---

### POST /register

用户注册

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开（需站点设置允许注册） |
| 说明 | 新用户注册，首个用户自动成为超级管理员 |

**请求体**:
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "full_name": "string (可选)"
}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "username": "string",
    "email": "string",
    "is_active": true
  }
}
```

**错误码**:
- `5000`: 注册已禁用
- `5001`: 用户名已存在
- `5002`: 邮箱已存在
- `5003`: 需要邮箱验证

**特性**:
- 首个注册用户自动成为超级管理员
- 可配置是否需要邮箱验证
- 可配置是否需要管理员审批
- 审计日志记录

---

### POST /send-verification

发送邮箱验证码

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 发送 6 位数字验证码到指定邮箱 |

**请求体**:
```json
{
  "email": "string"
}
```

**响应**:
```json
{
  "code": 0,
  "data": null,
  "msg": "Verification code sent"
}
```

---

### POST /verify-email

验证邮箱

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 使用验证码验证邮箱 |

**请求体**:
```json
{
  "email": "string",
  "code": "string"
}
```

**响应**:
```json
{
  "code": 0,
  "data": null,
  "msg": "Email verified"
}
```

---

### GET /verify

通过链接验证邮箱

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 通过邮件中的链接验证邮箱（Token 方式） |

**查询参数**:
- `token`: 验证令牌

---

### POST /resend-verification

重新发送验证邮件

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 重新发送邮箱验证邮件 |

**请求体**:
```json
{
  "email": "string"
}
```

---

### POST /forgot-password

忘记密码

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 发送密码重置邮件 |

**请求体**:
```json
{
  "email": "string"
}
```

**响应**:
```json
{
  "code": 0,
  "data": null,
  "msg": "Password reset email sent"
}
```

---

### POST /reset-password

重置密码

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 使用验证码重置密码 |

**请求体**:
```json
{
  "email": "string",
  "code": "string",
  "new_password": "string"
}
```

**响应**:
```json
{
  "code": 0,
  "data": null,
  "msg": "Password reset successful"
}
```

**审计日志**: `reset_password`

---

## 安全机制

### 登录保护

1. **失败次数限制**: 连续登录失败达到阈值后锁定账户
2. **验证码**: 可配置登录时需要验证码
3. **单会话模式**: 可配置同一账户只能有一个活跃会话

### 密码策略

通过站点设置配置：
- 最小长度
- 是否需要大写字母
- 是否需要小写字母
- 是否需要数字
- 是否需要特殊字符

### SSO 集成

当启用 SSO 时：
- 可禁用密码登录
- 安全检查：确保至少有一个超级管理员绑定了 SSO
