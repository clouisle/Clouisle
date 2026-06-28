# YUN-105 Click Captcha Hardening Design Document

## Background & Goals
- The existing click captcha only validates a static choice and can be scripted easily.
- Harden it enough to block common bots without adding a third-party captcha provider or new dependencies.
- Keep login/register illegal unless the backend can mint a one-time captcha proof.

Success criteria:
- Users complete a Cloudflare-like single click check.
- Backend validates the click target and plausible pointer trajectory before issuing a proof.
- Missing, too-fast, static, wrong, expired, or reused captcha data fails.
- Login/register continue to require the one-time proof when captcha is enabled.

## High-Level Design
- `GET /captcha` keeps returning public single-click metadata and stores the private expected click target in Redis.
- Login/register forms render one click check control and collect small pointer traces during the interaction.
- `POST /captcha/click` receives the click target, elapsed time, and pointer samples.
- Backend scores the pointer trace with simple local heuristics and mints the existing one-time proof only when the target and trace are valid.
- `verify_captcha()` remains the final login/register gate and consumes proofs once.

## Implementation Plan

### Stage 1: Planning docs
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-105-click-captcha-hardening.md`
- **Specific logic**: Add the hardening entry and document single click detection, pointer traces, backend heuristic scoring, and no new dependencies.
- **Validation**: Confirm the plan keeps the existing one-time proof flow and explicitly excludes third-party captcha providers.

### Stage 2: Backend payload and scoring
- **Files modified**: `backend/app/schemas/captcha.py`, `backend/app/core/captcha.py`, `backend/app/api/v1/endpoints/login.py`
- **Specific logic**: Add pointer point schema, accept pointer samples in click requests, validate a tolerant trajectory before consuming Redis challenge state, and pass pointer data from the endpoint into proof creation.
- **Validation**: Focused tests for valid pointer, missing pointer, too-fast pointer, static pointer, wrong choice, expired challenge, and one-time proof reuse.

### Stage 3: Frontend click interaction
- **Files modified**: `frontend/lib/api/auth.ts`, `frontend/app/(auth)/login/_components/login-form.tsx`, `frontend/app/(auth)/register/_components/register-form.tsx`
- **Specific logic**: Render one click-check control, send the backend-provided target, collect capped button-relative pointer samples, and reset trace/token on refresh or failure. The frontend only collects evidence; backend proof minting is the validation.
- **Validation**: Login/register submit remains blocked when captcha is enabled and no proof exists; failed proof refreshes captcha and shows the existing error.

### Stage 4: Validation
- **Files modified**: `backend/tests/api/test_click_captcha.py`
- **Specific logic**: Update existing tests to include pointer data and add negative coverage for suspicious trajectories.
- **Validation**: Run focused backend tests, ruff checks for touched backend files, frontend lint, and `git diff --check`.

## Testing Strategy
- Happy path: valid click target plus plausible pointer trace returns a proof that verifies once.
- Error path: missing pointer, too-fast elapsed time, identical/static samples, wrong option, expired challenge, missing proof, invalid proof, and proof reuse fail.
- Regression scope: login captcha setting, registration captcha enforcement, first-user registration bypass, existing captcha error codes.

## Risks & Mitigation
- Some real users may move unusually quickly or use keyboard activation.
  - Mitigation: keep thresholds tolerant; failed backend proof refreshes the check for retry.
- A determined bot can still synthesize pointer traces.
  - Mitigation: scope this as lightweight bot friction; add rate limiting or a managed captcha later if abuse continues.
- Login/register duplicated captcha UI can drift.
  - Mitigation: keep this pass surgical; extract a shared component only after behavior stabilizes.

Rollback plan:
- Revert pointer validation and frontend option rendering while keeping the previous Redis one-time proof contract.
