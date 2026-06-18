# YUN-96 Site Legal Settings Design Document

## Background & Goals
- Problem to solve: system settings cannot configure ICP record information or legal agreement/privacy entries for login and registration pages, and registration cannot require explicit agreement acceptance.
- Success criteria: admins can configure ICP and agreement/privacy fields; unauthenticated auth pages display configured legal entries; registration can be blocked until the user checks the agreement box when the setting is enabled.

## High-Level Design
- Extend the existing `general` site settings category with public legal/ICP keys.
- Expose the new public settings through the existing public site settings endpoint and frontend public settings types/defaults.
- Add a legal/compliance section to the existing admin site settings page.
- Render ICP and agreement/privacy entries from the shared auth layout shell so login/register pages stay consistent.
- Add a register-only checkbox controlled by `require_terms_acceptance_on_register`, with frontend validation and backend enforcement.

## Implementation Plan

### Stage 1: Backend setting contract
- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/schemas/site_setting.py`, `backend/app/api/v1/endpoints/site_settings.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`
- **Specific logic**: Add public general defaults for ICP, terms, privacy, and required acceptance; expose them in `PublicSiteSettingsResponse`; map them in the public endpoint; validate non-empty legal URLs in admin settings.
- **Validation**: Public settings response includes all new fields with stable default values and correct boolean/string types.

### Stage 2: Backend registration enforcement
- **Files modified**: `backend/app/schemas/user.py`, `backend/app/api/v1/endpoints/login.py`, `backend/app/locales/en/LC_MESSAGES/messages.po`, `backend/app/locales/zh/LC_MESSAGES/messages.po`
- **Specific logic**: Add optional `terms_accepted` to registration input; when `require_terms_acceptance_on_register` is enabled for non-first-user registration, reject missing/false acceptance with a field-level validation error.
- **Validation**: Registration still works without the field when the setting is disabled; registration fails with `terms_accepted` validation data when enabled and unchecked; accepted requests proceed.

### Stage 3: Frontend settings contract and admin UI
- **Files modified**: `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`, `frontend/contexts/site-settings-context.tsx`, `frontend/app/(dashboard)/site-settings/page.tsx`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`
- **Specific logic**: Extend public/general settings types and defaults; add admin controls for ICP number/URL, terms enabled/URL/text, privacy enabled/URL/text, and required register acceptance; reuse existing save, permission, validation, and `FieldError` patterns.
- **Validation**: Values load, save, refresh, and persist; URL validation shows localized field errors.

### Stage 4: Auth page legal display and register checkbox
- **Files modified**: `frontend/lib/api/auth.ts`, `frontend/app/(auth)/layout.tsx`, `frontend/app/(auth)/_components/auth-layout-shell.tsx`, `frontend/app/(auth)/register/_components/register-form.tsx`, `frontend/i18n/en/auth.json`, `frontend/i18n/zh/auth.json`
- **Specific logic**: Pass legal public settings to the auth layout shell; render compact ICP/legal footer entries; fetch public settings in register form; show a required agreement checkbox when configured and send `terms_accepted: true` only after validation.
- **Validation**: Login/register show legal entries when configured; register blocks unchecked submission when required and succeeds after checking.

### Stage 5: Generated types and verification
- **Files modified**: generated frontend i18n types under `frontend/i18n/types/`
- **Specific logic**: Run `node scripts/gen-i18n-types.ts` after translation changes.
- **Validation**: Run frontend lint/build and backend ruff/mypy/targeted pytest where practical; manually verify auth/admin flows in browser.

## Testing Strategy
- Happy path tests: configure ICP, terms, privacy, and required acceptance; login/register display entries; checked registration succeeds.
- Error path tests: invalid URL fields show admin validation; unchecked registration is rejected by frontend and backend.
- Regression scope: existing registration-disabled, approval, email verification, captcha/SSO login, centered/split auth layouts, public settings fallback behavior, English/Chinese translations.

## Risks & Mitigation
- Risk: public setting defaults are duplicated across backend and frontend. Mitigation: update all fallback sites in one segment and verify public response plus frontend build.
- Risk: long legal text can break auth layout. Mitigation: show text in a constrained scrollable dialog/area.
- Risk: users bypass frontend checkbox. Mitigation: backend validation is authoritative.
- Rollback plan: disable `require_terms_acceptance_on_register`, clear legal/ICP settings, or remove the added public/admin mappings.
