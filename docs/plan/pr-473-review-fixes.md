# PR #473 Review Fixes Design Document

## Background & Goals

PR #473 (`feature/notification-integrations-factory`, HEAD `bda9912bac2ba3bcc84111bcff3cb1a88fe21d15`, base `main` at `4f7328387bda54400ff5e967b83d1b4189f84076`) received a maximum-effort review with 13 confirmed correctness findings and two plausible candidates. This work fixes the confirmed regressions with focused regression coverage, and gathers evidence before deciding whether either candidate needs a code change.

Success criteria:
- Fix confirmed findings #1–#13 without broad refactors or new dependencies.
- Add targeted tests that reproduce each reported failure and preserve relevant negative/security boundaries.
- Decide #14 and #15 from reliable provider/base-vs-head evidence, not assumptions or self-fulfilling mocks.
- Preserve the existing backend/frontend CI coverage gates and report the exact verification results.

## High-Level Design

Changes are divided into five non-overlapping ownership groups:

- **A — Feishu callback/runtime:** SDK-compatible callback decryption; atomic receipt/outbox finalization; investigate department-root scope candidate.
- **B — Integration and notification compatibility:** legacy settings migration, history-only notification enum compatibility, explicit webhook-header clearing across backend and frontend, and send-time capability checks.
- **C — Agent runtime and public contract:** scoped workflow image materialization, AUTO-RAG current-message propagation, public Agent variables, and offline HTML candidate comparison.
- **D — Model contract/editor state:** preserve `default_params` on updates and hydrate function-call capability while editing.
- **E — Frontend request/form state:** make notification/document pagination locks generation-safe and protect WeChat form drafts from polling updates.

All changes reuse existing helpers and fixtures. External sends stay outside transactions; private assets remain authorization-scoped; old notification channel values are readable without re-enabling their senders. The two candidates remain unchanged unless their evidence meets the criteria below.

## Implementation Plan

### Stage 1: Register scope and assign isolated file ownership
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, this document.
- **Specific logic**: Add an in-progress index entry for this remediation. Keep these documents under the main agent's ownership. Implementers may only edit their assigned production and test files; coordinate any shared fixture before changing it.
- **Validation**: Confirm the initial branch/HEAD and clean worktree; inspect the final diff for ownership overlap.

### Stage 2: Feishu callback and durable delivery finalization (#1, #4; investigate #14)
- **Files modified**: `backend/app/api/v1/endpoints/feishu_agent.py`, `backend/app/services/feishu_agent_runtime.py`, and their callback/runtime tests. Modify `backend/app/api/v1/admin/endpoints/feishu.py` and its tests only if #14 is confirmed.
- **Specific logic**:
  - Use installed `lark_oapi.core.utils.decryptor.AESCipher` semantics for encrypted callback payloads; retain existing request-size, timestamp, signature, token, and event `header.app_id` checks. Correct the callback test encrypt helper so it does not encode the incorrect old protocol.
  - Follow `wechat_agent_runtime._finalize_receipt` / `_finalize_receipt_output`: atomically persist the Feishu receipt terminal state, all delivery rows, and active-run state. Keep external sends outside the transaction and preserve conditional claims/idempotency.
  - For #14, first establish the provider's `find_by_department` root `0` semantics. An existing mock asserting `['0', 'dept-a']` does not establish provider scope. If evidence proves leakage, separate company/ancestor team display from user-query scope without losing legitimate hierarchy behavior.
- **Validation**: SDK-format encrypted challenge/event success plus malformed ciphertext, invalid signature/token/app ID rejection; inject failure on a later delivery insert and verify complete rollback and successful idempotent recovery; if investigating #14, use root/direct/A/B and root-denied/A-allowed evidence, and record limitations without a live external call.

