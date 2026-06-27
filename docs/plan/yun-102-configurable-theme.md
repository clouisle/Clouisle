# YUN-102 Configurable Theme Design Document

## Background & Goals
- Problem to solve: theme settings only cover primary colors, and manual hex input makes it hard to configure a coherent visual system.
- Success criteria:
  - Admins can configure practical core theme colors with compact native color pickers.
  - Runtime theme applies page, card, top navigation, sidebar, hover, supporting, and chart colors through existing CSS variables.
  - Empty values preserve the default theme.
  - Optional alpha values support translucent surfaces.
  - Invalid colors fail fast through frontend validation and backend validation.

## High-Level Design
- Keep theme configuration in existing public `site_settings` keys under the `general` category.
- Extend the public settings API with flat theme color fields.
- Reuse existing CSS variables in `globals.css` instead of introducing a new theme engine.
- Apply configured colors through `PublicThemeApplicator` and `getBrandCssVariables()`.
- Add a visual preview block to show top navigation, sidebar, page, card, button, hover, and chart colors together before saving.

## Implementation Plan

### Stage 1: Backend theme keys and validation
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`, `backend/tests/api/test_site_settings_theme.py`
- **Specific logic**: Add public `theme_*_color` defaults for page, card, sidebar, top navigation, supporting, and chart tokens. Validate known theme color keys as empty string, `#RGB`, `#RGBA`, `#RRGGBB`, or `#RRGGBBAA`.
- **Validation**: Run targeted site settings theme tests and backend ruff checks.

### Stage 2: Public API and frontend types
- **Files modified**: `backend/app/schemas/site_setting.py`, `backend/app/api/v1/endpoints/site_settings.py`, `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`
- **Specific logic**: Add public response fields, normalize invalid stored colors to empty strings, and normalize admin-loaded theme colors before UI state uses them.
- **Validation**: Type check through frontend build and targeted tests.

### Stage 3: Runtime theme application
- **Files modified**: `frontend/lib/theme-config.ts`, `frontend/contexts/site-settings-context.tsx`, `frontend/lib/theme-config.test.ts`
- **Specific logic**: Map new settings to CSS variables (`--background`, `--card`, `--sidebar`, `--navbar`, `--navbar-hover`, `--accent`, `--muted`, `--chart-1` through `--chart-5`). Empty settings remove overrides.
- **Validation**: Run `bun test ./lib/theme-config.test.ts`.

### Stage 4: Admin UI and preview
- **Files modified**: `frontend/app/(dashboard)/site-settings/page.tsx`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`, generated `frontend/i18n/types/*`
- **Specific logic**: Replace manual-only theme color inputs with compact labeled color triggers that open a popover containing the native color picker, alpha slider, and reset action. Group colors by Brand, Page & Cards, Navigation / Workbench, Supporting UI, and Charts. Add a combined preview panel so admins can judge whether colors work together.
- **Validation**: Run translation lint, frontend lint, and frontend build.

## Testing Strategy
- Happy path tests:
  - Theme color validation accepts empty, short hex, full hex, and alpha hex values.
  - Theme helper maps representative settings to CSS variables.
  - Admin UI builds with generated translation types.
- Error path tests:
  - Invalid colors like `blue`, malformed hex, and non-string values are rejected.
  - Public API normalizes invalid stored color values to empty strings.
- Regression scope:
  - Default empty settings keep existing theme appearance.
  - Existing theme mode and branding display behavior remains unchanged.
  - No browser automation or dev server startup is required.

## Risks & Mitigation
- Possible side effect: too many settings make the page harder to scan. Mitigation: keep a practical core set and group by visual surface.
- Possible side effect: generated i18n types touch many files. Mitigation: regenerate with the existing script and do not hand-edit generated files.
- Image import or model-generated theme suggestions are intentionally not included in this increment. They require a separate design for image upload, palette extraction/model prompt flow, permissions, and error handling.
- Rollback plan: revert this branch change; settings default to empty and no data migration is required.
