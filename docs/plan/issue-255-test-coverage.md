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
- Backend progress checkpoint (2026-07-19, commit `0ae76cf3`): 797 tests passed and 2 were skipped; whole-app coverage remains 39% after additional condition and code executor behavior tests. The final 95% line and branch gates remain inactive.
- Frontend progress checkpoint (2026-07-19, commit `36ec4a2a`): 77 tests passed; Bun's loaded-module report is 42.56% lines and 27.48% functions after additional agent/workflow API and workflow type-spec tests. The census still fails because eligible sources are absent from LCOV, so neither loaded-module percentages nor the coverage target have passed.
- Baseline blockers found on 2026-07-19: stale workflow tests import renamed/removed APIs (`ExecutionNode`, `CircuitState`, and obsolete decorator signatures), and other existing failures span sandbox/workflow behavior. These must be aligned with current behavior before the backend baseline is valid.

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
