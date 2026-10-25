# Dashboard Search Debounce Design Document

## Background & Goals
Eleven dashboard main search fields currently use each keystroke directly for server queries. Collapse rapid edits into a single applied query after 300 ms without delaying the input itself. Existing debounce durations and platform infinite-scroll pages stay unchanged.

## High-Level Design
Reuse `frontend/hooks/use-debounce.ts`. Each affected list keeps its existing raw search state and derives a 300 ms debounced value for request parameters, request dependencies and search-driven page resets. Discrete filters and page navigation remain immediate. Document polling uses the applied search term.

## Implementation Plan
### Stage 1: Activity and audit searches
- **Files modified**: dashboard activity conversations/workflow runs tables, audit log table, related tests.
- **Specific logic**: debounce main search separately from existing remote user-picker search; preserve explicit export semantics.
- **Validation**: rapid edits do not query before settling; final query applies at page one; filters still act immediately.

### Stage 2: Applications and capabilities
- **Files modified**: dashboard admin Agent/Workflow panels, tool and skill panels, related tests.
- **Specific logic**: derive applied main search with the existing hook; replace raw request/reset dependencies without delaying input display.
- **Validation**: render components, edit search rapidly, observe final API arguments after delay, preserve tab/filter/pagination behavior.

### Stage 3: Knowledge, memories and models
- **Files modified**: dashboard KB list, KB document table, memory list, model list and tests.
- **Specific logic**: debounce API search and page reset; keep processing-document polling bound to applied query.
- **Validation**: verify final-term requests, page reset and polling/filter regressions.

### Stage 4: Integrated verification
- **Files modified**: this plan, implementation index and frontend conventions.
- **Specific logic**: execute focused interaction tests, TypeScript and targeted ESLint after all slices settle. No services or browser sessions.
- **Validation**: report actual command outcomes; remove temporary testing configuration.

## Testing Strategy
Exercise rapid input edits against a rendered component with real debounce timing and a mocked API transport; assert no intermediate search requests and final query/page. Preserve existing authorization, polling, filtering and CRUD tests. Do not replace real debounce behavior with an identity mock in the debounce-specific tests.

## Risks & Mitigation
- Raw search left in a fetch dependency bypasses debounce: inspect all request and reset paths.
- Search applied on a later page can issue an unnecessary old-page query: cohere page reset and applied query.
- Existing tests may assume immediate search; adjust meaningful timing interactions rather than pinning private state layout.
- Rollback only the eleven list integrations and accompanying tests/docs; shared hook behavior is unchanged.

## Status
Completed on 2026-10-25. All eleven main searches use the existing 300 ms hook. Raw inputs remain immediate; guarded effects reset settled searches to page one before issuing a request. Discrete filters, existing debounce durations and platform lists are unchanged. Audit export retains the current typed term because it is explicitly submitted.

Observed verification:
- Activity/audit regression and rendered timer interactions: 54 passed across 12 files.
- Application/capability regressions and rendered timer interactions: 48 passed across 12 files.
- KB/document/memory/model regressions and rendered timer interactions: 47 passed across 6 files.
- Total focused verification: 149 passed, 0 failed across 30 files. Debounce-specific tests use real hook timers and mocked API transport, verify immediate input display, no intermediate query, and exactly one final-query request at page one when starting on a later page.
- `bunx tsc --noEmit --incremental false`: passed. Targeted ESLint across eleven production components: passed.
- Initial integrated activity test runs timed out because a test window timer wrapper recursively replaced the native timer; capturing native timers fixed the harness. The repaired activity suite then passed in 5.05 seconds.
- No application services or browser sessions were launched. Temporary coverage-disabled Bun configuration was removed after verification.
