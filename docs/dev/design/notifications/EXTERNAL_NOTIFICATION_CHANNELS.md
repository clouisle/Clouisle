# 外部通知渠道扩展实现计划

## 概述

基于现有的 Email 和钉钉通知实现，按优先级扩展以下外部通知渠道：
1. 企业微信 (WeChat Work)
2. 飞书 (Feishu/Lark)
3. 通用 Webhook
4. Slack

## 实现顺序与优先级

| 优先级 | 渠道 | 原因 |
|--------|------|------|
| P0 | 企业微信 | 国内企业使用率高，与钉钉并列 |
| P1 | 飞书 | 字节系企业标配，增长快 |
| P2 | 通用 Webhook | 灵活性最高，可对接任意系统 |
| P3 | Slack | 海外/外企标配 |

## 每个渠道的实现清单

### Backend 修改

1. **models/notification.py** - 添加渠道枚举
2. **models/site_setting.py** - 添加渠道配置项
3. **core/<channel>.py** - 创建渠道核心实现（配置获取、发送函数）
4. **api/v1/endpoints/notifications.py** - 添加渠道验证逻辑
5. **tasks/notification.py** - 添加 Celery 异步任务
6. **api/v1/endpoints/site_settings.py** - 添加测试端点
7. **core/i18n.py** - 添加 i18n 翻译

### Frontend 修改

1. **lib/api/site-settings.ts** - 添加 TypeScript 接口和 API 方法
2. **app/(dashboard)/site-settings/notifications/page.tsx** - 添加设置 Tab
3. **i18n/en/siteSettings.json** - 英文翻译
4. **i18n/zh/siteSettings.json** - 中文翻译

---

## 渠道 1: 企业微信 (WeChat Work)

### 配置项
```python
# models/site_setting.py
"wechat_enabled": bool, default=False
"wechat_notification_type": string, default="webhook"  # webhook | app
# Webhook 方式
"wechat_webhook_url": string
# 企业应用方式
"wechat_corp_id": string      # 企业ID
"wechat_agent_id": string     # 应用AgentId
"wechat_secret": string       # 应用Secret
```

### API 实现
- Webhook: POST `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`
- 企业应用: 需要先获取 access_token，再调用消息发送接口

### 消息格式
```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "# 标题\n内容"
  }
}
```

---

## 渠道 2: 飞书 (Feishu/Lark)

### 配置项
```python
"feishu_enabled": bool, default=False
"feishu_notification_type": string, default="webhook"  # webhook | app
# Webhook 方式
"feishu_webhook_url": string
"feishu_secret": string  # 签名密钥（可选）
# 企业应用方式
"feishu_app_id": string
"feishu_app_secret": string
```

### API 实现
- Webhook: POST webhook URL，支持签名验证
- 企业应用: 需要 tenant_access_token

### 消息格式
```json
{
  "msg_type": "interactive",
  "card": {
    "header": {"title": {"tag": "plain_text", "content": "标题"}},
    "elements": [{"tag": "markdown", "content": "内容"}]
  }
}
```

---

## 渠道 3: 通用 Webhook

### 配置项
```python
"webhook_enabled": bool, default=False
"webhook_url": string
"webhook_method": string, default="POST"  # POST | GET
"webhook_headers": json, default={}  # 自定义请求头
"webhook_body_template": string  # 支持变量替换: {{title}}, {{content}}, {{link_url}}
"webhook_secret": string  # 用于签名（可选）
```

### 特性
- 支持自定义请求头（如 Authorization）
- 支持自定义请求体模板
- 支持 HMAC 签名

---

## 渠道 4: Slack

### 配置项
```python
"slack_enabled": bool, default=False
"slack_webhook_url": string  # Incoming Webhook URL
```

### 消息格式
```json
{
  "text": "标题",
  "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": "标题"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "内容"}}
  ]
}
```

---

## 关键文件路径

### Backend
- `backend/app/models/notification.py` - 渠道枚举
- `backend/app/models/site_setting.py` - 配置定义
- `backend/app/core/wechat.py` - 企业微信实现（新建）
- `backend/app/core/feishu.py` - 飞书实现（新建）
- `backend/app/core/webhook.py` - 通用 Webhook 实现（新建）
- `backend/app/core/slack.py` - Slack 实现（新建）
- `backend/app/api/v1/endpoints/notifications.py` - 渠道验证
- `backend/app/api/v1/endpoints/site_settings.py` - 测试端点
- `backend/app/tasks/notification.py` - Celery 任务
- `backend/app/core/i18n.py` - 翻译

### Frontend
- `frontend/lib/api/site-settings.ts` - API 接口
- `frontend/app/(dashboard)/site-settings/notifications/page.tsx` - 设置页面
- `frontend/i18n/en/siteSettings.json` - 英文
- `frontend/i18n/zh/siteSettings.json` - 中文

---

## 验证方式

1. **单元测试**: 每个渠道的发送函数
2. **集成测试**: 通过站点设置页面发送测试消息
3. **端到端测试**: 创建通知并选择外部渠道，验证发送状态

---

## 实现步骤

### 第一阶段: 企业微信
1. 添加 `NotificationChannel.WECHAT` 枚举
2. 添加企业微信配置项到 `DEFAULT_SETTINGS`
3. 创建 `backend/app/core/wechat.py`
4. 添加 Celery 任务
5. 添加 API 验证和测试端点
6. 添加前端设置 Tab
7. 添加 i18n 翻译

### 第二阶段: 飞书
（同上模式）

### 第三阶段: 通用 Webhook
（同上模式）

### 第四阶段: Slack
（同上模式）
