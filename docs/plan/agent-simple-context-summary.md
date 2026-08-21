# Agent Simple Context Summary Design Document

## Background & Goals

此前的 Agent Chat 上下文压缩是多层流水线：warning / auto_compact / blocking 分级阈值、selective micro compaction、macro 摘要、持久化 `ConversationContextCheckpoint`、`ConversationSessionMemory`、active-tool 窗口压缩、reactive retry。链路复杂且会在多级改写之间丢失上下文连续性。

本次将其替换为最简单的方式：

1. 每次模型调用前预检完整请求的 token 规模（消息 + 工具定义）。
2. 超过模型上下文长度的 90%（`summary_trigger_ratio`，默认 0.9）时，调用同一模型对上下文做一次摘要。
3. 新上下文 = 系统提示词 + 摘要消息（包含任务目标、已完成动作与结果、待完成事项、约束与决定）+ 最新用户消息，继续对话。

### Success criteria

- 预检在每次模型调用前执行（非流式、流式、编辑、重新生成四条链路一致）。
- 触发摘要后，除系统提示词和最新用户消息外的全部历史被替换为一条摘要用户消息。
- 摘要最多尝试 3 次（单次 180s 超时，间隔 2s）；全部失败则终止请求，用户端收到「请清理或缩短会话历史后重试。」。
- 摘要与水位持久化在 `conversations` 上；水位脱离活动分支时自动失效并按全量历史重新摘要。
- checkpoint 表 / session memory / micro/macro compaction / reactive retry 全部移除。

## High-Level Design

唯一决策入口仍是 `backend/app/services/chat_context.py::prepare_model_context`：

1. `_build_messages_with_file_content` 构建上下文：系统提示词 + （水位有效时的）持久化摘要 + 水位之后的历史 + 当前请求。
2. `_estimate_message_tokens(messages) + tool_definition_tokens` 估算请求规模；工具定义 token 由各 endpoint 用 `count_tool_definition_tokens` 计算后传入。
3. `before_tokens > int(context_limit * summary_trigger_ratio)` 时调用 `_summarize_context`：
   - `_render_summary_transcript` 将待摘要消息渲染为带角色标签的文本（含工具调用与工具结果）。
   - 通过 `model_manager.team_chat` 以固定 system 指令生成结构化摘要（Task / Completed actions and results / Pending work / Constraints and decisions），单次 180 秒超时、最多 3 次尝试。
   - 摘要经 `truncate_text_to_tokens` 收敛到 `summary_max_tokens`（默认 1000）。
4. 保留最近 `summary_keep_recent_turns`（默认 3）轮原文与当前轮的全部工具步骤：成功后请求变为 `[system, user(summary), 最近N轮原文..., 当前请求及进行中步骤]`，`CompressionMeta.stage="macro"`、`actions=["context_summary"]`，SSE 照常发出 compression_start/end。
5. 硬预算守卫：摘要后仍超 `input_budget` 时回退 `[system, 当前用户消息]`；再超则抛 `ContextLengthError(retryable=False)`。
6. 持久化水位：读取 `conversations.context_summary_text / context_summary_watermark_id`（水位仍在活动分支时生效），上下文为 `[system, 摘要, 水位之后的历史, 当前请求]`；摘要成功且 `history_override is None` 时把「旧摘要 + 水位后历史中除最近 N 轮外的部分」合并为新摘要，水位推进到被摘要覆盖的最后一个轮次的末条消息——保留的轮次仍以原文出现在后续请求中，随对话增长自然滚入未来摘要。
7. 当前轮（protected round）的 assistant 工具调用与结果永不摘要，避免工具循环中途触发摘要导致模型重复执行工具。
8. 工具循环中途（active round delta）的摘要仅请求本地，不推进水位。

## Implementation Plan

### Stage 1: Core rewrite

- **Files modified**: `backend/app/services/chat_context.py`
- **Specific logic**: 删除分级阈值、micro/macro/session-memory/checkpoint/active-tool 压缩与 `retry_prepare_model_context`；新增 `truncate_text_to_tokens`、`_assess_pressure`、`_render_summary_transcript`、`_summarize_context` 与精简后的 `CompressionMeta`。`build_model_messages` 不再读取 checkpoint。
- **Validation**: ruff check/format 通过；导入检查通过。

