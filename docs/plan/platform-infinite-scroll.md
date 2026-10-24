# Platform Infinite Scroll Design Document

## Background & Goals
Platform `/app` list pages must load the next server page when their bottom becomes visible. Remove first-page truncation from apps, knowledge bases and API keys; replace platform document, notification and execution-log pagers with the same interaction. Dashboard pagination stays unchanged. Full-response model/team/tool lists and memory graphs are not artificially paginated.

Success: existing items remain visible while appending; pages stop at the server total; changing search, filters, team or resource starts a fresh list; obsolete requests cannot overwrite a new list; failures permit explicit retry without an automatic request loop.

## High-Level Design
Use a shared IntersectionObserver sentinel hook matching the existing chat history approach. Each page retains ownership of its API parameters and accumulated data. Search that queries the server uses the existing debounce hook (300 ms). Append results are deduplicated by identity. API mutation refreshes start a coherent new list or refresh the loaded window as required by document processing and unread-notification semantics.

Applications have two independently paginated sources. The all tab advances non-exhausted Agent and Workflow sources; type tabs must not depend on exhaustion of the other source. Existing updated-at sorting applies to the loaded union, not an unimplemented globally ordered backend feed.

## Implementation Plan

### Stage 1: Shared sentinel and truncated lists
- **Files modified**: `frontend/hooks/use-infinite-scroll.ts`, platform `app/kb/page.tsx`, `app/api-keys/page.tsx`, backend knowledge-base list search and focused tests.
- **Specific logic**: observe the bottom of nested scrollable lists, page from the server, retain accumulated records, discard stale responses and prevent duplicate loads. Preserve KB name-or-description search by widening the existing server predicate; preserve team access checks.
- **Validation**: component interactions load page two, reset on search/team changes, terminate at total, and expose retry after rejection.

### Stage 2: Applications and execution logs
- **Files modified**: platform `app/apps/page.tsx`, Agent and Workflow `logs/page.tsx`, related tests.
- **Specific logic**: replace list truncation/pagers with append loading; independently exhaust application sources; preserve log filters and detail drawers.
- **Validation**: append page two without removing page one, exhaust one application type independently, reset on filters and ignore stale completions.

### Stage 3: Documents and notifications
- **Files modified**: platform `app/kb/[id]/_components/documents-table.tsx`, notification client and related tests.
- **Specific logic**: append server pages, keep document polling coherent across the loaded window, replace eager unread fetching with incremental loading and refresh after mutations that change membership.
- **Validation**: polling retains loaded pages; unread mutations do not skip the next unread item; selection and access restrictions remain intact.

### Stage 4: Verification and delivery
- **Files modified**: implementation index and this plan; existing relevant user/developer documentation as necessary.
- **Specific logic**: run focused component tests and frontend static checks once integration settles. Do not start application services or browser sessions.
- **Validation**: report observed command results and explicitly state the lack of browser visual verification.

## Testing Strategy
- Happy paths: bottom observer loads next page, preserves existing rows, stops at total and supports independent application sources.
- Error paths: rejected next-page requests preserve records and page position; manual retry retries the same page; observer callbacks do not duplicate an in-flight page.
- Regression: search/filter/team/resource reset, stale completions, CRUD refresh, document polling, unread notification mutations and unchanged dashboard behavior.

## Risks & Mitigation
- Offset pagination over mutable datasets can shift records. Deduplicate identities and refresh coherently after mutations; do not claim snapshot or cursor semantics.
- Agent/Workflow loaded-union sorting is not global cross-source pagination. Retain existing behavior without inventing a backend aggregate API.
- Nested scroll containers and short initial pages require observer coverage in component interaction checks.
- Rollback: revert only the platform infinite-scroll change set, restoring existing pagers and fetch behavior; no database migration.

## Status
Completed on 2026-10-25 across applications, knowledge bases, API keys, documents, notifications, Agent logs and Workflow logs. The KB server search now matches name or description, preserving the former platform client-filter behavior.

Verification:
- Frontend focused interaction/regression suite: **90 passed, 0 failed**, 12 files. Includes real component renders with controlled IntersectionObserver callbacks driving page-two requests, append/stop behavior, stale-request rejection, explicit retry, document polling and unread mutation refresh. Test transport is mocked; no live API/browser session was run.
- Backend focused KB list compatibility: **7 passed**.
- `bunx tsc --noEmit --incremental false`: passed.
- ESLint on the shared hook, hook tests and all seven changed list components: passed.
- `bun run i18n:gen-types`, `bun run i18n:lint`, `bun run i18n:check`: passed.
- Temporary Bun configuration disabled coverage for the focused run, avoiding modifications to existing coverage artifacts. No services or browser sessions were launched; visual browser geometry remains unverified.