### Stage 3: Migration, historical channels, webhook settings, and queued sends (#5–#7, #10)
- **Files modified**: `backend/app/core/integration_migration.py`, `backend/app/models/notification.py`, `backend/app/schemas/notification.py`, `backend/app/api/v1/admin/endpoints/integration_settings.py`, necessary notification tests/tasks, `frontend/app/(dashboard)/site-settings/integrations/_components/webhook-settings.tsx`, and its behavior test.
- **Specific logic**:
  - Migrate the actual legacy plaintext `feishu_app_secret` using `encrypt_secret`, preserve encrypted-key compatibility and defined precedence, and do not overwrite existing administrator-edited credentials. Stop short of guessing when current data cannot distinguish an old migration artifact from an intentional empty value.
  - Restore `dingtalk`, `wechat`, and `slack` as persisted/history-readable enum values only; keep creation and send paths rejecting unsupported channels.
  - Use Pydantic's existing `exclude_unset` distinction: omitted webhook headers preserve the secret; explicit `{}` is stored as non-empty encrypted string `"{}"`. Because GET masks stored headers as `{}`, the frontend must omit the field until headers are edited; explicit `{}` or cleared text after editing submits the clear operation. Do not alter generic blank-secret preservation.
  - Revalidate integration enabled state and `NOTIFICATION` capability at actual Feishu send time using `active_features`; reject via the established task failure path before constructing the client, rather than returning false and reporting success.
- **Validation**: memory-DB migration cases for true legacy key, encrypted-only/both-key precedence, rerun, existing edits, and rollback; ORM round-trip of historical channel values while send remains rejected; webhook omitted-vs-empty behavior and no secret disclosure; queued-then-disabled/capability-removed tasks make no provider call and are not marked successful.

### Stage 4: Agent images, AUTO-RAG context, public variables, and HTML candidate (#2, #3, #8; investigate #15)
- **Files modified**: `backend/app/services/agent.py`, `backend/app/services/agent_loop.py`, `backend/app/schemas/agent.py`, `backend/app/api/v1/endpoints/chat.py`; modify `backend/app/llm/tools/builtin/file_parser.py` only if #15 is confirmed.
- **Specific logic**:
  - In shared Agent message preparation, after scoped binding and before provider serialization, use `asset_view.resolve_view_content` with the real workflow scope, user, model config, and input capabilities. Keep durable refs intact and pass only ephemeral native content to the provider; do not expose private upload URLs or weaken adapter guards.
  - Forward `current_user_message_id` through `AgentLoop._context_kwargs` to the existing context builder, which already substitutes enriched content for the corresponding current DB row.
  - Add `variables: list[dict[str, Any]]` with an empty-list default to `AgentPublicOut` and pass `agent.variables or []` from the public endpoint; preserve file configuration and other raw definition metadata.
  - For #15, compare the same extensionless HTML fixture through base `.bin` and HEAD `.txt` extraction without mocking MarkItDown. The lockfile also changes MarkItDown from 0.1.6 to 0.1.8; separate suffix and dependency effects where locally possible, do not install or change dependencies. Change MIME dispatch only if the comparison demonstrates a regression.
- **Validation**: real scoped storage fixture through chat/stream and OpenAI/Gemini converters; unauthorized/text-only/oversize/checksum negative cases; real DB-backed context builder receives enriched current text exactly once; public response serialization preserves variables and does not expose private fields; candidate HTML comparison includes `.html`, XHTML, plain text, and script/style sentinels.

