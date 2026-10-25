# Site-managed Web Search Design Document

## Background & Goals
The user requests a new branch with two sequential changes: migrate Tavily/Bocha credentials to enterprise-wide site management, then add configured SearXNG. Agent choices reference site services; no Agent/team/env credential overrides or random public instances remain.

Success criteria: one administrator configuration surface; explicit default and enabled providers; encrypted write-only secrets; no raw secrets through generic APIs, Agent exports or runtime errors; existing non-global keys are not silently promoted or discarded; self-hosted SearXNG respects subpaths and SSRF policy.

## High-Level Design
- Reuse the existing global ToolConfig row (`tool_name=web_search`, `team_id=NULL`), with typed dedicated admin configuration API. Keep other tools' configuration behavior unchanged.
- Dedicated service owns secret encryption/decryption, enabled/default validation and site-only runtime resolution. Auto means the configured site default, not key-priority inference.
- Admin GET exposes flags/URL/configured booleans only. PUT secret null/omitted preserves, empty clears, nonempty replaces. Legacy encrypted backup remains private and is preserved by saves.
- Generic configuration APIs hide and reject web_search records; platform users cannot read/write search secrets. Admin endpoints use capability read/update/execute permissions.
- All execution entry points delegate search credential ownership to web_search itself. Agent only stores a provider enum; input/output schema removes arbitrary search configuration secrets. Search credentials in generic tools_credentials cannot become active.
- Startup migration runs after schemas under a transaction/advisory lock. Existing global credentials are encrypted and remain global; an existing environment Tavily key is imported once only if no global key exists. Agent/team credentials are encrypted into a private migration archive without promotion, then stripped from active rows. Default inferred once for existing global configuration, afterwards explicit. Operators replace unknown/conflicting keys through the site form.
- Dashboard tool configuration opens a dedicated site dialog independent of selected team. Platform capability view shows administrator-managed configuration. Agent dialog has no API Key input.
- SearXNG adds root Base URL and optional bearer token; no public default. Preserve reverse-proxy prefix when appending `/search`, enable JSON output on the instance. Reject userinfo/query/fragment and `/search` suffix; SSRF validation at save and use; redirects disabled. Token transport requires HTTPS.

## Implementation Plan
### Stage 1: Centralize existing providers
- **Files modified**: new schemas/service, search builtin, chat_tools.py, services/agent.py, admin/platform tools endpoints, Agent schemas/package import, startup migration, frontend admin API/dialog/selector/locales.
- **Specific logic**: Load only global configuration; explicit default/enabled flags; redact/encrypt secrets; reject old credential management APIs; migrate old records safely and idempotently.
- **Validation**: Config secret preserve/clear and authorization contracts, old override rejection, all runtime entry points use site config, PostgreSQL migration idempotence with conflicting keys, frontend global save without team and secret lifecycle.
- **Commit**: site-managed Tavily/Bocha cutover after focused proof.

### Stage 2: Add SearXNG
- **Files modified**: search service/schema/provider, site dialog/API/types/locales and tests.
- **Specific logic**: POST configured `/search` with query and JSON format; optional bearer auth; normalize title/url/snippet/citations, bounded results; explicit partial/upstream failure semantics.
- **Validation**: URL subpath, SSRF blocks/allowlist, redirect refusal, 403 JSON disabled, invalid JSON, timeout, empty and valid results. Exercise actual HTTP client with deterministic in-process transport; real instance relevance remains dependent on operator instance.
- **Commit**: SearXNG configured provider support.

### Stage 3: Integration and documentation
- **Files modified**: docs/guide tool/API/deployment references, README, CHANGELOG and this index/plan.
- **Specific logic**: Explain centralized ownership, archived legacy keys, credentials rotation/default behavior, SearXNG JSON enablement and private-target allowlist.
- **Validation**: Focused backend/frontend suites, static/lint/i18n checks, throwaway public-service/config/migration scenarios. No application service/browser started without explicit permission.

## Testing Strategy
- Happy paths: global save/read, rotations, provider enable and selection, citations unchanged, Agent inherit/default and explicit selection.
- Negative paths: unauthorized edits, generic raw-secret paths, Agent/team override, disabled provider/default, invalid Base URL, private/metadata target, redirects, invalid upstream JSON/403/timeouts.
- Migration: global vs conflicting per-team/Agent keys; no promotion; encrypted archive; unrelated config unchanged; duplicate starts serialized; repeated run unchanged.
- Existing tool APIs and non-search credential behavior remain regression scope.

## Risks & Mitigation
- Prior defaults were implicit; migration initializes once and UI makes subsequent changes explicit.
- Old per-Agent/team accounts cannot safely become shared accounts. Archive them encrypted, signal migration work to admin, and fail unconfigured rather than silently charging another account.
- SECRET_KEY stability is required for decryption, as with existing encrypted integrations.
- SearXNG quality depends on configured upstream engines; successful connectivity is not a relevance guarantee. Do not claim live SearXNG verification without a provided instance.
- Rollback requires restoring archived credentials deliberately; no runtime compatibility aliases are retained.

## Status
- In progress on `feat/site-managed-web-search`.
- Stage 1 verified: 263 focused backend tests and 53 frontend tests passed; TypeScript, targeted ESLint, Ruff and backend catalog/legacy sync checks passed.
- Real ORM smoke: SQLite configuration save/read/rotation/default selection/clear and public web_search with HTTP transport fixtures passed. PostgreSQL temporary-table migration preserved global account, encrypted/archive private credentials without promotion, sanitized Agent config and repeated idempotently; transaction rolled back.
- No application services or browser sessions started. Live authenticated commercial-provider calls not exercised.
- Stage 2 verification initially found new-test fixture defects (async declaration, repeated transport patching and translated UI label matching); fixed fixtures rather than changing runtime to satisfy assertions.
- Stage 2 full regression: backend 9687 passed / 4 skipped; frontend 2998 passed. TypeScript, targeted ESLint, Ruff, frontend i18n lint and backend catalog/legacy-sync checks passed.
- SearXNG actual ORM smoke passed: site save -> existing SSRF allowlist -> subpath-preserving form POST -> normalized cited result through deterministic HTTP transport. Removing the allowlist blocks the same saved private endpoint before any second request.
- No live SearXNG instance was provided, so live upstream availability/relevance was not verified. Configure an operator-owned instance and enable JSON before use; no random public fallback exists.
