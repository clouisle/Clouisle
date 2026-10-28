"""Persistent site/team/entrypoint approval policy layers.

The service owns three responsibilities:

1. **CRUD** of :class:`~app.models.tool_approval_policy.ToolApprovalPolicyDefinition`
   rows with server-side authorization. Site rows require site administration
   (``admin:settings:update`` or superuser), team rows require team owner/admin
   and the global ``tool:update`` permission, and entrypoint rows require the
   entrypoint's creator or a team owner/admin plus ``tool:update``. The
   referenced Agent/Workflow/APIKey is validated against the policy team, so a
   caller cannot attach a layer to an arbitrary or foreign resource id.
2. **Execution-time composition** through ``load_effective_policy_layers``:
   missing rows mean "no added restriction"; a malformed stored row becomes an
   unconditional ``deny`` layer instead of being ignored.
3. **Stable binding metadata**: each layer label embeds its write version
   (``site:v3``), and ``EffectivePolicyBinding.fingerprint`` hashes the exact
   definition versions and policy hashes. Changing a definition therefore
   changes the evaluated policy hash and invalidates pending approvals when the
   caller revalidates against ``claim_execution``.

No expression language, script hook or client-supplied decision is accepted:
only the typed :class:`~app.schemas.tool_approval.ToolApprovalPolicy` body.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Sequence
from uuid import UUID

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app.models.agent import Agent
from app.models.api_key import APIKey
from app.models.tool import Tool, ToolShare
from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.models.user import TeamMember, User
from app.models.workflow import Workflow
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ExternalApprovalAudienceError,
    PolicyEvaluation,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    assert_caller_only_approval_policy,
    external_approval_gate_kinds,
)
from app.schemas.tool_approval_policy import (
    ToolApprovalEntrypointKind,
    ToolApprovalPolicyCreateIn,
    ToolApprovalPolicyScope,
    ToolApprovalPolicyUpdateIn,
)
from app.services.tool_approvals import (
    evaluate_policy,
    normalize_tool_approval_policy,
    policy_hash,
)

POLICY_MANAGE_PERMISSION = "tool:update"
SITE_POLICY_READ_PERMISSION = "admin:settings:read"
SITE_POLICY_MANAGE_PERMISSION = "admin:settings:update"
TEAM_ADMIN_ROLES = frozenset({"owner", "admin"})

#: Execution entrypoints that can carry a concrete entrypoint-scoped layer.
_ENTRYPOINT_KIND_BY_SOURCE: dict[str, ToolApprovalEntrypointKind] = {
    ExecutionEntrypoint.CHAT.value: ToolApprovalEntrypointKind.AGENT,
    ExecutionEntrypoint.AGENT_RUN.value: ToolApprovalEntrypointKind.AGENT,
    ExecutionEntrypoint.NESTED_AGENT.value: ToolApprovalEntrypointKind.AGENT,
    ExecutionEntrypoint.WORKFLOW.value: ToolApprovalEntrypointKind.WORKFLOW,
    ExecutionEntrypoint.SUBWORKFLOW.value: ToolApprovalEntrypointKind.WORKFLOW,
    ExecutionEntrypoint.API_KEY.value: ToolApprovalEntrypointKind.API_KEY,
    ExecutionEntrypoint.EMBED.value: ToolApprovalEntrypointKind.API_KEY,
}

#: Entrypoints that invoke a model-driven agent tool call. Interactivity does
#: not matter here: a non-interactive agent run (API key, schedule, channel,
#: embed, nested agent) must still apply the tool's explicit policy. If that
#: policy needs caller confirmation, evaluation fails closed because nobody can
#: approve it. Direct calls (capability browsing, tool test) and workflow
#: entrypoints are governed by the stored site/team/entrypoint layers plus any
#: explicit per-operation policy.
_AGENT_CALL_ENTRYPOINT_VALUES: frozenset[str] = frozenset(
    {
        ExecutionEntrypoint.CHAT.value,
        ExecutionEntrypoint.AGENT_RUN.value,
        ExecutionEntrypoint.NESTED_AGENT.value,
        ExecutionEntrypoint.API_KEY.value,
        ExecutionEntrypoint.SCHEDULE.value,
        ExecutionEntrypoint.CHANNEL.value,
        ExecutionEntrypoint.EMBED.value,
        ExecutionEntrypoint.FEISHU_CHANNEL.value,
        ExecutionEntrypoint.WECHAT_CHANNEL.value,
    }
)

#: Metadata discovery operations. A direct browser honours only an explicit
#: one-level ``list:`` override, never the tool's operation default.
DISCOVERY_OPERATION_PREFIX = "list:"


def _entrypoint_value(entrypoint: ExecutionEntrypoint | str | None) -> str | None:
    return None if entrypoint is None else str(getattr(entrypoint, "value", entrypoint))


def _run_kind_value(run_kind: ExecutionRunKind | str | None) -> str | None:
    return None if run_kind is None else str(getattr(run_kind, "value", run_kind))


def is_agent_tool_call(
    entrypoint: ExecutionEntrypoint | str | None,
    *,
    run_kind: ExecutionRunKind | str | None = None,
) -> bool:
    """Whether an Agent tool call owns this invocation, interactive or not."""
    if _run_kind_value(run_kind) == ExecutionRunKind.WORKFLOW.value:
        return False
    return _entrypoint_value(entrypoint) in _AGENT_CALL_ENTRYPOINT_VALUES


def resolve_tool_layer_policy(
    tool: Tool,
    *,
    operation: str,
    entrypoint: ExecutionEntrypoint | str | None,
    run_kind: ExecutionRunKind | str | None = None,
) -> ToolApprovalPolicy:
    """The tool-owned policy layer for one concrete call.

    Mirrors ``execute_stored_tool``: an Agent invocation applies the stored
    tool policy whenever one was explicitly configured, even when the run is
    non-interactive (a caller gate then fails closed instead of being skipped).
    A direct call only observes an explicit one-level ``list:`` discovery
    override; everything else adds no restriction. A legacy external audience
    is always returned so previews keep showing the configuration error
    instead of an allowed decision.
    """
    base = normalize_tool_approval_policy(tool.approval_policy)
    try:
        assert_caller_only_approval_policy(base)
    except ExternalApprovalAudienceError:
        return base
    if bool(tool.approval_policy) and is_agent_tool_call(entrypoint, run_kind=run_kind):
        return base
    if operation.startswith(DISCOVERY_OPERATION_PREFIX):
        override = base.operation_overrides.get(operation)
        if override is not None:
            return override.model_copy(update={"operation_overrides": {}})
    return ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _policy_error(msg_key: str, *, status_code: int, code: int) -> BusinessError:
    return BusinessError(code=code, msg_key=msg_key, status_code=status_code)


def _reject_external_audiences(policy: ToolApprovalPolicy) -> None:
    """New policy bodies may only require caller confirmation.

    Persisted legacy rows stay readable (and are returned unchanged) so an
    administrator can see what to reconfigure; only an explicit write of an
    external audience is refused.
    """
    try:
        assert_caller_only_approval_policy(policy)
    except ExternalApprovalAudienceError as exc:
        raise _policy_error(
            "tool_approval_policy_external_audience_unsupported",
            status_code=422,
            code=ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED,
        ) from exc


def _access_denied() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_access_denied", status_code=403, code=403
    )


def _not_found() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_not_found",
        status_code=404,
        code=ResponseCode.NOT_FOUND,
    )


def _scope_invalid() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_scope_invalid",
        status_code=400,
        code=ResponseCode.BAD_REQUEST,
    )


def _entrypoint_invalid() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_entrypoint_invalid",
        status_code=404,
        code=ResponseCode.NOT_FOUND,
    )


def _tool_invalid() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_tool_invalid",
        status_code=404,
        code=ResponseCode.NOT_FOUND,
    )


def _duplicate() -> BusinessError:
    return _policy_error("tool_approval_policy_duplicate", status_code=409, code=409)


def _version_conflict() -> BusinessError:
    return _policy_error(
        "tool_approval_policy_version_conflict", status_code=409, code=409
    )


# ---------------------------------------------------------------------------
# Canonical metadata
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def entrypoint_kind_for(
    entrypoint: ExecutionEntrypoint | str | None,
) -> ToolApprovalEntrypointKind | None:
    """Map a runtime entrypoint to the concrete resource kind it uses."""
    if entrypoint is None:
        return None
    value = getattr(entrypoint, "value", entrypoint)
    return _ENTRYPOINT_KIND_BY_SOURCE.get(str(value))


def build_scope_key(
    scope: ToolApprovalPolicyScope,
    *,
    team_id: UUID | None = None,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    tool_id: UUID | None = None,
) -> str:
    """Canonical uniqueness key. ``None`` team/entrypoint fields are omitted."""
    parts = [scope.value]
    if team_id is not None:
        parts.append(f"team={team_id}")
    if entrypoint_kind is not None and entrypoint_id is not None:
        parts.append(f"entrypoint={entrypoint_kind.value}:{entrypoint_id}")
    if tool_id is not None:
        parts.append(f"tool={tool_id}")
    return "|".join(parts)


def policy_definition_hash(row: ToolApprovalPolicyDefinition) -> str:
    """Stable hash of a definition's identity, version and policy body."""
    return _sha256(
        _canonical_json(
            {
                "id": str(row.id),
                "scope": row.scope.value,
                "team_id": str(row.team_id) if row.team_id else None,
                "entrypoint_kind": (
                    row.entrypoint_kind.value if row.entrypoint_kind else None
                ),
                "entrypoint_id": (
                    str(row.entrypoint_id) if row.entrypoint_id else None
                ),
                "tool_id": str(row.tool_id) if row.tool_id else None,
                "version": row.version,
                "policy_hash": row.policy_hash,
            }
        )
    )


