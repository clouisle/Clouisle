# User Tool Connections Management Design Document

## Background & Goals
- **Problem**: The user profile and settings dialog (`SettingsDialog`) lacked a centralized place to inspect and manage user connections. Currently, connections can only be configured in local contexts (Agent tool config drawer, workflow tool node, or tool test panel). Users could not prepare personal external connections in advance, nor could they easily see when existing credentials or OAuth tokens required re-authentication.
- **Success Criteria**:
  1. A dedicated "工具连接" (Tool Connections) tab in `SettingsDialog` that operates on the user's active team context.
  2. Clear overview of all connections for the user in the team, indicating service name, connection name, account label, status (active, reauth_required), and default status.
  3. A quick-creation flow: select a connectable tool (builtin database, MCP, custom HTTP/code), fill declared connection fields or initiate OAuth login, and save directly.
  4. Quick management actions: set default, re-authenticate, and revoke/delete.

## High-Level Design
- **Components Involved**:
  - `frontend/components/user-tool-connections.tsx`: Self-contained component for listing, creating, and managing tool connections for the active team.
  - `frontend/components/settings-dialog.tsx`: Mounts the new `connections` tab in the user profile settings dialog.
  - `frontend/i18n/{en,zh}/settings.json` & `frontend/i18n/types/settings.ts`: Localized copy for titles, empty states, and actions.
- **Data Flow**:
  - Reads `currentTeam` from `useTeam()`.
  - Queries `toolConnectionsApi.list(currentTeam.id)` for connections.
  - Queries `toolsApi.list(currentTeam.id)` for connectable tool definitions (`identity_policy !== 'none'`).
  - Matches each connection to its corresponding tool (by `tool_id` or `builtin_tool_key`) to render tool icon and display name.
  - Creation submits to `toolConnectionsApi.create` or `toolConnectionsApi.createForTool`.

## Implementation Plan

### Stage 1: Design document & secondary task registration
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/user-tool-connections-management.md`
- **Specific logic**: Document design and register tasks in implementation index.
- **Validation**: Verify doc links and plan integrity.

### Stage 2: User tool connections component & quick creation
- **Files modified**: `frontend/components/user-tool-connections.tsx`
- **Specific logic**:
  - Query connections and connectable tools concurrently on team change.
  - Render list of connections with tool display name, icon, account label, status badge, and default indicator.
  - Actions: set default, re-auth (OAuth start), and revoke/delete.
  - Quick creation: select tool -> render declared connection fields (or OAuth login button) -> validate and submit.
- **Validation**: Verify creation, error validation, and management actions via automated component tests.

### Stage 3: SettingsDialog integration & i18n
- **Files modified**: `frontend/components/settings-dialog.tsx`, `frontend/i18n/en/settings.json`, `frontend/i18n/zh/settings.json`, `frontend/i18n/types/settings.ts`
- **Specific logic**: Add `connections` tab trigger and content; add bilingual translation entries.
- **Validation**: Run `bun test`, `bunx tsc --noEmit`, and `bunx eslint`.

### Stage 4: Component tests & regression verification
- **Files modified**: `frontend/components/user-tool-connections.test.tsx`, `frontend/components/settings-dialog.test.tsx`
- **Specific logic**: Test opening the connections tab, listing connections, quick-creating a connection, and handling actions.
- **Validation**: Full suite passes with >=95% coverage on new code.

## Testing Strategy
- **Happy Path**:
  - Renders connections with tool icons and names.
  - Adds connection for custom/MCP and builtin database tools.
  - Sets connection as default and revokes connection.
- **Error Path**:
  - Missing team context shows appropriate prompt.
  - Empty connections list shows friendly empty state with quick-add action.
  - Validation failures during connection creation (missing name, missing required secret fields).
- **Regression Scope**:
  - Existing `SettingsDialog` tabs (profile, account, wechat, feishu) remain intact.
  - Existing `ConnectionPicker` in agent/workflow editors remains unaffected.

## Risks & Mitigation
- **Secret Safety**: Secrets remain write-only; decrypted values are never returned to client.
- **Team Scope Isolation**: Connections are strictly scoped to `currentTeam.id`.
- **Re-render Efficiency**: Load tool metadata and connections concurrently; avoid redundant queries on tab switch.
