# Tool-Only Approval and API Key Design

## Background & Goals

Tool maintainers configure approval for Agent calls. Site, team and entrypoint policy layers duplicate that configuration and must not affect execution. API-key Agent clients must be able to approve their own pending calls and resume; workflows must never trigger tool approval regardless of authentication.

## High-Level Design

Use the tool's own decision and operation override as the approval authority for Agent runs. Persist and enforce the initiating API key identity at the durable run and execution boundary, rather than treating all keys owned by the same user as equivalent. Keep user-session decisions scoped to the owning user. Workflow tool executions bypass tool-approval creation, including nested execution and API-key paths. Remove the obsolete policy management surfaces and enforcement without deleting historical user data blindly; pending executions created under the old policy must not be silently executed under changed rules.

## Implementation Plan

### Stage 1: Remove policy layers
- **Files modified**: `backend/app/services/tool_approval_policies.py`, `tool_execution.py`, related endpoints, migrations, frontend policy management pages/API, callers and tests.
- **Specific logic**: Cut over all execution, preview and management callers to tool-only policy; retire obsolete layers and UI. Ensure pending executions whose original bindings no longer match are safely invalidated rather than approved under weakened policy.
- **Validation**: Cutover tests cover removed layers, cancellation and restarting waiting runs; historical policy rows remain stored for audit and rollback but are not read for new decisions.

### Stage 2: API-key decisions and resume
- **Files modified**: API key authentication dependencies, Agent run submission/worker/context, tool approval endpoints and service/model schemas; targeted tests.
- **Specific logic**: Capture the authenticated key ID when submitting a run; allow that same active authorized key to read and decide its execution, never a different key or unscoped key. Resume the frozen call after approval, reject idempotently and preserve caller identity across worker restart.
- **Validation**: SQLite-backed service/endpoint tests exercise waiting, same-key decision, queued resume, different-key denial, revocation, scope checks and idempotency; broker dispatch is stubbed. Legacy runs with no key column are excluded from key-scoped listings, while explicit-ID access checks their payload.

### Stage 3: Workflow exclusion
- **Files modified**: workflow tool executor, durable execution boundary and tests.
- **Specific logic**: Workflow-origin tool calls never create approval gates, regardless of tool configuration, API-key entrypoint or nesting.
- **Validation**: Workflow executor and execution-boundary tests cover direct, nested and API-key-origin workflow calls without approval gates; legacy pending calls are cancelled rather than executed.

### Stage 4: API documentation and integration
- **Files modified**: Agent API access component and translations, API guides, changelogs and tests.
- **Specific logic**: Document API-key approval endpoints, authentication scope, waiting events, decision, rejection and stream reconnection; remove obsolete policy-layer descriptions.
- **Validation**: Frontend full test suite, TypeScript and translation-key check passed. Backend full suite passed 10,711 tests with four skips; focused API-key/workflow test run passed 18 tests. No service or browser was started, so external HTTP/SSE and a live worker were not exercised.

## Testing Strategy

Test successful and rejected decisions, replay/idempotency, principal isolation, revoked and unscoped keys, workflow bypass, old pending bindings, persisted worker recovery and legacy policy configurations. Confirm no secret or approval state leaks across users or keys.

## Risks & Mitigation

API keys are bearer credentials: bind decisions to the original key and Agent authorization, never only the key owner. Avoid silent relaxation of old pending approvals; invalidate safely if policy bindings no longer hold. Keep user-auth flows and workflow pause nodes distinct. Revert associated commits if the cutover regresses these invariants.
