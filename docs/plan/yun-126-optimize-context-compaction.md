# YUN-126 Model-Generated Context Checkpoints Design Document

## Background & Goals

当前 Agent 对话会在每次模型调用前从 active branch 重建完整历史，再在内存中执行 selective micro、session-memory 或规则 macro 压缩。其直接后果是：

- 已有 session-memory 摘要没有覆盖边界，下一轮仍读取并解析全部历史；
- 同一个摘要可能在一次请求中被重复应用；
- 规则 macro 仅拼接用户问题、助手回复与工具输出，不具备模型语义总结能力；
- 压缩后仍可能停留在 trigger 水位附近，导致下一轮再次进入压缩。

YUN-126 将压缩从一次性消息变换升级为**持久化的模型生成 Context Checkpoint**。压缩完成后，后续模型调用只加载 checkpoint 之后的 active-branch tail，而不是从完整历史重新开始。

### Success criteria

1. 同一请求中，session-memory 不会重复应用或产生无收益压缩事件。
2. 达到压缩阈值时，使用模型根据旧 checkpoint 与新增完整轮次生成结构化摘要。
3. 新 checkpoint 记录精确 `covered_through_message_id`，后续上下文只读取该边界之后的消息。
4. 通过 `checkpoint_target_ratio` 形成低水位：触发后压到低于 trigger 的目标，避免每轮压缩。
5. 分支切换、消息编辑与重新生成不会复用不在 active branch 上的 checkpoint。
6. 模型总结失败时保持可用：退回规则 macro 或既有 emergency fallback。

## High-Level Design

### Distinct responsibilities

| Component | Purpose | Persistence |
|---|---|---|
| `ConversationSessionMemory` | 长期语义记忆：偏好、约束、决定、关注点 | 异步滚动更新 |
| `ConversationContextCheckpoint` | 精确压缩边界：已覆盖的上下文摘要 + message watermark | 在压缩时同步更新 |
| request-time micro compaction | 轻量删减 reasoning、旧工具结果与附件内容 | 仅本次请求 |
| deterministic macro fallback | 模型总结不可用时的降级摘要 | 仅本次请求 |

Session Memory 与 Context Checkpoint 不共享表，也不互相覆盖。

### Context assembly

```text
System prompt
+ checkpoint summary                         # only if valid on active branch
+ active-branch messages after checkpoint
+ current protected turn / current user input
```

压缩前保留完整用户轮、assistant tool call 与关联 tool result 的结构；cut point 只能位于一个完整 turn block 之后。

### Hysteresis

- `auto_compact_trigger_ratio`：高水位，默认 0.80。
- `checkpoint_target_ratio`：低水位，默认 0.60，必须小于 trigger。
- 触发 checkpoint 时，从尾部保留完整 raw/tool/media blocks，直到：

```text
system + checkpoint summary reserve + retained tail + current turn
<= input_budget * checkpoint_target_ratio
```

这样新 checkpoint 留出增长余量；只有后来消息将上下文重新推高到 trigger 才会再次总结。

### Model-generated summary contract

模型输入包含：

1. 上一 checkpoint 的结构化 payload / rendered summary（若有）；
2. 上一 checkpoint 边界到新 cut point 的完整历史；
3. 明确 JSON response schema。

输出字段：

```json
{
  "conversation_goal": "",
  "established_facts": [],
  "user_requirements": [],
  "constraints": [],
  "decisions": [],
  "completed_work": [],
  "pending_work": [],
  "tool_state": [],
  "important_artifacts": [],
  "open_questions": [],
  "latest_user_intent": ""
}
```

Prompt 约束：保留数字、ID、文件路径、接口、工具结论和未完成事项；不得写入 reasoning；不得编造；每项简短具体。Rendered summary 以稳定前缀注入，并作为 protected message。

## Implementation Plan

### Stage 1: Repair repeated compaction semantics

- **Files modified**: `backend/app/services/chat_context.py`, `backend/tests/services/test_chat_context_compression.py`
- **Specific logic**:
  - session-memory 摘要插入后标记为 protected；
  - 仅当替换真实降低 token 时采用该摘要；
  - preflight 已检查同一 base context 时，micro 不重复查询 session-memory；
  - stage `none` 不发送 compression SSE。
- **Validation**:
  - 相同 snapshot 连续应用第二次返回 unchanged；
  - 过大的 summary 回退到原消息；
  - 文件裁剪重建后只发生 preflight + rebuild 两次 session-memory 调用；
  - 无收益状态不发送 SSE。

