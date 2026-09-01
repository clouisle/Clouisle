# Agent Simple Context Summary Design Document

## Background & Goals

此前的 Agent Chat 上下文压缩是多层流水线：warning / auto_compact / blocking 分级阈值、selective micro compaction、macro 摘要、持久化 `ConversationContextCheckpoint`、`ConversationSessionMemory`、active-tool 窗口压缩、reactive retry。链路复杂且会在多级改写之间丢失上下文连续性。

本次将其替换为最简单的方式：

1. 每次模型调用前预检完整请求的 token 规模（消息 + 工具定义）。
2. 完整请求规模超过 `min(context_limit × 0.9, input_budget)` 时，调用同一模型对上下文做一次摘要；其中 90% 使用固定的 `DEFAULT_SUMMARY_TRIGGER_RATIO = 0.9`。
3. 新上下文 = 系统提示词 + 摘要消息（包含任务目标、已完成动作与结果、待完成事项、约束与决定）+ 最新用户消息。

### Success criteria

- 预检在每次模型调用前执行（非流式、流式、编辑、重新生成四条链路一致）。
- `messages + tool_definition_tokens` 超过 `context_limit × 0.9` 时，普通请求只保留系统提示词、一个摘要用户消息和当前用户消息；正在执行的工具轮次还会保留当前用户消息之后的 assistant/tool 协议消息，避免摘要截断未完成调用。
- 摘要固定包含 Task、Completed actions and results、Pending work、Constraints and decisions，并最多尝试 3 次（单次 180s 超时，间隔 2s）。
- 摘要与水位持久化在 `conversations` 上；下次请求从摘要水位之后继续，分支切换时自动忽略失效水位。
- 不再执行轮次保留、工具步骤压缩、checkpoint/session-memory 或 provider reactive retry。

## High-Level Design

唯一决策入口仍是 `backend/app/services/chat_context.py::prepare_model_context`：

1. `_build_messages_with_file_content` 构建系统提示词、有效水位摘要、水位之后的历史和当前请求。
2. `_estimate_message_tokens(messages) + tool_definition_tokens` 估算完整请求；工具定义 token 由各 endpoint 用 `count_tool_definition_tokens` 计算后传入。
3. 完整请求超过 `min(context_limit × 0.9, input_budget)` 时调用 `_summarize_context`：
   - `_render_summary_transcript` 将当前请求和未完成工具轮次之前的历史渲染为带角色标签的文本，包含工具调用与工具结果。
   - 通过 `model_manager.team_chat` 以固定 system 指令生成结构化英文摘要；单次 180 秒超时、最多 3 次尝试。
   - 摘要经 `truncate_text_to_tokens` 收敛到 `summary_max_tokens`（默认 1000）。
   - `summary_source_tokens`、`summary_result_tokens`、`summary_saved_tokens` 只统计被替换的历史消息段及新摘要消息，不包含未变化的系统提示词、当前请求或工具定义；SSE/UI 展示这组数值而非完整上下文的 `before_tokens` / `after_tokens`。
4. 成功后普通请求严格变为 `[system, user(summary), current_user]`；若当前轮仍有 assistant/tool 协议消息，则将其接在当前用户消息之后保留。`CompressionMeta.stage="macro"`、`actions` 包含 `context_summary`，SSE 照常发出 compression_start/end。
5. 摘要后的完整请求仍必须落在可用 input budget 内；否则直接抛不可重试的 `ContextLengthError`，不再回退到另一套上下文。
6. 摘要成功且 `history_override is None` 时把可见历史最后一条消息写入 watermark；后续请求只读取水位之后的历史。

## Implementation Plan

### Stage 1: Core rewrite

- **Files modified**: `backend/app/services/chat_context.py`
- **Specific logic**: 删除分级阈值、最近轮次保留、工具步骤压缩、emergency fallback 与 retry；保留完整 payload 预检、一次模型摘要和持久化水位。
- **Validation**: ruff check/format 通过；导入检查通过。

### Stage 2: Endpoint cutover

- **Files modified**: `backend/app/api/v1/endpoints/chat.py`、`chat_sse.py`
- **Specific logic**: 四条链路统一在 provider 调用前执行预检；流式链路在摘要模型调用前发送 compression_start。
- **Validation**: ruff check/format 通过；人工长对话观察 SSE 与摘要后的连续性。

### Stage 3: Dead configuration removal

- **Files modified**: `backend/app/schemas/agent.py`、`frontend/lib/api/agents.ts`
- **Specific logic**: 配置仅保留 `enabled`、`summary_max_tokens`、`emit_sse_events`；固定 90% 触发阈值和内部安全预算不再暴露为 agent 参数。
- **Validation**: backend 导入检查与 frontend TypeScript 检查。

### Stage 4: Existing persistence

- **Files modified**: `backend/app/models/agent.py`、`backend/app/core/init_data.py`
- **Specific logic**: 复用 `context_summary_text` / `context_summary_watermark_id`，不再引入新的 checkpoint、session-memory 或状态机。
- **Validation**: 长对话第二次请求从水位之后继续；切换分支时重新读取完整历史。

## Testing Strategy

按用户要求，本轮暂不修改测试文件；现有压缩相关测试待功能人工验证后再统一处理。

手动验证路径：配置较小 `context_length` 的模型发起长对话，观察 90% 触发时返回的 compression SSE 事件、摘要内容与后续任务连续性。

## Risks & Mitigation

- 摘要调用本身消耗一次模型请求；仅在完整预检超过 90% 时发生。
- 摘要质量决定历史信息保真度；固定字段要求保留目标、动作、结果、待办、约束和决定。
- tokenizer 估算偏差或当前请求本身过大时直接返回不可重试超长错误，不再偷偷切换到另一套历史。
- 摘要消息和当前用户消息连续出现；主流 provider 会按相邻 user 消息处理，必要时由 adapter 合并。


<!-- Historical implementation notes intentionally removed: the simple contract above has no recent-turn retention, tool-step compaction, or emergency fallback. -->
