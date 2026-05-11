# Agent Context Compression Design Document

## Background & Goals

当前项目已经完成了第一代 agent 上下文压缩能力：

- `backend/app/services/chat_context.py` 负责共享上下文准备、token budget 计算、micro/macro compaction 和 reactive retry
- `backend/app/api/v1/endpoints/chat.py` 已在非流式、流式、regenerate 三条链路中统一接入
- `compression` SSE 已可在前端聊天界面中显示

但当前触发模型仍然偏“硬预算守卫”：只有在上下文接近或超过最终 `input_budget` 时才真正开始压缩。这不符合当前目标。

本次要把系统升级为更接近“长上下文治理”的模式：

1. 在大约 **80% 上下文使用率**时开始主动压缩，而不是等到逼近 hard limit 才压
2. 引入更清晰的分层阈值：`warning / auto_compact / blocking / reactive`
3. 把当前偏粗粒度的 micro compaction 演进为更可控的 **selective micro compaction**
4. 保持非流式 / 流式 / regenerate 三条链路行为一致
5. 保留当前 reactive retry 兜底能力
6. 为第二阶段 Session Memory Extractor / SM Compact 预留结构化接入点

### Success criteria

- 使用率达到 `auto_compact_trigger_ratio`（默认约 0.8）时，系统会主动触发压缩
- 触发阈值与 hard input budget 解耦
- selective micro compaction 优先保留最近 raw turns / recent tool turns / 文件相关近场上下文
- compression SSE 能表达 proactive / blocking / reactive 的区别
- 非流式 / 流式 / regenerate 的压缩行为保持一致
- provider 侧 `ContextLengthError` 仍然最多只自动重试一次

## High-Level Design

### Architecture

在保留现有共享压缩层的基础上，继续以 `backend/app/services/chat_context.py` 为唯一压缩决策入口：

1. 构造完整上下文
2. 估算 token 使用量
3. 计算硬预算和分层阈值
4. 评估上下文压力状态
5. 根据压力状态选择：
   - 不压缩
   - selective micro compact
   - macro compact
   - Phase 2 的 Session Memory Compact
6. 如果仍超过 hard budget，抛出 `ContextLengthError`
7. endpoint 层继续复用 `prepare_model_context(...)` / `retry_prepare_model_context(...)`

### Pressure states

建议引入以下压力状态：

- `normal`
- `warning`
- `auto_compact`
- `blocking`
- `over_budget`

### Budget model

区分两种预算：

- **Hard budget**：`TokenBudget.input_budget`
  - 用于最终安全保护，不能超过
- **Trigger budgets**：基于 ratio 从 hard budget 推导
  - `warning_input_budget`
  - `trigger_input_budget`
  - `blocking_input_budget`

### Compaction stages

#### Stage A: proactive selective micro compaction

在达到 `auto_compact_trigger_ratio` 后优先执行：

- trim 历史 reasoning
- 只对超大且较旧的 tool result 做摘要
- 对低优先级旧 assistant narrative 进行 block 级压缩
- 继续保留最近原始 turn 和工具链原文

#### Stage B: blocking-level macro compaction

当达到 blocking 阈值，或者 selective micro 后仍高压时：

- 继续保留最近 raw turns
- 保留最近 tool turns
- 将更老的 blocks 摘要为 synthetic summary message

#### Stage C: reactive retry

如果 provider 侧仍返回 `ContextLengthError`：

- 调用 `retry_prepare_model_context(...)`
- 使用更激进参数
- 最多只重试一次

#### Stage D: Phase 2 Session Memory / SM Compact

在 selective micro 与 legacy macro 之间插入结构化 session memory compact：

- 先做 request-time ephemeral memory compact
- 后续再考虑持久化 extractor / snapshot

## Implementation Plan

### Stage 1: Ratio-based thresholds and pressure states

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - `backend/app/schemas/agent.py`
  - `backend/app/models/agent.py`
  - `backend/app/api/v1/endpoints/agents.py`
  - `frontend/lib/api/agents.ts`

- **Specific logic**:
  - 扩展 `ContextCompressionConfig`，新增：
    - `warning_ratio`
    - `auto_compact_trigger_ratio`
    - `blocking_ratio`
    - `compaction_policy`
    - `macro_on_trigger`
    - `retention_strategy`
  - 在 `backend/app/services/chat_context.py` 中新增：
    - `CompressionThresholds`（或等价结构）
    - `_build_compression_thresholds(...)`
    - `_assess_context_pressure(...)`
  - `prepare_model_context(...)` 从“是否超过 hard budget”切换为“按 pressure state 决策”
  - 保留 `TokenBudget.input_budget` 作为最终 hard limit
  - `retry_prepare_model_context(...)` 保持 aggressive fallback 语义

- **Validation**:
  - 构造 < warning、≈80%、> blocking、> hard budget 四类输入，确认 pressure state 正确
  - 确认新增 config 字段能通过 schema 校验与前端 type build
  - 确认旧 agent 配置不需要回填也能使用默认值运行

### Stage 2: Selective micro compaction

- **Files modified**:
  - `backend/app/services/chat_context.py`