### Stage 2: Context Checkpoint model and service

- **Files modified**:
  - `backend/app/models/agent.py`
  - `backend/app/core/init_data.py`
  - `backend/app/services/context_checkpoint.py`
  - `backend/app/services/message_branching.py`
  - `backend/app/services/chat_context.py`
  - `backend/app/schemas/agent.py`
  - `backend/tests/services/test_context_checkpoint.py`
  - `backend/tests/services/test_chat_context_compression.py`
- **Specific logic**:
  - 添加每 conversation 一条的 `ConversationContextCheckpoint`，含 active-branch watermark、摘要、结构化 payload、token estimate、提取模型与失败状态；
  - 服务负责读取有效 checkpoint、选择完整 turn cut point、调用团队模型总结、裁剪 summary 到预算、原子 upsert、失效检查；
  - 根据 checkpoint watermark 读取 active-path tail，避免处理覆盖历史及其附件；
  - `prepare_model_context` 在高水位执行 checkpoint 生成并立即用新 checkpoint 重建上下文；
  - 新增并校验 `checkpoint_target_ratio`、`checkpoint_summary_enabled`、`checkpoint_min_new_turns`。
- **Validation**:
  - 触发时 summary 模型仅调用一次，下一轮不重调；
  - 新历史从 checkpoint 边界之后读取；
  - token 使用率压到 target ratio；
  - 分支失效、空 tail、模型失败和超预算均有确定行为。

### Stage 3: Cutover and fallback cleanup

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/services/session_memory.py`
  - `backend/app/schemas/agent.py`
  - tests and implementation-plan status
- **Specific logic**:
  - 规则 macro 只作为模型 checkpoint 生成失败时的 request-local fallback；
  - `ConversationSessionMemory` 恢复为纯语义记忆，不再写入/承载 macro 结果；
  - 删除未接线的 `legacy_compact_*` 与 `hard_budget_only` 配置，或将其替换为真实 checkpoint fallback 控制；
  - 删除 `persist_macro_summary_best_effort` 的 session-memory 写入路径；
  - compression SSE 区分 `checkpoint_summary` 与 deterministic fallback 的 actions。
- **Validation**:
  - 流式、非流式、编辑与 regenerate 都通过共享 `prepare_model_context` 使用 checkpoint；
  - 全量 backend suite 与 coverage gate 通过；
  - 没有旧 session-memory macro 持久化调用或死配置。

## Testing Strategy

### Happy paths

1. 短对话：无 checkpoint、无压缩。
2. 首次越过 trigger：模型生成 checkpoint，保留最近完整尾部。
3. checkpoint 后连续多轮：不再总结，直到重新越过 trigger。
4. 新一轮压缩：旧 checkpoint + 增量历史合成为新 checkpoint。
5. 含工具和媒体：tool call/result 不跨 cut point 分离，媒体轮保留 raw。

### Error paths

1. 总结模型失败：使用规则 macro，不阻断业务回答。
2. 规则 fallback 后仍超预算：emergency fallback 或 `ContextLengthError`。
3. checkpoint watermark 离开 active branch：跳过并标 stale。
4. summary 不比覆盖历史更小：不写 checkpoint。
5. 并发旧任务落后于新 checkpoint：较新的 source message 保持获胜。

### Regression scope

- 非流式 Agent chat
- 流式 Agent chat
- regenerate / message edit active branch
- tool calling rounds
- 图片、文件、RAG 注入
- session-memory async extraction
- SSE compression task rendering

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| 模型摘要丢失关键事实 | 结构化 schema、完整历史增量、稳定保留最近 raw/tool/media tail、summary token 上限 |
| 每轮总结导致延迟/费用上升 | 高低水位滞回、checkpoint watermark、最小新增轮数 |
| 分支复用过期摘要 | active-branch watermark 校验与 stale 标记 |
| 总结模型故障 | deterministic macro + emergency fallback；不改变现有 ContextLengthError 语义 |
| checkpoint 超预算 | 只保存/使用有 token 收益的 summary，必要时缩短 tail 或 fallback |

## Rollback Plan

将 `checkpoint_summary_enabled=false` 可恢复到既有 session-memory + deterministic macro 管线。Checkpoint 数据为附加表，不修改原始 `messages`，可安全保留或后续删除。
