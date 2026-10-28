# Agent API Approval and Tool Arguments Design

## Background & Goals

The Agent API page omits approval interaction guidance, and approval previews do not show the original tool call arguments. Document the actual supported API contract and show the model-supplied arguments without disclosing secrets.

## High-Level Design

Trace the Agent API run and approval endpoints, their authentication and waiting states before documenting them. Trace the tool-call arguments through durable execution snapshots to the approval preview; preserve execution inputs and the existing secret-redaction boundary.

## Implementation Plan

### Stage 1: Agent API approval guidance
- **Files modified**: `frontend/app/(platform)/app/apps/[id]/api/_components/api-access-content.tsx`, `frontend/i18n/{en,zh}/agents.json`, `frontend/i18n/types/agents.ts`, component tests and API guides.
- **Specific logic**: Document interactive JWT approval, the decision endpoints, waiting events and API-key fail-closed behavior.
- **Validation**: Six frontend page/component tests passed; TypeScript, ESLint and the translation-key check passed.

### Stage 2: Approval argument preview
- **Files modified**: `backend/app/services/{agent_loop,tool,tool_execution,tool_approvals,agent}.py`, `backend/app/api/v1/endpoints/{chat_tools,tool_mcp}.py` and related tests.
- **Specific logic**: Preserve model arguments in tool-call events and history; project business arguments into redacted approval previews while retaining full execution parameters for digest, encryption and dispatch. Keep the approval marker in pending interaction state.
- **Validation**: Focused backend suite passed 98 tests, including tool approval resume and redaction; an independent snapshot smoke check confirmed secret masking and original-argument recovery.

### Stage 3: Integration verification
- **Files modified**: English and Chinese changelogs and API guides, plus this plan.
- **Specific logic**: Document the API authentication boundary and preview behavior. Existing persisted previews are not reconstructed.
- **Validation**: Ruff checks passed. No service or browser was started; visual verification remains unperformed.

## Testing Strategy

- Happy path: pending approval displays real arguments and the documented client flow reflects the actual run state.
- Error path: sensitive values are masked and unauthorized callers cannot decide another user's approval.
- Regression: tool execution, resume, and other API documentation sections retain their behavior.

## Risks & Mitigation

Previewing arguments may expose credentials: retain the existing redaction policy and test nested secrets. Existing durable pending executions may already contain snapshots created with the old projection; do not fabricate missing original arguments. Roll back the change by reverting the commits if the new preview or documentation is incorrect.
