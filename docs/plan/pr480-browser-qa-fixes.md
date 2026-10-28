# PR 480 Browser QA Fixes

## Background & Goals

Browser QA identified inaccurate API translation, MCP capability/error handling and policy inconsistencies, inaccessible approval-policy administration, and connection-management usability risks. Resolve each reported issue without weakening caller authorization or exposing secrets.

## High-Level Design

Correct translated message formatting; map MCP exceptions accurately and evaluate policies using the real entrypoint. Restore policy administration using the existing policy API and caller-only editor. Improve MCP browser capability handling and connection-management controls without changing existing durable bindings.

## Implementation Plan

### Stage 1: API translation
- **Files modified**: `frontend/i18n/{en,zh}/agents.json` and focused tests if needed.
- **Specific logic**: Render the literal execution ID placeholder instead of treating it as a missing interpolation argument.
- **Validation**: Existing Agent API page showed the Chinese description and literal `{execution_id}`.

### Stage 2: MCP error handling and policy boundary
- **Files modified**: `backend/app/api/v1/endpoints/tool_mcp.py`, relevant tool execution services and backend tests.
- **Specific logic**: Preserve typed errors nested in task-group exceptions, distinguish unsupported capabilities from connection failures, and enforce the effective policy for the actual entrypoint.
- **Validation**: Full backend suite passed 10,696 tests with four skips, including exception-group mapping and non-interactive fail-closed execution. Existing MCP servers loaded supported resources in the browser; unsupported prompt capability was disabled.

### Stage 3: MCP browser usability
- **Files modified**: `frontend/components/tools/mcp-tool-browser.tsx`, related MCP dialogs, bilingual catalogs and component tests.
- **Specific logic**: Respect capability flags, reset per-server tab state, explain external prompt trust, validate unexpanded URI templates, show truncated results and support standard close interactions.
- **Validation**: Browser confirmed URI template variables are flagged, external prompt preview is labeled untrusted, and Escape closes the dialog. Component tests covered truncation and server switching.

### Stage 4: Policy administration
- **Files modified**: Existing policy editor/API consumers, platform or administrator navigation, bilingual catalogs and tests.
- **Specific logic**: Provide authorized site, team and entrypoint policy management using existing optimistic concurrency and caller-only semantics, including explicit deny.
- **Validation**: Browser opened policy management, selected deny, created a temporary caller-approval entrypoint policy and deleted it after verification. Component/backend tests cover permissions and conflicts.

### Stage 5: Connection management
- **Files modified**: Admin capabilities client, connection manager, user connection UI, shared cards and related translations/tests.
- **Specific logic**: Route builtin editing to its connection manager; require confirmation before revoking or disconnecting; show accurate configuration state and use safe password autocomplete attributes.
- **Validation**: Browser opened PostgreSQL builtin management, observed `new-password`, and cancelled connection revocation and OAuth disconnect without affecting the existing connections. Component tests cover confirm paths.

### Stage 6: Integration
- **Files modified**: Relevant guides and changelogs, implementation index and this plan.
- **Specific logic**: Align documentation with final behavior; preserve existing pending approval snapshots.
- **Validation**: Full backend suite: 10,696 passed, four skipped. Full frontend suite passed; TypeScript, Ruff, ESLint and i18n checks passed (ESLint warnings remain). A fresh chat approval displayed the real web-search query and rejection succeeded. The requested GitHub tool was not selected by the model, so GitHub-specific approval and successful approval/resume were not proven in the browser; regression tests cover the resume path.

## Testing Strategy

- Happy paths: supported MCP operations, policy administration, connection selection, localized approval documentation.
- Negative paths: unsupported capabilities, incomplete URI templates, denied policies, cancellation of destructive operations and unauthorized access.
- Regression: caller-only approval, pending execution resume, secret masking, chat switching and multi-team access.

## Risks & Mitigation

Policies must fail closed for non-interactive or unauthorized calls; do not bypass enforcement to fix a UI error. MCP messages may contain secrets: expose only safe, localized failure details. Existing tool connections and approvals are user data; use temporary test objects and revoke only those created for verification. Revert the associated commits if regressions occur.
