# Ask-user Custom Answers and Skip Design Document

## Background & Goals

`ask_user` option lists currently permit only one listed value, and its durable API rejects an empty answer map when any question is required. Users therefore cannot supply a valid answer outside the suggested options or deliberately decline the whole interaction.

Success criteria:
- Every option-backed question offers a custom text input in addition to its listed choices.
- A custom non-empty string is a valid answer for an option-backed question; options remain suggestions, not an API-enforced enum.
- Users can skip every question from any page, including required questions.
- A skip is model-visible and distinct from an accidental or malformed missing answer.
- Existing normal answer payloads and all public/embed/JWT run adapters remain compatible.

## High-Level Design

The answer request gains an optional `skipped` boolean. Normal submissions keep sending `{ "answers": ... }`; skipping sends `{ "answers": {}, "skipped": true }`. The backend validates the pending question definition in both cases, requires an empty answer map for a skip, bypasses required-answer checks only for that explicit state, and persists the tool result as `{ "answers": {}, "skipped": true }`. The resumed model can therefore distinguish a refusal from omitted transport data.

`AskUserForm` continues to own one answer string per question. For an option-backed question, the existing selected value is also editable in a text input; entering custom text naturally deselects all choices. A footer `Skip all questions` action invokes the same durable submission path without paging or required-field validation.

## Implementation Plan

### Stage 1: Answer-result contract
- **Files modified**: `backend/app/schemas/agent.py`, `backend/app/services/agent_run_store.py`, `frontend/lib/api/agents.ts`, `frontend/hooks/use-chat.ts`, `frontend/hooks/use-run.ts`, chat adapters.
- **Specific logic**: Carry the optional explicit skip flag through every answer endpoint; preserve normal result JSON; persist an explicit skipped result; accept non-empty custom strings for option-backed answers; reject skip payloads containing answer values.
- **Validation**: Service and hook tests cover normal answers, custom values, explicit skips, malformed skips, stale calls, and adapter request bodies.

### Stage 2: Composer controls
- **Files modified**: `frontend/components/chat/ask-user-form.tsx`, `frontend/i18n/en/chat.json`, `frontend/i18n/zh/chat.json`.
- **Specific logic**: Render a custom text input under listed options; preserve option selection behavior; add a skip-all control that bypasses page validation and submits the explicit skip payload.
- **Validation**: Component tests cover custom answer precedence, retained page values, skip submission, disabled controls, and failed submission feedback.

### Stage 3: Entry-point migration
- **Files modified**: public/embed chat, Agent Run, preview, reusable Chat shell, and their focused tests.
- **Specific logic**: Migrate each pending-form callback to the answer submission object and preserve the original server tool-call identity.
- **Validation**: Entry-point tests assert normal and skipped payloads reach the existing durable callback.

### Stage 4: Regression verification and cleanup
- **Files modified**: affected tests and this plan/index.
- **Specific logic**: Remove outdated enum-only and answer-map-only assumptions; record final evidence.
- **Validation**: Focused isolated frontend tests, focused backend tests, TypeScript, and scoped lint pass.

## Verification Record

- Focused frontend tests: `bun test --isolate` over the form, chat shell, hook, public chat, preview, and API adapters passed **112 tests** with **468 assertions**. Coverage includes custom option answers, explicit skips, rejected submissions, and exact request bodies.
- Focused backend tests: `tests/services/test_chat_agent_tools.py`, `tests/services/test_agent_run_durable.py`, and `tests/api/test_chat_endpoint_branches_issue255.py` passed **41 tests**. Coverage includes custom option values, explicit skip persistence, endpoint forwarding, rejection of skips containing answers, duplicate submissions, stale calls, and terminal runs.
- TypeScript: `npx tsc --noEmit -p tsconfig.json` passed.
- Frontend lint: scoped ESLint passed with `--max-warnings=0`; `bun run i18n:lint` passed.
- Backend lint: scoped Ruff formatting and lint checks passed.

## Testing Strategy

- Happy path: select an option, type a custom value, move between pages, and submit the final answer map.
- Skip path: skip a required multi-question interaction and confirm exactly one persisted `skipped` tool result resumes the run.
- Error path: reject unknown keys, invalid question definitions, empty normal required answers, and skip payloads with values.
- Regression scope: public/embed/JWT answer endpoints, durable run resumption, message privacy, and every Agent composer.

## Risks & Mitigation

- **Ambiguous non-response**: persist `skipped: true`, never interpret `{}` as a skip implicitly.
- **API bypass of option intent**: custom responses are explicitly supported strings; non-string option responses remain invalid.
- **Partial skip**: reject a skip payload containing answer values so one run has one unambiguous outcome.
- **Stale UI callback**: retain the existing pending tool-call ID validation and row-lock idempotency path.