### Stage 5: Model update contract and capability hydration (#9, #13)
- **Files modified**: `backend/app/schemas/model.py`, focused model schema/endpoint tests, `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, and its real-effects regression test.
- **Specific logic**: Add `default_params: Optional[dict[str, Any]] = None` to `ModelUpdate`; the existing endpoint already uses `model_dump(exclude_unset=True)`. In edit-form reset/hydration, initialize `supportsFunctionCall` from `caps.function_call`, preserving existing save behavior and unknown capabilities.
- **Validation**: endpoint persistence for omitted/null/empty/nested JSON and invalid non-object input; real React effects test confirms an existing `function_call: true` remains set after an unrelated edit and model switches/reopen/create reset state correctly.

### Stage 6: Generation-safe pagination and WeChat draft preservation (#11, #12)
- **Files modified**: platform notifications `notifications-client.tsx`, platform knowledge-base `documents-table.tsx`, `frontend/components/wechat-knowledge.tsx`, and focused component tests.
- **Specific logic**: Keep request sequence checks and `useInfiniteScroll`; ensure the in-flight count belongs only to the active generation. A first-page or force-refresh request taking over a new sequence resets its count, and only the current sequence's `finally` may release its lock/loading state. Keep same-generation append/refresh exclusion. Initialize WeChat draft state once per form session/selected agent identity, not whenever polling supplies a new object reference; retain the existing key-based reset on binding/form reopen.
- **Validation**: with real component/hook/observer, keep request A pending, switch to B, resolve B's first page, then trigger observer true without an intervening false and assert B page 2 loads. Resolve/reject A while B page 2 is pending and verify A cannot change B state or unlock B. Verify WeChat variables/STT and validation draft survive same-agent polling, while agent/binding/form-session changes initialize correctly.

### Stage 7: Integrated verification and disposition report
- **Files modified**: this document and `docs/IMPLEMENTATION_PLAN.md`; behavior-specific docs only if required by confirmed changes.
- **Specific logic**: Integrate group results, audit shared contracts, report the disposition of all 15 review items and actual test outcomes. Mark an item fixed only after its regression and relevant negative cases pass. The initial remediation was kept uncommitted; the user subsequently requested a remote push. Commit/push only for that explicit delivery request; do not post PR comments.
- **Validation**: Backend `ruff check .`, `ruff format --check .`, full `uv run pytest`, and independent `scripts/check_coverage.py` line/branch gate (both at least 95%). Frontend lint, `test:coverage`, `coverage:check`, and build (function/line at least 95%). Run i18n checks only if visible text changes. Finish with `git diff --check` and scope/status review.

## Testing Strategy

- Happy path coverage: valid Feishu SDK callback and final delivery, scoped workflow image serialization, enriched AUTO-RAG context, public variable projection, model parameter updates, functional notification pagination, polling-safe WeChat form edits.
- Negative/fault coverage: invalid callback authentication/ciphertext, scope/capability/storage boundaries, outbox insert rollback and recovery, ambiguous migration provenance, legacy channel send rejection, webhook omission vs explicit clear, queued send after disablement, stale requests/finalizers, and model switching.
- Regression scope: existing Feishu callback/runtime/admin tests; integration migration, notification ORM/factory/task/webhook tests; Agent runtime/context/schema/file-parser tests; model schema/API/dialog tests; both real infinite-scroll suites and WeChat form tests.
- Targeted backend tests use `uv run pytest -o addopts='' --import-mode=importlib <paths>` to avoid shared coverage output. Targeted frontend tests use isolated `bun test --isolate --coverage-dir /private/tmp/pr473-<group>-coverage <paths>` so parallel groups do not overwrite reports. Tests use local fixtures/mocks; no app services, browsers, real Feishu calls, or model calls are started. The user explicitly allowed the full pytest suite's temporary in-process localhost/Unix-socket test listeners (closed by fixture teardown); this permission does not extend to application servers or persistent services.

## Delivery Scope and Remaining Limitations

- All 13 original confirmed items have focused regression coverage, and candidate #14 was confirmed against official provider semantics and fixed. Candidate #15 remains unconfirmed; no parser change was made.
- The migration fix handles a fresh upgrade and idempotent reruns. It deliberately does not guess how to repair an already-migrated empty/disabled Feishu Integration without provenance.
- Local SDK/ORM/storage/React fixtures validate the changes; no live Feishu/model-provider deployment smoke test, application server, or browser session was run. Temporary listeners were only those owned and closed by authorized tests.
- The new workflow-image regression covers valid PNG and auth/capability/converter boundaries, not every planned JPEG/oversize/checksum combination. Existing shared boundary tests remain in full regression scope. The WeChat regression uses fresh same-binding objects through the real refresh path; it is not a live five-second polling/browser exercise.
- No dependencies, coverage thresholds/exclusions, or lockfiles were changed. No PR comment was made. After verification, the user explicitly requested a remote push; delivery uses grouped commits and the existing hooks without force or bypass.

## Risks & Mitigation

- **Credential migration ambiguity**: do not overwrite administrator intent when provenance is unknowable; record the edge as blocked and request a separate migration decision.
- **Receipt durability**: `completed` means the complete delivery intent is durable, not that a provider send succeeded. Preserve the delivery outbox's own retry semantics; do not put network sends/long asset downloads inside a database transaction.
- **Private asset handling**: keep workflow scope authorization, MIME/capability checks, bounded reads, and unresolved-ref adapter guards; never substitute public URLs.
- **Historic enum values**: preserve read compatibility only; keep new sends blocked by the actual integration registry/capability gates.
- **Candidate confidence**: root department mock behavior is not provider evidence; HTML extension behavior alone is not proof of a base regression, especially with a simultaneous MarkItDown version change.
- **Concurrency/ownership**: A–E own distinct code/test areas; main agent alone edits implementation docs. Coordinate before touching shared test helpers.
- **Stop condition**: after three failed implementation/verification attempts on one item, stop and document the blocker rather than weakening gates or broadening scope.

Rollback is limited to reverting the isolated code changes per group. Do not perform destructive database cleanup; any migration compatibility addition must remain safe when the application code is rolled back.

## Review Item Disposition

| # | Status | Evidence/next step |
|---|---|---|
| 1 | Fixed — focused validation passed | Real SDK dispatcher challenge/event roundtrips reproduced 200-vs-endpoint-403 before correction; direct-JSON AES plaintext now works. 134 callback/runtime tests pass; inner binary envelope explicitly rejected. |
| 2 | Fixed — focused validation passed | Scoped storage produces ephemeral native image data via existing helper; chat/stream OpenAI and Gemini conversions preserve valid PNG bytes and durable binding. Unauthorized/text-only/unresolved-ref negatives pass. |
| 3 | Fixed — focused validation passed | Real DB/context builder substitutes enriched current text once; stored raw message unchanged. |
| 4 | Fixed — focused validation passed | Submitted-state claim, complete outbox, and active-run clearing share a transaction; injected second insert failure rolls back and recovery succeeds. Corrected callback/runtime suite: 134 passed. |
| 5 | Fixed — focused validation passed | Actual legacy plaintext secret is encrypted once; encrypted precedence/rerun and existing administrator configuration tested. Already-migrated ambiguous state is not overwritten. |
| 6 | Fixed — integrated focused validation passed | Historical enum/output remains readable; creation schema explicitly accepts only EMAIL/WEBHOOK/FEISHU. Existing unsupported-creation assertions unchanged. 83 related schema/API/factory/task tests passed. |
| 7 | Fixed — focused validation passed | Explicit empty headers serialized by API; untouched masked headers omitted by UI. Main corrected controlled-parent harness: all 11 webhook tests pass, including accumulated edits and clearing. |
| 8 | Fixed — focused validation passed | Public schema and endpoint retain raw variable definitions/fileConfig without private configuration; independent default lists tested. C group: 70 passed. |
| 9 | Fixed — focused validation passed | Restored schema field; 57 model schema/API tests passed, including omitted/null/empty/nested persistence. |
| 10 | Fixed — focused validation passed | Task reloads current integration and rejects disabled/removed notification capability before constructing provider client; existing task exception path remains responsible for failure/retry. |
| 11 | Fixed — focused validation passed | Both real-hook observer regressions pass with A pending/B append, stale finalization, and retry coverage. |
| 12 | Fixed — focused validation passed | Same-agent binding refresh preserves initialized draft; identity switching resets. Three frontend suites total 28 passed. |
| 13 | Fixed — focused validation passed | Missing edit setter restored; 12 real-effects tests pass after correcting the test locator/create-mode setup. |
| 14 | Fixed — focused validation passed | Official direct-member/root permission semantics; user scope excludes implicit root while company team remains. Real-client MockTransport regressions cover root-direct leakage and root-denied/A-allowed. 51 related tests passed. |
| 15 | Unconfirmed — no production change | With installed MarkItDown 0.1.8, the same HTML fixture is cleaned through `.bin/.html/.xhtml`, while the current `.txt` path retains raw HTML/script/style. This confirms suffix behavior but not the exact base (0.1.6)-to-head regression; no dependency install/switch was performed. |

## Final Verification (2026-10-25)

All required gates passed on the final source state; thresholds, exclusions, lockfiles, and dependencies were unchanged.

| Gate | Result |
|---|---|
| Backend full `uv run --no-sync --directory backend pytest` | **9,593 passed, 4 skipped, 6 warnings**; 9,597 collected; 136.24 seconds |
| Backend independent coverage gate | **Line 96.71%, branch 95.14%**, both at least 95% |
| Backend `ruff check .` | Passed |
| Backend `ruff format --check .` | Passed; 1,160 files already formatted |
| Frontend `bun run --cwd frontend lint` | Passed; 0 errors, 12 existing unused-variable warnings |
| Frontend `bun run --cwd frontend test:coverage` | **2,960 passed, 0 failed** across 552 files |
| Frontend coverage | **Function 95.66%, line 97.90%**, both at least 95% |
| Frontend `coverage:check` | All **527** eligible tracked source files present in LCOV |
| Frontend `build` | Production compilation, TypeScript, and static generation passed |
| `git diff --check` | Passed |

The first backend full run's three notification creation failures were fixed at the input type boundary; the second full run above is the final result. The four skips correspond to existing platform/opt-in/branch-dependent tests: Linux-only capability semantics, two explicitly opt-in real sandbox package-installation tests, and a benchmark-wrapper test when its endpoints are absent. Full logs were captured locally under `/private/tmp/pr473-backend-full-final.log`, `/private/tmp/pr473-frontend-coverage.log`, `/private/tmp/pr473-frontend-lint.log`, and `/private/tmp/pr473-frontend-build.log`. Optional `mypy app/` and live-provider/browser smoke tests were not run. At initial remediation completion, no commit, push, or PR comment had been made; the user then explicitly requested a remote push.

### Remote delivery preparation

- Split the changes into Feishu, notification/integration, Agent, model, frontend state, and documentation commits, all referencing PR #473.
- Pre-commit rejected the frontend-state group because the touched WeChat test contained three pre-existing unused-parameter warnings. Replaced the two mock implementation parameter declarations with explicit generic function types, preserving their call signatures and runtime behavior. No hook/rule was disabled. Scoped zero-warning ESLint and all **23 WeChat tests** then passed; the normal pre-commit lint and i18n checks also passed.
- Repeated production build after that test-only type adjustment: passed (`/private/tmp/pr473-push-build.log`). The push uses the existing pre-push full-test/coverage hook and a normal fast-forward update to `origin/feature/notification-integrations-factory`, never force push.

## Validation Evidence

### Candidate #14 provider evidence

On 2026-10-25, the official [Feishu `find_by_department` documentation](https://open.feishu.cn/document/server-docs/contact-v3/user/find_by_department) was fetched read-only. It describes the result as “指定部门直属的用户信息列表”, states “根部门的部门 ID 为 0”, and states that app-identity queries against root check for all-staff directory permission. Therefore a non-root-only scope querying `0` can include root-direct employees outside that scope and demand unnecessary root permission. This confirms the candidate without assuming the endpoint recursively returns the entire organization. The main agent implemented the bounded fix: retain company/ancestor team metadata, but query root users only when root was explicitly selected.

### Implementation and test evidence

- **#14 — fixed, focused validation passed:** Added a real `FeishuClient.list_users`/`httpx.MockTransport` regression parameterized for root access allowed/denied. Before the fix, all three scoped tests failed: root IDs leaked into the query and root-denied requests failed. The production change only excludes the synthetic company root from derived user-department IDs; an explicitly selected root still uses the existing explicit branch, and the team hierarchy retains the company node.
  - `uv run --no-sync --directory backend pytest -o addopts='' --import-mode=importlib --no-cov -p no:cacheprovider tests/api/test_admin_feishu.py tests/admin/test_admin_feishu_endpoints.py tests/services/test_feishu_client.py` — **51 passed**.
  - Scoped `ruff check` passed. Initial format check requested a single response-constructor line wrap in the new test; corrected it with a local edit. Repeated scoped `ruff format --check` passed (2 files), and `git diff --check` passed.
- **Main-agent integrated focused checks:** the eight migration/notification/webhook suites passed **169 tests** after the local formatting/import corrections. The callback/runtime/admin-Feishu/client/model schema/API group passed **242 tests**, with two upstream SDK deprecation warnings. The latter run includes the corrected real SDK callback framing.

Other implementation groups are being integrated. Record focused and full validation evidence here only after commands actually run on the resulting branch. Keep failures, skipped checks, and unresolved candidate evidence explicit.

- **#7 frontend — fixed after controlled-parent reassessment:** all **11 webhook behavior tests passed** (44 assertions), including untouched masked headers omission, explicit clear, cumulative URL/method/secret/header edits, validation failures, and read-only controls. No second production copy of parsed header state remains.
- **#11/#12 frontend — focused validation passed:** notifications real-hook, documents real-hook, and WeChat component suites passed **28 tests** (146 assertions). These cover the specified A/B request interleaving, stale completion, append retry, same-agent fresh binding-object draft preservation, and selected-agent reset.
- **Frontend lint — passed:** `bun run --cwd frontend lint` returned 0 with 12 existing unused-variable warnings; new warnings introduced by the new notification tests were removed. Full `bun run --cwd frontend test:coverage`, `coverage:check`, and `build` also returned 0. All **527** eligible tracked source files appear in LCOV; **2,960 tests passed, zero failed**, function coverage **95.66%**, line coverage **97.90%** (both unchanged minimum 95%). Production compilation, TypeScript, and static page generation completed.
- **Backend static checkpoint:** `ruff check .` passed; `ruff format --check .` identified three local line wraps in newly added tests, corrected surgically. Final static checks will be repeated after all implementation agents finish.

### Callback integration audit (#1)

The first A-group run passed 120 callback/runtime tests but used an insufficient fixture: it changed AES key/IV handling while retaining the incorrect inner `random16 || length || JSON || app_id` framing. Integration diff review detected this mismatch. Installed `lark_oapi.event.dispatcher_handler` decrypts via `AESCipher.decrypt_str` and immediately JSON-unmarshals that plaintext. A was resumed to remove inner framing and validate the same fixture through the real SDK event dispatcher, retaining timestamp/signature/token/event app-ID checks. The first green run is **not** completion evidence for #1.

The corrected test first reproduced SDK dispatcher 200 versus local endpoint 403 for both challenge and event, then passed after direct-JSON parsing replaced the incorrect frame. Final A command: `uv run --no-sync --directory backend pytest -o addopts='' --import-mode=importlib --no-cov -p no:cacheprovider tests/api/test_feishu_agent_callback.py tests/services/test_feishu_agent_runtime.py` — **134 passed**, two upstream SDK deprecation warnings. Scoped lint, formatting, and diff checks passed. This supersedes the earlier callback evidence; #4 transaction tests remain included.

### Integration group checkpoint and stop/reassessment (#5, #6, #7, #10)

- Group B reports **167 backend tests passed**. Frontend webhook behavior tests reached the three-failure limit and stopped before further attempts.
- Remaining frontend failures concern controlled-prop test lifecycle (calling `onSettingsChange` without rerendering the updated settings before save) and an unchanged `toMatchObject(disabledSettings)` assertion that still expects the deliberately omitted masked `webhook_headers` key.
- Reassessment: preserve the intended omission-vs-explicit-empty production contract. Use a controlled settings wrapper/explicit rerender for edited-value tests, and assert untouched headers are absent rather than equal to the masked object. Do not loosen secret-clearing assertions or change the generic updater. After this documented reassessment, B may make that bounded test-harness correction and rerun once.
- That bounded rerun finished with **169 backend tests passed, 9 frontend tests passed, 2 frontend tests failed**. Main-agent inspection found the test helper still never applied `onSettingsChange`, and URL/method interactions had been removed despite their changed-value assertions. Main corrected the helper to use an actual stateful parent, restored those interactions, and asserted the accumulated URL/secret/header payload without mutating initial props. Removed redundant production `headersValue` state (controlled props already hold parsed values) and typed the sparse payload as `Partial<WebhookSettings>`. The resulting full 11-test suite passed. This was a source-backed harness reassessment, not another blind retry.
- Main-agent inspection confirmed the task gate raises before recipient lookup/factory construction, and the real task wrapper catches that error and records FAILED/retry. Added a bounded wrapper regression for both a disabled integration and removed notification capability, without mocking `_send_notification_feishu`: **15 task tests passed**, including zero recipient/factory calls and FAILED (not SUCCESS).

### Agent group integration evidence (#2, #3, #8; candidate #15)

- C completed the four-file focused test command (`tests/services/test_agent_service_workflow_asset_e2e.py`, `tests/services/test_agent_loop_branch_coverage_issue255.py`, `tests/api/test_chat_preflight_issue255.py`, `tests/test_agent_schemas_issue255.py`) with **70 passed**. Scoped Ruff lint/format and diff checks passed. Main-agent review removed the need for a general image-resolution abstraction: the final production change keeps the existing image construction and adds only scoped materialization in the shared builder, preserving no-image request ordering.
- The first image fixture contained literal escaped byte sequences; integration review required a valid PNG fixture and byte-for-byte decoded checks. The final fixture uses base64-decoded PNG data and both chat/stream requests pass through real OpenAI and Gemini converters, with payload bytes equal to stored bytes and the original asset binding retained. Unauthorized scope, text-only capability, and unresolved-ref rejection tests pass. The new tests do **not** add oversize/checksum-negative cases; the shared helper's existing boundary suite is part of the full backend run.
- The real DB/context-builder test confirms the current enriched text occurs once and the stored raw message remains unchanged. Public projection tests retain `fileConfig`, independent empty-list defaults, and private field exclusion.
- **#15 remains unconfirmed, parser unchanged:** installed MarkItDown **0.1.8** produces `# Visible heading\n\nVisible paragraph.` from the same HTML bytes with `.bin/.html/.xhtml`; `.txt` and actual `FileParserService.extract_text(..., 'fixture.txt')` preserve the complete HTML, including script/style sentinels. This is actual extractor behavior, not merely inferred suffix dispatch. However, the exact base/HEAD full tool extractor comparison and base dependency **0.1.6** were not run. No dependency was installed/switched and no environment changes were made to force a conclusion. Do not claim a confirmed cross-version regression.

