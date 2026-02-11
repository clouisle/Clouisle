# 系统自动通知

系统自动通知功能允许管理员配置在特定事件发生时自动发送通知给相关用户。

## 功能概述

- **站内通知**：所有启用的自动通知都会创建站内通知
- **外部渠道**：可配置通过邮件、钉钉、企业微信、飞书、Slack、Webhook 等渠道发送
- **全局配置**：外部渠道为全局配置，适用于所有启用的通知类型

## 通知类型

### 团队相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `team.member_added` | 成员被添加到团队 | 被添加的用户 |
| `team.member_removed` | 成员被移出团队 | 被移除的用户 |
| `team.role_changed` | 成员角色变更 | 角色变更的用户 |
| `team.ownership_transferred` | 团队所有权转移 | 新所有者 |
| `team.model_granted` | 模型授权给团队 | 团队成员 |
| `team.model_revoked` | 模型授权被撤销 | 团队成员 |

### 用户相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `user.activated` | 用户账户被激活 | 被激活的用户 |
| `user.deactivated` | 用户账户被禁用 | 被禁用的用户 |
| `user.password_reset` | 用户密码被重置 | 密码被重置的用户 |
| `user.pending_approval` | 新用户注册待审批 | 所有超级管理员 |

### 知识库相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `kb.doc_indexed` | 文档索引完成 | 文档所属团队 |
| `kb.doc_failed` | 文档处理失败 | 文档所属团队 |

### 工作流相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `workflow.run_success` | 工作流运行成功 | 触发者 |
| `workflow.run_failed` | 工作流运行失败 | 触发者 |

### Agent 相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `agent.published` | Agent 发布 | Agent 所属团队 |
| `agent.unpublished` | Agent 取消发布 | Agent 所属团队 |

### API Key 相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `apikey.expiring` | API Key 即将过期 | API Key 所有者 |
| `apikey.expired` | API Key 已过期 | API Key 所有者 |

**说明**：
- API Key 过期检查通过 Celery Beat 定时任务执行，每天 09:00 运行
- 即将过期提醒在过期前 7 天、3 天、1 天发送

### 安全相关

| 类型 | 说明 | 通知对象 |
|------|------|----------|
| `security.login_anomaly` | 检测到异常登录 | 登录的用户 |
| `security.account_locked` | 账户被锁定 | 被锁定的用户 |
| `security.password_changed` | 密码已修改 | 修改密码的用户 |

**登录异常检测说明**：
- 系统会记录用户最近的登录 IP 地址和设备信息（User-Agent）
- 当用户从新的 IP 地址或设备登录时，会触发异常登录通知
- 登录历史保留 30 天，每个用户最多记录 10 个 IP 和 10 个设备

## 配置方式

### 管理后台配置

1. 进入 **站点设置** → **通知设置** → **自动通知** 标签页
2. 勾选需要启用的通知类型
3. 选择外部通知渠道（需先在对应渠道配置页面启用）
4. 保存配置

### API 配置

**获取配置**

```http
GET /api/v1/site-settings/auto-notifications
```

响应示例：
```json
{
  "code": 0,
  "data": {
    "enabled_types": [
      "team.member_added",
      "team.member_removed",
      "user.activated",
      "security.login_anomaly"
    ],
    "channels": ["email", "dingtalk"]
  },
  "msg": "success"
}
```

**更新配置**

```http
PUT /api/v1/site-settings/auto-notifications
Content-Type: application/json

{
  "enabled_types": [
    "team.member_added",
    "team.member_removed",
    "user.activated",
    "security.login_anomaly"
  ],
  "channels": ["email"]
}
```

## 外部渠道

自动通知支持以下外部渠道：

| 渠道 | 配置项 | 说明 |
|------|--------|------|
| `email` | SMTP 设置 | 邮件通知 |
| `dingtalk` | 钉钉机器人 Webhook | 钉钉群通知 |
| `wechat` | 企业微信机器人 Webhook | 企业微信群通知 |
| `feishu` | 飞书机器人 Webhook | 飞书群通知 |
| `slack` | Slack Webhook | Slack 频道通知 |
| `webhook` | 自定义 Webhook URL | 通用 HTTP 回调 |

**注意**：外部渠道需要先在对应的设置页面配置并启用，才能在自动通知中使用。

## 通知内容

### 消息格式

