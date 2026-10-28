# Automatic Tool Connections Design Document

## Background & Goals

Agent tools currently prompt authors to bind a concrete external account. Shared Agents then reuse that binding instead of automatically selecting the invoking user's account. Selectable tools also reject omitted identity modes, and a sole personal connection without a default marker cannot be selected automatically.

Success criteria:
- An unbound personal/selectable tool resolves the invoking user's connection in the consuming team: explicit default first, otherwise the sole non-revoked connection.
- Multiple connections without a default require the user to set a default; missing connections explain how to configure one, and inactive connections explain reconnection.
- Authors can explicitly pin an authorized personal/team connection. Existing explicit bindings retain their account semantics.
- Automatic selection never falls back to another user, a team account, or another team. API-key, embed, channel and scheduled origins still require fixed connections.
- Manual workflow runs may resolve the triggering user's connection without enabling interactive approvals. Approved executions remain pinned to their original connection/version.

## High-Level Design

Reuse `connection_mode` (`personal`/`team`) and nullable `connection_id`; no schema migration or extra policy enum. Missing mode on a selectable tool means personal. A missing personal connection ID means runtime selection; a stored ID means fixed binding. Team-only tools retain their scope restriction and existing interactive default behavior.

Resolution remains inside the unified execution boundary. Resolve once and construct the approval binding snapshot from that same result so a concurrent default change cannot separate credentials from the recorded identity. Keep model arguments independent from trusted actor/team/origin fields.

The shared connection picker exposes automatic-current-user and fixed-connection choices for personal/selectable tools. Automatic mode does not store the author's connection ID or require the author to configure an account. Agent badges communicate automatic selection; workflow nodes reuse the same picker. Existing connection management handles creating accounts, setting defaults, and OAuth login.

## Implementation Plan

### Stage 1: Runtime selection and persistence
- **Files modified**: `backend/app/services/tool_execution.py`, `backend/app/services/tool_connections.py`, `backend/app/schemas/tool_mcp.py`, connection/origin/execution boundary tests and MCP endpoint tests.
- **Specific logic**: default selectable tools to personal; allow automatic selection for interactive origins and manual workflow origins only; select a default or sole personal connection with strict team/service/owner filters; preserve inactive-state errors and reject ambiguity; produce binding from the resolved connection.
- **Validation**: real SQLite persistence with two users, shared tools, absent/sole/multiple/default/inactive connections, fixed-owner binding, noninteractive origin rejection, and approval resume after default changes.

### Stage 1b: Authenticated MCP tool discovery
- **Files modified**: `backend/app/services/tool.py`, `agent_tool_execution.py`, `agent.py`, `agent_run_worker.py`, `backend/app/api/v1/endpoints/chat.py`, `tool_mcp.py`, discovery and worker regression tests.
- **Specific logic**: reuse one credential/OAuth MCP configuration builder for invocation and discovery; pass the actual run user and trusted origin into tool enumeration; surface connection errors rather than silently omitting authenticated MCP tools; localize discovery failure events. Worker display names use server prefixes without a redundant unauthenticated enumeration.
- **Validation**: two users receive different authorized MCP catalogs; missing connection raises actionable failure on both chat and workflow Agent surfaces; worker failure event and persisted error contain localized guidance.

### Stage 2: Authoring controls and guidance
- **Files modified**: shared connection picker, Agent tool selector, workflow tool-node configuration, tool test panel, relevant frontend tests, `frontend/i18n/{en,zh}/tools.json`, `frontend/i18n/types/tools.ts`; backend legacy/catalog translations.
- **Specific logic**: default to current-user automatic selection, preserve existing fixed selections, clear fixed IDs when selecting automatic, show explicit fixed-binding sharing semantics, and provide configuration/login/default-selection guidance.
- **Validation**: exercise real component interactions with the existing DOM renderer, inspect emitted bindings, and run targeted Bun tests, TypeScript and ESLint. No application servers or browser sessions.

### Stage 3: Integration and documentation
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, bilingual tool connection guides, tools API reference, bilingual guide changelogs, this plan.
- **Specific logic**: document default/sole/ambiguous rules, fixed-account sharing, origin restrictions and errors; record exercised verification.
- **Validation**: focused backend tests and frontend checks once after integration; direct execution smoke through the stored-tool runtime proving two users reach different account credentials and missing authorization fails before invocation.

## Testing Strategy

Happy paths: two users invoke one unbound tool with different credentials; sole account works without a default; explicit default wins; manual workflow automatic selection; fixed author account remains fixed. Error paths: no personal account despite team/other-user accounts; multiple accounts without default; inactive selected/default account; wrong team/service; background origin without fixed account. Regressions: approval account/version pinning, MCP discovery identity, existing fixed workflow execution, builtin database and OAuth boundaries.

## Risks & Mitigation

- Existing unbound selectable tools become personal-auto rather than requiring a scope choice. Team-only policy stays authoritative; fixed IDs never silently switch accounts.
- Sole-account fallback includes inactive accounts to return reconnect guidance rather than silently choosing a different identity. Revoked accounts are excluded.
- Manual workflow origins are separate from interactive capability; automatic account selection must not enable caller approvals.
- Rollback: revert these scoped changes together; no database migration is required and persisted fixed bindings remain compatible.

## Verification

- Real HTTP smoke through Agent stored-tool dispatch, encrypted connection resolution, authorization and the HTTP adapter: Alice and Bob each authenticated to httpbin Basic Auth as themselves; a third user without a connection received the Chinese configure/login message; Bob using an explicit fixed Alice binding authenticated as Alice. No local services or browsers were started.
- Pre-change resolver snapshot reproduced HTTP 400 `tool_connection_required` for a selectable tool with a valid caller default but no mode. The new regression scenarios accept this configuration.
- Primary backend integration: 223 tests passed, including per-user selection, missing/default/ambiguous/inactive cases, fixed identity and approval resume, MCP endpoint/discovery and worker error localization.
- Frontend surface verification: 29 authoring interactions plus 10 tool-test-panel tests passed, with TypeScript and scoped ESLint. Covers automatic/fixed binding changes, missing-fixed-account recovery, connection management, workflow tool-switch isolation and automatic test execution. The test panel no longer blocks the shared picker's automatic option.
- Backend scoped Ruff checks and frontend/backend locale checks passed. The pre-existing `test_tool_connections.py` materialized-builtin test has unrelated formatting differences and was intentionally not reformatted.
- Wider discovery regressions: 230 tests passed after removing two obsolete contracts (plaintext global-credential fallback and direct resource-subscription approval) that contradicted existing runtime behavior. No implementation was changed to satisfy either obsolete expectation.
- Browser layout and real third-party MCP/OAuth-provider interoperability were not exercised. The MCP account-specific catalog regression exercises the real client enumeration with an authenticated in-process session boundary.
- Isolated commit tree (excluding pre-existing user edits): primary backend 222 tests and frontend 27 authoring tests plus TypeScript passed; lower counts exclude the user's independent builtin/form/icon tests. Scoped backend format check passed for all 20 changed Python files. Commit hooks remain enabled.
