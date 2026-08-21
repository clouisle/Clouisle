# Agent Context Loop Fix Design Document

## Background & Goals

会话 53272312（Agent「项目经理」，max_iterations=200）暴露的故障链：

1. 长工具循环中上下文膨胀至 194k tokens（窗口 100k）
2. `summary_keep_recent_turns` 按 USER 消息数轮次，该会话仅 4 轮 → "保留最近 3 轮"保留了几乎全部内容，摘要区为空
3. 当前轮 203 条工具步骤（114k tokens）被 protected 永不摘要
4. 超预算后 emergency fallback 把上下文砍到 `[system, 当前请求]` 两条 → 模型每轮迭代都"失忆重启"，反复 `inspect_asset` 直到撞满迭代上限

成功标准：

- 任意长度的工具循环内，送入模型的上下文始终 ≤ input_budget，且**永远包含**：系统提示词、任务目标（摘要或原文）、最近若干步工具交互原文、当前请求
- emergency fallback 不再产生"只剩 system+当前请求"的失忆形态
- 压缩过程对用户端可见（compression SSE 事件先于长时间摘要发出）

## High-Level Design

### Phase 1: 核心正确性

#### 1.1 保留区双重上限（修"轮次保留无界"）

新增配置 `summary_keep_budget_ratio`（默认 0.3，0.1–0.8）：原文保留区（最近 N 轮 + 当前请求）总 token 不得超过 `input_budget × ratio`。

算法：先按现有 `_recent_turns_start_index` 取保留起点，估算保留区 token；超限则把 keep_start 前移到更老的轮次边界（最老的保留轮落入摘要区），循环直至达标或只剩当前请求。保留区至少含当前请求 + 最后 10 条消息。

#### 1.2 工具循环确定性压缩（修"当前轮无界膨胀"——核心）

新模块 `backend/app/services/tool_step_compaction.py`，恢复旧 `compact_active_tool_messages` 的职能但精简：

- 输入：`messages`、`round_steps_start`（当前轮 override 起始 index）、`keep_recent_steps`（新配置 `summary_keep_recent_steps`，默认 12）、token 上限
- 行为：当前轮步骤中，**最后 K 条原文保留**；更早的**已完成** tool_call/result 配对压缩为一条 assistant 进度摘要消息：
  ```
  [工具进度摘要] 本轮前 N 步已完成（详情从略）：
  1. inspect_asset({"ref":"7e68"}) → docx 文件元数据（77KB）
  2. ...
  ```
  每步一行：工具名 + 参数截断 + 结果首行截断。纯规则生成，无模型调用、无额外延迟
- 协议安全：只压缩完整配对（assistant tool_calls + 其全部 tool 结果）；未完成尾部（最后一次调用尚未收到结果）永不触碰
- 幂等：每轮迭代从 endpoint 重建的完整 override 列表重新推导，不叠加损失
- 触发时机：prepare 内，模型摘要阶段之后，当 `after_tokens > trigger_budget` 时执行（确定性压缩成本低，可每次迭代执行）

#### 1.3 emergency fallback 保底（修"失忆重置"）

emergency 触发时的兜底上下文从 `[system, 当前请求]` 改为 `[system, 持久化摘要(若有), 当前请求]`——即使所有压缩手段失败，模型仍保有任务目标与已完成工作的摘要，不再从零重启。

#### 1.4 执行顺序（prepare 内）

```
build messages（含水印摘要注入）
→ 估算 before_tokens
→ 超 trigger：模型摘要（DB 历史 + 老轮次，保留区受 1.1 约束）
→ 仍超 trigger 或 override 区过大：1.2 确定性步骤压缩
→ 仍超 input_budget：1.3 emergency（带持久化摘要）
```

### Phase 2: 压缩过程可见（两阶段 prepare）

现状问题：摘要模型调用（最长 180s×3）在 prepare 内同步执行，SSE 首字节被阻塞，用户端无任何指示（08:29 超时即此）。

方案：拆分 API——

```python
plan = await build_context_plan(...)      # 快速：构建+估算+判断是否将触发摘要
# endpoint: if plan.will_summarize: yield compression_start
prepared = await plan.finalize()          # 执行摘要
# endpoint: yield compression_end
```

- 流式三条链路在 finalize 前发 compression_start（前端已有任务态渲染），finalize 后发 compression_end
- 非流式路径顺序调用两阶段
- 注意确认 global_timeout 是否覆盖 finalize，必要时将其排除在该预算外

## Implementation Plan

### Stage 1: 确定性步骤压缩模块

- **Files**: 新增 `backend/app/services/tool_step_compaction.py`
- **Logic**: `compact_round_tool_steps()` 如 1.2 所述；复用 chat_context 的 token 估算（传入 callable，避免循环依赖）
- **Validation**: 单测——完整配对压缩、未完成尾部保留、最后 K 步保留、幂等性

### Stage 2: prepare 接入与保留区上限

- **Files**: `backend/app/services/chat_context.py`
- **Logic**: 1.1 保留区预算约束；1.2 压缩调用接入执行链；1.3 emergency 保底摘要
- **Validation**: 单测复现 53272312 形态（4 轮 + 203 步 override + fake summarizer），断言最终上下文 ≤ budget 且含 system/摘要/最近步骤/当前请求

### Stage 3: 配置面

- **Files**: `backend/app/schemas/agent.py`、`frontend/lib/api/agents.ts`、`DEFAULT_CONTEXT_COMPRESSION_CONFIG`
- **Logic**: 新增 `summary_keep_budget_ratio`、`summary_keep_recent_steps`
- **Validation**: schema 校验 + tsc

### Stage 4: 两阶段 prepare 与 SSE（Phase 2）

- **Files**: `backend/app/services/chat_context.py`、`backend/app/api/v1/endpoints/chat.py`（4 处调用点）
- **Validation**: 流式手测 compression_start 先于长摘要出现；tsc/ruff

### Stage 5: 验证与回归

- 新增聚焦测试（旧压缩测试套件仍按约定暂缓处理）
- 手测：重启 backend 后在 53272312 会话发"继续"，验证 agent 推进真实工作、compression 事件可见、无死循环

## Testing Strategy

- 单测：保留区预算约束（少轮次大工具循环形态）、步骤压缩协议安全、emergency 保底摘要
- 复现回归：53272312 数据形态重放（fake summarizer，不发真实请求）
- 手动：真实会话续跑观察

## Risks & Mitigation

- 规则式步骤摘要质量低于模型摘要 → 每步保留工具名+参数+结果首行，且最近 12 步原文；后续可升级
- 极端"单轮巨大"场景会摘要到最近轮次 → 摘要指令已强制保留关键标识符，属预期行为
- 两阶段重构触及 8 个调用点 → 机械替换，ruff/tsc 兜底
- 重复相同工具调用的模型行为本身（非上下文问题）→ 可选后续：连续 N 次相同调用注入 system 提醒（本期不做）