- **标题**：包含站点名称和通知类型
- **内容**：支持 Markdown 格式
- **上下文**：
  - 团队通知会包含团队名称
  - 用户通知会包含用户名

### 示例

**团队成员添加通知**：
```
标题：【Clouisle】[开发团队] 您已加入团队
内容：
**团队**: 开发团队

您已被添加到团队 **开发团队**，角色为 **成员**。
```

**登录异常通知**：
```
标题：【Clouisle】[@admin] 检测到异常登录
内容：
**用户**: admin

检测到您的账户从异常位置或设备登录。

- **IP 地址**: 192.168.1.100
- **时间**: 2026-02-04T10:30:00+08:00
- **设备信息**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...

如果这不是您本人的操作，请立即修改密码。
```

## 技术实现

### 架构

```
业务模块 → AutoNotificationService → 站内通知
                                   ↓
                              外部渠道任务 (Celery)
                                   ↓
                         邮件/钉钉/企业微信/飞书/Slack/Webhook
```

### 核心组件

| 组件 | 路径 | 说明 |
|------|------|------|
| 通知类型枚举 | `app/models/notification.py` | `AutoNotificationType` |
| 自动通知服务 | `app/services/auto_notification.py` | `AutoNotificationService` |
| 配置存储 | `app/models/site_setting.py` | `auto_notification_config` |
| API 端点 | `app/api/v1/endpoints/site_settings.py` | `/auto-notifications` |
| 登录异常检测 | `app/core/login_anomaly.py` | 登录模式分析 |
| API Key 检查 | `app/tasks/api_key.py` | 定时任务 |

### 使用示例

```python
from app.services.auto_notification import AutoNotificationService
from app.models.notification import AutoNotificationType, NotificationLevel
from app.core.i18n import t

# 发送用户级别通知
await AutoNotificationService.send_to_user(
    notification_type=AutoNotificationType.USER_ACTIVATED,
    user_id=user.id,
    title=t("notify_user_activated_title"),
    content=t("notify_user_activated_content", username=user.username),
    level=NotificationLevel.MEDIUM,
)

# 发送团队级别通知
await AutoNotificationService.send_to_team(
    notification_type=AutoNotificationType.TEAM_MEMBER_ADDED,
    team_id=team.id,
    title=t("notify_team_member_added_team_title"),
    content=t("notify_team_member_added_team_content",
              username=user.username,
              team_name=team.name),
    level=NotificationLevel.LOW,
)

# 发送全局通知
await AutoNotificationService.send_global(
    notification_type=AutoNotificationType.USER_PENDING_APPROVAL,
    title=t("notify_user_pending_approval_title"),
    content=t("notify_user_pending_approval_content", username=user.username),
    level=NotificationLevel.HIGH,
)
```

## 定时任务

### API Key 过期检查

- **任务名称**: `tasks.check_api_key_expiration`
- **执行时间**: 每天 09:00
- **功能**:
  - 检查 7 天内即将过期的 API Key，在第 7、3、1 天发送提醒
  - 检查过去 24 小时内已过期的 API Key，发送过期通知

### 配置

在 `app/core/celery.py` 中配置：

```python
celery_app.conf.beat_schedule = {
    "check-api-key-expiration": {
        "task": "tasks.check_api_key_expiration",
        "schedule": crontab(hour=9, minute=0),
    },
}
```

## 多语言支持

所有通知消息都支持多语言，翻译定义在 `app/core/i18n.py` 中：

```python
TRANSLATIONS = {
    "notify_team_member_added_title": {
        "en": "You have joined a team",
        "zh": "您已加入团队",
    },
    "notify_team_member_added_content": {
        "en": "You have been added to team **{team_name}** as **{role}**.",
        "zh": "您已被添加到团队 **{team_name}**，角色为 **{role}**。",
    },
    # ... 更多翻译
}
```

## 默认配置

系统默认启用以下通知类型：

- `team.member_added`
- `team.member_removed`
- `team.role_changed`
- `team.ownership_transferred`
- `team.model_granted`
- `team.model_revoked`
- `user.activated`
- `user.deactivated`
- `user.password_reset`
- `user.pending_approval`
- `kb.doc_indexed`
- `kb.doc_failed`
- `workflow.run_failed`
- `apikey.expiring`
- `apikey.expired`
- `security.login_anomaly`
- `security.account_locked`
- `security.password_changed`

默认不启用外部渠道，需要管理员手动配置。