- Full-suite #6 reassessment: keep the ORM/output enum broad enough for persisted historical rows, but narrow `NotificationAdminCreate.notify_channels` to `Literal[EMAIL, WEBHOOK, FEISHU]` so both validation and generated request schema describe only active sender types. This is a local type restriction, not a second registry or new abstraction. Preserve existing rejection tests unchanged and extend the ORM regression to JSON output serialization. The frontend active-channel union remains unchanged. The first scoped run caught a missing import in the newly extended serialization assertion (82 passed, 1 failed); added that import and corrected only its line wrapping. The next run passed **all 83 related tests**, plus full Ruff lint/format and diff checks. Final full pytest/coverage is rerunning on this corrected state.

- **Migration provenance limitation:** fresh upgrades using the actual base plaintext key are fixed and tested. If a deployment has already run the erroneous migration and created an empty disabled Integration, current data cannot reliably distinguish that artifact from an administrator's intentional empty/disabled configuration. The patch preserves existing rows and remaining legacy settings rather than guessing; automatic repair of that ambiguous state is not claimed.

### Integrated gate checkpoint

After all agents stopped editing, backend `ruff check .` passed and `ruff format --check .` reported **1,160 files already formatted**. `git diff --check` passed. The first full backend run completed with **9,590 passed, 3 failed, 4 skipped** (6 warnings). All three failures are existing `test_admin_create_rejects_unsupported_notification_channels[dingtalk/wechat/slack]` tests: restoring persisted enums also widened creation-schema acceptance. This violates #6's history-only requirement, so the item is reopened for a surgical creation-boundary restriction; do not change the existing rejection assertions. Coverage still passes independently: line **96.71%**, branch **95.14%**. Temporary test listeners were limited to the user's prior permission; no application services, browser sessions, or real provider calls were started.