def decode_policy(
    row: ToolApprovalPolicyDefinition,
) -> tuple[ToolApprovalPolicy, str | None]:
    """Parse a stored policy body, reporting corruption instead of ignoring it."""
    try:
        policy = ToolApprovalPolicy.model_validate(row.policy)
    except Exception:
        return (
            ToolApprovalPolicy(default_decision=ApprovalDecision.DENY),
            "approval_policy_invalid",
        )
    if policy_hash(policy) != row.policy_hash:
        return policy, "approval_policy_hash_mismatch"
    return policy, None


def _source_for(scope: ToolApprovalPolicyScope) -> PolicySource:
    if scope == ToolApprovalPolicyScope.SITE:
        return PolicySource.SITE
    if scope == ToolApprovalPolicyScope.TEAM:
        return PolicySource.TEAM
    return PolicySource.ENTRYPOINT


_STRICTNESS: dict[ApprovalDecision, int] = {
    ApprovalDecision.ALLOW: 0,
    ApprovalDecision.REQUIRE_APPROVAL: 1,
    ApprovalDecision.DENY: 2,
}


def _default_only(policy: ToolApprovalPolicy) -> ToolApprovalPolicy:
    """The policy's own default decision/gates without its operation overrides."""
    return ToolApprovalPolicy(
        default_decision=policy.default_decision, gates=policy.gates
    )