### Stage 2: Endpoint cutover

- **Files modified**: `backend/app/api/v1/endpoints/chat.py`、`chat_sse.py`、`chat_helpers/general.py`、`chat_helpers/__init__.py`
- **Specific logic**: 四条链路删除 prepare 与 provider 两侧的 ContextLengthError 重试块，prepare 调用统一传入 `tool_definition_tokens`；`build_compression_events` 收敛为精简 payload；删除 `should_retry_context_length`、`enqueue_session_memory_extraction` 及 session-memory 失效化调用。
- **Validation**: ruff check/format 通过。

### Stage 3: Dead module removal

- **Files deleted**: `backend/app/services/context_checkpoint.py`、`context_compaction.py`、`session_memory.py`、`backend/app/tasks/session_memory.py`
- **Files modified**: `backend/app/models/agent.py`（删除两个模型类与状态枚举）、`models/__init__.py`、`main.py` 与 `core/init_data.py`（删除建表迁移）、`services/message_branching.py`
- **Validation**: `uv run ruff check app` 全绿；应用导入正常。既有数据库表不主动删除，仅停止读写。

### Stage 4: Config surface

- **Files modified**: `backend/app/schemas/agent.py`、`frontend/lib/api/agents.ts`
- **Specific logic**: `ContextCompressionConfig` 收敛为 `enabled / summary_trigger_ratio / summary_max_tokens / output_token_reserve / safety_margin_tokens / emit_sse_events`；旧 agent 存量 JSON 配置中的多余键由 Pydantic 默认忽略。SSECompression 类型同步收敛。
- **Validation**: `bunx tsc --noEmit` 通过。

## Testing Strategy

按用户要求，本轮暂不修改测试文件；现有大量压缩相关测试会失败，待功能人工验证后再统一处理。

手动验证路径：配置较小 `context_length` 的模型发起长对话，观察 90% 触发时返回的 compression SSE 事件与后续回答是否延续先前任务状态。

## Risks & Mitigation

- 摘要调用本身消耗一次模型请求（输入 ≈ 当前上下文）；仅在水位后上下文超过 90% 时发生。
- tokenizer 估算偏差可能导致 provider 侧仍报超长；此时不再自动重试，错误直接暴露给调用方。
- 连续两条 user 消息（摘要 + 当前请求）：主流 provider 均接受；Anthropic 会自动合并。

## Update: persistent summary watermark

无状态实现在历史超过 90% 后会每个请求都重复触发摘要。已改为最小持久化：`conversations` 表新增 `context_summary_text` / `context_summary_watermark_id` 两列（`init_conversation_context_summary_columns` 运行时迁移，见 `core/init_data.py`）。触发恢复锯齿形——压缩后降到低位，随新对话增长再次越线才再压；水位脱离活动分支（编辑/重新生成分支）时自动忽略并按全量历史重新摘要，自愈无需状态机。

## Update: token-first retention and complete preflight accounting

按轮数保留不是硬规则：单轮可能包含大量 assistant/tool 交互，因此 `summary_keep_recent_turns` 只作为保留起点，`summary_keep_budget_ratio` 才是硬上限，默认从 `0.3` 收紧为 `0.15`。当最近一轮本身超过保留区时，该轮也进入摘要区；持久化水位使用实际保留边界，避免下一次请求重新加载同一超长轮并再次摘要。

工具循环额外执行确定性压缩：逐步降低原样保留的最近工具步骤数；若最新工具结果仍超出输入预算，只截断 tool-result 文本（保留角色、tool_call_id、assistant tool-call 参数和协议结构），不破坏工具重放。摘要 transcript 也先按摘要请求自身的输入/输出预算截断。

每次 provider 调用前的估算现在包含：消息 envelope、`reasoning_content`、序列化 `tool_calls`、图片输入的保守 token 预留，以及 endpoint 传入的工具定义 token。触发阈值同时受可用 input budget 限制，最终仍有硬预算检查与 emergency fallback。

验证：聚焦长循环回归 7/7；完整 payload smoke 中 100k token 工具结果被压至 1,184 tokens（含 1,000 工具定义，预算 5,000）；真实 53272312 会话重放由 187,582 tokens 压至 10,089 tokens，16 条消息，`within_budget=true`。
