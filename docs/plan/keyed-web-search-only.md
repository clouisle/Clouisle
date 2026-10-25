# Keyed Web Search Only Design Document

## Background & Goals
Bing RSS returned unrelated results for `上海天气 今天`; the user requests removing all keyless search. Retain only Tavily and Bocha. Success means no keyless network calls or selectable options, and a clear missing-key error.

## High-Level Design
Auto selects configured Tavily first, then Bocha. With neither key it fails before opening a client. Selected-provider failures are returned directly, without another provider or keyless fallback. Existing Bing/DuckDuckGo Agent selections migrate to auto, retaining credentials and order.

## Implementation Plan
### Stage 1: Backend cutover
- **Files modified**: web_search.py, init_data.py, backend locales and legacy translation catalog.
- **Specific logic**: Delete Bing request/parser/imports; remove fallback logic; add generic missing-search-key error; migrate retired engines to auto.
- **Validation**: No-key/removed-engine calls must not open a client. Existing provider responses and citations remain unchanged. Exercise migration in temporary PostgreSQL table twice.

### Stage 2: Frontend and contracts
- **Files modified**: tool selector, both Agent locales, locale types and search tests.
- **Specific logic**: Offer auto/Tavily/Bocha only; explain inherited keys and missing-key failure; remove obsolete Bing tests.
- **Validation**: Selector interaction test, focused backend regressions, TypeScript, ESLint and Ruff.

### Stage 3: Verification and documentation
- **Files modified**: README, tools guides, CHANGELOG, implementation index and plans.
- **Specific logic**: Document keyed-only routing and supersede previous Bing proposal.
- **Validation**: Run public web_search without credentials and invalid engine, observe explicit failure and no HTTP; valid-provider behavior checked with HTTP transport fixtures, without claiming live keyed-provider verification.

## Testing Strategy
Happy paths: Tavily and Bocha credential priority and normalized citations. Error paths: missing key, retired engine, selected provider HTTP failure without fallback. Migration: all retired engines, repeated run, preserved unrelated tools and credentials.

## Risks & Mitigation
Agents formerly using keyless search now require inherited or Agent-specific credentials. This is intentional; fail explicitly rather than returning unrelated content. Deploy frontend/backend together. Rollback by reverting this commit, not by preserving dead aliases.

## Status
- Completed. Removed Bing request/parser, selector option and keyless fallback; retired engine choices migrate to auto.
- Backend: 208 focused search/tool/init tests and 18 i18n tests passed; Ruff passed. Babel catalogs compiled; catalog and legacy-sync checks passed.
- Frontend: 6 selector tests passed; TypeScript and selector ESLint passed. No browser or service started; visual layout not browser-verified.
- Public web_search smoke with `上海天气 今天`: auto without credentials reports the localized missing-key error in Chinese/English; Bing/DuckDuckGo are rejected; explicit Tavily/Bocha without keys return provider-specific errors.
- Temporary PostgreSQL table verified Bing/DuckDuckGo/ddg migration to auto, preserved credentials/order/unrelated tools and repeated-run idempotence; transaction rolled back.
- Live authenticated Tavily/Bocha search was not exercised; provider normalization and failure behavior were verified through existing deterministic HTTP/client fixtures.
