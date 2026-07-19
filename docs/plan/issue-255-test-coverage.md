# Issue #255 Test Coverage Design Document

## Background & Goals
- Problem to solve: the repository has no trustworthy whole-application coverage baseline or CI gate. Backend tests are disabled in CI, frontend tests are not run, and existing ignored reports measure only partial or stale source sets.
- Success criteria:
  - Backend and frontend report coverage independently; no blended percentage hides a weak side.
  - Backend measures all importable code under `backend/app`, including branches.
  - Frontend measures eligible application TypeScript/TSX and rejects files absent from Bun's LCOV report.
  - Both sides reach and enforce at least 95% for their agreed metrics.
  - Critical authentication, authorization, chat, workflow, knowledge, storage, notification, and admin behavior has happy and error-path coverage.
  - Local commands and CI artifacts make reports reproducible and inspectable.

## High-Level Design
- Keep the existing runners: pytest plus `pytest-cov` for backend and Bun's native test coverage for frontend.
- Establish clean baselines before adding tests or enabling the final threshold; existing ignored reports are not acceptance evidence.
- Backend denominator is the complete `app` package. Frontend denominator is eligible tracked `.ts`/`.tsx` under `app`, `components`, `contexts`, `hooks`, and `lib`, checked against LCOV source records.
- Exclude only tests, generated types/declarations, and genuinely non-executable framework/config files. Do not exclude low-coverage application modules.
- Use report-driven, risk-ordered test batches. Activate independent 95% gates only after both suites pass.
- Publish separate CI artifacts without adding an external coverage service.

## Coverage Contract

### Backend
- Metrics: line and branch coverage, each at least 95% at completion.
- Source: all of `backend/app`.
- Reports: terminal missing lines, `backend/coverage.xml`, and `backend/htmlcov/`.
- Canonical command: `uv run pytest` after coverage options are centralized in `backend/pyproject.toml`.

### Frontend
- Metrics: lines, functions, and statements, each at least 95% at completion.
- Source census: eligible `.ts`/`.tsx` under `frontend/app`, `frontend/components`, `frontend/contexts`, `frontend/hooks`, and `frontend/lib` must appear in LCOV.
- Reports: terminal summary and `frontend/coverage/lcov.info`.
- Canonical commands: `bun run test:coverage` and `bun run coverage:check`.

## Implementation Plan

