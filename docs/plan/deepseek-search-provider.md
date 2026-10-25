# DeepSeek Search Provider Design Document

## Background & Goals
- DeepSeek exposes its own Search API (`POST https://api.deepseek.com/v1/tools/search`, Bearer auth, `count` 1–50) independently of chat completions.
- Add it as a site-managed provider so administrators can enable it, choose it as the default, and offer it to Agents and workflow tool nodes.
- Success: only enabled providers appear in selectors; site credentials stay encrypted/write-only; provider failure never falls back to another engine.

## High-Level Design
- Extend the existing provider catalog (`WebSearchEngine`, `WEB_SEARCH_ENGINES`) instead of adding a parallel path.
- Store `deepseek_enabled` and an encrypted `DEEPSEEK_API_KEY` in the same global `web_search` ToolConfig row through `ENGINE_ENABLED_FIELDS`, `ENGINE_SECRET_FIELDS`, `ENGINE_REQUIRED_SECRETS` and `SECRET_UPDATE_FIELDS`.
- Resolve the key only in `get_web_search_runtime` when DeepSeek is selected; expose only `deepseek_enabled` and `deepseek_api_key_configured` publicly.
- Extend every engine whitelist that validates Agent configuration, package import and the startup legacy migration.
- Dispatch in `web_search`; request `need_content: false` and map `summary` (fallback `snippet`) as result text, plus `rerank_score` as score.

## Implementation Plan
### Stage 1: Configuration and runtime
- **Files modified**: `backend/app/schemas/web_search.py`, `backend/app/services/web_search_config.py`, `backend/app/llm/tools/builtin/web_search.py`, provider whitelists, backend translations.
- **Specific logic**: Enabled flag, encrypted key, configured-state flag, required-secret validation, runtime decryption, endpoint/headers/body, malformed response and HTTP failure handling.
- **Validation**: Real HTTP smoke against the live endpoint with a deliberately invalid key (expects 401, proving route reachability), deterministic mocked transport for exact request assertions.

### Stage 2: Entry points and localization
- **Files modified**: `frontend/lib/api/tools.ts`, admin configuration dialog, shared engine selector, Agent labels, locale files, generated translation types.
- **Specific logic**: Provider toggle, write-only key field, default-engine validation, test-engine option, enabled-engine labels.
- **Validation**: DOM tests for saving/normalizing the key, refusing a disabled default, mixed-config fixtures.

### Stage 3: Documentation and verification
- **Files modified**: operator guide, tools list, API reference, README, CHANGELOG, implementation index.
- **Specific logic**: Document account billing/QPS, endpoint choice and why `summary` is used.
- **Validation**: Backend and frontend regression, ruff/eslint/TypeScript/i18n, real component smoke.

## Testing Strategy
- Happy paths: default resolution, encrypted key decryption, request construction, result/citation mapping, admin save and selector availability.
- Error paths: malformed result list, HTTP 402/5xx status, missing key/disabled provider, invalid default, wrong request method.
- Regression scope: Tavily/Bocha/SearXNG request tests, site redaction tests, configuration persistence, Agent/workflow selector tests.

## Risks & Mitigation
- DeepSeek Search changes independently of chat; keep the provider behind the site configuration and surface failures explicitly.
- `content` is billed/optional and large; request only `summary` to avoid unnecessary payload.
- Account-level QPS/billing is external; document it and do not retry automatically.
- Rollback: remove the provider from the catalog and forward-only configuration; stored ciphertext is ignored when disabled.

## Status
- Completed.
