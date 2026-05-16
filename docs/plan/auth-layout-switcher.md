# Auth Layout Switcher Design Document

## Background & Goals
- Problem to solve: authentication pages currently only support a centered card. Admins need a site setting that can switch to a desktop split layout matching the provided left-form/right-preview reference.
- Success criteria: login, register, forgot password, and reset password share the selected layout; the setting is managed in admin site settings; mobile remains single-column and usable.

## High-Level Design
- Backend site settings add a public `auth_page_layout` general setting with values `centered` and `split`.
- Frontend public settings expose `auth_page_layout` to unauthenticated auth routes.
- Admin general settings adds a select control to choose the auth page layout.
- Auth routes use a shared wrapper that renders the existing centered card by default, or a split desktop shell with the card on the left and a calm product preview panel on the right.

## Implementation Plan

### Stage 1: Setting contract
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/schemas/site_setting.py`, `backend/app/api/v1/endpoints/site_settings.py`, `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`
- **Specific logic**: Add `auth_page_layout` default, public response field, frontend types, and admin general settings mapping.
- **Validation**: Confirm missing values default to `centered`; invalid values do not break auth rendering.

### Stage 2: Admin settings UI
- **Files modified**: `frontend/app/(dashboard)/site-settings/page.tsx`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`
- **Specific logic**: Add a select under site branding for `centered` and `split`, reusing the existing save flow and permission disable state.
- **Validation**: Load, change, save, and reload the setting.

### Stage 3: Shared auth layout
- **Files modified**: `frontend/app/(auth)/layout.tsx`, `frontend/app/(auth)/_components/auth-layout-shell.tsx`, `frontend/i18n/en/auth.json`, `frontend/i18n/zh/auth.json`
- **Specific logic**: Fetch public settings server-side in the auth layout, render centered layout unchanged for default, and render split desktop shell with right-side product preview when selected.
- **Validation**: Desktop split view shows the reference-like two-column structure; mobile falls back to the auth card only.

### Stage 4: Auth page integration
- **Files modified**: `frontend/app/(auth)/login/page.tsx`, `frontend/app/(auth)/register/page.tsx`, `frontend/app/(auth)/forgot-password/page.tsx`, `frontend/app/(auth)/reset-password/page.tsx`
- **Specific logic**: Keep existing forms but tune card width and duplicate branding only where needed so pages sit cleanly in both layouts.
- **Validation**: Login, register, forgot password, and reset password render without horizontal overflow.

## Testing Strategy
- Happy path tests: admin changes layout to split, public auth pages render split on desktop; change back to centered restores current layout.
- Error path tests: public settings request failure or unknown value renders centered layout.
- Regression scope: SSO/password login controls, registration disabled behavior, forgot/reset password token redirect, locale switcher placement.
- Completed checks: `bun run --cwd frontend lint`, `node frontend/scripts/lint-translations.ts --strict`, `uv run --directory backend ruff check app/api/v1/endpoints/site_settings.py app/models/site_setting.py app/schemas/site_setting.py`, `curl -I` for `/login`, `/register`, and `/forgot-password`, plus public settings API response check.
- Build note: `bun run --cwd frontend build` is currently blocked by an existing unrelated type error in `frontend/app/(dashboard)/api-keys/_components/api-key-dialog.tsx:169` where `number | ""` is assigned to `number | undefined`.

## Risks & Mitigation
- Risk: server layout fetch could fail before auth pages render. Mitigation: catch and default to centered.
- Risk: admin setting can save an arbitrary string if called directly. Mitigation: frontend only sends known values and auth layout treats unknown values as centered.
- Rollback plan: set `auth_page_layout` to `centered` or remove the setting from public/admin mappings.
