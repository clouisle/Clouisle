# PR 480 Review Fixes Design Document

## Background & Goals

Sixteen parallel reviews of PR #480 found two release blockers and a set of
authorization, migration, and UI defects. Fix the defects that have a clear,
verifiable behavior; record the two that need a product/design decision.

## Decisions

### Fixed

- Chat stream route: only the authenticated `chat_stream` wrapper is registered;
  the implementation helper is no longer a route.
- Stored site/team/entrypoint policy layers are loaded for every new execution,
  and the MCP `policy` override is applied instead of being discarded. The
  explicit Agent confirmation is a decision flag, so a tool operation override
  cannot relax it and no duplicate layer source is introduced.
- Startup DDL: one statement per call (the asyncpg prepared-statement path
  rejects multi-command strings), so the connection CHECK constraints and the
  retired grant cleanup actually run.
- Skill definition fingerprints are 28-bit, inside PostgreSQL `INTEGER`.
- Legacy PRIVATE database-tool credentials migrate to a personal (owner) scope;
  creator-less private rows stay team-scoped with a warning.
- Approval-policy and OAuth routes require an active user.
- Workflow binding validation reads the real `data.toolConfig` container.
- Connection update/revoke lock the row and update only changed columns.
- MCP request budget never undercuts an explicit operation timeout.
- MCP resource/prompt previews can replay `execution_id`; the browser retries
  those previews after approval.
- Admin tool list no longer lists a materialized builtin twice; builtin
  creation is rejected; `test_tool` authorizes the team before materializing.
- Package import applies `approval_policy` and bumps `definition_version`.
- Approved resumes create/reuse the conversation sandbox session; stopping a
  waiting/queued run cancels its pending executions.
- Interaction credential denylist widened, response digest keyed, inbox scan
  paginated; DB config parsing tolerates legacy numeric strings.
- Frontend: MCP header values are masked again, connection fields keep all
  attributes, the connection picker clears stale rows, capability bounds match
  the backend, reconnect effects use a stable ref, and closing a run invalidates
  in-flight interaction responses.

### Deferred (need a decision)

- **OAuth callback login binding.** The callback is state-bound but not tied to
  the browser session that started the flow. Fixing it requires an HttpOnly
  state cookie or a SPA exchange endpoint (frontend change). Design first.
- **Non-interactive caller-gate contract.** Docs promise `6510` for a caller
  gate at a non-interactive entrypoint, while the execution boundary allows it.
  Aligning changes behavior for every API-key/embed/schedule run; decide which
  side is authoritative.

## Testing Strategy

- New: stored team policy deny/require blocks or pauses an execution; skill
  version fits `INT4`; MCP budget extends to the explicit timeout; admin list
  has one entry per builtin; package import bumps version and keeps policy.
- Existing suites: approvals, connections, OAuth, interactions, agent resume,
  worker transitions, MCP client, tools endpoints, package resources.

## Risks & Mitigation

- Loading policy layers adds queries per execution; layers only tighten and the
  stored rows are indexed by scope/tool.
- Widening the interaction scan is bounded at `MAX_LIST_SCAN * 10` and logs when
  the total may be partial.
