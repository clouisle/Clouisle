# 默认模型上下文预算一致性修复设计文档

## Background & Goals

当前 Agent 可以不设置 `model_id`，此时请求会使用全局 `Model.is_default=True` 的聊天模型。默认模型解析分成两段：

1. `chat.py` 在调用 `prepare_model_context` 前通过 `get_agent_chat_model(agent)` 读取 Agent 绑定的 `TeamModel`；当 `agent.model_id` 为空时返回 `None`。
2. `model_manager.team_chat(..., model_id=None)` 在真正调用模型时才解析全局默认模型，并校验团队授权。

这会造成上下文预算与实际调用模型脱节：压缩阶段收到 `model_context_limit=None`，回退到 `DEFAULT_CONTEXT_LIMIT=32000`；实际模型调用却可能是 `context_length=1000000` 的全局默认模型。

已观察到的症状：

```json
{
  "input_budget": 27000,
  "hard_budget": 27000,
  "before_tokens": 29855
}
```

而默认模型配置为 1M 上下文。`27000 = 32000 - 4000 - 1000`，说明压缩阶段使用了默认 32K 上限。

### Goals

- 默认模型、显式模型和上下文压缩使用同一个已解析的 `Model` 配置。
- 在进入 `prepare_model_context` 前获得真实的 `context_length`、`max_output_tokens`、`provider` 和模型标识。
- 保持团队授权、禁用模型、无默认模型等现有错误语义。
- 覆盖非流式、流式、regenerate/edit 等所有 Chat 路径。
- 为 SSE 增加足以诊断预算来源的运行时字段，避免只看到 `input_budget=27000` 却无法知道来源。

### Non-goals

- 不引入团队级 `context_length` 配置。
- 不修改 `Model` 与 `TeamModel` 的数据模型关系。
- 不改变模型选择优先级：显式 Agent 模型优先，全局默认模型兜底。
- 不改变模型 Provider 的真实请求参数或团队配额规则。

## High-Level Design

### Ownership

```text
Model.context_length / Model.max_output_tokens
    └── 全局模型规格

TeamModel
    └── 团队授权、启用状态、配额、优先级

Agent.model_id
    └── 可选的 TeamModel.id
```

上下文预算仍由全局 `Model` 规格和 Agent 的压缩配置共同计算：

```text
input_budget = model.context_length
             - agent.output_token_reserve
             - agent.safety_margin_tokens
```

### Unified resolution

新增一个可复用的团队聊天模型解析入口，或将现有解析逻辑扩展为同时覆盖显式模型和默认模型。入口必须返回：

```text
resolved Model
resolved TeamModel
```

规则：

1. `Agent.model_id` 有值：按 `TeamModel.id` 读取，并使用其关联的 `Model`。
2. `Agent.model_id` 为空：按 `Model.model_type=chat AND is_default=True AND is_enabled=True` 读取全局默认模型。
3. 用 `team_id + model.id` 查找团队授权的 `TeamModel`。
4. 团队未授权或授权禁用时，沿用 `team_chat` 当前的模型不可用/未授权错误。
5. 将解析结果传给上下文准备和后续 `team_chat`，其中 `model_id` 是模型配置 UUID；`tokenizer_model_id` 仅用于 tokenizer 选择，另行传递 provider、context length 和 max output metadata。

解析结果中的 UUID 是所有 `team_chat` 路由调用使用的唯一模型配置标识；provider 模型名不作为路由句柄传入。

## Implementation Plan

### Stage 1: Centralize default team-chat model resolution

- **Files modified**:
  - `backend/app/llm/manager.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - 可能的 `backend/app/api/v1/endpoints/chat_helpers/model_utils.py`
- **Specific logic**:
  - 显式 Agent 模型保持现有 `TeamModel.id` 语义。
  - Agent 未设置模型时解析全局默认 chat Model，再查当前团队的 TeamModel 授权。
  - 返回独立的模型配置 UUID、tokenizer model name、provider、context length 和 max output metadata。
  - `team_chat` 路由只使用模型配置 UUID；tokenizer model name 仅用于 tokenizer 选择。
  - 没有默认模型、模型禁用、团队未授权时在上下文准备前快速失败。
- **Validation**:
  - 显式 Agent 模型仍解析原绑定模型。
  - 未设置 Agent 模型时解析 `DeepSeek V4 Flash` 等全局默认模型。
  - 未授权团队不会先构造错误预算后才在模型调用阶段失败。

### Stage 2: Thread resolved metadata through every Chat path

- **Files modified**:
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/services/chat_context.py`（仅必要的参数/metadata 调整）
- **Specific logic**:
  - 非流式首轮、非流式工具轮次、流式首轮、流式工具轮次、regenerate/edit 全部使用同一解析结果。
  - 调用 `prepare_model_context` 时传入：
    - `model_id`
    - `provider`
    - `model_context_limit`
    - `model_max_output_tokens`
  - 调用 `team_chat` 时使用同一模型标识，避免压缩模型和实际调用模型分叉。
  - 保留 reactive retry 的 aggressive 语义，但 retry 使用相同的有效模型上下文元数据。