- **Specific logic**:
  - 在现有 `_split_turn_blocks(...)` 和 `_is_tool_turn(...)` 基础上新增 block retention 分析 helper：
    - `_analyze_turn_block(...)`
  - 用 selective micro 替换当前“全量摘要 tool result”策略：
    - 保留最近 3 个 user turn block 原文
    - 保留最近 2 个 tool turn block 原文
    - 保留包含图片/文件输入的近场 block 原文
    - 仅对超大且较旧的 tool result 进行摘要
    - 历史 reasoning 继续优先裁剪
  - 新增可调字段：
    - `keep_recent_tool_results`
    - `keep_recent_tool_result_minutes`
    - `tool_result_compact_min_tokens`
  - 对 `assistant tool_call -> tool_result` 配对结构只改内容，不改关联字段

- **Validation**:
  - 人工构造长工具链上下文，确认 recent tool turns/raw blocks 保留稳定
  - 验证旧 tool results 会被选择性压缩，而不是所有 tool results 一起变短
  - 验证压缩前后 `tool_call_id` 结构不破坏

### Stage 3: Compression observability and frontend messaging

- **Files modified**:
  - `backend/app/api/v1/endpoints/chat.py`
  - `frontend/lib/api/agents.ts`
  - `frontend/hooks/use-chat.ts`
  - `frontend/hooks/use-embed-chat.ts`
  - `frontend/components/chat/message.tsx`
  - `frontend/i18n/en/chat.json`
  - `frontend/i18n/zh/chat.json`

- **Specific logic**:
  - 扩展 `build_compression_event(...)` payload，新增：
    - `pressure_level`
    - `trigger_ratio`
    - `warning_ratio`
    - `blocking_ratio`
    - `trigger_budget`
    - `hard_budget`
    - `utilization_before`
    - `utilization_after`
    - `policy_used`
    - `actions`
    - `retained_recent_turns`
    - `retained_tool_turns`
    - `compacted_blocks`
  - `trigger` 语义标准化为：
    - `proactive_threshold`
    - `blocking_threshold`
    - `context_length_error`
  - 前端继续复用 compression task，不新增消息类型
  - `message.tsx` 按 proactive / blocking / reactive 输出更清晰的文案

- **Validation**:
  - 流式主聊天和 regenerate 都能展示 proactive compression
  - embed chat 不因 payload 增强而报错
  - 压缩步骤文案能表达 proactive / reactive 区别
  - message end 后 compression task 正常 completed

### Stage 4: Phase 2 Session Memory / SM Compact design hooks

- **Files modified**:
  - `backend/app/services/chat_context.py`
  - 可能的 memory / snapshot / async extraction 相关 backend 模块（实施前再定点）

- **Specific logic**:
  - 在共享压缩层中预留 `session memory compact` 插入点
  - 第一阶段先设计 request-time ephemeral session memory compact：
    - `_extract_session_memory_from_blocks(...)`
    - `_build_session_memory_message(...)`
  - memory summary 结构推荐包含：
    - Current task / user intent
    - Confirmed constraints
    - Important files/modules
    - Key decisions
    - Tool findings
    - Open items / next steps
  - 第二阶段如果效果稳定，再评估是否做 conversation-level persisted snapshot

- **Validation**:
  - 当前阶段先验证接口与压缩阶段插槽设计合理，不要求一次性实现持久化 extractor
  - 确认 selective micro -> session memory compact -> legacy macro -> reactive retry 的顺序在代码结构上可插入

## Testing Strategy

### Happy path tests

1. 短会话
   - 不触发压缩
   - `pressure_level = normal`

2. 使用率接近 80% 的中长会话
   - 触发 proactive selective micro compact
   - 未超过 hard budget 也会产生 compression metadata / SSE

3. 长工具链会话
   - recent tool turns 被保留
   - selective micro 压缩较旧的大工具输出

4. regenerate
   - 和主流式一样按 ratio 阈值执行压缩
   - reactive retry 行为不变

### Error path tests

1. selective micro 后仍高压
   - 进入 macro compact
2. macro 后仍超 hard budget
   - 抛出 `ContextLengthError`
3. provider 流式调用时仍返回 `ContextLengthError`
   - 只自动 retry 一次
4. 扩展后的 compression payload
   - 前端旧逻辑不崩溃

### Regression scope

重点回归：

- 非流式 agent chat
- 流式 agent chat
- regenerate
- embed chat
- 文件上传 / fileContent 注入
- 图片输入 / vision 请求
- 工具调用链完整性

## Risks & Mitigation

### 风险 1：80% 触发过早，导致上下文保真度下降

- **Mitigation**:
  - 默认只在 80% 先触发 selective micro，不立即做 macro
  - `macro_on_trigger` 默认关闭
  - 优先保留 recent raw/tool blocks

### 风险 2：selective micro 规则不准，误压关键上下文

- **Mitigation**:
  - block 级保留策略先从保守规则开始
  - recent user/tool/file blocks 默认不压
  - 只对超大旧 tool results 做摘要

### 风险 3：SSE payload 增强后前端兼容性问题

- **Mitigation**:
  - 保持 `compression` 事件类型不变
  - 仅向 payload 增量加字段
  - 前端先按可选字段兼容解析

### 风险 4：后续 Phase 2 Session Memory 设计与当前结构耦合不够

- **Mitigation**:
  - 先在 `chat_context.py` 建立清晰的 pressure / policy / compaction stage 插槽
  - 不在 endpoint 层散落新策略判断

### Rollback plan

如果 80% proactive compaction 在验证中表现不佳，可快速回退：

- 将 `auto_compact_trigger_ratio` 默认值调高至接近 1.0
- 保留新的预算结构，但退回“接近 hard budget 才压”的行为
- selective micro helper 可继续保留，为后续重新调阈值做准备
