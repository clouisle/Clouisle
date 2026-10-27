# Agent Tool Access Guidance Design Document

## Background & Goals

An Agent user may lack access to one configured tool or lack that tool's personal connection/authorization. The user must see which tool needs attention and whether to request access or configure/sign in to a connection. Existing authorization and identity isolation remain unchanged.

## High-Level Design

Add safe tool-specific context to known permission and connection errors at Agent tool discovery and execution boundaries. Existing durable run errors and tool result events carry localized messages to chat; unknown errors keep existing behavior. Never expose credentials or bypass access checks.

## Implementation Plan

### Stage 1: Contextual guidance
- **Files modified**: `backend/app/services/agent_tool_execution.py`, `backend/app/api/v1/endpoints/chat_tools.py`, backend translation catalogs.
- **Specific logic**: Wrap recognized access and connection failures with the configured tool display name and actionable localized guidance; preserve status and authorization decisions. Format business error parameters in tool results.
- **Validation**: Exercise unauthorized access, missing and inactive connection, OAuth reauthorization, and successful execution paths.

### Stage 2: Delivery verification
- **Files modified**: focused existing backend tests and user-facing changelogs.
- **Specific logic**: Verify discovery failures propagate through durable worker error events and invocation failures are visible tool results, with English and Chinese translations.
- **Validation**: Run focused tests and an in-process smoke scenario; no services or browser started.

## Testing Strategy

Test owner/team access and missing/inactive authorization, both discovery and invocation, plus unrelated errors and success regression. Validate both locales and catalog synchronization.

## Risks & Mitigation

Do not expose protected tool metadata beyond what the Agent configuration already references; never expose secret values. Do not infer authentication failure from arbitrary MCP transport errors. Roll back contextual messages independently of authorization logic.
