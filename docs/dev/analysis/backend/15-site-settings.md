# 站点设置 API

**文件**: `backend/app/api/v1/endpoints/site_settings.py`
**路径前缀**: `/api/v1/site-settings`

## 概述

站点设置用于配置系统级别的参数，包括通用设置、安全设置、邮件设置、通知渠道等。

## 接口列表

### GET /public

获取公开设置

| 属性 | 值 |
|------|-----|
| 认证 | 无 |
| 权限 | 公开 |
| 说明 | 获取公开的站点设置（用于登录页面等） |

**响应**:
```json
{
  "code": 0,
  "data": {
    "site_name": "Clouisle",
    "site_description": "string",
    "site_icon": "string",
    "registration_enabled": true,
    "password_login_enabled": true,
    "captcha_enabled": false
  }
}
```

---

### GET /

获取所有设置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取所有站点设置 |

**查询参数**:
- `category`: 设置分类（general, security, email, notification 等）

---

### GET /{key}

获取指定设置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 获取指定的设置项 |

**路径参数**:
- `key`: 设置键名

---

### PUT /{key}

更新指定设置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 更新指定的设置项 |

**路径参数**:
- `key`: 设置键名

**请求体**:
```json
{
  "value": "any"
}
```

**审计日志**: `update_site_setting`

---

### PUT /

批量更新设置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 批量更新多个设置项 |

**请求体**:
```json
{
  "settings": {
    "site_name": "New Name",
    "registration_enabled": false
  }
}
```

**审计日志**: `bulk_update_site_settings`

---

### POST /reset

重置设置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 重置设置为默认值 |

**请求体**:
```json
{
  "keys": ["site_name", "site_description"]
}
```

**审计日志**: `reset_site_settings`

---

## 测试接口

### POST /test-email

测试邮件配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试邮件验证 SMTP 配置 |

**请求体**:
```json
{
  "to_email": "test@example.com"
}
```

---

### POST /test-dingtalk

测试钉钉配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试消息验证钉钉配置 |

---

### POST /test-wechat

测试企业微信配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试消息验证企业微信配置 |

---

### POST /test-feishu

测试飞书配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试消息验证飞书配置 |

---

### POST /test-webhook

测试 Webhook 配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试请求验证 Webhook 配置 |

---

### POST /test-slack

测试 Slack 配置

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 发送测试消息验证 Slack 配置 |

---

### POST /archive-audit-logs

触发审计日志归档

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 超级管理员 |
| 说明 | 手动触发审计日志归档任务 |

**审计日志**: `trigger_audit_log_archive`

---

## 设置分类

### 通用设置 (general)

| 键名 | 说明 | 默认值 |
|------|------|--------|
| `site_name` | 站点名称 | Clouisle |
| `site_description` | 站点描述 | - |
| `site_icon` | 站点图标 | - |

### 安全设置 (security)

| 键名 | 说明 | 默认值 |
|------|------|--------|
| `registration_enabled` | 允许注册 | true |
| `email_verification_required` | 需要邮箱验证 | false |
| `admin_approval_required` | 需要管理员审批 | false |
| `password_login_enabled` | 允许密码登录 | true |
| `captcha_enabled` | 启用验证码 | false |
| `max_login_attempts` | 最大登录尝试次数 | 5 |
| `lockout_duration` | 锁定时长（分钟） | 30 |
| `single_session_mode` | 单会话模式 | false |
| `allow_account_deletion` | 允许账户删除 | true |

### 密码策略 (password)

| 键名 | 说明 | 默认值 |
|------|------|--------|
| `password_min_length` | 最小长度 | 8 |
| `password_require_uppercase` | 需要大写字母 | false |
| `password_require_lowercase` | 需要小写字母 | false |
| `password_require_number` | 需要数字 | false |
| `password_require_special` | 需要特殊字符 | false |

### 邮件设置 (email)

| 键名 | 说明 |
|------|------|
| `smtp_host` | SMTP 服务器 |
| `smtp_port` | SMTP 端口 |
| `smtp_user` | SMTP 用户名 |
| `smtp_password` | SMTP 密码 |
| `smtp_from_email` | 发件人邮箱 |
| `smtp_from_name` | 发件人名称 |
| `smtp_use_tls` | 使用 TLS |

### 通知渠道设置

各渠道配置项详见对应文档。

### 存储设置 (storage)

| 键名 | 说明 | 默认值 |
|------|------|--------|
| `audit_log_retention_days` | 审计日志保留天数 | 90 |
| `audit_log_archive_enabled` | 启用审计日志归档 | false |

---

## 安全检查

### SSO 安全检查

禁用密码登录前，系统会检查：
- 是否有至少一个超级管理员绑定了 SSO
- 如果没有，将拒绝禁用密码登录

这是为了防止所有管理员被锁定在系统外。
