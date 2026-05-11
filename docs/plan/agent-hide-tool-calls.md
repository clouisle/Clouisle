# Agent Hide Tool Calls Design Document

## Background & Goals
- Problem to solve: Agent owners need a setting in the Agent settings panel to hide tool call UI from chat surfaces without disabling tool execution.
- Success criteria: The setting is saved on the Agent, exposed to public/embed Agent chat metadata, and suppresses tool call cards/steps in preview, normal chat, and embed Agent chat.

## High-Level Design
- Add an Agent-level boolean field `hide_tool_calls`, defaulting to `false`.
- Surface the field in Agent settings as a switch labeled as hiding tool calls.
- Pass the field to the shared chat renderer and skip tool call rendering there so execution and stored history remain unchanged.

## Implementation Plan

### Stage 1: Backend persistence and API
- **Files modified**: `backend/app/models/agent.py`, `backend/app/schemas/agent.py`, `backend/app/api/v1/endpoints/agents.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/api/v1/endpoints/embed.py`, `backend/app/core/init_data.py`, `backend/app/main.py`
- **Specific logic**: Add `hide_tool_calls` to the Agent model, create/update/output schemas, API response builders, public/embed response payloads, and startup migration.
- **Validation**: Run backend type/lint checks where practical; confirm API response typing includes the field.

### Stage 2: Frontend setting and persistence
- **Files modified**: `frontend/lib/api/agents.ts`, `frontend/lib/api/embed.ts`, `frontend/app/(platform)/app/apps/[id]/page.tsx`, `frontend/app/(platform)/app/apps/[id]/_components/agent-settings-drawer.tsx`, `frontend/i18n/en/agents.json`, `frontend/i18n/zh/agents.json`
- **Specific logic**: Add API types, form state, save payload, and a switch in Agent settings.
- **Validation**: Run i18n type generation/lint and frontend lint.

### Stage 3: Chat renderer suppression
- **Files modified**: `frontend/components/chat/chat-container.tsx`, `frontend/components/chat/message.tsx`, Agent chat/preview/embed call sites
- **Specific logic**: Add a `hideToolCalls` prop and skip tool call cards/steps while keeping text, media result parts, RAG/compression/generation task parts, and final answer unchanged.
- **Validation**: Frontend lint; manual UI verification if a dev server is available.

## Testing Strategy
- Happy path: Turn the setting on for an Agent with tools, send a message that uses a tool, and verify tool call cards/steps are hidden while the final answer remains visible.
- Error path: Tool failure should not show tool result cards when hidden.
- Regression scope: Agents without the setting enabled continue showing tool calls; workflow chat rendering remains unchanged.

## Risks & Mitigation
- Risk: Hiding at data conversion time could lose history context for later UI operations. Mitigation: Hide only at render time.
- Risk: Public/embed pages may miss the setting. Mitigation: Include `hide_tool_calls` in public and embed Agent info schemas/responses.
- Rollback plan: Remove the switch/prop usage and leave the DB field unused, or revert the field and migration if not deployed.
