# Tool Runtime Coverage Design Document

## Background & Goals

Pre-push backend tests reported 19 failures and coverage of 94.64% lines and 90.78% branches, below the independent 95% gates. Restore passing behavioral tests and cover real security and execution boundaries without lowering thresholds or bypassing hooks.

## High-Level Design

Investigate failures against the current runtime contract. Cover tool connection authorization, OAuth, approvals, migrations and chat execution using deterministic, isolated scenarios. Preserve fail-closed security and avoid incidental implementation assertions. Run full gates and push only after they pass.

## Implementation Plan

### Stage 1: Failure diagnosis
- **Files modified**: Relevant failing backend tests and implementation, as evidence requires.
- **Specific logic**: Check approval policy enforcement, caller identity, legacy migration expectations and inactive user preflight against current contracts.
- **Validation**: Run affected scenarios and confirm security-sensitive denial and approval behavior.

### Stage 2: Meaningful coverage
- **Files modified**: Backend test modules covering tool connections, OAuth, approvals, execution and other uncovered runtime boundaries.
- **Specific logic**: Exercise accessible and forbidden identities, status transitions, invalid credentials and provider failures; use existing fixtures and real business logic where practical.
- **Validation**: Focused tests, then independent line and branch coverage reports at 95% or more.

Latest full backend run: 10,588 passed, 4 skipped; line coverage 96.76%, branch coverage 95.13%. Both independent 95% backend coverage gates pass.

### Stage 3: Full gates and delivery
- **Files modified**: Applicable test fixes and documentation as needed.
- **Specific logic**: Run complete pre-push checks and correct any additional regressions; commit logical changes and push the branch.
- **Validation**: Full backend and frontend checks pass without skipping hooks.

## Testing Strategy

Cover successful and rejected authorizations, approval precedence and changed policies, identity isolation, expired and missing connections, and existing chat/workflow paths. Isolate external dependencies and ensure tests assert consumer-visible behavior.

## Risks & Mitigation

Stale tests can encode removed semantics; compare with current contracts before modifying. A passing test must not reduce access checks or assert mocks instead of behavior. Rollback by reverting the relevant focused commits; do not bypass coverage gates.
