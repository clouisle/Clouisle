# Team Tool Approval Management and Audit

## Background & Goals

Team administrators need one place to inspect and manage tool-owned approval settings, while dangerous approval operations must be auditable. The page must not create a separate team approval policy layer. Agent API-key approvals remain bound to their originating key; workflow tool calls never require approval.

## High-Level Design

Add a team-management surface that lists authorized tools and edits each tool's own approval policy via existing authorization and update paths. Respect private and cross-team sharing boundaries. Extend existing audit logging at approval decision and tool definition update boundaries, with minimal secret-safe metadata and idempotent retry handling.

## Implementation Plan

### Stage 1: Team approval management
- **Files modified**: Team management navigation and components under `frontend/app/(platform)/app/team`, tool approval editor and team/tool API integrations as needed; English and Chinese catalogs and types.
- **Specific logic**: List the tools visible to the current administrator, identify which can be edited, and edit the tool's own default and operation-specific policy without creating a team-wide layer. Preserve existing authorization and legacy fail-closed behavior.
- **Validation**: Team page and panel tests passed 27 cases, including team changes, private/shared boundaries and unavailable builtins. TypeScript and i18n checks passed; actual browser display was not exercised.

### Stage 2: Audit decisions and settings
- **Files modified**: Tool approval decision endpoints/services, tool update endpoints, audit utilities and focused backend tests.
- **Specific logic**: Log approval/rejection and policy updates with actor, tool/execution and outcome, using existing audit conventions. Never record secrets, raw call arguments or bearer tokens. Avoid duplicate success events on idempotent decision retries.
- **Validation**: Audit tests cover JWT/API-key approve/reject, denied decisions, idempotent replay and policy change with secret-safe metadata. Audit delivery is best effort: persistence failures are logged but do not roll back decisions.

### Stage 3: Integration and documentation
- **Files modified**: Team administration/approval user guides, English and Chinese changelogs, this plan and implementation index.
- **Specific logic**: Describe team management as a centralized editor of individual tools, not an additional approval layer, and document audit event coverage.
- **Validation**: Backend full suite passed 10,733 with four skipped; frontend full suite passed. Ruff, ESLint (nine existing warnings), TypeScript and i18n checks passed. No server or browser was started; live PostgreSQL/Celery and actual visual UI remain unverified.

## Testing Strategy

- Happy paths: list and edit authorized tools; Agent API-key approval and rejection; audit records for decisions and configuration changes.
- Negative paths: wrong key, revoked key, unauthorized team user, private and shared tools, legacy approval policy, repeated decision and masked secrets.
- Regression: direct/nested/API-key workflow tool calls never pause for approval; existing JWT and Agent resume behavior remain intact.

## Risks & Mitigation

Centralized management must not expand authority or leak private definitions. Authorize using existing backend checks and do not fabricate access on the frontend. Audit metadata excludes user input and secret material; failed audit delivery and asynchronous persistence must follow the repository's documented semantics. Revert associated commits if the change alters workflow semantics or authorization.