### Stage 1: Design docs and implementation index
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/issue-255-test-coverage.md`
- **Specific logic**: Register issue #255, define honest denominators and metrics, and capture the staged implementation and validation strategy.
- **Validation**: Confirm work occurs on `test/issue-255-coverage-95` and planning docs exist before code changes.

### Stage 2: Backend and frontend coverage baselines
- **Files modified**: `backend/pyproject.toml`, `backend/uv.lock`, `frontend/bunfig.toml`, `frontend/package.json`, `frontend/scripts/check-coverage.ts`
- **Specific logic**: Add `pytest-cov`; configure whole-`app` line/branch reporting; configure Bun text/LCOV reporting; add an LCOV source census so unloaded frontend files cannot disappear from the denominator. Keep final 95% gates inactive until reached.
- **Validation**: Run clean reports, verify expected source roots, intentionally omit a frontend LCOV source to test fail-fast behavior, and record baseline summaries below.

### Stage 3: Backend critical-path coverage
- **Files modified**: Report-selected files under `backend/tests/`, preferring existing modules
- **Specific logic**: Add meaningful happy/error tests in risk order: authentication and permissions; provider/API failures; workflow lifecycle; knowledge/storage/background jobs; notification/admin/persistence behavior; then remaining report-driven gaps.
- **Validation**: Run targeted tests after each batch and the complete backend suite before each incremental commit. Confirm line and branch metrics never regress.

### Stage 4: Frontend critical-path coverage
- **Files modified**: Report-selected colocated frontend tests; test runtime setup only when DOM behavior requires it
- **Specific logic**: Cover pure helpers and API contracts first, then hooks/contexts, then critical auth, chat, workflow, knowledge, permission, notification, and admin component behavior. Avoid snapshot-only and import-only tests.
- **Validation**: Run targeted tests plus coverage/census after each batch. Confirm eligible source representation and all metrics never regress.

### Stage 5: Agent UI automation guide and reusable prompt
- **Files modified**: `docs/guide/testing/agent-ui-automation.md`
- **Specific logic**: Maintain a model-readable feature map alongside frontend functional tests. For each critical UI flow, document its purpose, prerequisites/test data, route, stable visible landmarks, happy/error scenarios, side effects and cleanup, and reusable Agent prompt instructions. Keep selectors semantic and behavior-oriented so the guide is useful across browser automation implementations.
- **Validation**: Cross-check every documented flow against its functional test. Record browser validation separately when a browser test environment is available; do not claim it from source inspection alone.

### Stage 6: CI reporting, final 95% gates, and documentation
- **Files modified**: `.github/workflows/ci.yml`, `backend/pyproject.toml`, `frontend/bunfig.toml`, `docs/dev/README.md`, relevant backend/frontend testing docs, planning docs
- **Specific logic**: Run both suites in CI; upload separate backend XML/HTML and frontend LCOV artifacts with `if: always()`; document exact local commands; activate final independent 95% thresholds; mark plans complete.
- **Validation**: Run the full backend/frontend pre-commit checks, prove a temporary threshold above measured coverage fails, and inspect CI artifact paths.

## Baseline Results
- Backend clean baseline (2026-07-19, commit `f45530d`): 43.22% line coverage (`16,100/37,249`) and 18.95% branch coverage (`2,204/11,630`) over all `app` source; 710 tests passed and 2 were skipped. The existing 99.56% report is invalid because it covers only `app/llm/types`.
- Frontend provisional baseline (2026-07-19): Bun's loaded-file report is 75.77% lines and 94.44% functions across only three loaded source files; the census reports 467 eligible application files absent from LCOV. The loaded-file percentage is therefore not acceptance evidence.
- Backend progress checkpoint (2026-07-19, commits through `0ac5be62`): 1,346 tests passed and 2 were skipped; whole-app combined coverage remains 49% (`37,272` statements, `17,026` missed; `11,640` branches, `1,107` partial) after workflow, knowledge-task, usage-reset, and audit-archive batches. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-19, commits through `7d261e45`): 402 isolated tests passed; Bun reports 82.90% lines and 80.79% functions after adding auth-route, API-key, AI-element, and UI-primitive behavior coverage. The source census still reports 329 eligible application files absent from LCOV. The final independent 95% metrics and zero-absent-source gate remain inactive.
- Backend progress checkpoint (2026-07-19, commits through `c6679e85`): 1,374 tests passed and 2 were skipped; whole-app combined coverage remains 49% (`37,272` statements, `16,932` missed; `11,640` branches, `1,109` partial) after chat access, workflow-plan, vector-store, knowledge-task, and notification-task batches. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-19, commits through `b73918d5`): 417 isolated tests passed; Bun reports 86.05% lines and 84.25% functions after adding message-part and sub-workflow-node behavior coverage. The source census remains failing; the final independent 95% metrics and zero-absent-source gate remain inactive.
- Backend baseline collection issues previously observed in stale worktrees have been resolved on the branch: the complete current suite is the source of truth.
- Backend progress checkpoint (2026-07-19, commits through `ef4cd5ef`): 1,405 tests passed and 2 were skipped; whole-app combined coverage remains 49% (`37,272` statements, `16,822` missed; `11,640` branches, `1,120` partial) after team-model access, upload-storage, workflow-cancellation, and TOTP/error-message batches. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-19, commits through `ef4cd5ef`): 438 isolated tests passed; Bun reports 86.25% lines and 84.66% functions after package API, time-range selector, and change-password behavior coverage. The source census reports 324 eligible application files absent from LCOV. The final independent 95% metrics and zero-absent-source gate remain inactive.
- Backend progress checkpoint (2026-07-20, commits through `c3b6f5e6`): 1,445 tests passed and 2 were skipped; whole-app combined coverage is 50% (`37,272` statements, `16,528` missed; `11,640` branches, `1,159` partial). The usage-quota tests now freeze their reset date so the suite remains deterministic across calendar changes. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `c3b6f5e6`): 453 isolated tests passed; Bun reports 86.49% lines and 84.84% functions after conversation, language-toggle, and simple primitive behavior coverage. The source census reports 313 eligible application files absent from LCOV. The final independent 95% metrics and zero-absent-source gate remain inactive.
- Backend progress checkpoint (2026-07-20, commits through `7bb5aef9`): 1,535 tests passed and 2 were skipped; whole-app combined coverage is 51% (`37,272` statements, `16,087` missed; `11,640` branches, `1,188` partial) after chat endpoints, vector cleanup, admin TOTP, token-counter, LLM-error, and application-boundary batches. The final independent 95% line and branch gates remain inactive.
- Backend progress checkpoint (2026-07-20, commit `0d5bdae5`): 1,773 tests passed and 2 were skipped; whole-app combined coverage is 53% (`37,272` statements, `15,432` missed; `11,640` branches, `1,215` partial). Pytest now uses importlib mode, preventing duplicate test basenames in separate directories from aborting collection. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-20, commit `b3b60854`): 530 isolated tests passed; Bun reports 85.66% lines and 82.74% functions. The source census reports 270 eligible application files absent from LCOV. The final independent 95% metrics and zero-absent-source gate remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `39a07abc`): 536 isolated tests passed; Bun reports 85.71% lines and 82.84% functions after tool-element and permission-guard behavior coverage. The source census still reports 270 eligible application files absent from LCOV. The final independent 95% metrics and zero-absent-source gate remain inactive.
- Frontend build checkpoint (2026-07-20, commit `192babe0`): `bun run build` passes after excluding the standalone Bun-only coverage script from Next.js application typechecking; the script remains run directly by `bun run coverage:check`.
- Backend progress checkpoint (2026-07-20, commits through `7d7903cd`): 1,781 tests passed and 2 were skipped; whole-app combined coverage is 53% (`37,272` statements, `15,403` missed; `11,640` branches, `1,214` partial) after tool-service error coverage. The final independent 95% line and branch gates remain inactive.
- Backend progress checkpoint (2026-07-20, commits through `e19458e5`): 1,784 tests passed and 2 were skipped; whole-app combined coverage is 53% (`37,272` statements, `15,392` missed; `11,640` branches, `1,213` partial) after workflow-orchestrator and event-loop fallback coverage. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `d813b0a4`): 542 isolated tests passed; dashboard workflow-status, agent-performance, and team-token charts now cover loading, empty, and populated data states. The source census remains intentionally failing because eligible sources are still absent from LCOV; final independent 95% metrics and zero-absent-source gate remain inactive.
- Backend progress checkpoint (2026-07-20, commits through `b265caa4`): 1,789 tests passed and 2 were skipped; whole-app combined coverage is 53% (`37,272` statements, `15,389` missed; `11,640` branches, `1,213` partial) after knowledge-base task guard coverage. The final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `210b3e7c`): 547 isolated tests passed before the latest source-content batch; role deletion, top-agent filtering, and source-content data-boundary behavior are covered. The source census remains failing because eligible sources are still absent from LCOV; final independent 95% metrics and zero-absent-source gate remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `c9813ea4`): 576 isolated tests passed with 2,588 assertions; Bun reports 86.64% lines and 84.10% functions. The source census reports 266 eligible application files absent from LCOV. Dashboard workflow-trigger states and tooltips, debounce timing, and API/schema coverage batches are included; final independent 95% metrics and the zero-absent-source gate remain inactive.
- Backend progress checkpoint (2026-07-20, commits through `9eef9f77`): 1,831 tests passed and 2 were skipped; whole-app combined coverage is 54%. The audit-decorator success and failure paths are covered; final independent 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-20, commits through `935eef86`): 585 isolated tests passed with 2,618 assertions. Permission-guard single, OR, require-all, fallback, and loading paths are covered. The source census and final independent 95% metrics remain inactive because eligible sources are still absent from LCOV.
- Backend focused checkpoint (2026-07-20, commit `41e0b0f0`): 16 Volcengine audio-generation tests passed. Payload precedence, validation, reference conversion, and provider response/error paths are covered; the final whole-app 95% line and branch gates remain inactive.
- Frontend focused checkpoint (2026-07-20): the active branch's broader validation-helper suite has 11 passing tests and 27 assertions, with `lib/validation.ts` at 100% line/function coverage. The final source census and 95% frontend metrics remain inactive.

## Testing Strategy
- Happy path tests:
  - Successful authentication/authorization, API/service operations, workflow execution, chat completion, knowledge upload/search, and frontend state/UI transitions.
  - Coverage commands produce terminal and machine-readable reports for the complete agreed source sets.
- Error path tests:
  - Invalid credentials/input, permission and tenant denial, provider/storage/task failures, workflow validation/retry/cancellation, request rejection, frontend recovery/cleanup, missing LCOV source files, and unmet thresholds.
- Regression scope:
  - Existing backend pytest suite, ruff, formatting, and mypy.
  - Existing frontend Bun tests, lint, build, and generated i18n type policy.
  - CI license and existing quality checks remain unchanged.

## Risks & Mitigation
- Risk: an honest 95% target across hundreds of modules creates a large review. Mitigation: use small risk-ordered commits and split review only if branch size becomes unmanageable; tooling alone does not complete the issue.
- Risk: Bun reports only loaded files. Mitigation: enforce a tracked-source-to-LCOV census instead of broad exclusions or mass imports.
- Risk: tests inflate numbers without confidence. Mitigation: require behavioral assertions and critical happy/error paths; reject import-only, snapshot-only, and assertion-free additions.
- Risk: enabling 95% immediately makes CI permanently red. Mitigation: collect the baseline first and use only a documented non-decreasing transitional ratchet; final acceptance still requires 95%.
- Rollback plan: remove the coverage configuration and CI steps while retaining valid behavioral tests. Generated reports are ignored and require no repository cleanup.
