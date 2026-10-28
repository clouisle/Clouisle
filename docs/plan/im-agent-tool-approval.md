# IM Agent Tool Approval Design Document

## Background & Goals

Feishu and WeChat can answer ask_user, but channel tool calls bypass interactive Agent confirmation. Implement per-call confirmation via IM text, using the existing durable AgentRun and caller-only ToolApproval boundary. No approval may be applied to another user, channel, conversation, run or call.

## High-Level Design

Introduce distinct trusted Feishu and WeChat execution origins, retaining legacy channel origin as non-interactive. A shared service validates waiting run, bound user, conversation, entrypoint, execution and call, and creates the existing approval decision with a receipt-derived idempotency key. The channels announce safe execution metadata through their existing durable outboxes, then route `/approve <code>` and `/reject <code>` to that service. A full execution UUID is used as the code to eliminate truncated-code collisions and persists without schema changes. The announcement creation timestamp fences old messages. Channel session routing, authorization, delivery and durable AgentRun remain authoritative. ask_user retains its existing path; unknown waits fail closed.

## Implementation Plan

### Stage 1: Trusted origins and shared boundary
- **Files modified**: `backend/app/schemas/tool_approval.py`, `backend/app/services/tool_context.py`, `backend/app/services/tool_execution.py`, `backend/app/services/channel_tool_approval.py`, related tests.
- **Specific logic**: Add specific Feishu/WeChat origins, require valid origin ID, permit caller confirmation only for those known durable IM runs; preserve fixed-connection policy for channels. Implement safe preview, exact full-UUID token and authorized decision bound to run, user, origin, conversation and pending tool ID. Use existing `decide_approval` and resume scheduler; deterministic provider/receipt idempotency. No raw secrets.
- **Validation**: Reject wrong user, channel, run, token, expired or resolved approvals; duplicate decision and dispatch recovery; verify legacy non-interactive entries unchanged.

### Stage 2: Feishu channel
- **Files modified**: `backend/app/services/feishu_agent_runtime.py`, Feishu tests, backend translation catalogs.
- **Specific logic**: Submit trusted Feishu origin, announce approval idempotently; fence pre-announcement messages; accept explicit commands; route actual ask_user separately and reject unknown waits; preserve receipt and authorized session processing.
- **Validation**: Exercise allow/reject, stale commands, duplicate receipts, mixed question/approval, output delivery and stop.

### Stage 3: WeChat channel
- **Files modified**: `backend/app/services/wechat_agent_runtime.py`, WeChat tests, backend translation catalogs.
- **Specific logic**: Same contract using WeChat durable outbox and authorized binding; `/skip` remains ask_user only; other text cannot approve.
- **Validation**: Same security/recovery and ask_user tests on WeChat.

### Stage 4: Documentation and verification
- **Files modified**: existing Feishu and WeChat guides, approval reference, changelogs, implementation index.
- **Specific logic**: Document commands, full UUID requirement, single approval and deployment compatibility.
- **Validation**: Run backend targeted tests, Ruff, i18n sync, and an executable end-to-end scenario without services; no live provider or browser without explicit permission.

## Testing Strategy

- Happy path: channels announce the redacted operation and process approved/rejected calls, including successive calls and ask_user before/after approval.
- Negative paths: wrong actor, session, origin, identifier, stale/replayed command, expired execution, missing outbox, revoked access and malformed/unknown waiting kinds fail closed.
- Regression: existing ask_user, channel fixed connections, web approval, workflow and old channel entrypoints retain semantics. Verify no plaintext credentials in notifications.

## Risks & Mitigation

Provider replies may arrive out of order: use per-execution full identifier and persisted notification cutoff. Decision/dispatch crash: existing parked-run recovery and idempotency, plus explicit resume scheduling when execution already decided. Concurrent deployment: deploy consumers with support before producers issue new origins; rollback must drain waiting IM approvals. Keep old origin non-interactive.
