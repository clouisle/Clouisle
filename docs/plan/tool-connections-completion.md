# Tool Connections Completion Design Document

## Background & Goals

HTTP tools reject URL placeholders and lack variable completion. Code tools resolve connection credentials but do not provide them to sandbox code. Custom database tools duplicate the connection abstraction.

Success: HTTP templates render safely with completion; Python/JavaScript tools consume their selected connection; database querying is a builtin capability with database identity supplied by connections. Existing saved resources remain usable after migration.

## High-Level Design

Keep the unified connection authorization boundary. Render HTTP URLs before centralized SSRF validation. Pass code credentials through a secure per-execution sandbox mechanism, never plaintext durable task/job metadata. Replace custom database creation with builtin database tools and migrate existing definitions/bindings without deleting accounts or saved workflows.

## Implementation Plan

### Stage 1: HTTP templates and completion
- **Files modified**: `backend/app/llm/tools/executors.py`, HTTP tool dialogs and their existing variable editor dependencies.
- **Specific logic**: Render URL placeholders from execution arguments and selected connection fields; validate the final target using centralized SSRF protection. Reuse variable input completion for `{{`.
- **Validation**: Valid rendered path/query, connection field substitution, missing fields, blocked private targets, frontend completion insertion.

### Stage 2: Code connection credentials
- **Files modified**: `backend/app/services/tool.py`, sandbox compiler/gateway/runtime modules as required by existing secure transport.
- **Specific logic**: Expose selected connection fields to Python and JavaScript code with a documented interface. Preserve parameters; isolate credentials per execution. Do not put secrets into logs or durable task payloads.
- **Validation**: Actual snippet execution for both languages, different connections in consecutive executions, absent/unauthorized connections, transport secrecy.

### Stage 3: Builtin database cutover
- **Files modified**: Database executor, builtin registry, tool schemas/models, startup migration, database UI entrypoints, Agent/workflow references and package handling where needed.
- **Specific logic**: Remove custom database creation/type; retain four database engines as builtin capabilities using unified connections. Preserve old definition ids or migrate all references and bindings coherently. No credential loss or silent selection of a different account.
- **Validation**: Existing saved custom database resource migration, idempotent rerun, builtin execution dispatch, connection ownership checks, API/frontend type compatibility.

### Stage 4: Integration and delivery
- **Files modified**: Affected tests, user/operator guides, changelogs, implementation index.
- **Specific logic**: Resolve shared schema/executor changes; remove obsolete callers and documentation.
- **Validation**: Targeted backend/frontend suites, Ruff, TypeScript, ESLint and i18n checks; throwaway execution smoke without starting services or browsers.

## Testing Strategy

Happy paths cover HTTP rendering, Python/JavaScript credential access and database builtin execution. Negative cases cover unresolved placeholders, SSRF rejection, inaccessible/revoked connections and migration conflicts. Regression scope includes Agent/workflow dispatch, approvals, tool testing and package import/export. No browser or application service is authorized.

## Risks & Mitigation

- Dynamic URLs can bypass pre-render validation: validate the final rendered destination, preserving existing DNS/redirect defenses.
- Sandbox jobs may be durable: use secure secret references or encryption rather than plaintext payloads; prevent cross-execution leakage.
- Database cutover can strand references or credentials: migrate definitions and bindings together and make migration idempotent. Rollback requires restoring compatible application code and database backup if persisted enum/data changes are incompatible.
- Database migration uses four canonical builtins (`postgresql_query`, `mysql_query`, `redis_query`, `mongodb_query`). A single transaction covers connection re-keying, definition retirement and live/versioned reference rewrites; PostgreSQL startup concurrency uses an advisory transaction lock. Retired definition rows remain for audit history.
- Legacy policies merge conservatively into the canonical definition; a stricter old policy can restrict the engine's builtin for the team. Disabled state is preserved conservatively. Explicit default collisions and multiple same-engine Agent aliases fail with actionable errors instead of merging accounts or choosing an identity.
- Code execution uses a job-id/purpose-bound envelope from the existing tool keyring. API/Agent and Sandbox Workers must share keys; retain previous keys until queued jobs drain. Snippets receive `credentials` separately from `params`; deliberate printing/persistence by user code is not scrubbed. Editor Run remains connectionless; saved-tool Test accepts a connection.

## Status

Completed.

### Verification

- Affected backend integration set: 249 passed; additional snake-case workflow identity preservation regression: 6 migration tests passed after the final change.
- Full backend services/API/core/LLM run: 9055 passed, 20 failed, 4 skipped. Eighteen failures match the previously established baseline; the remaining two are pre-existing grant-DDL source assertions and file-download approval expectations (their relevant behavior is unchanged in this task). Full suite is not green.
- Changed frontend surface: 61 passed across HTTP completion, capability listing/testing, Agent selection and workflow tool configuration. TypeScript, ESLint and i18n lint/usage checks passed.
- Real Python and JavaScript subprocess snippets consumed connection credentials; real SQLite connection authorization distinguishes personal/team accounts and rejects a user without a personal default. No external sandbox/Celery service was started; Linux Bubblewrap namespace execution was not exercised on this host.
- Real SQLite migration covered retained personal connection ids, encrypted field preservation, live/versioned references, idempotence, policy/disabled-state preservation, rollback on invalid config, conflicting defaults and duplicate Agent aliases.
- Public contract smoke rejects `custom_type=database`, confirms removal of the dedicated database test endpoint, and lists all four builtin operation schemas. Clearing and reinitializing the registry twice retained all four tools.
- Ruff and backend translation catalog synchronization passed. No browser, application service or external database was started; live driver connectivity and PostgreSQL advisory-lock behavior remain unexercised.
