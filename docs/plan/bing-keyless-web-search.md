# Keyless Bing Web Search Design Document

## Background & Goals
- DuckDuckGo HTML search returned HTTP 202 anti-bot pages in live checks. Remove its implementation and configuration option rather than retaining a fallback chain.
- Use Bing RSS without an API key; retain Tavily and Bocha priority and existing citation/result contracts.
- Success: auto with no credentials and explicit Bing search return real results; unavailable providers never appear as successful empty searches; saved DuckDuckGo Agent choices migrate to Bing.

## High-Level Design
- `web_search` routes auto to Tavily, Bocha, then Bing; a failed keyed provider in auto mode uses Bing. Explicit keyed selections do not silently change providers.
- Bing uses the existing httpx and BeautifulSoup dependencies to request RSS and normalize title, URL, snippet and citation ID. Chinese queries select zh-CN; other queries select en-US, avoiding observed IP-derived market mismatch.
- Remove DuckDuckGo network, parser and runtime aliases. A startup data migration changes only built-in web_search entries with legacy engines in Agent tools_config, preserving order, credentials and unrelated configuration.
- Frontend engine selector and both locales expose Bing instead of DuckDuckGo.

## Implementation Plan

### Stage 1: Backend provider and stored configuration cutover
- **Files modified**: `backend/app/llm/tools/builtin/web_search.py`, `backend/app/core/init_data.py`, backend search/init tests.
- **Specific logic**: Remove DuckDuckGo parsing and requests; use Bing directly. Migrate saved legacy engine selections idempotently after schema initialization.
- **Validation**: Exercise real Bing through public web_search; test RSS parsing, invalid links, result limits, empty/challenge pages, HTTP failure and timeout. Exercise migration on temporary PostgreSQL tables including repeated execution and unrelated entries.

### Stage 2: Frontend and documentation cutover
- **Files modified**: Agent tool selector, English/Chinese Agent locale files, locale types, README and relevant tool guides, TODO and CHANGELOG.
- **Specific logic**: Replace option value and label with Bing; document keyless behavior and public-endpoint reliability limits.
- **Validation**: Frontend type/lint checks and available non-browser component checks; verify no runtime DuckDuckGo implementation or option remains. No browser or service is started.

### Stage 3: Integrated verification
- **Files modified**: Existing behavior tests, this plan and implementation index.
- **Specific logic**: Update affected contracts and remove obsolete parser tests; keep citations and tool output formatting unchanged.
- **Validation**: Run focused backend tests without repository-wide coverage output, live Chinese/English searches, and frontend static checks.

## Testing Strategy
- Happy paths: auto/no key, explicit Bing, keyed auto fallback, citations and result bounds.
- Error paths: unsupported engine, HTTP error, timeout, no usable RSS items and challenge HTML.
- Regression: Tavily/Bocha routing, tool output rendering and webpage fetch tests.
- Migration: legacy entries only, array order and credentials preserved, non-web-search tools untouched, repeated execution unchanged.

## Risks & Mitigation
- Bing RSS is a public keyless endpoint, not a paid API SLA; blocking or empty responses remain explicit failures. Keep keyed providers available.
- Region affects relevance; specify market instead of relying on egress geolocation.
- Deploy backend and frontend together; startup migrates saved Agent choices. Historical tool outputs are not rewritten.
- Rollback: revert the cutover commit and deliberately reset affected engine selections if returning to the removed provider.

## Status
- Completed: DuckDuckGo requests/parsers/options and runtime aliases removed; saved Agent configurations migrate to Bing at startup.
- Backend: 212 focused tests passed (`pytest --no-cov` across multi-engine search, issue255 web search, companion tool coverage, tool output and init-data suites); Ruff check passed and changed search files are formatted.
- Frontend: 6 selector tests passed, including saving Bing without a key; TypeScript and selector ESLint checks passed. No browser/service was started; visual layout was not browser-verified.
- Live public `web_search`: `python asyncio` (auto), `上海 天气` (explicit Bing), and `Clouisle AI` (auto) each returned 3 usable results with citation IDs.
- Existing PostgreSQL container: migration exercised against a transaction-local temporary Agent table; aliases changed while credentials/order/unrelated entries survived, repeated execution was unchanged, empty/NULL rows survived. Transaction rolled back; production Agent rows were not changed.
