# Agent Media Tool Failure Visibility Design Document

## Background & Goals

当前 agent 文生图/视频工具把成功或失败都封装为结构化 tool result，其中媒体类结果依赖前端正文里的 `media-result` part 才能稳定展示。现状有三个连在一起的问题：

- regenerate 流只发 `tool_result`，没有补发 `media_result`，导致媒体结果在重试路径里容易消失
- tool result 的错误语义在 SSE 和历史恢复里不完整，失败工具会被当作普通成功结果
- OpenAI / OpenAI-compatible 图片模型直接收到 `quality=high` 会返回 provider 400，虽然工具层会收口异常，但体验上既不稳定也不够前置

### Success criteria

- 正常流与 regenerate 流都遵循 `tool_result -> media_result` 的媒体事件顺序
- tool result 的失败状态能在实时聊天和历史恢复里保持一致
- 失败媒体结果仍走正文展示，不回退到工具面板
- OpenAI-compatible 图片质量别名 `high` 会被规范为 `hd`
- 不支持的图片质量值会在工具层返回稳定、可读的错误

## High-Level Design

### Backend SSE parity

在 `backend/app/api/v1/endpoints/chat.py` 中抽出共享 helper，用同一套逻辑构建：

- `tool_result` SSE payload（补上 `is_error`）
- `media_result` SSE payload（对 `media.image` / `media.video` 自动发出）

这样 normal stream 与 regenerate stream 都复用同一契约，避免再次分叉。

### Frontend historical error restoration

在 `frontend/lib/utils/tool-result.ts` 中增加一个极小的 `inferToolResultIsError()` helper，对结构化 tool output 做保守判断：

- `success === false` 视为错误
- 存在非空 `error` 字段视为错误

`frontend/lib/utils/message-converter.ts` 在历史恢复时复用这个 helper，同时把对应 `tool-call` part 标成 `error`，确保刷新历史后仍能看到失败态。

### Image quality normalization

在 `backend/app/llm/tools/builtin/media.py` 中增加最小质量规范化逻辑：

- 仅对 `openai` / `azure_openai` / `custom` 这类 OpenAI-compatible 图片 provider 生效
- `high -> hd`
- `standard -> standard`
- `hd -> hd`
- 其它值 fail fast，并返回 i18n 错误

## Implementation Plan

### Stage 1: Backend media SSE parity and tool error flags
- **Files modified**:
  - `backend/app/api/v1/endpoints/chat.py`
- **Specific logic**:
  - 抽出共享 helper 生成 `tool_result` SSE payload，并按 display result 推断 `is_error`
  - 抽出共享 helper 生成 `media_result` SSE event
  - 正常流与 regenerate 流统一复用 helper，保持事件顺序一致
- **Validation**:
  - failed media payload 的 `tool_result` 带 `is_error: true`
  - media payload 能生成 `media_result` SSE event

### Stage 2: Frontend history tool error restoration
- **Files modified**:
  - `frontend/lib/utils/tool-result.ts`
  - `frontend/lib/utils/message-converter.ts`
- **Specific logic**:
  - 新增 `inferToolResultIsError()` helper
  - 两条历史恢复路径都用同一 helper 计算 `isError`
  - 历史恢复时同步把关联 `tool-call` part 标成 `error`
- **Validation**:
  - 历史 failed tool result 不再固定为 `isError: false`
  - failed media/tool call 的 header 状态能恢复为 error

### Stage 3: Image quality normalization and validation
- **Files modified**:
  - `backend/app/llm/tools/builtin/media.py`
  - `backend/app/locales/en/LC_MESSAGES/messages.po`
  - `backend/app/locales/zh/LC_MESSAGES/messages.po`
- **Specific logic**:
  - 对 OpenAI-compatible provider 规范图片 quality
  - 非法值在工具层返回 i18n 友好错误
- **Validation**:
  - `quality=high` 会落到 provider 支持值 `hd`
  - `quality=ultra` 之类非法值在工具层稳定失败

### Stage 4: Targeted verification
- **Files modified**:
  - `backend/tests/llm/test_chat_media_tool_summaries.py`
  - `backend/tests/llm/test_media_builtin_tools.py`
- **Specific logic**:
  - 为 SSE helper 补充最小单测
  - 为图片 quality 规范化补充最小单测
  - 前端无现成测试基建时，依赖 lint + 代码路径验证
- **Validation**:
  - `PYTHONPATH=. uv run pytest tests/llm/test_chat_media_tool_summaries.py tests/llm/test_media_builtin_tools.py -v`
  - `uv run ruff check app tests`
  - `bun run lint`

## Testing Strategy

### Happy path tests

1. 正常流成功文生图，正文显示图片
2. regenerate 成功文生图，正文同样显示图片
3. `quality=high` 请求会转换为 `hd`

### Error path tests

1. 正常流失败文生图，tool call 显示失败态，正文显示错误
2. regenerate 失败文生图，同样能看到失败态
3. 历史刷新后 failed tool result 仍保留错误语义
4. `quality=ultra` 在工具层直接返回可读错误

### Regression scope

- 非媒体 tool result 的历史恢复
- 视频媒体 payload 的 `media_result` 展示路径
- 普通 tool panel 渲染

## Risks & Mitigation

### 风险 1：后端 helper 改动影响现有 tool SSE 格式
- **Mitigation**:
  - 保持原字段不变，只补充可选 `is_error`
  - 仅对媒体 payload 额外补发 `media_result`

### 风险 2：过度泛化 quality 校验误伤非 OpenAI provider
- **Mitigation**:
  - 仅对 OpenAI-compatible provider 启用映射和限制
  - 其它 provider 保持原样透传

### 风险 3：历史恢复只修 result，不修 tool-call header
- **Mitigation**:
  - 在 converter 中同步回写 `tool-call` 的 `state = 'error'`

### Rollback plan

若本次修复引发意外回归，可按以下顺序回退：

1. 先回退 quality 规范化 helper
2. 再回退 message converter 的错误恢复逻辑
3. 最后回退 chat SSE helper，恢复原始 inline event 发送