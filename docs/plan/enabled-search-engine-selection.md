# Enabled Search Engine Selection Design Document

## Background & Goals
- Agent orchestration currently offers disabled providers; workflow tool mappings expose `search_engine` as plain text.
- Both surfaces must offer only site-enabled providers plus `auto`, without exposing credentials or changing saved choices implicitly.

## High-Level Design
- Add authenticated `GET /tools/web-search/engines`, using the existing tool-read permission. Return only enabled engine names, derived from the existing site configuration service.
- Add `toolsApi.getWebSearchEngines()` and a shared frontend search-engine select using existing Select controls and translated labels.
- Agent configuration and workflow built-in `web_search.search_engine` constant mappings consume the shared select. Variable mappings remain supported.
- Fetch failures expose no provider options; `auto` remains the explicit site-default routing choice. Existing unavailable selections remain visible as the selected value but are not offered in the menu. Runtime authorization/configuration checks remain authoritative.

## Implementation Plan
### Stage 1: Safe availability API
- **Files modified**: `backend/app/api/v1/endpoints/tools.py`, focused backend API tests, API reference.
- **Specific logic**: Authenticated read of existing enabled flags; output only provider identifiers, never keys, URLs, tokens or archived credentials.
- **Validation**: Exercise no configuration, mixed enabled flags, all disabled and response redaction.

### Stage 2: Orchestration controls
- **Files modified**: `frontend/lib/api/tools.ts`, shared select component, Agent `tool-selector.tsx`, workflow `tool-node-config.tsx`, focused component tests.
- **Specific logic**: Share enabled-provider fetching and option labels. Workflow selection persists `constantValue`; variable source remains unchanged. Do not mutate historical engine selections on load or failure.
- **Validation**: Render and interact with both surfaces using DOM tests; check hidden disabled engines, saved selection, selected labels, workflow update payload and fetch failure.

### Stage 3: Verification and documentation
- **Files modified**: `CHANGELOG.md`, workflow/operator guides, this plan and implementation index.
- **Specific logic**: Document enabled-only choices and preserved runtime enforcement.
- **Validation**: Backend focused tests and HTTP smoke; frontend DOM interaction smoke, focused regression tests, TypeScript and targeted lint. No application servers or browser sessions will be started.

## Testing Strategy
- Happy paths: enabled provider selection and persisted choice in both entrypoints; workflow variable mapping unaffected.
- Negative paths: disabled providers absent, unavailable saved choice preserved, failed availability request offers no providers.
- Regression scope: Agent tool configuration, workflow tool-node configuration, existing web-search runtime tests.

## Risks & Mitigation
- Availability can change after the editor loads; runtime still validates enabled status on every execution.
- Preserve saved disabled values rather than silently selecting a different provider.
- Rollback: revert API and frontend commits together; no database changes.

## Status
- Completed. API: `5a9f6da`; shared selector and Agent integration: `e0bf731`; workflow integration: `cb9f10e`. Committed locally, not pushed.
- Backend regression: 106 tests passed across tool endpoints, configuration/redaction and web-search runtime. New endpoint tests: 7 passed after test cleanup. Ruff passed.
- Frontend regression: 33 tests passed across the shared select, Agent tool selector, workflow configuration and tool API client. TypeScript and targeted ESLint passed.
- Standalone smoke: actual authenticated HTTP route and site flag parsing returned only enabled provider names, returned `[]` when all disabled, and exposed no configuration secrets.
- Follow-up fix: the workflow editor never received a `search_engine` mapping because the backend tool catalog intentionally exposes only model-facing `query`/`num_results`. Tool nodes now add the optional engine routing control to both new and saved `web_search` nodes; a real component smoke selected `web_search` and saved `search_engine = searxng` while retaining `query`.
- Initial DOM fixture failures came from importing Base UI before DOM initialization and a fresh mocked team object on every render; corrected test fixtures without changing production behavior.
- No application servers or browser sessions were started. DOM interaction was verified in happy-dom; browser layout was not inspected.