def _resolved_for_operation(
    policy: ToolApprovalPolicy, operation: str
) -> ToolApprovalPolicy:
    """Resolve one operation's chain and keep only its decision/gates."""
    resolved = policy.for_operation(operation)
    return _default_only(resolved)


def merge_tool_approval_policies(
    upper: ToolApprovalPolicy, lower: ToolApprovalPolicy
) -> ToolApprovalPolicy:
    """Combine two policies so the result is never weaker than either one.

    Used when one scope has both a generic row (``tool_id`` null) and a
    tool-specific row: both stay mandatory. Decisions take the strictest rank
    (deny > require_approval > allow), approval gates are unioned, and each
    operation's override is merged from the two sides' *resolved* operation
    policies so an override on one side cannot bypass the other side's default.
    """
    decision = max(
        (upper.default_decision, lower.default_decision),
        key=lambda item: _STRICTNESS[item],
    )
    gates: tuple[ApprovalGate, ...] = ()
    if decision == ApprovalDecision.REQUIRE_APPROVAL:
        gates = (*upper.gates, *lower.gates)

    operations = set(upper.operation_overrides) | set(lower.operation_overrides)
    overrides: dict[str, ToolApprovalPolicy] = {}
    for operation in sorted(operations):
        upper_effective = _resolved_for_operation(upper, operation)
        lower_effective = _resolved_for_operation(lower, operation)
        overrides[operation] = merge_tool_approval_policies(
            upper_effective, lower_effective
        )
    return ToolApprovalPolicy(
        default_decision=decision,
        gates=gates,
        operation_overrides=overrides,
    )


def _deny_layer(
    scope: ToolApprovalPolicyScope,
    row: ToolApprovalPolicyDefinition,
    error: str,
) -> tuple[ToolApprovalPolicy, str | None, PolicyLayer]:
    """Fail-closed layer for unreadable, tampered or unmergeable definitions."""
    policy = ToolApprovalPolicy(default_decision=ApprovalDecision.DENY)
    return (
        policy,
        error,
        PolicyLayer(
            source=_source_for(scope),
            label=f"{scope.value}:{row.id.hex[:8]}:invalid",
            policy=policy,
        ),
    )


