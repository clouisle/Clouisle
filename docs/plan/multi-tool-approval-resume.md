# Multi-tool Approval Resume Design Document

## Background & Goals

An Agent model turn can request several tool calls. The loop parks on the first approval and currently discards later calls. Preserve every remaining call in order, apply each call's existing authorization and approval policy, and resume only after each required decision. No approval is transferable to another call.

## High-Level Design

The loop treats approval-enabled builtin calls as exclusive barriers. At a durable interaction pause it passes the unstarted calls to the worker. The worker encrypts those calls in the existing durable worker payload, using the tool-secret keyring. On resume, the loop consumes the saved calls before invoking the model, using the ordinary scheduler, execution boundary, event stream and persistence. Each subsequent pause saves only its unstarted suffix. Existing single-call and historical runs need no migration.

## Implementation Plan

### Stage 1: Retain and resume pending calls
- **Files modified**: `backend/app/services/agent_loop.py`, `backend/app/services/agent_run_worker.py`.
- **Specific logic**: Capture remaining call IDs/names/arguments at the pause; encrypt in worker payload and reconstruct at resume. Inject calls into the normal execution branch without another model call. Keep resumed turn iteration semantics and preserve event ordering. Make configured builtin approvals exclusive before dispatch.
- **Validation**: Exercise successive waiting states, exact arguments and calls in order, mixed approval/non-approval and stop behavior.

### Stage 2: Regression coverage
- **Files modified**: `backend/tests/services/test_tool_batch_scheduler.py`, `backend/tests/services/test_agent_run_worker_lifecycle.py` or focused existing test files.
- **Specific logic**: Drive real AgentLoop with scripted model, approvals and resume; verify reject continues remaining calls, old payloads, no duplicate side effects and encrypted payload. Check shared scheduler behavior without approval unchanged.
- **Validation**: Run targeted backend tests and scenario smoke; confirm results and failure paths.

### Stage 3: Documentation
- **Files modified**: `docs/guide/CHANGELOG.md`, `docs/guide/CHANGELOG_zh-CN.md`, `docs/IMPLEMENTATION_PLAN.md`.
- **Specific logic**: Document sequential confirmations, no batch approval and keyring retention for waiting runs.
- **Validation**: Ruff checks and targeted tests; no services or browser.

## Testing Strategy

Happy paths: multiple approvals and mixed calls retain original order, exact arguments and separate decisions. Error paths: rejection produces a tool error without side effect and later calls continue; malformed ciphertext fails closed; stop does not execute remaining calls. Regression: ordinary parallel tools, ask-user pause, existing single approvals and durable reconnect.

## Risks & Mitigation

The saved call arguments may contain secrets: persist only encrypted, never emit ciphertext or raw queued arguments in status. Old keyring keys must remain available until waiting runs complete; rollback must drain waiting runs before deploying old code. Existing worker ownership and recovery semantics remain unchanged; calls must use their original IDs to prevent duplicate execution.
