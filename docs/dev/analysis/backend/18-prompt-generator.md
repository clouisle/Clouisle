# 提示词生成 API

**文件**: `backend/app/api/v1/endpoints/prompt_generator.py`
**路径前缀**: `/api/v1/prompt-generator`

## 概述

提示词生成器使用 AI 帮助用户生成和优化 Agent 的系统提示词。

## 接口列表

### POST /generate

生成提示词

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 根据描述生成系统提示词（SSE 流式） |

**请求体**:
```json
{
  "description": "string",
  "language": "zh",
  "style": "professional"
}
```

**参数说明**:
- `description`: Agent 功能描述
- `language`: 输出语言（zh, en）
- `style`: 生成风格（professional, friendly, concise）

**响应**: Server-Sent Events

```
event: content
data: {"delta": "你是一个"}

event: content
data: {"delta": "专业的"}

event: done
data: {}
```

---

### POST /optimize

优化提示词

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | 已登录用户 |
| 说明 | 根据反馈优化现有提示词（SSE 流式） |

**请求体**:
```json
{
  "current_prompt": "string",
  "feedback": "string",
  "language": "zh"
}
```

**参数说明**:
- `current_prompt`: 当前提示词
- `feedback`: 优化反馈/要求
- `language`: 输出语言

**响应**: Server-Sent Events

---

## 生成风格

| 风格 | 说明 |
|------|------|
| `professional` | 专业正式 |
| `friendly` | 友好亲切 |
| `concise` | 简洁明了 |

## 使用的模型

使用系统配置的默认 CHAT 模型进行生成。

## Meta Prompt

生成器内部使用 Meta Prompt 来指导 AI 生成高质量的系统提示词：

1. 明确角色定位
2. 定义能力边界
3. 设置交互风格
4. 包含必要约束
5. 提供示例格式