def _merged_layer(
    scope: ToolApprovalPolicyScope,
    rows: Sequence[ToolApprovalPolicyDefinition],
) -> tuple[ToolApprovalPolicy, str | None, PolicyLayer]:
    """Build one layer from all rows of a scope, never dropping a row.

    ``rows`` is ordered generic-first. Corrupt rows and unreadable hashes make
    the whole scope fail closed with ``deny``; a valid-specific row can never
    replace or relax a generic mandatory row.
    """
    decoded: list[ToolApprovalPolicy] = []
    for row in rows:
        policy, error = decode_policy(row)
        if error is not None:
            return _deny_layer(scope, row, error)
        decoded.append(policy)
    try:
        merged = decoded[0]
        for policy in decoded[1:]:
            merged = merge_tool_approval_policies(merged, policy)
    except ValueError:
        # Only reachable for a body that passed decoding but cannot be
        # resolved deterministically (e.g. a deeper override chain than the
        # resolver allows). Refuse instead of executing with partial semantics.
        return _deny_layer(scope, rows[0], "approval_policy_invalid")
    label = "+".join(f"{row.id.hex[:8]}:v{row.version}" for row in rows)
    return (
        merged,
        None,
        PolicyLayer(
            source=_source_for(scope), label=f"{scope.value}:{label}", policy=merged
        ),
    )


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------


async def _ensure_permissions(user: User) -> None:
    try:
        await user.fetch_related("roles__permissions")
    except Exception:  # pragma: no cover - ORM prefetch is best-effort here
        pass


