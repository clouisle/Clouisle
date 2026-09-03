# YUN-146 Agent 对话改用模型工具提问并支持多问题

## Background & Goals
当前 Agent 对话通过旧式文本标记请求用户输入，再由前端解析成单问题卡片。该协议无法稳定关联工具调用、暂停 Agent 或提交结构化答案，也不支持一次提交多个问题。

目标是使用正常的模型内置 `ask_user` 工具，以 `questions` 数组支持单问题和多问题；持久化 AgentRun 等待状态和 pending tool call；通过 `tool_call_id` 与结构化 `answers` 恢复同一个 run；用通用 tool-call/tool-result 协议渲染多问题表单；并完全删除旧式提问协议、旧事件/消息类型和旧 UI 卡片。

`ask_user` 对所有可交互的流式 Agent 可用；后端在非流式运行中不暴露需要暂停的交互工具。

## High-Level Design
模型调用 `ask_user` 时输入：

```json
{
  "questions": [
    {
      "id": "deployment_target",
      "question": "部署到哪里？",
      "options": ["云端", "本地"],
      "required": true
    }
  ]
}
```

`questions` 至少包含一项；每项拥有稳定 `id`、问题文本、可选选项和必填标记。执行层在持久化原始 tool call 后将 AgentRun 置为非终态 `waiting`，发布通用 run event，worker 退出而不完成运行。答案接口验证运行归属、pending tool-call 标识、答案完整性及单次消费，保存匹配 `tool_result` 后唤醒一个 continuation worker。

PostgreSQL/AgentRun 是执行真相；Redis 仅用于事件重放、发布和唤醒。前端从通用 tool-call 的 `toolName`、`input`、`toolCallId` 和关联 tool-result 识别 `ask_user`，单问题不走特殊分支。

## Implementation Plan

### Stage 1: Durable model-tool contract
- **Files**: `backend/app/llm/tools/builtin/`, `backend/app/llm/tools/registry.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/api/v1/endpoints/chat_tools.py`, `backend/app/services/agent_loop.py`
- **Work**: Register and validate the OpenAI-compatible `ask_user` tool; preserve generic tool-call/result identity.
- **Validation**: Tool schema and valid/invalid argument tests.

### Stage 2: Waiting and answer resumption
- **Files**: `backend/app/models/agent_run.py`, `backend/app/schemas/agent.py`, `backend/app/services/agent_run_store.py`, `backend/app/services/agent_run_stream.py`, `backend/app/services/agent_run_worker.py`, `backend/app/api/v1/endpoints/chat.py`, related migrations.
- **Work**: Add durable waiting, pending interaction persistence, authorized structured answer submission, idempotency, replay, stop, and same-run continuation.
- **Validation**: Waiting/resume, replay, identity errors, duplicate, stop, and continuation tests.

### Stage 3: Remove legacy XML question protocol
- **Files**: Prompt/parser/event modules, frontend XML parsing/cards and their tests.
- **Work**: Remove the old text-markup prompting instructions, parser, re-exports, old SSE/message event types, and frontend markup parsing/card components. Expose `ask_user` as the canonical chat tool; no text markup is emitted or parsed.
- **Validation**: Repository stale-reference search and focused API/prompt/helper tests.

### Stage 4: Multi-question chat UI
- **Files**: Chat parts/rendering/hook/adapters/public/embed/run pages and tests.
- **Work**: Render generic `ask_user` tool calls as one shared array-based form with required validation and structured durable input.
- **Validation**: One/many-question component, adapter, and page tests.

### Stage 5: Regression verification and cleanup
- **Files**: Focused tests and this index.
- **Work**: Run focused backend/frontend tests and type checks; remove stale imports/fixtures; record observed results.
- **Validation**: End-to-end test harness for pause/resume without starting services or browsers.
## Testing Strategy
- Happy paths: schema, tool-call persistence, waiting, answer submission, replay, continuation, one/many-question UI.
- Negative paths: malformed questions, missing required answers, wrong run/tool ids, duplicate submissions, stopped/terminal runs.
- Regression: generic tools, text follow-up/steer, media/attachments, reconnect/stop, public/embed adapters.

## Risks & Mitigation
- Persist pending state before publishing/waking to prevent reconnect races.
- Preserve original `tool_call_id` and reject mismatched submissions.
- Keep waiting non-terminal and resume only through authorized answer submission.
- Keep ordinary suggested-question text behavior separate from `ask_user`.


## Verification results (2026-09-03)
- Backend: `backend/.venv/bin/pytest -q tests/llm/test_tool_registry_behavior_coverage.py tests/services/test_chat_agent_tools.py tests/services/test_agent_loop_behavioral_smoke.py tests/services/test_agent_run_durable.py` — 40 passed. The worker persists pending `ask_user` state before waiting and emits the structured answer result from the continuation worker.
- Frontend: `bun test --isolate` — 2298 passed; `bunx tsc --noEmit` — clean. The focused ask_user/message/adapter subset also passed 90 tests; the standalone legacy `embed.test.ts` still targets removed workflow APIs and is outside this feature's contract.
- Legacy protocol search: no stale references remain.
- No services or browsers were started during verification.
