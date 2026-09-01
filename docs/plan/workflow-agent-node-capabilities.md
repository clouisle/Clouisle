# Workflow Agent Node Capability Alignment Design Document

## Background & Goals

The workflow Agent node currently loses the editor's `messageSource`/`inputMappings` shape, accepts only textual messages at runtime, does not expose generated files or the agent's internal tool dialogue, and passes the wrong model-manager keyword. This makes agents with file/image capabilities unusable and makes workflow execution diverge from direct Agent chat.

Success criteria:
- File, files, image, and images workflow variables reach the selected Agent as attachments when the Agent enables attachments.
- The Agent node exposes response, tool calls, usage, artifacts, and a serializable execution dialogue for downstream variables and run inspection.
- Every workflow Agent model call uses the Agent's configured model through `model_id`, with the normal team/default fallback when unset.
- Existing legacy workflow Agent config remains readable.

## High-Level Design

The workflow executor remains the orchestration boundary. It resolves the frontend `agentConfig` mapping shape, classifies attachment variables by their declared type, and calls the shared `AgentService`. `AgentService` gains an optional attachment input and records an in-memory, serializable dialogue for the invocation; it does not create a user conversation because workflow runs already have durable `NodeExecution` records.

Images become LLM `ContentPart` image entries. File URLs are parsed through the existing bounded file parser and appended as an uploaded-files section in the user message. Relative upload URLs use the existing public API URL behavior in the parser. Tool results are retained in the dialogue and artifact extraction preserves the existing artifact payloads returned by sandbox tools.

The existing workflow run node output surface already renders arbitrary node outputs and fetches `NodeExecution` details. Frontend output declarations and the output renderer are extended only where needed to expose the new fields.

## Implementation Plan

### Stage 1: Backend AgentService contract
- **Status**: Complete

- **Files modified**: `backend/app/services/agent.py`
- **Specific logic**: Add optional image/file attachment inputs; build a multimodal current-user message; parse raw workflow file URLs with the existing parser; resolve the Agent's selected TeamModel to its global model UUID and invoke through `team_chat`/`team_chat_stream`; collect assistant/tool dialogue, reasoning, tool results, and generated artifact payloads.
- **Validation**: Unit tests assert multimodal messages, TeamModel resolution, and serializable detail fields for streaming/non-streaming calls.

### Stage 2: Workflow Agent executor integration
- **Status**: Complete

- **Files modified**: `backend/app/services/workflow/executors/tool.py`
- **Specific logic**: Read `messageVariableRef`/`messageConstantValue` and `inputMappings` while retaining legacy `message`/`context`; resolve mapped file/image values; reject attachment use when the selected Agent has attachments disabled; forward attachments to AgentService; return aliased response plus `toolCalls`, `usage`, `dialogue`, and `artifacts` outputs.
- **Validation**: Focused executor tests cover frontend config, file/image mapping, disabled attachment rejection, model selection, streaming, and legacy config.

### Stage 3: Workflow output contracts and presentation
- **Status**: Complete

- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config-drawer.tsx`, `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer.tsx`
- **Specific logic**: Declare Agent output fields with accurate types, expose configured response alias in the variable picker, render response/artifacts/dialogue in the node detail without hiding existing generic JSON output, and keep arbitrary outputs available to downstream references.
- **Validation**: Frontend component tests assert output declarations and artifact/dialogue rendering; existing run-detail behavior remains unchanged for other node types.

### Stage 4: Regression coverage and cleanup
- **Status**: Complete

- **Files modified**: focused backend/frontend test files and implementation-plan documents; no i18n changes were required because output field names are stable API identifiers.
- **Specific logic**: Add observable-contract tests, remove no unrelated compatibility paths, and keep existing output names backward compatible.
- **Validation**: Run targeted backend pytest, targeted frontend Bun tests, TypeScript, lint, and diff checks.

### Stage 5: Agent-selected variable contract correction
- **Status**: Complete
- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/agent-node-config.tsx`, `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config-drawer.tsx`, and their focused tests.
- **Specific logic**: Treat the selected Agent's declared variables as the node's dynamic input contract; preserve compatible user mappings while removing stale fields. Keep the selected Agent's output contract fixed to `response`, `toolCalls`, `usage`, `dialogue`, and `artifacts`, and add the configured response alias only when distinct. Reuse one declaration helper in the node configuration and downstream variable picker.
- **Validation**: Focused tests cover input replacement/preservation, empty Agent variables, fixed output declarations, aliases, and duplicate prevention; run TypeScript, ESLint, i18n lint, and diff checks.

### Stage 6: Agent attachment input mappings
- **Status**: Complete
- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/agent-node-config.tsx`, `backend/app/services/workflow/executors/tool.py`, their focused tests, and workflow translations.
- **Specific logic**: When a selected Agent enables attachments, declare fixed `files` and `images` attachment mappings separate from its declared prompt variables. Preserve compatible mappings across refreshes, resolve them separately from normal context inputs, and pass them to the shared AgentService as files and images.
- **Validation**: Focused frontend configuration tests and workflow executor tests cover enabled/disabled attachment contracts and mapped file/image delivery; run TypeScript, lint, i18n lint, and diff checks.

## Testing Strategy

- Happy path: text-only Agent, image input, file input, multiple attachments, configured Agent model, tool call plus artifact result, stream and non-stream execution.
- Error path: missing Agent, missing required message, attachment capability disabled, malformed attachment value, model-manager failure, and legacy config fallback.
- Regression: existing workflow tool executor tests, AgentService chat tests, workflow node output tests, and workflow run page tests.

## Risks & Mitigation

- File parsing adds network and parser work: use the existing parser and Agent attachment limits; do not duplicate download logic.
- Dialogue/output payloads can grow: keep only normalized tool-call/result fields and existing artifact metadata, not raw provider objects.
- Agent model authorization remains centralized in `model_manager`; passing `model_id` preserves the current team authorization and default resolution.
- Rollback: executor output additions are additive; attachment and dialogue support can be reverted independently without changing workflow run persistence.
