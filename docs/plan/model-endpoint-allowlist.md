# Model Endpoint Allowlist Design Document

## Background & Goals

Model discovery and provider connection tests accept administrator-supplied Base URLs. The product must support HTTP, HTTPS, public IPs, private IPs, localhost, and internal model gateways without environment-variable configuration, while requiring every model endpoint to be explicitly approved through the admin UI.

Success criteria:

- Store one full model endpoint Origin allowlist in the database through Site Settings.
- Validate the allowlist itself and validate effective model Base URLs before model persistence.
- Re-check the same policy before discovery, model tests, and runtime model requests.
- Preserve provider-specific URL paths while matching only normalized scheme, host, and port.
- Give localized, actionable failures without leaking credentials or raw upstream responses.

## High-Level Design

Add `model_endpoint_allowlist` as a private JSON SiteSetting under the Security category. The Security settings page edits one Origin per line and uses the existing SiteSetting bulk-update API. Empty allowlists reject model endpoints until an administrator explicitly adds Origins.

A shared backend policy normalizes an endpoint to its Origin and compares it against the database allowlist. It accepts exact scheme/hostname/port matches, handles default ports, and never matches wildcards. The policy is used at persistence and immediately before outbound requests. Existing provider defaults and persisted model Origins are seeded during initialization so upgrades do not invalidate configured models.

## Implementation Plan

### Stage 1: SiteSetting and origin policy

- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`, `backend/app/services/` policy module, `backend/app/core/init_data.py`, schemas and locales.
- **Specific logic**: Register one private JSON setting, validate entries, normalize Origins, and expose an async policy for effective Base URLs.
- **Validation**: Reject malformed entries, normalize default ports and trailing paths, deduplicate values, and verify empty/non-empty allowlist behavior.

### Stage 2: Model persistence and outbound enforcement

- **Files modified**: `backend/app/api/v1/admin/endpoints/models.py`, model request paths and tests.
- **Specific logic**: Validate submitted/effective Base URLs before create/update; apply the same policy to discovery, draft/persisted tests, and runtime model request boundaries. Keep discovery redirects disabled and retain bounded response parsing.
- **Validation**: Unlisted endpoints fail before HTTP clients are called; allowlisted HTTP/HTTPS/IP/internal endpoints continue; deleting an allowlist entry blocks the next outbound operation.

### Stage 3: Dynamic Security settings UI

- **Files modified**: `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`, Security settings page/tests, locale catalogs and generated types.
- **Specific logic**: Add a one-entry-per-line editor, save through the existing security settings API, show actionable empty/list validation errors, and avoid exposing the setting publicly.
- **Validation**: Load, edit, save, normalize, and reload the allowlist without a service restart.

### Stage 4: Compatibility and rollout evidence

- **Files modified**: `backend/app/core/init_data.py`, tests, `docs/IMPLEMENTATION_PLAN.md`.
- **Specific logic**: Seed built-in provider Origins and existing model Origins idempotently, documenting that new model endpoints require explicit allowlisting.
- **Validation**: Existing configured models remain usable; repeated initialization does not duplicate entries; fresh installations remain explicit and deterministic.

## Testing Strategy

- Backend unit tests for Origin normalization, allowlist validation, persistence rejection, discovery/test enforcement, and initialization idempotence.
- Frontend API and Security page tests for one-entry-per-line editing and save/reload behavior.
- Regression tests for public, private, localhost, IPv4, IPv6, HTTP, HTTPS, custom ports, duplicate entries, malformed values, and unlisted targets.
- Existing backend coverage gate, frontend isolated tests, lint, i18n checks, and production build.

## Risks & Mitigation

- **Existing model breakage**: Seed current provider defaults and persisted Origins before enforcing the policy.
- **DNS changes**: Match the configured Origin at the URL policy boundary and retain destination checks before outbound requests; do not treat response validation as SSRF prevention.
- **Credential leakage**: Keep API keys out of logs and user-facing upstream error text.
- **Configuration mistakes**: Make empty-list behavior explicit in the UI and return an actionable localized error.

## Rollback Plan

The SiteSetting is additive. Removing enforcement restores the previous connection behavior while leaving the stored allowlist inert. Removing the setting from the UI does not delete it or alter existing model records.

## Completion Evidence

- Backend: `uv run pytest` passed 6,778 tests with 3 skipped; `scripts/check_coverage.py` reported 97.45% line and 95.06% branch coverage.
- Frontend: 2,092 isolated tests passed with 9,588 assertions; the focused Security settings/API suite passed 12 tests; production `next build`, full ESLint, and translation lint passed.
- Localization: backend catalog and legacy-sync checks passed; frontend translation types were regenerated and catalog lint passed.
