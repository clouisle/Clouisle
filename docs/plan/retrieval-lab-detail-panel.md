# Retrieval Lab Detail Panel Design Document

## Background & Goals

Retrieval Lab result cards currently expand full chunk content inline. Long chunks change list height and make comparing ranks difficult. The goal is a compact master-detail interface that keeps the result list stable while preserving all production retrieval data.

Success criteria:
- Result cards remain compact and selectable, with no visible or copyable chunk ID.
- Desktop uses one resizable, independently scrolling detail panel shared by A and B.
- Mobile uses the existing Sheet and mobile breakpoint hook.
- Scores, ranks, Markdown, timings, diagnostics, fallback reasons, A/B overlap and movement, presets, permissions, and errors remain available.

## High-Level Design

`RetrievalLab` stores one selection as a configuration side plus chunk ID. The selected result is derived from the latest A/B responses, so stale result objects are not retained across searches. Result lists own response-level timings and diagnostics. A shared `ResultDetail` owns chunk-level scores, content, and fallback reasons and renders in either the desktop resizable panel or mobile Sheet.

## Implementation Plan

### Stage 1: Side-aware result selection
- **Files modified**: `frontend/components/knowledge-bases/retrieval-lab/index.tsx`
- **Specific logic**: Replace the expanded ID set with one `{ side, chunkId }` selection. Clear it at search start and select A's first result, otherwise B's first result, after completion.
- **Validation**: Verify identical chunk IDs in A and B select the correct side and content; verify failed/empty searches close stale details.

### Stage 2: Compact result cards
- **Files modified**: `frontend/components/knowledge-bases/retrieval-lab/index.tsx`
- **Specific logic**: Render each card as a native button containing rank, document, stage, movement, and a two-line highlighted excerpt. Remove chunk ID display and copy behavior. Expose selected and focus states with ARIA and theme tokens.
- **Validation**: Assert no full or shortened chunk ID is visible, selection is single, and A/B overlap and movement remain intact.

### Stage 3: Responsive shared details
- **Files modified**: `frontend/components/knowledge-bases/retrieval-lab/index.tsx`
- **Specific logic**: Extract `ResultDetail`. Use `ResizablePanelGroup` for desktop with independent result/detail scrolling and `Sheet` with `useIsMobile` on narrow screens. Keep timings and diagnostics above their corresponding result list.
- **Validation**: Verify one desktop detail region, resize handle labeling, mobile Sheet open/switch/close behavior, long content containment, and authenticated Markdown images.

### Stage 4: i18n and tests
- **Files modified**: `frontend/i18n/en/knowledgeBases.json`, `frontend/i18n/zh/knowledgeBases.json`, `frontend/i18n/types/knowledgeBases.ts`, `frontend/components/knowledge-bases/retrieval-lab.test.tsx`
- **Specific logic**: Add accessible detail, selection, close, and resize labels in both locales; remove obsolete chunk-copy keys; regenerate types; update test mocks and selection scenarios.
- **Validation**: Run focused Bun tests, the translation generator, and strict translation lint.

### Stage 5: Validation
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/retrieval-lab-detail-panel.md`
- **Specific logic**: Record completed stages and validation outcomes without modifying the Retrieval API or reverting existing cleanup work.
- **Validation**: Run frontend lint/build where feasible and `git diff --check`; inspect the final changed-file list.

## Testing Strategy

- Happy paths: A-only automatic selection, A/B side switching, shared chunk IDs, desktop panel, mobile Sheet, Markdown content, scores, timings, diagnostics, presets.
- Error paths: A failure with B fallback, both sides empty/failed, retry clears old detail, mobile close clears selection.
- Regression scope: Retrieval settings, immediate A/B calls, permissions, IME handling, sanitized errors, overlap and rank movement, authenticated Markdown images.

## Validation Results

- Retrieval Lab focused tests: 10 passed.
- Dashboard/platform wrapper tests: 2 passed.
- Strict translation lint: passed.
- Frontend ESLint: passed.
- Frontend production build: passed.
- `git diff --check`: passed.

## Risks & Mitigation

- A/B results can share chunk IDs. Include side in selection identity.
- A new search can invalidate the selected object. Store only side and ID, and derive from current responses.
- Long Markdown can overflow the panel. Keep the panel and content scroll containers bounded and allow code/table horizontal overflow.
- Responsive components can duplicate details. Render desktop details only outside mobile mode and Sheet details only in mobile mode.
- Rollback is localized to the component, translations, generated type, tests, and these planning entries.