### Frontend group checkpoint and stop/reassessment (#11, #12)

- Group E made the scoped pagination-lock and WeChat initialization changes but stopped after its third failing targeted run. No full frontend gate has been claimed.
- Reported blockers are in the new test interactions: controlled WeChat input did not receive a draft via native dispatched events, and an observer/deferred-mock sequence allowed an unexpected extra documents request. Notifications failure output is being collected without rerunning.
- Main-agent reassessment found the documents second-page deferred mock was installed with `mockImplementationOnce` only for B's first page; page 2 fell back to an immediately resolving default, so the four-call assertion was a harness error. Installed a distinct one-shot page-2 deferred and kept observer events true throughout. The WeChat native event path was replaced with the already established Input-stub callback capture pattern (keyed by variable input ID); the draft must be observed before the refresh as well as after it. These corrections preserve the real hook and original race; no shared hook or production guard was loosened. Notifications already installed its page-2 deferred before observer delivery; retain that sequence and collect its actual result during the bounded rerun.

### Model group checkpoint and stop/reassessment (#9, #13)

- Group D restored `ModelUpdate.default_params`; its focused backend suite passed **57 tests** (`test_model_schemas.py`, `test_admin_models_issue255.py`). Full integration checks remain pending.
- Group D added the missing function-call hydration setter and a real-effects frontend regression. Its latest focused run had **11 passed, 1 failed**: changing the model prop in the mounted harness still showed a true switch when false was expected.
- The implementer reached the three-failure limit and stopped. Main-agent reassessment identified a test locator error: the new helper selected switch index 0 (`isEnabled`, always true in its fixture), not the function-call switch (index 2). The existing `resetForm` depends on `model` and its effect depends on `open/resetForm`, so supported model-object switching already triggers hydration. Corrected only the regression locator and create-mode setup (select chat before expecting chat capability controls), removed the unnecessary generic test ID from the Switch stub, and retained the one-line production setter. The complete real-effects suite now passes: **12 passed, 0 failed**. Scoped frontend lint and backend Ruff lint passed; a new test line-wrap format failure was corrected by local edit. No capability-state refactor was needed.
