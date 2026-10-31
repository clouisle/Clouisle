# File Preview Extend UI Alignment Design Document

## Background & Goals

The shared `FilePreviewPanel` renders PDF, DOCX, XLSX, PPTX, and CSV files in the agent chat right-side canvas and the knowledge-base document preview pages. Its custom wrappers diverged from the official Extend UI examples:

- PDF used `@embedpdf/viewer` with a hand-built chrome instead of the official plugin-based `PDFViewer`.
- DOCX and XLSX used partial custom toolbars without the official thumbnails, search, zoom modes, and sheet controls.
- PPTX rendered the raw `ReactPptxViewer` with no toolbar.
- CSV was converted to XLSX in the browser instead of using the official grid viewer.

Goal: make these surfaces match the official Extend UI components while preserving panel-level loading, size limits, download, permission, and close behavior.

## High-Level Design

- Vendor the official `base-vega` registry sources under `frontend/components/extend/`:
  - `pdf-viewer.tsx`, `docx-viewer.tsx`, `xlsx-viewer.tsx`, `pptx-viewer.tsx`, `csv-viewer.tsx`
  - shared `document-viewer-sidebar.tsx`, `file-thumbnail.tsx`, `docx-annotation-card.tsx`
  - `lib/pdf-thumbnail-utils.ts`
- Add `components/icon-placeholder.tsx` mapping the registry's Lucide icon names (Clouisle ships Lucide only); the XLSX viewer defines its two context-menu primitives inline.
- Keep `FilePreviewPanel` as the owner of blob fetching, size limits, error/permission states, download, and close. Viewers receive an object URL via `src`.
- Split CSV out of the spreadsheet mode so `CsvViewer` receives decoded text; CSV decoding keeps the UTF-8 then GB18030 fallback.
- Synchronize the DOCX/XLSX dark rendering toggle with `next-themes`.
- Load every document viewer through `next/dynamic` with `ssr: false`.
- Add the Glide Data Grid `#portal` mount point required by `CsvViewer`.
- Pass `showUpload={false}` because previews are read-only.
- PDF, DOCX, and PPTX previews default to the official `automatic` zoom mode so the document fits the panel on open; XLSX and CSV only expose numeric zoom in the registry components.
- Localize every viewer string through a `ViewerI18nProvider` context in
  `components/extend/viewer-i18n.tsx`. The panel builds the labels from the
  `common.fileViewer` namespace (`i18n/en|zh/common.json`) so tooltips, menus,
  ARIA labels, zoom modes, search states, empty states, and annotation badges
  follow the active locale. Vendor components fall back to English when used
  without a provider.

## Implementation Plan

### Stage 1: Vendor official viewers

- **Files added**: `frontend/components/extend/*`, `frontend/lib/pdf-thumbnail-utils.ts`, `frontend/components/icon-placeholder.tsx`
- **Dependencies**: `@embedpdf/core|engines|models|pdfium|plugin-*@2.15.x`, `pdf-lib`, `@glideapps/glide-data-grid`, `papaparse`, upgraded `@extend-ai/react-docx/xlsx/pptx`; removed `@embedpdf/viewer`.
- **Validation**: `bunx tsc --noEmit` and `bun run build`.

### Stage 2: Reconnect the shared panel

- **Files modified**: `frontend/components/file-preview/file-preview-panel.tsx`, `file-preview-types.ts`, `index.ts`
- **Logic**: `src` object URLs, theme state, CSV text mode and decoding, removal of the obsolete custom parse-error callbacks, lazy viewer imports.
- **Validation**: panel tests and typecheck.

### Stage 3: Localize vendored viewer copy

- **Files added**: `frontend/components/extend/viewer-i18n.tsx`
- **Files modified**: every vendored viewer, `docx-annotation-card.tsx`, `i18n/en/common.json`, `i18n/zh/common.json`, `i18n/types/common.ts`
- **Logic**: add a `common.fileViewer` label set, replace hard-coded tooltips, ARIA labels, placeholders, menu items, zoom modes, search states, empty/error states, XLSX context actions, and comment/tracked-change badges.
- **Validation**: `bunx tsc --noEmit`, `bun run i18n:check`, `bun run i18n:lint`.

### Stage 4: Application integration

- **Files modified**: `frontend/app/layout.tsx`, `frontend/bunfig.toml`, `frontend/scripts/check-coverage.ts`
- **Logic**: add Glide portal, exclude vendored registry sources from coverage, extend the coverage census test.
- **Validation**: full Bun suite and coverage census.

## Testing Strategy

- Happy path: panel loads text, CSV, PDF, DOCX, PPTX, spreadsheet, image, video, audio, HTML, and markdown previews from a loader blob.
- Error path: 403/401/generic loader errors, oversized files, unsupported binaries, protected raw URLs.
- Regression scope: chat artifacts canvas tests, both knowledge-base document detail and preview pages, typecheck, ESLint, i18n usage/parity checks, production build.
- The vendored viewers are third-party registry code and are excluded from the 95% coverage gate; the panel, localization mapping, and classification logic remain covered.

## Risks & Mitigation

- **PDFium WASM is self-hosted**: `scripts/copy-pdfium-wasm.ts` copies `@embedpdf/pdfium/dist/pdfium.wasm` to `public/pdfium/pdfium.wasm` via `predev`/`prebuild`. `lib/pdf-thumbnail-utils.ts` resolves `/pdfium/pdfium.wasm` against `window.location.origin` before passing it to the blob-URL worker engine; a root-relative path does not resolve reliably inside that worker. Keep the direct `@embedpdf/pdfium` dependency aligned with `@embedpdf/engines` when re-vendoring; the generated asset is gitignored.
- **Upstream strings**: new copy introduced by a future registry sync will stay English until a matching `common.fileViewer` key is added. Re-vendoring must diff the label set.
- **Bundle size**: viewers are lazily imported, so they only load when a matching file is previewed.
- **Vendored drift**: files are registry snapshots; upstream fixes require re-vendoring.
