# Model Prompt Caching Visibility 设计文档

## Background & Goals

### 背景
- Anthropic 对话缓存已启用（`cache_control` 断点，见上轮改动），OpenAI/Gemini/DeepSeek/Moonshot 为服务端自动/隐式缓存。
- 但各供应商响应中回报的缓存命中/写入明细（`cached_tokens`、`cache_read_input_tokens`、`cached_content_token_count`、`prompt_cache_hit_tokens` 等）**全部被丢弃**：`Usage` 类型只有 `prompt/completion/total`，消息持久化 `token_usage` 只有 `{prompt, completion}`。
- 结果：缓存是否真正命中不可见，无法验证缓存生效、无法做成本分析。

### 目标
1. `Usage` 统一透传缓存明细字段（缓存命中 + 缓存写入），全部 7 个 chat adapter（非流式 + 流式）解析供应商原生字段并归一化。
2. 消息持久化 `token_usage` 扩展可选缓存字段（向后兼容）。
3. 前端 token 统计 popover 展示缓存命中 token 数（i18n 双语）。

### 非目标
- xAI `x-grok-conv-id` 会话路由 header（需要调用链传会话 id，改动面大，收益低；单独评估）。
- Gemini 1.5 显式 `cachedContent` 资源管理（需额外 API 生命周期管理，32k+ tokens 门槛；2.5+ 隐式缓存已覆盖）。
- OpenAI 缓存写入计费（`cache_write_tokens`，仅 GPT-5.6+，当前无模型接入）。

## High-Level Design

### 数据流
```text
供应商响应 usage
  → adapter 解析原生字段 → 统一 Usage{total_input_tokens, cache_read_tokens, cache_creation_tokens}
  → chat.py _calculate_model_usage / 流式 stream_usage 透传
  → 消息 token_usage = {prompt, completion, total_input?, cache_read?, cache_creation?}
  → message_end SSE usage 透传
  → 前端 message-converter 重建 metadata.usage → TokenStatsContent 展示
```

### 字段归一化映射

| 供应商 | 原生字段 | → cache_read_tokens | → cache_creation_tokens |
|---|---|---|---|
| OpenAI / OpenAI-compatible | `prompt_tokens_details.cached_tokens` | ✓ | — |
| Anthropic | `cache_read_input_tokens` | ✓ | `cache_creation_input_tokens` |
| Gemini | `usage_metadata.cached_content_token_count` | ✓ | — |
| DeepSeek | `prompt_cache_hit_tokens` | ✓ | — |
| Moonshot | `prompt_tokens_details.cached_tokens`（OpenAI 兼容） | ✓ | — |
| xAI | `cached_prompt_text_tokens` 或 `prompt_tokens_details.cached_tokens` | ✓ | — |

## Implementation Plan

### Stage 1: Usage 类型扩展 + adapter 解析
- **Files**: `backend/app/llm/types/base.py`、7 个 adapter（openai / openai_compatible / deepseek / moonshot / xai / anthropic / gemini）
- **逻辑**: `Usage` 增加 `total_input_tokens`、`cache_read_tokens` / `cache_creation_tokens`（默认 0）；每个 adapter 的非流式 `chat()` 与流式 usage chunk 解析处按上表填充缓存明细，并保留完整输入 token 总量。
- **Validation**: 各 adapter 单测断言 usage 缓存字段；现有断言不受影响（新字段默认 0）。

### Stage 2: chat.py 记账与 SSE 透传
- **Files**: `backend/app/api/v1/endpoints/chat.py`（6 处流式循环 + 非流式 + message_end 事件）
- **逻辑**: `_calculate_model_usage` 增加完整输入与缓存字段透传；消息 `token_usage` 扩展 `{prompt, completion, total_input?, cache_read?, cache_creation?}`；`message_end` SSE `usage` 增加 `total_input_tokens`、`cache_read_tokens` / `cache_creation_tokens`。
- **Validation**: 端到端测试断言 message_end 与持久化含缓存字段；旧格式兼容。

### Stage 3: 前端透传与展示
- **Files**: `frontend/lib/api/agents.ts`（BackendMessage token_usage 类型）、`frontend/lib/utils/message-converter.ts`、`frontend/components/chat/message.tsx`、`frontend/i18n/{en,zh}/chat.json`、`frontend/i18n/types/chat.ts`
- **逻辑**: `token_usage` 类型加可选 `total_input`、`cache_read` / `cache_creation`；converter 重建 usage 含完整输入与缓存字段；`TokenStatsContent` 使用该完整输入字段保持 token 统计口径一致；i18n 键 `cachedTokens` / `cacheCreationTokens`。
- **Validation**: converter 单测 + message 组件测试（若存在）。
### Stage 4: 全量验证
- 后端：llm 目录全部测试 + chat 相关 + Ruff。
- 前端：受影响的 hook/converter/组件测试与 tsc。


## Testing Strategy
- 端到端：message_end SSE usage 含 `total_input_tokens` 与缓存字段；持久化 token_usage 含 `total_input` 与缓存字段。
- 回归：旧响应（无缓存字段）→ 新字段默认 0，现有断言不变。
- 前端：converter 重建 usage 含缓存字段；popover 渲染条件（>0 才显示）。

## Risks & Mitigation
- **缓存字段语义差异**：供应商 `prompt_tokens` 是否含缓存命中？OpenAI/DeepSeek 的 `prompt_tokens` 是总输入（含命中），`cached_tokens` 是其中命中部分——只做明细展示，不改 prompt/completion 记账语义，避免统计口径变化。
- **流式 usage 快照**：沿用现有"最后 chunk 覆盖"逻辑，缓存字段随同一 Usage 对象透传，无额外合并风险。
- **前端兼容**：`cache_read`/`cache_creation` 为可选字段，旧消息无此字段时展示逻辑跳过。

## Rollback
- 全部为纯增量字段（默认 0 / 可选），无 schema 迁移；回退只需还原 Usage 类型与 adapter 解析。
