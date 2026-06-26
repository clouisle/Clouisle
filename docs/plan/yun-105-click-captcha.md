# YUN-105 Click Captcha Design Document

## Background & Goals
- Replace the existing typed math captcha with a click-based human verification interaction.
- Preserve security validation on login and add the same critical coverage to registration when captcha is enabled.
- Provide clear retry behavior for missing, invalid, expired, or failed captcha state.

Success criteria:
- Users complete human verification by clicking a challenge control.
- Login still requires captcha when `enable_captcha` is enabled.
- Registration also requires captcha when `enable_captcha` is enabled, except first-user bootstrap registration.
- Backend rejects missing, invalid, expired, or reused tokens.
- Non-browser tests cover success and failure paths.

## High-Level Design
- Backend `app.core.captcha` generates a public click-choice challenge descriptor and stores only the private expected clicked option in Redis with the existing captcha TTL.
- Backend `/captcha` returns click-oriented public metadata: `captcha_id`, `challenge`, `prompt`, `expires_in`; it must not return the correct option or a reusable login/register proof token.
- Backend `/captcha/click` validates the clicked public option against the server-side target and issues a separate private one-time proof token; client `elapsed_ms` is advisory and Redis TTL/server state is authoritative.
- Login and register submit `captcha_id` plus the proof `captcha_token`; the backend verifies the proof and deletes it on use.
- Frontend login/register replace the text answer input with a click button that exchanges the public challenge for a private proof; submit is blocked until the proof exists.
- Scope: password reset, resend verification, and email-code verification remain out of scope for YUN-105 because they already require email delivery/cooldown checks and are separate sensitive-operation controls from the existing login/register captcha setting.

## Implementation Plan

### Stage 1: Backend captcha contract
- **Files modified**: `backend/app/core/captcha.py`, `backend/app/schemas/captcha.py`, `backend/app/api/v1/endpoints/login.py`, `backend/app/schemas/user.py`
- **Specific logic**: Generate click challenges, verify one-time tokens, keep legacy answer compatibility only at API boundary if needed for minimal breakage, enforce captcha on login and non-first-user register when enabled.
- **Validation**: Unit tests for success, missing token, wrong token, expired/deleted token, and register enforcement.

### Stage 2: Frontend login click interaction
- **Files modified**: `frontend/lib/api/auth.ts`, `frontend/app/(auth)/login/_components/login-form.tsx`, `frontend/i18n/en/auth.json`, `frontend/i18n/zh/auth.json`
- **Specific logic**: Replace typed captcha answer state with click verification state; refresh resets the click; backend captcha errors refresh and show clear retry prompt.
- **Validation**: Type/lint checks and generated i18n types.

### Stage 3: Documentation and regression checks
- **Files modified**: `docs/dev/analysis/backend/01-login.md`, `docs/dev/analysis/frontend/01-auth.md`, `docs/guide/user-guide/authentication/login-register.md`, `docs/guide/user-guide/authentication/login-register_zh-CN.md`
- **Specific logic**: Document trigger scenarios, retry/failure behavior, and risk-control fallback under existing captcha setting.
- **Validation**: Backend focused pytest, ruff checks for touched Python files, frontend lint/build if feasible.

## Testing Strategy
- Happy path: generated click token verifies once and allows login/register paths.
- Error path: missing captcha, wrong token, reused token, expired/deleted captcha all fail with captcha errors.
- Regression scope: login captcha setting, registration first-user bootstrap bypass, normal registration enforcement.

## Risks & Mitigation
- Existing clients may still submit `captcha_answer`; mitigate by accepting it as a deprecated alias for `captcha_token` while frontend migrates.
- Bot resistance remains lightweight because the app only had a simple math captcha; mitigate by keeping server-side one-time tokens, TTL, and existing login lockout/rate controls as fallback risk controls.
- Validation reassessment after three failed attempts: the first two test runs used incorrect invocation paths/environment, and the third exposed a test fake that did not match the async Redis helper contract. Fix the fake to be async, then rerun the focused test command with explicit `PYTHONPATH`.
- Rollback: restore math challenge generation and frontend text input while keeping the same captcha error codes.
