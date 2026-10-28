# Approval Tool Description Design Document

## Background & Goals

The chat approval panel shows the operation name but not what it does. Show the description of the exact model-facing tool selected for the paused call, including MCP child tools. Keep the description associated with the waiting run across reconnects and conversation switches. Do not infer descriptions when absent.

## High-Level Design

The Agent loop already receives the model-facing tool schemas, including MCP discovery descriptions. On an approval pause, copy the matching function description into the existing pending interaction payload. The durable run status and events already carry that payload to the frontend. The chat approval panel renders it as plain text. This adds no external lookup or new permissions and does not alter approval binding or execution.

## Implementation Plan

### Stage 1: Capture the description
- **Files modified**: `backend/app/services/agent_loop.py`, `backend/tests/services/test_agent_loop_behavioral_smoke.py`.
- **Specific logic**: Match the exact paused tool name against the current model schemas; attach a non-empty description only to tool-approval interaction arguments before the pause and event are emitted. Preserve other interactions unchanged.
- **Validation**: Exercise matching, missing description, and ask-user behavior in the Agent loop.

### Stage 2: Show the description
- **Files modified**: `frontend/lib/chat/pending-approval.ts`, `frontend/components/tool-interactions/pending-tool-approval-card.tsx`, `frontend/components/chat/agent-chat-surface.tsx`, `frontend/app/(chat)/chat/[id]/page.tsx` and related tests.
- **Specific logic**: Extract the optional string from pending run state and render it as text in the existing approval panel, in both chat surfaces; omit absent or blank descriptions.
- **Validation**: Exercise status parsing, rendered description, old payloads, decisions, and conversation switching.

### Stage 3: Document and verify
- **Files modified**: `docs/guide/CHANGELOG.md`, `docs/guide/CHANGELOG_zh-CN.md`, `docs/IMPLEMENTATION_PLAN.md`.
- **Specific logic**: Document description availability and complete the stage index.
- **Validation**: Run targeted backend and frontend tests, frontend type checking and lint. Browser verification is excluded unless explicitly permitted.

## Testing Strategy

- Happy path: an MCP child approval carries and renders its exact discovered description; reconnect uses the persisted payload.
- Error path: missing, blank or malformed descriptions do not invent text; unrelated tool descriptions are not substituted.
- Regression: ask-user payloads and approval decisions remain unchanged; chat switching remains isolated.

## Risks & Mitigation

Descriptions originate from tool providers and may be verbose or untrusted. Render as plain text with bounded scrollable space, never HTML. Existing pending approvals without descriptions remain actionable. Rollback removes the optional payload field and display without changing stored execution or decisions.