def _has_global_permission(user: User, permission: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    for role in getattr(user, "roles", None) or ():
        for grant in getattr(role, "permissions", None) or ():
            if getattr(grant, "code", None) in (permission, "*"):
                return True
    return False


def _is_site_reader(user: User) -> bool:
    return _has_global_permission(user, SITE_POLICY_READ_PERMISSION) or (
        _has_global_permission(user, SITE_POLICY_MANAGE_PERMISSION)
    )


def _is_site_editor(user: User) -> bool:
    return _has_global_permission(user, SITE_POLICY_MANAGE_PERMISSION)


async def _membership(user: User, team_id: UUID) -> TeamMember | None:
    return await TeamMember.filter(team_id=team_id, user_id=user.id).first()


async def _require_team_read(user: User, team_id: UUID) -> None:
    if getattr(user, "is_superuser", False):
        return
    if await _membership(user, team_id) is None:
        raise _access_denied()


async def _require_team_manager(user: User, team_id: UUID) -> None:
    """Team owner/admin plus the global tool-management permission."""
    if getattr(user, "is_superuser", False):
        return
    await _ensure_permissions(user)
    member = await _membership(user, team_id)
    if member is None or member.role not in TEAM_ADMIN_ROLES:
        raise _access_denied()
    if not _has_global_permission(user, POLICY_MANAGE_PERMISSION):
        raise _access_denied()


def _parse_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Scope validation
# ---------------------------------------------------------------------------


async def _validate_tool(
    tool_id: UUID | None,
    *,
    team_id: UUID | None,
    scope: ToolApprovalPolicyScope,
) -> Tool | None:
    """Validate that a tool id exists and is usable from the policy scope."""
    if tool_id is None:
        return None
    tool = await Tool.filter(id=tool_id).first()
    if tool is None:
        raise _tool_invalid()
    if scope in (ToolApprovalPolicyScope.TEAM, ToolApprovalPolicyScope.ENTRYPOINT):
        assert team_id is not None
        if (
            tool.team_id != team_id
            and not await ToolShare.filter(
                tool_id=tool.id, shared_with_team_id=team_id
            ).exists()
        ):
            raise _tool_invalid()
    return tool


async def _entrypoint_owner(
    kind: ToolApprovalEntrypointKind,
    entrypoint_id: UUID,
    team_id: UUID,
) -> UUID | None:
    """Return the entrypoint creator/owner, or raise when it is out of scope."""
    if kind == ToolApprovalEntrypointKind.AGENT:
        row = await Agent.filter(id=entrypoint_id, team_id=team_id).first()
        if row is None:
            raise _entrypoint_invalid()
        return row.created_by_id
    if kind == ToolApprovalEntrypointKind.WORKFLOW:
        row = await Workflow.filter(id=entrypoint_id, team_id=team_id).first()
        if row is None:
            raise _entrypoint_invalid()
        return row.created_by_id
    key = await APIKey.filter(id=entrypoint_id).first()
    if (
        key is None
        or not await TeamMember.filter(team_id=team_id, user_id=key.user_id).exists()
    ):
        raise _entrypoint_invalid()
    return key.user_id


async def _can_edit_row(user: User, row: ToolApprovalPolicyDefinition) -> bool:
    if row.scope == ToolApprovalPolicyScope.SITE:
        return _is_site_editor(user)
    if getattr(user, "is_superuser", False):
        return True
    if row.team_id is None:
        return False
    if not _has_global_permission(user, POLICY_MANAGE_PERMISSION):
        return False
    member = await _membership(user, row.team_id)
    if member is None:
        return False
    if member.role in TEAM_ADMIN_ROLES:
        return True
    if row.scope != ToolApprovalPolicyScope.ENTRYPOINT:
        return False
    if row.entrypoint_kind is None or row.entrypoint_id is None:
        return False
    try:
        owner_id = await _entrypoint_owner(
            row.entrypoint_kind, row.entrypoint_id, row.team_id
        )
    except BusinessError:
        return False
    return owner_id == user.id


async def _authorize_row_write(user: User, row: ToolApprovalPolicyDefinition) -> None:
    if row.scope == ToolApprovalPolicyScope.SITE:
        await _ensure_permissions(user)
        if not _is_site_editor(user):
            raise _access_denied()
        return
    if row.team_id is None:
        raise _scope_invalid()
    if getattr(user, "is_superuser", False):
        return
    await _ensure_permissions(user)
    if not _has_global_permission(user, POLICY_MANAGE_PERMISSION):
        raise _access_denied()
    member = await _membership(user, row.team_id)
    if member is None:
        raise _access_denied()
    if row.scope == ToolApprovalPolicyScope.TEAM:
        if member.role not in TEAM_ADMIN_ROLES:
            raise _access_denied()
        return
    if row.entrypoint_kind is None or row.entrypoint_id is None:
        raise _scope_invalid()
    if member.role in TEAM_ADMIN_ROLES:
        return
    owner_id = await _entrypoint_owner(
        row.entrypoint_kind, row.entrypoint_id, row.team_id
    )
    if owner_id != user.id:
        raise _access_denied()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyDefinitionView:
    row: ToolApprovalPolicyDefinition
    policy: ToolApprovalPolicy
    configuration_error: str | None
    can_edit: bool


def _view(row: ToolApprovalPolicyDefinition, *, can_edit: bool) -> PolicyDefinitionView:
    policy, error = decode_policy(row)
    if error is None and external_approval_gate_kinds(policy):
        # Keep the stored body intact for reconfiguration, but never present
        # a legacy external audience as a usable policy.
        error = "approval_gate_external_audience_unsupported"
    return PolicyDefinitionView(
        row=row, policy=policy, configuration_error=error, can_edit=can_edit
    )


def _validate_create_scope(payload: ToolApprovalPolicyCreateIn) -> None:
    scope = payload.scope
    if scope == ToolApprovalPolicyScope.SITE:
        if (
            payload.team_id is not None
            or payload.entrypoint_kind is not None
            or payload.entrypoint_id is not None
        ):
            raise _scope_invalid()
        return
    if scope == ToolApprovalPolicyScope.TEAM:
        if (
            payload.team_id is None
            or payload.entrypoint_kind is not None
            or payload.entrypoint_id is not None
        ):
            raise _scope_invalid()
        return
    if (
        payload.team_id is None
        or payload.entrypoint_kind is None
        or payload.entrypoint_id is None
    ):
        raise _scope_invalid()


async def list_policy_definitions(
    actor: User,
    *,
    team_id: UUID | None = None,
    scope: ToolApprovalPolicyScope | None = None,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    tool_id: UUID | None = None,
) -> list[PolicyDefinitionView]:
    """List configured layers the caller may see, with server-computed editability.

    A team-scoped listing also includes site baseline rows read-only so team
    admins can see what they cannot relax. Without ``team_id`` only site rows
    are listed and site-administration permission is required.
    """
    await _ensure_permissions(actor)
    if team_id is None:
        if not _is_site_reader(actor):
            raise _access_denied()
        query = Q(scope=ToolApprovalPolicyScope.SITE)
    else:
        await _require_team_read(actor, team_id)
        query = (
            Q(scope=ToolApprovalPolicyScope.SITE)
            | Q(scope=ToolApprovalPolicyScope.TEAM, team_id=team_id)
            | Q(scope=ToolApprovalPolicyScope.ENTRYPOINT, team_id=team_id)
        )
    filters: dict[str, Any] = {}
    if scope is not None:
        filters["scope"] = scope
    if entrypoint_kind is not None:
        filters["entrypoint_kind"] = entrypoint_kind
    if entrypoint_id is not None:
        filters["entrypoint_id"] = entrypoint_id
    if tool_id is not None:
        filters["tool_id"] = tool_id
    rows = await ToolApprovalPolicyDefinition.filter(query, **filters).order_by(
        "scope", "scope_key"
    )
    return [_view(row, can_edit=await _can_edit_row(actor, row)) for row in rows]


async def create_policy_definition(
    actor: User, payload: ToolApprovalPolicyCreateIn
) -> PolicyDefinitionView:
    _validate_create_scope(payload)
    await _ensure_permissions(actor)
    if payload.scope == ToolApprovalPolicyScope.SITE:
        if not _is_site_editor(actor):
            raise _access_denied()
        await _validate_tool(payload.tool_id, team_id=None, scope=payload.scope)
    elif payload.scope == ToolApprovalPolicyScope.TEAM:
        assert payload.team_id is not None
        await _require_team_manager(actor, payload.team_id)
        await _validate_tool(
            payload.tool_id, team_id=payload.team_id, scope=payload.scope
        )
    else:
        assert payload.team_id is not None
        assert payload.entrypoint_kind is not None
        assert payload.entrypoint_id is not None
        owner_id = await _entrypoint_owner(
            payload.entrypoint_kind, payload.entrypoint_id, payload.team_id
        )
        if not getattr(actor, "is_superuser", False):
            if not _has_global_permission(actor, POLICY_MANAGE_PERMISSION):
                raise _access_denied()
            member = await _membership(actor, payload.team_id)
            if member is None:
                raise _access_denied()
            if member.role not in TEAM_ADMIN_ROLES and owner_id != actor.id:
                raise _access_denied()
        await _validate_tool(
            payload.tool_id, team_id=payload.team_id, scope=payload.scope
        )

    _reject_external_audiences(payload.policy)
    scope_key = build_scope_key(
        payload.scope,
        team_id=payload.team_id,
        entrypoint_kind=payload.entrypoint_kind,
        entrypoint_id=payload.entrypoint_id,
        tool_id=payload.tool_id,
    )
    if await ToolApprovalPolicyDefinition.filter(scope_key=scope_key).exists():
        raise _duplicate()
    body = payload.policy.model_dump(mode="json")
    try:
        row = await ToolApprovalPolicyDefinition.create(
            scope=payload.scope,
            scope_key=scope_key,
            team_id=payload.team_id,
            entrypoint_kind=payload.entrypoint_kind,
            entrypoint_id=payload.entrypoint_id,
            tool_id=payload.tool_id,
            policy=body,
            policy_hash=policy_hash(payload.policy),
            version=1,
            created_by_id=actor.id,
        )
    except IntegrityError as exc:
        raise _duplicate() from exc
    return _view(row, can_edit=True)


async def update_policy_definition(
    actor: User,
    policy_id: UUID,
    payload: ToolApprovalPolicyUpdateIn,
) -> PolicyDefinitionView:
    row = await ToolApprovalPolicyDefinition.filter(id=policy_id).first()
    if row is None:
        raise _not_found()
    await _authorize_row_write(actor, row)
    if payload.expected_version is not None and payload.expected_version != row.version:
        raise _version_conflict()
    _reject_external_audiences(payload.policy)
    new_hash = policy_hash(payload.policy)
    updated = await ToolApprovalPolicyDefinition.filter(
        id=row.id, version=row.version
    ).update(
        policy=payload.policy.model_dump(mode="json"),
        policy_hash=new_hash,
        version=row.version + 1,
        updated_at=datetime.now(timezone.utc),
    )
    if not updated:
        raise _version_conflict()
    await row.refresh_from_db()
    return _view(row, can_edit=True)


async def delete_policy_definition(actor: User, policy_id: UUID) -> None:
    row = await ToolApprovalPolicyDefinition.filter(id=policy_id).first()
    if row is None:
        raise _not_found()
    await _authorize_row_write(actor, row)
    await row.delete()


# ---------------------------------------------------------------------------
# Execution-time composition
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyLayerDefinition:
    """One scope's layer plus the definition rows that produced it.

    ``rows`` holds the scope's generic row (``tool_id`` null) followed by its
    tool-specific row. Both remain mandatory; the merged policy is never
    weaker than either.
    """

    rows: tuple[ToolApprovalPolicyDefinition, ...]
    policy: ToolApprovalPolicy
    configuration_error: str | None
    layer: PolicyLayer

    @property
    def version(self) -> int | None:
        return max((row.version for row in self.rows), default=None)

    @property
    def policy_hash(self) -> str:
        return policy_hash(self.policy)

    @property
    def definition_hash(self) -> str:
        return _sha256(
            _canonical_json(
                [
                    {
                        "id": str(row.id),
                        "version": row.version,
                        "policy_hash": row.policy_hash,
                    }
                    for row in self.rows
                ]
            )
        )


@dataclass(frozen=True, slots=True)
class EffectivePolicyBinding:
    """Ordered layers and the fingerprint of the definitions behind them."""

    entries: tuple[PolicyLayerDefinition, ...]
    fingerprint: str

    @property
    def layers(self) -> tuple[PolicyLayer, ...]:
        return tuple(entry.layer for entry in self.entries)

    @property
    def defined(self) -> bool:
        return bool(self.entries)


async def _select_rows(
    scope: ToolApprovalPolicyScope,
    *,
    team_id: UUID | None,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    tool_id: UUID,
) -> tuple[ToolApprovalPolicyDefinition, ...]:
    """Return the scope's generic row and its tool-specific row, in that order.

    Both are returned when both exist so the caller can merge them strictly.
    """
    query = Q(tool_id=tool_id) | Q(tool_id__isnull=True)
    filters: dict[str, Any] = {"scope": scope}
    if team_id is not None:
        filters["team_id"] = team_id
    if entrypoint_kind is not None:
        filters["entrypoint_kind"] = entrypoint_kind
    if entrypoint_id is not None:
        filters["entrypoint_id"] = entrypoint_id
    rows = await ToolApprovalPolicyDefinition.filter(query, **filters)
    generic = tuple(row for row in rows if row.tool_id is None)
    specific = tuple(row for row in rows if row.tool_id == tool_id)
    return (*generic, *specific)


def _scope_entry(
    scope: ToolApprovalPolicyScope,
    rows: Sequence[ToolApprovalPolicyDefinition],
) -> PolicyLayerDefinition | None:
    if not rows:
        return None
    policy, error, layer = _merged_layer(scope, rows)
    return PolicyLayerDefinition(
        rows=tuple(rows),
        policy=policy,
        configuration_error=error,
        layer=layer,
    )


async def _load_binding(
    *,
    team_id: UUID | None,
    entrypoint_kind: ToolApprovalEntrypointKind | None,
    entrypoint_id: UUID | None,
    tool_id: UUID,
) -> EffectivePolicyBinding:
    entries: list[PolicyLayerDefinition] = []
    site_entry = _scope_entry(
        ToolApprovalPolicyScope.SITE,
        await _select_rows(ToolApprovalPolicyScope.SITE, team_id=None, tool_id=tool_id),
    )
    if site_entry is not None:
        entries.append(site_entry)
    if team_id is not None:
        team_entry = _scope_entry(
            ToolApprovalPolicyScope.TEAM,
            await _select_rows(
                ToolApprovalPolicyScope.TEAM, team_id=team_id, tool_id=tool_id
            ),
        )
        if team_entry is not None:
            entries.append(team_entry)
    if (
        team_id is not None
        and entrypoint_kind is not None
        and entrypoint_id is not None
    ):
        entrypoint_entry = _scope_entry(
            ToolApprovalPolicyScope.ENTRYPOINT,
            await _select_rows(
                ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team_id,
                entrypoint_kind=entrypoint_kind,
                entrypoint_id=entrypoint_id,
                tool_id=tool_id,
            ),
        )
        if entrypoint_entry is not None:
            entries.append(entrypoint_entry)
    fingerprint = _sha256(
        _canonical_json(
            [
                {
                    "id": str(row.id),
                    "scope": row.scope.value,
                    "team_id": str(row.team_id) if row.team_id else None,
                    "entrypoint_kind": (
                        row.entrypoint_kind.value if row.entrypoint_kind else None
                    ),
                    "entrypoint_id": (
                        str(row.entrypoint_id) if row.entrypoint_id else None
                    ),
                    "tool_id": str(row.tool_id) if row.tool_id else None,
                    "version": row.version,
                    "policy_hash": row.policy_hash,
                }
                for entry in entries
                for row in entry.rows
            ]
        )
    )
    return EffectivePolicyBinding(entries=tuple(entries), fingerprint=fingerprint)


async def load_effective_policy_binding(
    context: Any, tool: Tool
) -> EffectivePolicyBinding:
    """Load site/team/entrypoint layers for one execution context and tool.

    ``context`` is duck-typed (``team_id``, ``entrypoint``, ``entrypoint_id``);
    this keeps the module independent from the execution service. A missing
    team or entrypoint id simply yields fewer layers. Corrupt rows produce a
    ``deny`` layer, never a silent skip.
    """
    team_id = _parse_uuid(getattr(context, "team_id", None))
    entrypoint_kind = entrypoint_kind_for(getattr(context, "entrypoint", None))
    entrypoint_id = (
        _parse_uuid(getattr(context, "entrypoint_id", None))
        if entrypoint_kind is not None
        else None
    )
    return await _load_binding(
        team_id=team_id,
        entrypoint_kind=entrypoint_kind,
        entrypoint_id=entrypoint_id,
        tool_id=tool.id,
    )


async def load_effective_policy_layers(
    context: Any, tool: Tool
) -> Sequence[PolicyLayer]:
    """Return stored layers in strength order; empty means no added restriction."""
    binding = await load_effective_policy_binding(context, tool)
    return binding.layers


# ---------------------------------------------------------------------------
# Admin preview
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectivePolicyView:
    evaluation: PolicyEvaluation
    layers: tuple[PolicyLayerDefinition, ...]
    layer_can_edit: tuple[bool, ...]
    can_edit_team: bool
    entrypoint_interactive: bool


async def get_effective_policy(
    actor: User,
    *,
    team_id: UUID,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    entrypoint: ExecutionEntrypoint | None = None,
    tool_id: UUID,
    operation: str,
    entrypoint_interactive: bool = True,
) -> EffectivePolicyView:
    """Compose the effective policy for an editor preview.

    The preview mirrors ``execute_stored_tool`` for the *actual* entrypoint:
    every Agent invocation applies an explicitly configured tool policy, even
    when it is non-interactive (a caller gate then surfaces a configuration
    error because nobody can approve it). Direct calls (capability browsing,
    tool test) observe just an explicit one-level discovery override.
    ``entrypoint`` is the runtime entrypoint; when it is omitted an agent
    entrypoint kind implies an agent call and everything else is a direct
    call. Stored site/team/entrypoint layers are always composed, so a
    configured deny or required approval can never be preview-only.
    """
    if (entrypoint_kind is None) != (entrypoint_id is None):
        raise _scope_invalid()
    await _ensure_permissions(actor)
    await _require_team_read(actor, team_id)
    tool = await _validate_tool(
        tool_id, team_id=team_id, scope=ToolApprovalPolicyScope.TEAM
    )
    assert tool is not None
    if entrypoint_kind is not None and entrypoint_id is not None:
        await _entrypoint_owner(entrypoint_kind, entrypoint_id, team_id)
    binding = await _load_binding(
        team_id=team_id,
        entrypoint_kind=entrypoint_kind,
        entrypoint_id=entrypoint_id,
        tool_id=tool.id,
    )
    if entrypoint is not None:
        tool_entrypoint = entrypoint
    elif entrypoint_kind is ToolApprovalEntrypointKind.AGENT:
        tool_entrypoint = ExecutionEntrypoint.CHAT
    else:
        tool_entrypoint = ExecutionEntrypoint.TOOL_TEST
    tool_layer = PolicyLayer(
        source=PolicySource.TOOL,
        label="tool",
        policy=resolve_tool_layer_policy(
            tool,
            operation=operation,
            entrypoint=tool_entrypoint,
        ),
    )
    evaluation = evaluate_policy(
        [*binding.layers, tool_layer],
        operation,
        entrypoint_interactive=entrypoint_interactive,
    )
    layer_can_edit: list[bool] = []
    for entry in binding.entries:
        editable = True
        for row in entry.rows:
            if not await _can_edit_row(actor, row):
                editable = False
                break
        layer_can_edit.append(editable)
    if getattr(actor, "is_superuser", False):
        can_edit_team = True
    else:
        member = await _membership(actor, team_id)
        can_edit_team = bool(
            member is not None
            and member.role in TEAM_ADMIN_ROLES
            and _has_global_permission(actor, POLICY_MANAGE_PERMISSION)
        )
    return EffectivePolicyView(
        evaluation=evaluation,
        layers=binding.entries,
        layer_can_edit=tuple(layer_can_edit),
        can_edit_team=can_edit_team,
        entrypoint_interactive=entrypoint_interactive,
    )


__all__ = [
    "EffectivePolicyBinding",
    "EffectivePolicyView",
    "POLICY_MANAGE_PERMISSION",
    "PolicyDefinitionView",
    "PolicyLayerDefinition",
    "TEAM_ADMIN_ROLES",
    "build_scope_key",
    "create_policy_definition",
    "decode_policy",
    "delete_policy_definition",
    "entrypoint_kind_for",
    "get_effective_policy",
    "is_agent_tool_call",
    "list_policy_definitions",
    "load_effective_policy_binding",
    "load_effective_policy_layers",
    "merge_tool_approval_policies",
    "policy_definition_hash",
    "resolve_tool_layer_policy",
    "update_policy_definition",
]