- **Validation**:
  - 1M 默认模型下，`input_budget` 接近 `995000`，约 30K 历史不会触发压缩。
  - 32K 模型仍计算为约 `27000` input budget。
  - 四条 Chat 路径的模型标识和预算一致。

### Stage 3: Improve compression observability

- **Files modified**:
  - `backend/app/api/v1/endpoints/chat_sse.py`
  - `backend/app/services/chat_context.py`
  - `backend/tests/llm/test_chat_sse_events_issue255.py`
- **Specific logic**:
  - 在 `compression_end` 中增加可选诊断字段：
    - `context_limit`
    - `output_reserve`
    - `safety_margin`
    - `model_id`
    - `provider`
  - 保持现有 `input_budget`、`hard_budget`、`pressure_level`、`stage`、`actions` 兼容。
  - 字段只用于诊断，不将敏感 API key 或完整模型配置发送到客户端。
- **Validation**:
  - SSE 能明确区分“模型实际为 32K”与“模型配置为 1M 但压缩逻辑错误回退 32K”。
  - 前端旧客户端忽略新增字段仍能正常渲染。

### Stage 4: Regression, rollout, and cleanup

- **Files modified**:
  - `backend/tests/api/` 下默认模型 Chat 测试
  - `backend/tests/services/` 下上下文预算测试
  - `docs/IMPLEMENTATION_PLAN.md`
  - 本设计文档
- **Specific logic**:
  - 添加默认模型、显式模型、未授权团队、默认模型禁用、无默认模型测试。
  - 清理不再需要的 `model_id or "gpt-4"` 作为上下文预算来源的路径；`gpt-4` 只能作为 tokenizer fallback，不能作为模型上下文上限来源。
  - 更新计划状态并记录验证结果。
- **Validation**:
  - 运行默认模型相关 focused tests。
  - 运行完整 backend suite。
  - 运行 `scripts/check_coverage.py`，保持 line/branch 95% gate。
  - 验证流式、非流式、regenerate/edit 和 reactive retry。

## Testing Strategy

### Happy paths

1. Agent 显式绑定 1M TeamModel：预算使用 1M。
2. Agent 未绑定模型、全局默认模型为 1M：预算使用 1M。
3. Agent 未绑定模型、全局默认模型为 32K：预算使用 32K。
4. 同一全局默认模型被多个团队授权：各团队使用相同 `context_length`，但配额独立。
5. 约 30K tokens 在 1M 默认模型下不产生 compression SSE。

### Error paths

1. 没有启用的全局默认 chat Model：返回现有 model-not-found 错误。
2. 全局默认模型存在但团队未授权：返回现有 team authorization 错误。
3. 全局默认模型被禁用：不进入模型调用，也不构造误导性的 32K 压缩预算。
4. 显式 Agent 模型无效：保持现有错误行为。
5. Provider 实际返回 `ContextLengthError`：retry 仍最多执行一次，并使用同一有效模型元数据。

### Regression scope

- 非流式 Agent Chat。
- 流式 Agent Chat。
- 工具调用多轮循环。
- regenerate / edit active branch。
- 文件、图片、RAG 注入。
- compression SSE 和前端任务文案。
- 团队授权与配额检查。

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| 默认模型没有团队授权 | 在上下文准备前复用统一授权检查并快速失败 |
| endpoint 与 manager 重复查询造成不一致 | 尽量复用同一解析入口，并显式传递解析后的模型句柄 |
| 1M 上下文导致压缩过晚 | 保留 Agent 级 output reserve、safety margin 和 trigger ratio |
| Provider 实际限制小于数据库配置 | 继续保留 Provider `ContextLengthError` 的一次 reactive retry |
| 新 SSE 字段破坏旧客户端 | 只增加可选字段，不改变现有字段和事件名称 |
| 非流式/流式路径漏改 | 对所有 `prepare_model_context` 调用点建立清单并增加路径测试 |

## Rollback Plan

如果统一解析导致默认模型授权行为出现回归，可以先回退 endpoint 的 metadata threading，保留诊断字段和 focused tests；不删除全局 `Model.context_length` 数据。由于本修复不涉及数据库结构迁移，回滚只需要恢复模型解析代码与对应测试。
