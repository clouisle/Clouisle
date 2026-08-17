# YUN-135: Extend the Knowledge-Base Tour to Document Ingestion

## Background & Goals

The platform `kb` onboarding tour currently ends after knowledge-base creation. Extend the same persisted `kb` tour through the detail page, local file upload, URL import, document processing statuses, and Retrieval Lab validation.

Success criteria:

- Creating `Product docs` from the tour navigates to `/app/kb/kb-1` when the API returns `{ id: 'kb-1' }`.
- The tour survives the list-to-detail-to-search route transitions without resetting or routing detail/search pages back to `/app/kb`.
- Detail, dialog, status, and Retrieval Lab targets use stable, exact `data-testid` contracts.
- Upload guidance displays the accepted formats derived from the shared constant and the runtime maximum size in both locales.
- Missing document statuses advance without fabricated rows; present statuses are highlighted.
- English and Simplified Chinese catalogs remain structurally and ICU-consistent, with generated types updated.

## High-Level Design

`KnowledgeBaseDialog` owns create success navigation and remains compatible with every existing caller. The static `/app/kb` tour route is matched as a route family by `OnboardingTour`, while the existing `/app` exact-boundary exception remains intact. Detail and Retrieval Lab components expose permanent loading/loaded anchors so async data does not interrupt route continuation. The existing provider state, `kb` tour ID, local-storage completion format, and step lifecycle remain unchanged.

## Implementation Plan

### Stage 1: Preserve tour continuity

- **Files modified**: `frontend/app/(platform)/app/kb/_components/kb-dialog.tsx`, `frontend/components/onboarding/steps/kb-steps.ts`, `frontend/components/onboarding/onboarding-tour.tsx`.
- **Specific logic**: Capture the created knowledge base, close/toast/callback, then push `/app/kb/<id>` only in the create branch. Mark the existing submit step as click-advancing and route-waiting. Use `routeMatches` for current-step route effects. Extend the existing dialog overlay selector predicate for the two KB ingestion dialogs. Keep edit/error behavior and provider lifecycle unchanged.
- **Validation**: Focused dialog and onboarding tests prove create navigation, edit/error non-navigation, nested route preservation, exact `/app` boundary behavior, and overlay class behavior.

### Stage 2: Add ingestion and retrieval anchors

- **Files modified**: `frontend/app/(platform)/app/kb/[id]/page.tsx`, `frontend/app/(platform)/app/kb/[id]/_components/upload-document-dialog.tsx`, `frontend/app/(platform)/app/kb/[id]/_components/import-url-dialog.tsx`, `frontend/app/(platform)/app/kb/[id]/_components/documents-table.tsx`, `frontend/components/knowledge-bases/retrieval-lab/index.tsx`, both `knowledgeBases.json` catalogs.
- **Specific logic**: Add the exact detail, dialog, document-status, lab, query, submit, and post-search test IDs from the approved local plan. Derive the upload format label from `KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES`, and render the fetched/default maximum size through `knowledgeBases.maxFileSize`. Preserve APIs, permissions, validation, and result rendering.
- **Validation**: Component contracts assert every anchor, dynamic format list, configured/fallback size, status IDs, query interaction, and post-search wrapper states.

### Stage 3: Extend ordered bilingual tour content

- **Files modified**: `frontend/components/onboarding/steps/kb-steps.ts`, `frontend/i18n/en/onboarding.json`, `frontend/i18n/zh/onboarding.json`.
- **Specific logic**: Preserve the first existing KB steps except the approved submit flags, append the ordered detail/upload/import/status/search steps with `/app/kb` route-family matching and exact placement/advance flags, and add `step31a` through `step31p`. Do not mark cross-route ingestion/status steps optional. Update only the existing KB tour descriptions requested by the plan.
- **Validation**: Step contract tests assert target order, route flags, placements, status-prefix selectors, and bilingual key presence/content.

### Stage 4: Regenerate types and validate regressions

- **Files modified**: Generated `frontend/i18n/types/onboarding.ts` and `frontend/i18n/types/knowledgeBases.ts`, plus affected tests.
- **Specific logic**: Update all contract tests named in the approved local plan. Run the generator; retain semantic generated changes and remove timestamp-only churn from unrelated generated files. Run strict translation validation, TypeScript, focused Bun tests, coverage, and the configured coverage threshold gate.
- **Validation**: Execute every command in the approved plan's Verification section from the repository root.

## Testing Strategy

- Happy path: create and navigate, open/close both ingestion dialogs, show configured upload rules, render all four status states, enter `policy`, submit retrieval, and render `kb-search-results`.
- Error paths: validation failure keeps the create dialog open and never routes; API failures leave dialog state and tour navigation unchanged; default upload limit remains enforced when settings fail; absent status rows are skipped by existing target-not-found handling.
- Regression scope: existing edit/create callers, permission-gated detail actions, upload/import APIs and preview routes, Retrieval Lab permissions/back route/authenticated markdown, `/app` route boundary, dialog overlay pass-through, EN/ZH parity, TypeScript, and coverage threshold.

## Risks & Mitigation

- Async detail/document rendering can make tour targets disappear. Keep permanent loading roots and omit `skipIfMissing` from cross-route ingestion/status steps so existing target-not-found advancement handles absent rows.
- A static route can accidentally redirect descendants to the list. Centralize the fix in `routeMatches` and retain its `/app` boundary special case.
- Generator timestamps can create unrelated churn. Restore unchanged generated type files after semantic regeneration.
- Upload copy can drift from validation constants. Derive the displayed format list from `KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES` and reuse the existing fetched/default size state.

## Rollback

Revert the YUN-135 feature branch changes as one unit. No backend schema, API, or data migration is involved.

## Verification Record

- Onboarding focused suite: 20 tests passed, 0 failed.
- KB dialog/detail/upload/import/document suite: 23 tests passed, 0 failed.
- Retrieval Lab and platform search-client suite: 16 tests passed, 0 failed.
- Translation generation, strict EN/ZH parity/ICU validation, and `bunx tsc --noEmit` passed.
- Full frontend coverage gate: 2,226 tests passed, 0 failed; LCOV covered all 485 eligible source files.
