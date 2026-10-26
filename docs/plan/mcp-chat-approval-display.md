# MCP Chat Approval and Display Repair

## Background & Goals

- Chat shows streamed `mcp_…` names and repeatedly changes the thought header.
- MCP child-operation approval policies are ignored by the current execution boundary.
- Success: complete MCP calls remain inside thought details; the active MCP thought header stays stable; explicitly configured child policies and Agent confirmation switches both pause before side effects.
- Discovery, direct testing, workflows and non-interactive entrypoints must never create approval waits.

## High-Level Design

Keep the existing AgentLoop, ToolExecutor and durable approval/resume path. Filter incomplete streamed MCP names against the model's offered definitions. During interactive Agent execution only, compose the explicitly stored MCP policy with the Agent's caller-confirmation requirement; non-MCP tools retain their existing explicit Agent switch. An empty stored policy means allow, not an inferred confirmation requirement. Both creation and claiming use the same composed policy fingerprint. Do not add a discovery cache: tool-list loading precedes model execution and does not emit tool-call events; the reported visible names occur on the streamed invocation path.

## Implementation Plan

### Stage 1: Approval boundary
- **Files modified**: `backend/app/services/tool_execution.py`, `backend/tests/services/test_tool_execution_boundary.py`.
- **Specific logic**: Honor exact MCP `tool:{name}` operation policies only for interactive Agent calls; preserve caller confirmation as an additional requirement; exclude workflow-owned calls.
- **Validation**: Real SQLite Tool/approval persistence through chat dispatch. Assert no MCP operation before approval, successful one-time resume, rejection of replay, and bypass for discovery/test/workflow/background origins.

### Stage 2: Stream and thought presentation
- **Files modified**: `backend/app/services/agent_loop.py`, existing loop behavior tests, `frontend/components/chat/message.tsx`, `frontend/components/chat/message.test.tsx`.
- **Specific logic**: Do not publish partial MCP aliases that are not offered tools. Keep MCP details inside the thought trace and the active header generic and stable.
- **Validation**: Fragmented MCP-name event smoke; DOM rerender across reasoning/call/result/reasoning, stable thought/header identity and nested tool detail. No application services or browser sessions.

## Testing Strategy

- Chat child operation requires approval; an unrelated allowed operation executes normally.
- Agent confirmation cannot be relaxed by a child allow rule.
- Non-Agent/list/test/workflow paths never wait, including workflow-owned Agent calls.
- Existing approval resume, workflow bypass, chat tool dispatch and frontend message suites.
- TypeScript, targeted ESLint and Ruff.

## Risks & Mitigation

- Saved non-empty policies previously ignored in chat now apply there; empty policies remain allow.
- Approval creation and claim must use identical policy layers to avoid rejecting approved executions.
- No browser or live external MCP compatibility claim; verification uses production dispatch with local persistence and a controlled protocol boundary.
- Rollback: revert the repair commit; no schema or data migration.

## Status

Completed.

### Verification

- Backend targeted regression suites: 99 passed. Includes MCP child approval, one-time resume, explicit Agent confirmation precedence, discovery/test/workflow bypass, AgentLoop fragmented-name events and durable approval recovery.
- Frontend chat and pending approval suites: 289 passed across 35 files; TypeScript and targeted ESLint passed.
- Ruff format/check passed for the five changed backend files.
- Standalone production-dispatch smoke with real SQLite persistence and a controlled MCP protocol boundary: `awaiting_approval` with zero side effects, then `succeeded` with one external-boundary invocation after approval.
- No browser, application service or live external MCP server was started. UI evidence is DOM render/rerender, not a browser visual check.
