# Remove Tool Connection Delegation

## Background & Goals

Connection binding is the user's authorization to use an external identity through the configured Agent/workflow. Sharing a runnable workflow also permits its callers to execute its configured connection. Separate grants, operation allowlists and expiry controls are redundant and must be removed, not hidden.

Success criteria: no delegation UI/API/model/config contract; authorized shared workflow execution uses the saved personal connection; unrelated callers cannot select another user's connection ID directly or read its secrets; revoked, invalid or mismatched connections still fail.

## High-Level Design

Keep connection CRUD, OAuth, secret encryption, team/service identity, and workflow/Agent access checks. Validate newly selected connections at configuration save time using the configuring actor. Runtime use of someone else's connection must come from an authorized, server-loaded persisted binding, never an arbitrary client-provided connection ID. Remove grant fields from execution contexts, approval snapshots, schemas, frontend state and packages. Connection binding/version remains the execution identity invariant.

## Implementation Plan

### Stage 1: Backend contract and execution
- **Files modified**: connection models/schemas/services/routes, tool execution/approval services, Agent/workflow configuration and execution callers, model exports.
- **Specific logic**: remove delegation records and endpoints; authorize persisted bindings for execution while keeping owner-only direct selection/management; validate binding on save; retain OAuth and connection version checks.
- **Validation**: shared workflow uses owner's bound connection; unauthorized direct ID and unauthorized new binding fail; revoke/team/service mismatch fail; no secret exposure.

### Stage 2: Frontend cutover
- **Files modified**: connection picker/manager, API DTOs, Agent/workflow binding forms, locale JSON and generated types, relevant tests.
- **Specific logic**: remove grant controls and request fields; connection selection remains the only configuration step; explain that shared execution uses saved connection.
- **Validation**: connection creation/selection/OAuth unchanged; no delegation requests or controls; existing binding saves without grant metadata.

### Stage 3: Existing data and verification
- **Files modified**: migration/bootstrap code and regression fixtures as needed; operator/API documentation.
- **Specific logic**: strip obsolete grant metadata from persisted configurations; retire obsolete database schema safely without deleting connections or OAuth credentials. Preserve workflow/package configurations and approval connection identities.
- **Validation**: upgrade is idempotent, existing saved binding runs without a grant; obsolete routes absent; targeted backend/frontend tests and standalone execution smoke; Ruff, TypeScript, ESLint and locale checks.

## Testing Strategy

- Positive: owner direct use, shared workflow use, scheduled execution with explicit persisted binding, OAuth access/refresh, team connection use.
- Negative: arbitrary foreign connection ID, unauthorized binding edit, secret retrieval, revoked connection, wrong tool/team, stale connection version.
- Regression: tool confirmation/approval resume remains separate; builtin/custom/MCP tools all use the same connection boundary.
- No services or browser sessions; UI runtime evidence uses DOM rendering and interaction. External provider compatibility is not implied.

## Risks & Mitigation

- Sharing a workflow intentionally shares use of its configured external identity, not credential visibility. Document this consequence clearly.
- Never replace grant checks with an unconditional foreign-connection bypass; use persisted configuration as authority.
- Old deployment processes must not run against retired schema; document coordinated backend/worker upgrade and backup requirement.
- Rollback requires matching pre-upgrade database/application backup if obsolete schema is removed.

## Status

Completed.

### Verification

- Backend targeted suites: 122 passed across connection resolution, approvals, execution boundary, OAuth, MCP endpoints, builtin tools, package resources, workflow tool nodes, approval resume and execution origin.
- Shared execution regression uses real SQLite persistence: a team member executing a workflow-bound owner personal connection succeeds once, while the same member selecting that connection through an untrusted direct id is rejected before invocation.
- Configuration-time checks cover Agent create/update/duplicate, workflow update/duplicate/version restore and package import (bindings stripped on import).
- Full `tests/services` + `tests/api` run: 18 failures, all reproduced identically on the pre-change baseline (stale unrelated tests); no new failure introduced.
- Ruff check, targeted frontend tests, TypeScript, ESLint and frontend i18n lint/usage checks passed. The dashboard capabilities test has a pre-existing baseline `lucide-react` mock export failure.
- Route/model smoke confirms no grant route and no delegation model exports remain.
- Migration drops `connection_grants` and the obsolete `tool_executions.grant_id`/`grant_version` columns. Coordinated backend/worker upgrade is required; obsolete grant keys left inside old Agent/workflow JSON are ignored.
- No browser, application service or external provider was started.

