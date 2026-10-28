# IM Chat Run Discovery Design Document

## Background & Goals

Chat only reconnects runs recorded in browser storage, so IM-origin runs in the same conversation do not show pending confirmations. Recover the owning user's active run from durable state, without exposing another user's run or applying stale responses after a conversation switch.

## High-Level Design

The authenticated conversation response includes the owning user's active run ID. Chat uses it only when no local run snapshot exists, then uses the existing owner-scoped run status and subscription paths. Embed adapters remain unchanged.

## Implementation Plan

### Stage 1: Owner-scoped discovery
- **Files modified**: `backend/app/api/v1/endpoints/agents.py`, `backend/app/schemas/agent.py`.
- **Specific logic**: Include the latest active run ID scoped by conversation, agent, and user in conversation details.
- **Validation**: Verify matching and foreign-owner runs against ORM-backed scenarios.

### Stage 2: Chat recovery
- **Files modified**: `frontend/lib/api/agents.ts`, `frontend/lib/chat/chat-adapter.ts`, `frontend/hooks/use-chat.ts`.
- **Specific logic**: Discover the run on missing local snapshot, guard asynchronous responses by generation and conversation, then reuse existing status recovery.
- **Validation**: Exercise pending approval recovery and switching conversations while discovery is pending.

### Stage 3: Verification and documentation
- **Files modified**: relevant tests and changelogs.
- **Specific logic**: Verify no-snapshot and stale-response cases and document cross-surface recovery.
- **Validation**: Targeted backend and frontend tests, type checks, and service-free smoke scenario.

## Testing Strategy

Cover an IM waiting approval, no active run, foreign owner and stale asynchronous results; retain local snapshot and embed behavior.

## Risks & Mitigation

Concurrent runs and stale replies can display the wrong approval: constrain discovery by owner and conversation and check the reconnect generation before applying. Roll back backend and frontend together; the new response field is additive.
