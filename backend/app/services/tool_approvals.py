"""Deterministic tool approval policy, execution binding and state machine.

The service is the single server-side boundary for tool execution approval.
It owns:

* policy normalisation and deterministic composition (deny > require > allow,
  approval gate union, caller/designated-user/team-role audiences);
* the immutable binding of operation, tool definition version, effective
  principal, connection/grant version, encrypted parameters and policy;
* approval decisions (one row-locked transaction, idempotent replay, reject
  wins), expiry/cancellation and outcome recording;
* the single execution claim that makes exactly one worker allowed to call the
  external adapter. Deciding an approval only makes an execution ``ready``;
  it never performs the side effect (the AgentRun/workflow worker claims and
  executes the original deferred tool call).

Secrets: parameters are stored as a Fernet token; previews, policy snapshots
and approval displays are redacted metadata only. Approvers never receive the
ciphertext, connection secrets or the claim token.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import ValidationError
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q, Subquery
from tortoise.transactions import in_transaction

from app.core.tool_secrets import (
    ToolSecretError,
    decrypt_tool_secret,
    encrypt_tool_secret,
)
from app.models.tool_approval import (
    ToolApprovalDecision,
    ToolApprovalRequest,
    ToolExecution,
)
from app.models.user import TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    NON_INTERACTIVE_ENTRYPOINTS,
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    PolicyEvaluation,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
    default_tool_approval_policy,
    external_approval_gate_kinds,
    gate_signature,
    gate_stage_key,
)

if TYPE_CHECKING:
    from fastapi import Request

    from app.models.tool import Tool
    from app.services.tool_connections import ConnectionBinding

logger = logging.getLogger(__name__)

MAX_PARAMETERS_BYTES = 1024 * 1024
MAX_POLICY_SNAPSHOT_BYTES = 256 * 1024
MAX_PREVIEW_BYTES = 16 * 1024
MAX_RESULT_REF_BYTES = 8 * 1024
MAX_RESULT_REF_KEYS = 32
MAX_ERROR_DETAIL_LENGTH = 2000
MAX_REASON_LENGTH = 2000
MAX_CLAIM_TOKEN_LENGTH = 64
DEFAULT_APPROVAL_TTL = timedelta(hours=24)
DEFAULT_READY_TTL = timedelta(hours=1)
MAX_EXECUTION_TTL = timedelta(days=30)
MAX_INBOX_SCAN = 1000
REDACTED = "***REDACTED***"
TRUNCATED = "***TRUNCATED***"

# Conservative names that are never shown in a preview even when the tool did
# not declare them as credential fields. Matching is exact (case-insensitive),
# not substring, so ordinary names such as "token_count" stay visible.
_ALWAYS_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "cookies",
        "set-cookie",
        "headers",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "private_key",
        "x-api-key",
        "credentials",
        "env",
    }
)
_ALLOWED_CANCEL_REASONS = frozenset(
    {
        ToolExecutionCancelReason.CANCELLED,
        ToolExecutionCancelReason.REVOKED,
        ToolExecutionCancelReason.RUN_STOPPED,
    }
)
_POLICY_RANK = {
    ApprovalDecision.ALLOW: 0,
    ApprovalDecision.REQUIRE_APPROVAL: 1,
    ApprovalDecision.DENY: 2,
}
_POLICY_SOURCE_ORDER = {
    PolicySource.SITE: 0,
    PolicySource.TEAM: 1,
    PolicySource.TOOL: 2,
    PolicySource.ENTRYPOINT: 3,
}


class PolicyConfigurationError(ValueError):
    """A stored policy cannot be interpreted safely; never means allow."""

    def __init__(self, code: str = "policy_configuration_required") -> None:
        self.code = code
        super().__init__(code)


class _BindingSnapshotError(ValueError):
    """A connection binding snapshot is unusable."""


@dataclass(frozen=True)
class ParameterSnapshot:
    """Encrypted full parameters plus a reviewer-safe preview."""

    ciphertext: str
    digest: str
    preview: dict[str, Any]
    redacted_paths: tuple[str, ...]


@dataclass(frozen=True)
class _BindingFacts:
    connection_id: UUID
    team_id: UUID | None
    scope: str
    owner_user_id: UUID | None
    effective_user_id: UUID | None
    secret_version: int
    status: str
    is_active: bool


@dataclass(frozen=True)
class _GatePlan:
    gate: ApprovalGate
    stage_index: int
    stage_key: str
    approver_user_ids: tuple[str, ...]
    approver_roles: tuple[str, ...]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _error(
    code: ResponseCode,
    message: str,
    *,
    msg_key: str,
    status_code: int = 400,
    data: Any = None,
) -> BusinessError:
    return BusinessError(
        code=code,
        msg=message,
        msg_key=msg_key,
        status_code=status_code,
        data=data,
    )


def _not_found(execution: bool = False) -> BusinessError:
    if execution:
        return _error(
            ResponseCode.TOOL_EXECUTION_NOT_FOUND,
            "Tool execution not found",
            msg_key="tool_execution_not_found",
            status_code=404,
        )
    return _error(
        ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND,
        "Approval request not found",
        msg_key="tool_approval_request_not_found",
        status_code=404,
    )


def _input_invalid(message: str = "Invalid tool approval input") -> BusinessError:
    return _error(
        ResponseCode.TOOL_APPROVAL_INPUT_INVALID,
        message,
        msg_key="tool_approval_input_invalid",
        status_code=422,
    )


def _policy_configuration_required(detail: str) -> BusinessError:
    return _error(
        ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED,
        "Tool approval policy requires a valid approver audience",
        msg_key="tool_approval_policy_configuration_required",
        status_code=422,
        data={"reason": detail},
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _jsonable(value: Any, *, path: str = "") -> Any:
    """Strictly convert an execution parameter value to JSON-safe data."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise _input_invalid(f"Non-finite number at {path or '<root>'}")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _input_invalid(f"Non-string parameter key at {path or '<root>'}")
            if any(ord(char) < 32 for char in key):
                raise _input_invalid(f"Invalid parameter key at {path or '<root>'}")
            result[key] = _jsonable(item, path=f"{path}.{key}" if path else key)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _jsonable(item, path=f"{path}[{index}]") for index, item in enumerate(value)
        ]
    raise _input_invalid(f"Unsupported parameter value at {path or '<root>'}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


# ---------------------------------------------------------------------------
# Policy composition
# ---------------------------------------------------------------------------


def normalize_tool_approval_policy(
    raw: Mapping[str, Any] | ToolApprovalPolicy | None,
) -> ToolApprovalPolicy:
    """Parse a stored/incoming policy, failing closed on malformed input."""
    if raw is None:
        return default_tool_approval_policy()
    if isinstance(raw, ToolApprovalPolicy):
        return raw
    if isinstance(raw, Mapping):
        if not raw:
            return default_tool_approval_policy()
        try:
            return ToolApprovalPolicy.model_validate(dict(raw))
        except ValidationError as exc:
            raise PolicyConfigurationError("approval_policy_invalid") from exc
    raise PolicyConfigurationError("approval_policy_invalid")


def _ordered_layers(layers: Sequence[PolicyLayer]) -> list[PolicyLayer]:
    ordered = sorted(
        layers,
        key=lambda layer: (
            _POLICY_SOURCE_ORDER.get(layer.source, 99),
            (layer.label or ""),
        ),
    )
    seen: set[PolicySource] = set()
    for layer in ordered:
        if layer.source in seen:
            raise PolicyConfigurationError("approval_policy_layer_duplicate")
        seen.add(layer.source)
    return ordered


def _merge_gates(gates: Iterable[ApprovalGate]) -> tuple[ApprovalGate, ...]:
    merged: list[ApprovalGate] = []
    indexes: dict[tuple[str, tuple[str, ...]], int] = {}
    for gate in gates:
        signature = gate_signature(gate)
        existing_index = indexes.get(signature)
        if existing_index is None:
            indexes[signature] = len(merged)
            merged.append(gate)
            continue
        existing = merged[existing_index]
        merged[existing_index] = ApprovalGate(
            kind=existing.kind,
            user_ids=existing.user_ids,
            roles=existing.roles,
            allow_self_approval=(
                existing.allow_self_approval and gate.allow_self_approval
            ),
        )
    return tuple(merged)


def _evaluation_hash(
    *,
    operation: str,
    entrypoint_interactive: bool,
    layers: Sequence[PolicyLayer],
    decision: ApprovalDecision,
    gates: Sequence[ApprovalGate],
) -> str:
    payload = {
        "operation": operation,
        "entrypoint_interactive": entrypoint_interactive,
        "layers": [
            {
                "source": layer.source.value,
                "label": layer.label,
                "policy": layer.policy.model_dump(mode="json"),
            }
            for layer in layers
        ],
        "decision": decision.value,
        "gates": [gate.model_dump(mode="json") for gate in gates],
    }
    return _sha256(_canonical_json(payload))


def policy_hash(value: ToolApprovalPolicy | PolicyEvaluation) -> str:
    """Stable policy fingerprint used in execution/approval bindings."""
    if isinstance(value, PolicyEvaluation):
        return value.policy_hash
    if isinstance(value, ToolApprovalPolicy):
        return _sha256(_canonical_json(value.model_dump(mode="json")))
    raise TypeError("policy_hash requires ToolApprovalPolicy or PolicyEvaluation")


def evaluate_policy(
    layers: Sequence[PolicyLayer],
    operation: str,
    *,
    entrypoint_interactive: bool,
    require_caller_confirmation: bool = False,
    caller_self_approvable: bool = False,
) -> PolicyEvaluation:
    """Compose layers deterministically; deny wins and approvals union.

    Within one layer an exact ``operation_overrides`` entry replaces that
    layer's default decision and gates. Across layers the strictest decision
    wins (deny > require_approval > allow) and every approval gate from a
    requiring layer is kept, so a lower layer can tighten but never relax a
    higher mandatory layer.

    ``caller_self_approvable`` marks a non-interactive origin whose caller can
    still decide its own caller gates (an API-key Agent run). It never makes
    such a run interactive and never adds external audiences.
    """
    normalized_operation = operation.strip()
    if not normalized_operation or len(normalized_operation) > 200:
        raise PolicyConfigurationError("approval_operation_invalid")
    ordered = _ordered_layers(layers)
    if not ordered:
        raise PolicyConfigurationError("approval_policy_missing")

    decisions: list[ApprovalDecision] = []
    gates: list[ApprovalGate] = []
    sources: list[str] = []
    configuration_errors: list[str] = []

    for layer in ordered:
        sources.append(layer.label or layer.source.value)
        try:
            effective = layer.policy.for_operation(normalized_operation)
        except ValueError:
            decisions.append(ApprovalDecision.DENY)
            configuration_errors.append("approval_policy_invalid")
            continue
        decision = effective.default_decision
        decisions.append(decision)
        if decision == ApprovalDecision.REQUIRE_APPROVAL:
            if not effective.gates:
                configuration_errors.append("approval_audience_missing")
            gates.extend(effective.gates)
        elif effective.gates:
            # Gates on an allow/deny policy are malformed and never executed.
            configuration_errors.append("approval_gates_without_requirement")

    final_decision = max(decisions, key=lambda item: _POLICY_RANK[item])
    merged_gates = _merge_gates(gates)
    # A legacy external audience anywhere in any layer (including unused
    # operation overrides and malformed allow/deny bodies) is a configuration
    # error, never a previewable approval or an implicit allow. This is the
    # single runtime/preview decision source.
    legacy_external = any(
        external_approval_gate_kinds(layer.policy) for layer in ordered
    )
    if legacy_external:
        final_decision = ApprovalDecision.DENY
        merged_gates = ()
        configuration_error = "approval_gate_external_audience_unsupported"
    else:
        if final_decision == ApprovalDecision.DENY:
            merged_gates = ()
        if require_caller_confirmation and final_decision != ApprovalDecision.DENY:
            # An explicit Agent confirmation can never be relaxed by a tool or
            # stored layer operation override: it applies to every operation.
            final_decision = ApprovalDecision.REQUIRE_APPROVAL
            merged_gates = _merge_gates(
                (*merged_gates, ApprovalGate(kind=ApprovalGateKind.CALLER))
            )
            sources.append("agent_confirmation")
        if final_decision == ApprovalDecision.REQUIRE_APPROVAL:
            if not merged_gates:
                configuration_errors.append("approval_audience_missing")
            if (
                not entrypoint_interactive
                and not caller_self_approvable
                and any(gate.kind == ApprovalGateKind.CALLER for gate in merged_gates)
            ):
                configuration_errors.append("approval_audience_unavailable")
        configuration_error = configuration_errors[0] if configuration_errors else None
    fingerprint = _evaluation_hash(
        operation=normalized_operation,
        entrypoint_interactive=entrypoint_interactive,
        layers=ordered,
        decision=final_decision,
        gates=merged_gates,
    )
    return PolicyEvaluation(
        decision=final_decision,
        gates=merged_gates,
        policy_hash=fingerprint,
        sources=tuple(sources),
        configuration_error=configuration_error,
    )


# ---------------------------------------------------------------------------
# Parameter snapshots and redaction
# ---------------------------------------------------------------------------


def _normalize_sensitive_keys(
    keys: Iterable[str],
) -> tuple[frozenset[str], frozenset[str]]:
    leaf_names: set[str] = set()
    paths: set[str] = set()
    for raw in keys:
        if not isinstance(raw, str):
            raise _input_invalid("Sensitive field names must be strings")
        name = raw.strip()
        if not name:
            continue
        if len(name) > 200 or any(ord(char) < 32 for char in name):
            raise _input_invalid("Invalid sensitive field name")
        normalized = name.lower()
        if "." in normalized:
            paths.add(normalized)
        else:
            leaf_names.add(normalized)
    leaf_names.update(_ALWAYS_SENSITIVE_KEYS)
    return frozenset(leaf_names), frozenset(paths)


def _is_sensitive(
    leaf_name: str,
    path: str,
    sensitive_leafs: frozenset[str],
    sensitive_paths: frozenset[str],
) -> bool:
    leaf = leaf_name.lower()
    lowered_path = path.lower()
    return leaf in sensitive_leafs or lowered_path in sensitive_paths


def _preview_value(
    value: Any,
    *,
    path: str,
    sensitive_leafs: frozenset[str],
    sensitive_paths: frozenset[str],
    redacted: set[str],
    depth: int,
) -> Any:
    if depth > 6:
        return TRUNCATED
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        keys = sorted(value.keys(), key=str)[:100]
        for key in keys:
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if _is_sensitive(key_text, child_path, sensitive_leafs, sensitive_paths):
                redacted.add(child_path)
                result[key_text] = REDACTED
            else:
                result[key_text] = _preview_value(
                    value[key],
                    path=child_path,
                    sensitive_leafs=sensitive_leafs,
                    sensitive_paths=sensitive_paths,
                    redacted=redacted,
                    depth=depth + 1,
                )
        if len(value) > len(keys):
            result["_truncated"] = True
        return result
    if isinstance(value, (list, tuple)):
        items = [
            _preview_value(
                item,
                path=f"{path}[{index}]",
                sensitive_leafs=sensitive_leafs,
                sensitive_paths=sensitive_paths,
                redacted=redacted,
                depth=depth + 1,
            )
            for index, item in enumerate(value[:50])
        ]
        if len(value) > 50:
            items.append(TRUNCATED)
        return items
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}…(truncated)"
    return value


def redact_parameters(
    parameters: Mapping[str, Any],
    sensitive_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a reviewer-safe preview; never contains declared secret values."""
    sensitive_leafs, sensitive_paths = _normalize_sensitive_keys(sensitive_keys)
    redacted: set[str] = set()
    preview = _preview_value(
        parameters,
        path="",
        sensitive_leafs=sensitive_leafs,
        sensitive_paths=sensitive_paths,
        redacted=redacted,
        depth=0,
    )
    if not isinstance(preview, dict):
        preview = {"value": preview}
    if _utf8_size(_canonical_json(preview)) > MAX_PREVIEW_BYTES:
        return {
            "_truncated": True,
            "_keys": sorted(str(key) for key in parameters.keys())[:100],
        }
    return preview


def build_parameter_snapshot(
    parameters: Mapping[str, Any],
    *,
    sensitive_keys: Iterable[str] = (),
) -> ParameterSnapshot:
    """Encrypt full parameters and build a redacted preview.

    The digest binds the *full* parameter map (including secret values), so any
    later change invalidates an approval even when the preview looks the same.
    """
    if not isinstance(parameters, Mapping):
        raise _input_invalid("Execution parameters must be an object")
    try:
        jsonable = _jsonable(dict(parameters))
    except BusinessError:
        raise
    canonical = _canonical_json(jsonable)
    if _utf8_size(canonical) > MAX_PARAMETERS_BYTES:
        raise _input_invalid("Execution parameters are too large")
    sensitive_leafs, sensitive_paths = _normalize_sensitive_keys(sensitive_keys)
    redacted: set[str] = set()
    preview_value = _preview_value(
        jsonable,
        path="",
        sensitive_leafs=sensitive_leafs,
        sensitive_paths=sensitive_paths,
        redacted=redacted,
        depth=0,
    )
    preview = (
        preview_value if isinstance(preview_value, dict) else {"value": preview_value}
    )
    if _utf8_size(_canonical_json(preview)) > MAX_PREVIEW_BYTES:
        preview = {
            "_truncated": True,
            "_keys": sorted(str(key) for key in jsonable.keys())[:100],
        }
    try:
        ciphertext = encrypt_tool_secret(canonical)
    except Exception as exc:  # pragma: no cover - deployment key failure
        logger.exception("Failed to encrypt tool execution parameters")
        raise _error(
            ResponseCode.TOOL_EXECUTION_PARAMETERS_UNREADABLE,
            "Tool execution parameters could not be encrypted",
            msg_key="tool_execution_parameters_unreadable",
            status_code=500,
        ) from exc
    return ParameterSnapshot(
        ciphertext=ciphertext,
        digest=_sha256(canonical),
        preview=preview,
        redacted_paths=tuple(sorted(redacted)),
    )


# ---------------------------------------------------------------------------
# Connection binding
# ---------------------------------------------------------------------------


def _binding_value(binding: Any, name: str, default: Any = None) -> Any:
    if binding is None:
        return default
    if isinstance(binding, Mapping):
        return binding.get(name, default)
    return getattr(binding, name, default)


def _coerce_uuid(value: Any, field_name: str) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise _BindingSnapshotError(f"{field_name}_invalid") from exc


def _normalize_binding(
    binding: "ConnectionBinding | Mapping[str, Any]",
) -> _BindingFacts:
    connection_id = _coerce_uuid(
        _binding_value(binding, "connection_id"), "connection_id"
    )
    if connection_id is None:
        raise _BindingSnapshotError("connection_id_missing")
    team_id = _coerce_uuid(_binding_value(binding, "team_id"), "team_id")
    owner_user_id = _coerce_uuid(
        _binding_value(binding, "owner_user_id"), "owner_user_id"
    )
    effective_user_id = _coerce_uuid(
        _binding_value(binding, "effective_user_id"), "effective_user_id"
    )
    scope = str(_enum_value(_binding_value(binding, "scope")) or "").strip()
    if scope not in {"user", "team", "site"}:
        raise _BindingSnapshotError("connection_scope_invalid")
    status = str(_enum_value(_binding_value(binding, "status")) or "").strip()
    if not status:
        raise _BindingSnapshotError("connection_status_missing")
    try:
        secret_version = int(_binding_value(binding, "secret_version"))
    except (TypeError, ValueError) as exc:
        raise _BindingSnapshotError("connection_version_invalid") from exc
    if secret_version < 1:
        raise _BindingSnapshotError("connection_version_invalid")
    is_active_raw = _binding_value(binding, "is_active", None)
    is_active = bool(is_active_raw) if is_active_raw is not None else status == "active"
    if not is_active or status != "active":
        raise _BindingSnapshotError("connection_inactive")
    if scope == "user":
        if owner_user_id is None:
            raise _BindingSnapshotError("connection_owner_required")
        if effective_user_id is None or effective_user_id != owner_user_id:
            raise _BindingSnapshotError("connection_effective_user_mismatch")
    else:
        if owner_user_id is not None or effective_user_id is not None:
            raise _BindingSnapshotError("connection_owner_unexpected")
    return _BindingFacts(
        connection_id=connection_id,
        team_id=team_id,
        scope=scope,
        owner_user_id=owner_user_id,
        effective_user_id=effective_user_id,
        secret_version=secret_version,
        status=status,
        is_active=is_active,
    )


def _validate_new_binding(
    facts: _BindingFacts,
    *,
    execution_team_id: UUID,
    actor_user_id: UUID,
    operation: str,
    interactive: bool,
) -> UUID | None:
    """Validate a fresh resolver snapshot and return the effective user id."""
    if facts.team_id is not None and facts.team_id != execution_team_id:
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "Connection belongs to a different team",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )
    if facts.scope == "user":
        assert facts.owner_user_id is not None
        return facts.effective_user_id
    return None


def _binding_matches_execution(
    execution: ToolExecution, facts: _BindingFacts
) -> str | None:
    """Return a mismatch code, or ``None`` when the snapshot still binds."""
    if execution.connection_id != facts.connection_id:
        return "connection_changed"
    if execution.team_id != facts.team_id and facts.team_id is not None:
        return "connection_team_changed"
    if execution.connection_version != facts.secret_version:
        return "connection_version_changed"
    if execution.connection_scope != facts.scope:
        return "connection_scope_changed"
    if execution.connection_owner_user_id != facts.owner_user_id:
        return "connection_owner_changed"
    if execution.effective_user_id != facts.effective_user_id:
        return "effective_user_changed"
    if not facts.is_active:
        return "connection_inactive"
    return None


def validate_binding_snapshot(
    execution: ToolExecution, binding: "ConnectionBinding | Mapping[str, Any]"
) -> None:
    """Public preflight helper used by execution entrypoints."""
    try:
        facts = _normalize_binding(binding)
    except _BindingSnapshotError as exc:
        raise _error(
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
            "The connection binding changed",
            msg_key="tool_approval_binding_changed",
            status_code=409,
            data={"reason": str(exc)},
        ) from exc
    mismatch = _binding_matches_execution(execution, facts)
    if mismatch:
        raise _error(
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
            "The connection binding changed",
            msg_key="tool_approval_binding_changed",
            status_code=409,
            data={"reason": mismatch},
        )


# ---------------------------------------------------------------------------
# Binding hash
# ---------------------------------------------------------------------------


def compute_binding_hash(
    *,
    tool_id: UUID,
    tool_definition_version: int,
    operation: str,
    actor_user_id: UUID,
    effective_user_id: UUID | None,
    team_id: UUID,
    entrypoint: ExecutionEntrypoint,
    entrypoint_id: str | None,
    run_kind: ExecutionRunKind | None,
    run_id: UUID | None,
    tool_call_id: str | None,
    connection_id: UUID | None,
    connection_version: int | None,
    connection_scope: str | None,
    connection_owner_user_id: UUID | None,
    parameters_digest: str,
    policy_hash: str,
    expires_at: datetime | None,
) -> str:
    """Deterministic hash binding identity, definition, connection and params."""
    payload = {
        "tool_id": str(tool_id),
        "tool_definition_version": tool_definition_version,
        "operation": operation,
        "actor_user_id": str(actor_user_id),
        "effective_user_id": str(effective_user_id) if effective_user_id else None,
        "team_id": str(team_id),
        "entrypoint": _enum_value(entrypoint),
        "entrypoint_id": entrypoint_id,
        "run_kind": _enum_value(run_kind) if run_kind else None,
        "run_id": str(run_id) if run_id else None,
        "tool_call_id": tool_call_id,
        "connection_id": str(connection_id) if connection_id else None,
        "connection_version": connection_version,
        "connection_scope": connection_scope,
        "connection_owner_user_id": str(connection_owner_user_id)
        if connection_owner_user_id
        else None,
        "parameters_digest": parameters_digest,
        "policy_hash": policy_hash,
        "expires_at": _iso(expires_at),
    }
    return _sha256(_canonical_json(payload))


def binding_hash_for_execution(execution: ToolExecution) -> str:
    """Recompute the stored binding hash from an execution row."""
    return compute_binding_hash(
        tool_id=execution.tool_id,
        tool_definition_version=execution.tool_definition_version,
        operation=execution.operation,
        actor_user_id=execution.actor_user_id,
        effective_user_id=execution.effective_user_id,
        team_id=execution.team_id,
        entrypoint=execution.entrypoint,
        entrypoint_id=execution.entrypoint_id,
        run_kind=execution.run_kind,
        run_id=execution.run_id,
        tool_call_id=execution.tool_call_id,
        connection_id=execution.connection_id,
        connection_version=execution.connection_version,
        connection_scope=execution.connection_scope,
        connection_owner_user_id=execution.connection_owner_user_id,
        parameters_digest=execution.parameters_digest,
        policy_hash=execution.policy_hash,
        expires_at=execution.expires_at,
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def _resolve_deadline(
    requested: datetime | None, *, now: datetime, default: timedelta
) -> datetime:
    deadline = _as_utc(requested) if requested is not None else now + default
    assert deadline is not None
    if deadline <= now:
        raise _input_invalid("Execution expiry must be in the future")
    if deadline > now + MAX_EXECUTION_TTL:
        raise _input_invalid("Execution expiry is too far in the future")
    return deadline


def _is_expired(value: datetime | None, now: datetime) -> bool:
    normalized = _as_utc(value)
    return normalized is not None and normalized <= now


async def _require_team_membership(actor: User, team_id: UUID) -> None:
    if getattr(actor, "is_superuser", False):
        return
    exists = await TeamMember.filter(team_id=team_id, user_id=actor.id).exists()
    if not exists:
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "You do not have access to this team's tool executions",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )


async def _plan_gates(
    evaluation: PolicyEvaluation,
    *,
    actor: User,
    team_id: UUID,
    interactive: bool,
    caller_self_approvable: bool = False,
) -> list[_GatePlan]:
    if evaluation.configuration_error:
        raise _policy_configuration_required(evaluation.configuration_error)
    if evaluation.decision != ApprovalDecision.REQUIRE_APPROVAL:
        return []

    plans: list[_GatePlan] = []
    used_keys: set[str] = set()
    for gate in evaluation.gates:
        stage_key = gate_stage_key(gate)
        if stage_key in used_keys:
            continue
        used_keys.add(stage_key)
        if gate.kind == ApprovalGateKind.CALLER:
            if not interactive and not caller_self_approvable:
                raise _policy_configuration_required("approval_audience_unavailable")
            plans.append(
                _GatePlan(
                    gate=gate,
                    stage_index=len(plans),
                    stage_key=stage_key,
                    approver_user_ids=(),
                    approver_roles=(),
                )
            )
            continue
        raise _policy_configuration_required("approval_external_audience_unsupported")

    if not plans:
        raise _policy_configuration_required("approval_audience_missing")
    return plans


def _display_payload(
    *,
    tool: "Tool",
    operation: str,
    preview: Mapping[str, Any],
    entrypoint: ExecutionEntrypoint,
    entrypoint_id: str | None,
    run_kind: ExecutionRunKind | None,
    run_id: UUID | None,
    tool_call_id: str | None,
    connection_id: UUID | None,
    connection_scope: str | None,
    connection_account_label: str | None,
    effective_user_id: UUID | None,
    sources: Sequence[str],
) -> dict[str, Any]:
    return {
        "tool_id": str(tool.id),
        "tool_name": getattr(tool, "display_name", None) or getattr(tool, "name", None),
        "operation": operation,
        "parameters": dict(preview),
        "entrypoint": entrypoint.value,
        "entrypoint_id": entrypoint_id,
        "run_kind": run_kind.value if run_kind else None,
        "run_id": str(run_id) if run_id else None,
        "tool_call_id": tool_call_id,
        "connection": (
            {
                "connection_id": str(connection_id),
                "scope": connection_scope,
                "account_label": connection_account_label,
                "effective_user_id": (
                    str(effective_user_id) if effective_user_id else None
                ),
            }
            if connection_id
            else None
        ),
        "policy_sources": list(sources),
        "note": "Approval binds this exact operation and parameter digest; editing parameters requires a new execution.",
    }


def _execution_api_key_id(
    entrypoint: ExecutionEntrypoint, entrypoint_id: str | None
) -> UUID | None:
    """The authenticating API key of an ``api_key`` entrypoint execution.

    The identity comes from the trusted runtime scope set by the run submitter,
    never from request data. ``entrypoint_id`` is the server-derived key id and
    covers payloads created before the explicit field existed.
    """
    if getattr(entrypoint, "value", entrypoint) != ExecutionEntrypoint.API_KEY.value:
        return None
    from app.services.tool_context import current_tool_identity

    identity = current_tool_identity()
    candidate: Any = None
    if identity is not None:
        identity_entrypoint = getattr(identity, "entrypoint", None)
        if identity_entrypoint in (None, ExecutionEntrypoint.API_KEY.value):
            candidate = getattr(identity, "api_key_id", None)
    if candidate is None and entrypoint_id:
        candidate = entrypoint_id
    if candidate is None:
        return None
    try:
        return UUID(str(candidate))
    except (TypeError, ValueError):
        return None


async def create_execution(
    *,
    tool: "Tool",
    operation: str,
    parameters: Mapping[str, Any],
    actor: User,
    team_id: UUID,
    entrypoint: ExecutionEntrypoint,
    entrypoint_id: str | None = None,
    run_kind: ExecutionRunKind | None = None,
    run_id: UUID | None = None,
    tool_call_id: str | None = None,
    connection_binding: "ConnectionBinding | Mapping[str, Any] | None" = None,
    connection_account_label: str | None = None,
    effective_user_id: UUID | None = None,
    policy_layers: Sequence[PolicyLayer] = (),
    policy: Mapping[str, Any] | ToolApprovalPolicy | None = None,
    tool_definition_version: int | None = None,
    sensitive_fields: Iterable[str] = (),
    entrypoint_interactive: bool | None = None,
    require_caller_confirmation: bool = False,
    expires_at: datetime | None = None,
    now: datetime | None = None,
    preview_parameters: Mapping[str, Any] | None = None,
) -> ToolExecution:
    """Evaluate policy and persist one immutable execution request.

    Returns an execution that is:

    * ``ready`` — policy allowed it; the caller may claim and execute;
    * ``awaiting_approval`` — gates are persisted; no side effect may start;
    * ``cancelled`` with ``cancel_reason=policy_denied`` — policy denied it.

    A policy/audience configuration failure raises instead of persisting or
    allowing anything.

    ``preview_parameters`` is an optional reviewer projection: when supplied,
    the stored preview is derived from it rather than from ``parameters``.
    Digest, ciphertext and dispatch always use ``parameters``. Callers use it
    to keep execution-only options (for example an orchestration-selected
    search engine) out of the approval display.
    """
    current = _as_utc(now) or _utcnow()
    if not getattr(actor, "is_active", True):
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "Inactive users cannot execute tools",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )
    if not getattr(tool, "is_enabled", True):
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "The tool is disabled",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )
    normalized_operation = operation.strip()
    if not normalized_operation or len(normalized_operation) > 200:
        raise _input_invalid(
            "Operation must be a non-empty string up to 200 characters"
        )
    if any(ord(char) < 32 for char in normalized_operation):
        raise _input_invalid("Operation contains control characters")
    if (run_kind is None) != (run_id is None):
        raise _input_invalid("run_kind and run_id must be provided together")
    if tool_call_id is not None and run_id is None:
        raise _input_invalid("tool_call_id requires a durable run")
    if entrypoint_id is not None and len(entrypoint_id) > 200:
        raise _input_invalid("entrypoint_id is too long")
    if connection_account_label is not None and len(connection_account_label) > 150:
        raise _input_invalid("connection_account_label is too long")
    await _require_team_membership(actor, team_id)

    interactive = (
        entrypoint_interactive
        if entrypoint_interactive is not None
        else entrypoint not in NON_INTERACTIVE_ENTRYPOINTS
    )
    if not interactive and not entrypoint_id:
        raise _input_invalid("Non-interactive entrypoints require entrypoint_id")

    tool_layer = PolicyLayer(
        source=PolicySource.TOOL,
        label="tool",
        policy=normalize_tool_approval_policy(
            policy if policy is not None else getattr(tool, "approval_policy", None)
        ),
    )
    layers = [*policy_layers, tool_layer]
    # An API-key Agent run is non-interactive, but the authenticated key can
    # still decide the caller gate it triggered. This never widens the gates.
    execution_api_key_id = _execution_api_key_id(entrypoint, entrypoint_id)
    # A non-interactive caller gate may wait for approval only when the call is
    # bound to an authenticated key identity. An ``api_key`` entrypoint whose
    # id resolves to nothing has no audience and must fail closed as before.
    caller_self_approvable = execution_api_key_id is not None
    try:
        evaluation = evaluate_policy(
            layers,
            normalized_operation,
            entrypoint_interactive=interactive,
            require_caller_confirmation=require_caller_confirmation,
            caller_self_approvable=caller_self_approvable,
        )
    except PolicyConfigurationError as exc:
        raise _policy_configuration_required(exc.code) from exc
    if evaluation.configuration_error:
        raise _policy_configuration_required(evaluation.configuration_error)

    definition_version = tool_definition_version
    if definition_version is None:
        definition_version = int(getattr(tool, "definition_version", 1) or 1)
    if definition_version < 1:
        raise _input_invalid("tool_definition_version must be >= 1")

    snapshot = build_parameter_snapshot(parameters, sensitive_keys=sensitive_fields)
    if preview_parameters is not None:
        # The digest and ciphertext always bind the executed parameters. The
        # reviewer preview may instead project the caller's business argument
        # object, excluding orchestration-injected options, under the same
        # redaction policy.
        snapshot = replace(
            snapshot,
            preview=redact_parameters(
                preview_parameters, sensitive_keys=sensitive_fields
            ),
            redacted_paths=(),
        )
    facts: _BindingFacts | None = None
    if connection_binding is not None:
        try:
            facts = _normalize_binding(connection_binding)
            resolved_effective_user = _validate_new_binding(
                facts,
                execution_team_id=team_id,
                actor_user_id=actor.id,
                operation=normalized_operation,
                interactive=interactive,
            )
        except _BindingSnapshotError as exc:
            raise _input_invalid("Connection binding is invalid") from exc
        resolved_effective_user_id = resolved_effective_user
        connection_id = facts.connection_id
        connection_version = facts.secret_version
        connection_scope = facts.scope
        connection_owner_user_id = facts.owner_user_id
        if (
            effective_user_id is not None
            and resolved_effective_user_id != effective_user_id
        ):
            raise _error(
                ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
                "Effective principal does not match the connection owner",
                msg_key="tool_execution_access_denied",
                status_code=403,
            )
    else:
        if effective_user_id is not None and effective_user_id != actor.id:
            raise _error(
                ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
                "An execution without a connection cannot use another user's identity",
                msg_key="tool_execution_access_denied",
                status_code=403,
            )
        resolved_effective_user_id = effective_user_id or actor.id
        connection_id = None
        connection_version = None
        connection_scope = None
        connection_owner_user_id = None

    default_ttl = (
        DEFAULT_APPROVAL_TTL
        if evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL
        else DEFAULT_READY_TTL
    )
    deadline = _resolve_deadline(expires_at, now=current, default=default_ttl)

    binding_digest = compute_binding_hash(
        tool_id=tool.id,
        tool_definition_version=definition_version,
        operation=normalized_operation,
        actor_user_id=actor.id,
        effective_user_id=resolved_effective_user_id,
        team_id=team_id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
        run_kind=run_kind,
        run_id=run_id,
        tool_call_id=tool_call_id,
        connection_id=connection_id,
        connection_version=connection_version,
        connection_scope=connection_scope,
        connection_owner_user_id=connection_owner_user_id,
        parameters_digest=snapshot.digest,
        policy_hash=evaluation.policy_hash,
        expires_at=deadline,
    )
    display = _display_payload(
        tool=tool,
        operation=normalized_operation,
        preview=snapshot.preview,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
        run_kind=run_kind,
        run_id=run_id,
        tool_call_id=tool_call_id,
        connection_id=connection_id,
        connection_scope=connection_scope,
        connection_account_label=connection_account_label,
        effective_user_id=resolved_effective_user_id,
        sources=evaluation.sources,
    )
    policy_snapshot = {
        "evaluation": evaluation.model_dump(mode="json"),
        "layers": [
            {
                "source": layer.source.value,
                "label": layer.label,
                "policy": layer.policy.model_dump(mode="json"),
            }
            for layer in _ordered_layers(layers)
        ],
    }
    if _utf8_size(_canonical_json(policy_snapshot)) > MAX_POLICY_SNAPSHOT_BYTES:
        raise _policy_configuration_required("approval_policy_snapshot_too_large")

    gate_plans = await _plan_gates(
        evaluation,
        actor=actor,
        team_id=team_id,
        interactive=interactive,
        caller_self_approvable=caller_self_approvable,
    )

    if evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL:
        status = ToolExecutionStatus.AWAITING_APPROVAL
        cancel_reason = None
        finished_at = None
    elif evaluation.decision == ApprovalDecision.ALLOW:
        status = ToolExecutionStatus.READY
        cancel_reason = None
        finished_at = None
    else:
        status = ToolExecutionStatus.CANCELLED
        cancel_reason = ToolExecutionCancelReason.POLICY_DENIED
        finished_at = current

    execution = ToolExecution(
        actor_user_id=actor.id,
        effective_user_id=resolved_effective_user_id,
        team_id=team_id,
        tool_id=tool.id,
        tool_definition_version=definition_version,
        operation=normalized_operation,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
        api_key_id=execution_api_key_id,
        run_kind=run_kind,
        run_id=run_id,
        tool_call_id=tool_call_id,
        connection_id=connection_id,
        connection_version=connection_version,
        connection_scope=connection_scope,
        connection_owner_user_id=connection_owner_user_id,
        connection_account_label=connection_account_label,
        parameters_cipher=snapshot.ciphertext,
        parameters_digest=snapshot.digest,
        parameters_preview=snapshot.preview,
        policy_snapshot=policy_snapshot,
        policy_hash=evaluation.policy_hash,
        binding_hash=binding_digest,
        status=status,
        cancel_reason=cancel_reason,
        finished_at=finished_at,
        expires_at=deadline,
    )
    execution.validate_invariants()

    async with in_transaction() as conn:
        await execution.save(using_db=conn)
        for plan in gate_plans:
            request = ToolApprovalRequest(
                execution_id=execution.id,
                stage_index=plan.stage_index,
                stage_key=plan.stage_key,
                gate_kind=plan.gate.kind,
                approver_user_ids=list(plan.approver_user_ids),
                approver_roles=list(plan.approver_roles),
                allow_self_approval=plan.gate.allow_self_approval,
                masked_display=display,
                status=ApprovalRequestStatus.PENDING,
                expires_at=deadline,
            )
            request.validate_invariants()
            await request.save(using_db=conn)
    return execution


# ---------------------------------------------------------------------------
# Loading / authorization
# ---------------------------------------------------------------------------


async def get_execution(execution_id: UUID) -> ToolExecution:
    execution = await ToolExecution.filter(id=execution_id).first()
    if execution is None:
        raise _not_found(execution=True)
    return execution


async def find_execution_by_tool_call(
    *, run_kind: ExecutionRunKind, run_id: UUID, tool_call_id: str
) -> ToolExecution | None:
    """Lookup the execution created for a deferred durable tool call."""
    return (
        await ToolExecution.filter(
            run_kind=run_kind,
            run_id=run_id,
            tool_call_id=tool_call_id,
        )
        .order_by("-created_at")
        .first()
    )


async def list_run_executions(
    *,
    run_kind: ExecutionRunKind,
    run_id: UUID,
    tool_call_id: str | None = None,
) -> list[ToolExecution]:
    query = ToolExecution.filter(run_kind=run_kind, run_id=run_id)
    if tool_call_id is not None:
        query = query.filter(tool_call_id=tool_call_id)
    return await query.order_by("created_at")


async def list_executions_for_actor(
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    status: ToolExecutionStatus | None = None,
    tool_id: UUID | None = None,
    run_kind: ExecutionRunKind | None = None,
    run_id: UUID | None = None,
    api_key: Any | None = None,
) -> tuple[list[ToolExecution], int]:
    """Durable executions initiated by ``user`` (secret-safe projections).

    With ``api_key`` the listing is narrowed to that exact credential (never
    merely its owner) and to the key's current Agent scope.
    """
    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 100))
    if (run_kind is None) != (run_id is None):
        raise _input_invalid("run_kind and run_id must be provided together")
    query = ToolExecution.filter(actor_user_id=user.id)
    if api_key is not None:
        scope = await _api_key_execution_scope(api_key)
        if scope is None:
            return [], 0
        query = query.filter(scope)
    if status is not None:
        query = query.filter(status=status)
    if tool_id is not None:
        query = query.filter(tool_id=tool_id)
    if run_kind is not None:
        query = query.filter(run_kind=run_kind, run_id=run_id)
    total = await query.count()
    executions = (
        await query.order_by("-created_at")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return executions, total


def _is_team_admin(member: TeamMember | None) -> bool:
    return member is not None and member.role in {"owner", "admin"}


def stored_api_key_id(execution: ToolExecution) -> UUID | None:
    """Credential that owns an execution, explicit or legacy entrypoint id."""
    stored = getattr(execution, "api_key_id", None)
    if stored is not None:
        try:
            return UUID(str(stored))
        except (TypeError, ValueError):
            return None
    if (
        _enum_value(execution.entrypoint) != ExecutionEntrypoint.API_KEY.value
        or not execution.entrypoint_id
    ):
        return None
    try:
        return UUID(str(execution.entrypoint_id))
    except (TypeError, ValueError):
        return None


async def _api_key_agent_ids(api_key: Any) -> list[UUID]:
    """Agent scope of one key; empty means every Agent (legacy keys)."""
    agents = await api_key.agents.all()
    return [agent.id for agent in agents]


async def _api_key_is_live(api_key: Any) -> bool:
    """Authoritative credential check against the stored key row.

    The in-memory flag is only a fast path: a key revoked or expired between
    authentication and a later operation must neither decide nor be listed.
    """
    key_id = getattr(api_key, "id", None)
    if key_id is None or not getattr(api_key, "is_active", True):
        return False
    from app.core.timezone import now_utc
    from app.models.api_key import APIKey

    return await (
        APIKey.filter(id=key_id, is_active=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now_utc()))
        .exists()
    )


async def _api_key_bound_run_ids(api_key: Any) -> Subquery | None:
    """Runs this credential may see, as an ``IN`` subquery (never materialized).

    Mirrors the detail constraints: the run must exist, belong to the key owner,
    be bound to the same key and stay inside the key's current Agent scope.

    Legacy AgentRuns persisted before API-key binding existed (NULL key id) are
    deliberately excluded, even when their worker payload names this key: the
    payload cannot be checked portably in SQL across databases, so a key-scoped
    list fails closed instead of risking mismatched metadata. Detail and
    decision by explicit id still validate the legacy payload evidence.
    """
    if not await _api_key_is_live(api_key):
        return None
    from app.models.agent_run import AgentRun

    key_id = getattr(api_key, "id", None)
    run_q = Q(user_id=getattr(api_key, "user_id", None), api_key_id=key_id)
    agent_ids = await _api_key_agent_ids(api_key)
    if agent_ids:
        run_q &= Q(agent_id__in=agent_ids)
    return Subquery(AgentRun.filter(run_q).values("id"))


async def execution_owned_by_api_key(execution: ToolExecution, api_key: Any) -> bool:
    """Whether this exact active key credential, not just its owner, owns it.

    Binding requires the stored key id, the key owner as actor, an Agent run
    and the key's current Agent scope. A second key owned by the same user is
    rejected, and narrowing the key's Agent scope revokes future decisions.
    """
    key_id = getattr(api_key, "id", None)
    if key_id is None or not await _api_key_is_live(api_key):
        return False
    stored = stored_api_key_id(execution)
    if stored is None or str(stored) != str(key_id):
        return False
    if str(execution.actor_user_id) != str(getattr(api_key, "user_id", None)):
        return False
    if (
        _enum_value(execution.run_kind) != ExecutionRunKind.AGENT.value
        or execution.run_id is None
    ):
        return False
    from app.models.agent_run import AgentRun

    run = await AgentRun.filter(id=execution.run_id).first()
    if run is None:
        return False
    if str(getattr(run, "user_id", "")) != str(getattr(api_key, "user_id", "")):
        return False
    # The owning run must agree with the execution binding. Pre-column runs
    # carry the same identity in their worker payload; a run with no evidence
    # at all is a legacy row and keeps the execution binding alone.
    run_key_id = getattr(run, "api_key_id", None)
    if run_key_id is None:
        payload = run.worker_payload if isinstance(run.worker_payload, dict) else {}
        run_key_id = payload.get("api_key_id")
        if not run_key_id and payload.get("tool_entrypoint") == "api_key":
            run_key_id = payload.get("tool_entrypoint_id")
    if run_key_id is not None and str(run_key_id) != str(key_id):
        return False
    agent_ids = await _api_key_agent_ids(api_key)
    return not agent_ids or run.agent_id in agent_ids


async def _api_key_execution_scope(api_key: Any) -> Q | None:
    """Execution query scope for one key; ``None`` means no row may match.

    The run restriction is an ``IN`` subquery so pagination/counts stay exact
    without materializing run ids, and so a corrupt or legacy execution whose
    run is missing, owned by someone else or bound to another key is invisible.
    """
    key_id = getattr(api_key, "id", None)
    if key_id is None:
        return None
    runs = await _api_key_bound_run_ids(api_key)
    if runs is None:
        return None
    binding = Q(api_key_id=key_id) | Q(
        api_key_id__isnull=True,
        entrypoint=ExecutionEntrypoint.API_KEY,
        entrypoint_id=str(key_id),
    )
    return binding & Q(
        run_kind=ExecutionRunKind.AGENT,
        run_id__isnull=False,
        run_id__in=runs,
    )


async def _api_key_request_scope(api_key: Any) -> Q | None:
    """Approval-request query scope mirroring the execution binding."""
    key_id = getattr(api_key, "id", None)
    if key_id is None:
        return None
    runs = await _api_key_bound_run_ids(api_key)
    if runs is None:
        return None
    binding = Q(execution__api_key_id=key_id) | Q(
        execution__api_key_id__isnull=True,
        execution__entrypoint=ExecutionEntrypoint.API_KEY,
        execution__entrypoint_id=str(key_id),
    )
    return binding & Q(
        execution__run_kind=ExecutionRunKind.AGENT,
        execution__run_id__isnull=False,
        execution__run_id__in=runs,
    )


async def can_view_execution(
    execution: ToolExecution, user: User, *, api_key: Any | None = None
) -> bool:
    """Execution initiator/effective principal, or a current team owner/admin.

    Approving is stricter: an approver sees the masked approval display via
    the approval endpoints, not this execution projection.

    With an API key the credential is the only audience: the key must own the
    execution and still be allowed the Agent owning its run.
    """
    if not getattr(user, "is_active", True):
        return False
    if api_key is not None:
        return await execution_owned_by_api_key(execution, api_key)
    if user.id in {execution.actor_user_id, execution.effective_user_id}:
        return True
    member = await TeamMember.filter(team_id=execution.team_id, user_id=user.id).first()
    return _is_team_admin(member)


async def get_execution_for_viewer(
    execution_id: UUID, user: User, *, api_key: Any | None = None
) -> ToolExecution:
    execution = await get_execution(execution_id)
    if not await can_view_execution(execution, user, api_key=api_key):
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "You do not have permission to view this tool execution",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )
    return execution


def _request_audience_matches(
    request: ToolApprovalRequest,
    execution: ToolExecution,
    user: User,
    *,
    team_role: str | None,
    is_team_member: bool,
) -> bool:
    if not getattr(user, "is_active", True):
        return False
    user_id = str(user.id)
    if request.gate_kind == ApprovalGateKind.CALLER:
        # The actor confirms their own access-authorized operation; execution
        # authorization is rechecked separately before any side effect.
        return str(execution.actor_user_id) == user_id
    # Historical external audiences are never authorized after the cutover.
    return False


async def can_view_approval_request(
    request: ToolApprovalRequest,
    execution: ToolExecution,
    user: User,
    *,
    now: datetime | None = None,
    api_key: Any | None = None,
) -> bool:
    """Whether ``user`` is in this gate's audience (never a superuser bypass).

    An API key sees only gates of executions bound to that credential.
    """
    current = _as_utc(now) or _utcnow()
    if _is_expired(execution.expires_at, current) and execution.status not in {
        ToolExecutionStatus.SUCCEEDED,
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.OUTCOME_UNKNOWN,
        ToolExecutionStatus.CANCELLED,
    }:
        return False
    if api_key is not None:
        if not await execution_owned_by_api_key(execution, api_key):
            return False
        return _request_audience_matches(
            request,
            execution,
            user,
            team_role=None,
            is_team_member=False,
        )
    member = await TeamMember.filter(team_id=execution.team_id, user_id=user.id).first()
    if member is None:
        return False
    return _request_audience_matches(
        request,
        execution,
        user,
        team_role=member.role,
        is_team_member=True,
    )


async def get_approval_request_for_viewer(
    request_id: UUID,
    user: User,
    *,
    now: datetime | None = None,
    api_key: Any | None = None,
) -> ToolApprovalRequest:
    request = (
        await ToolApprovalRequest.filter(id=request_id)
        .prefetch_related("execution")
        .first()
    )
    if request is None:
        raise _not_found()
    execution = request.execution
    if execution is None:
        raise _not_found()
    if not await can_view_approval_request(
        request, execution, user, now=now, api_key=api_key
    ):
        raise _error(
            ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            "You are not an approver for this request",
            msg_key="tool_approval_not_authorized",
            status_code=403,
        )
    return request


async def list_pending_approvals_for_user(
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    now: datetime | None = None,
    api_key: Any | None = None,
) -> tuple[list[ToolApprovalRequest], int]:
    """Pending gates whose frozen/current audience includes ``user``.

    The scan is bounded; an inbox that exceeds ``MAX_INBOX_SCAN`` pending rows
    is a deployment issue, not a reason to return someone else's request.

    With ``api_key`` the inbox contains only gates of executions owned by that
    exact credential and still inside its Agent scope.
    """
    current = _as_utc(now) or _utcnow()
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    memberships = await TeamMember.filter(user_id=user.id).values_list(
        "team_id", "role"
    )
    role_map = {
        (row[0] if isinstance(row, tuple) else row[0]): (
            row[1] if isinstance(row, tuple) else row[1]
        )
        for row in memberships
    }
    audience_q = Q(gate_kind=ApprovalGateKind.CALLER, execution__actor_user_id=user.id)
    if api_key is not None:
        request_scope = await _api_key_request_scope(api_key)
        if request_scope is None:
            return [], 0
        audience_q &= request_scope

    requests = (
        await ToolApprovalRequest.filter(
            audience_q,
            status=ApprovalRequestStatus.PENDING,
            execution__status=ToolExecutionStatus.AWAITING_APPROVAL,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=current))
        .filter(
            Q(execution__expires_at__isnull=True) | Q(execution__expires_at__gt=current)
        )
        .prefetch_related("execution")
        .order_by("-created_at")
        .limit(MAX_INBOX_SCAN)
    )
    authorized: list[ToolApprovalRequest] = []
    for request in requests:
        execution = request.execution
        if execution is None:
            continue
        team_role = role_map.get(execution.team_id)
        if _request_audience_matches(
            request,
            execution,
            user,
            team_role=team_role,
            is_team_member=team_role is not None,
        ):
            authorized.append(request)
    total = len(authorized)
    start = (page - 1) * page_size
    return authorized[start : start + page_size], total


async def _assert_can_decide(
    request: ToolApprovalRequest,
    execution: ToolExecution,
    approver: User,
    *,
    api_key: Any | None = None,
) -> None:
    if api_key is not None and not await execution_owned_by_api_key(execution, api_key):
        # A key is a credential, not a role: another key of the same owner and
        # a key that lost its Agent scope are both rejected.
        raise _error(
            ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            "You are not an approver for this request",
            msg_key="tool_approval_not_authorized",
            status_code=403,
        )
    member = await TeamMember.filter(
        team_id=execution.team_id, user_id=approver.id
    ).first()
    team_role = member.role if member is not None else None
    if not _request_audience_matches(
        request,
        execution,
        approver,
        team_role=team_role,
        is_team_member=member is not None,
    ):
        raise _error(
            ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            "You are not an approver for this request",
            msg_key="tool_approval_not_authorized",
            status_code=403,
        )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def _decision_request_hash(
    request_id: UUID, decision: ApprovalVote, reason: str | None
) -> str:
    return _sha256(
        _canonical_json(
            {
                "request_id": str(request_id),
                "decision": decision.value,
                "reason": reason,
            }
        )
    )


def _verify_replay(
    existing: ToolApprovalDecision,
    *,
    request_id: UUID,
    request_hash: str,
) -> ToolApprovalDecision:
    if existing.request_id != request_id or existing.request_hash != request_hash:
        raise _error(
            ResponseCode.TOOL_APPROVAL_IDEMPOTENCY_CONFLICT,
            "Idempotency key was reused for a different decision",
            msg_key="tool_approval_idempotency_conflict",
            status_code=409,
        )
    return existing


async def _schedule_run_resume(execution_id: UUID) -> None:
    """Best-effort resume of the durable run owning a terminal execution.

    Agent and workflow resume are independent: a missing/failed workflow
    scheduler must not stop an AgentRun from resuming (and vice versa). The
    decision/expiry remains committed even if dispatch fails; each runtime
    records its own enqueue failure.
    """
    execution = await ToolExecution.filter(id=execution_id).first()
    if execution is None:
        return
    try:
        from app.services.agent_run_store import (
            schedule_agent_run_approval_resume,
        )

        await schedule_agent_run_approval_resume(execution)
    except Exception:
        logger.warning(
            "Failed to schedule AgentRun resume for execution %s",
            execution_id,
            exc_info=True,
        )
    try:
        from app.services.workflow.tool_approval_resume import (
            schedule_workflow_run_approval_resume,
        )

        await schedule_workflow_run_approval_resume(execution)
    except ImportError:
        logger.debug("Workflow approval resume module is not available")
    except Exception:
        logger.warning(
            "Failed to schedule WorkflowRun resume for execution %s",
            execution_id,
            exc_info=True,
        )


def _normalize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    cleaned = reason.replace("\x00", "").strip()
    if len(cleaned) > MAX_REASON_LENGTH:
        raise _input_invalid("Approval reason is too long")
    return cleaned or None


# Decision failures worth an audit row: authorization denials, expired gates,
# invalidated bindings and conflicted/repeated decisions. Pure request-shape
# validation (unknown vote, missing idempotency key) stays out of the log.
_DECISION_FAILURE_AUDIT_CODES = frozenset(
    {
        ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
        ResponseCode.TOOL_APPROVAL_EXPIRED,
        ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED,
        ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
        ResponseCode.TOOL_APPROVAL_CONFLICT,
        ResponseCode.TOOL_APPROVAL_IDEMPOTENCY_CONFLICT,
    }
)

_DECISION_ACTIONS = {
    ApprovalVote.APPROVE.value: "approve_tool_execution",
    ApprovalVote.REJECT.value: "reject_tool_execution",
}


def _decision_vote(value: Any) -> str | None:
    try:
        return ApprovalVote(value).value
    except (TypeError, ValueError):
        return None


def _policy_audit_payload(value: Any) -> Any:
    """Default-expanded, JSON-safe policy body for before/after comparison."""
    try:
        return normalize_tool_approval_policy(value).model_dump(mode="json")
    except (TypeError, ValueError):
        return value


def approval_policy_changed(before: Any, after: Any) -> bool:
    """Whether a write really changes the stored approval policy.

    Comparisons use the normalized policy (defaults included) so an explicit
    body that restates the current policy does not emit a second audit event.
    """
    try:
        return _canonical_json(_policy_audit_payload(before)) != _canonical_json(
            _policy_audit_payload(after)
        )
    except (TypeError, ValueError):
        # A malformed stored body is not a valid "unchanged" signal.
        return repr(before) != repr(after)


def _decision_audit_metadata(
    execution: ToolExecution | None,
    *,
    execution_id: UUID | None,
    request_id: UUID | None,
    vote: str | None,
    outcome: str | None,
) -> dict[str, Any]:
    """Minimal non-secret identifiers; parameters and the reason never enter."""
    execution_status = _enum_value(execution.status) if execution is not None else None
    metadata = {
        "execution_id": str(execution.id if execution is not None else execution_id)
        if (execution is not None or execution_id is not None)
        else None,
        "approval_request_id": str(request_id) if request_id is not None else None,
        "team_id": str(execution.team_id) if execution is not None else None,
        "tool_id": str(execution.tool_id) if execution is not None else None,
        "operation": execution.operation if execution is not None else None,
        "entrypoint": _enum_value(execution.entrypoint)
        if execution is not None
        else None,
        "run_kind": _enum_value(execution.run_kind)
        if execution is not None and execution.run_kind is not None
        else None,
        "run_id": str(execution.run_id)
        if execution is not None and execution.run_id is not None
        else None,
        "connection_scope": execution.connection_scope
        if execution is not None
        else None,
        "decision": vote,
        "outcome": outcome,
        "execution_status": execution_status,
    }
    return {key: value for key, value in metadata.items() if value is not None}


async def _audit_decision_event(
    *,
    approver: User,
    vote: str | None,
    execution: ToolExecution | None,
    execution_id: UUID | None,
    request_id: UUID | None,
    outcome: str | None,
    status: str,
    error_message: str | None,
    api_key: Any | None,
    http_request: Request | None,
) -> None:
    """Best-effort audit write.

    The decision is already durable (or was definitively refused); an audit
    failure must never turn it into an API error that invites a retry.
    """
    try:
        from app.services.audit_log import AuditLogService

        await AuditLogService.log(
            user=approver,
            action=_DECISION_ACTIONS.get(vote or "", "decide_tool_execution"),
            resource_type="tool_execution",
            resource_id=(execution.id if execution is not None else execution_id),
            resource_name=(execution.operation if execution is not None else None),
            operation=vote or "decide",
            status=status,
            request=http_request,
            metadata=_decision_audit_metadata(
                execution,
                execution_id=execution_id,
                request_id=request_id,
                vote=vote,
                outcome=outcome,
            ),
            error_message=error_message,
            api_key=api_key,
        )
    except Exception:
        logger.exception(
            "Failed to audit tool approval decision request=%s execution=%s",
            request_id,
            execution_id,
        )


async def audit_tool_approval_policy_update(
    *,
    tool: "Tool",
    before: Any,
    after: Any,
    actor: User,
    http_request: Request | None = None,
    api_key: Any | None = None,
) -> bool:
    """Audit one tool approval-policy change at the definition update boundary.

    Returns ``False`` without writing when the normalized policy is unchanged.
    Only policy structure (decisions, gates, approver ids/roles and declared
    sensitive field names) is recorded; credentials and call arguments never
    enter the audit row.
    """
    if not approval_policy_changed(before, after):
        return False
    try:
        from app.services.audit_log import AuditLogService

        before_payload = _policy_audit_payload(before)
        after_payload = _policy_audit_payload(after)
        await AuditLogService.log(
            user=actor,
            action="update_tool_approval_policy",
            resource_type="tool",
            resource_id=tool.id,
            resource_name=tool.name,
            operation="update",
            status="success",
            request=http_request,
            changes={
                "before": {"approval_policy": before_payload},
                "after": {"approval_policy": after_payload},
            },
            metadata={
                "team_id": str(tool.team_id),
                "definition_version": getattr(tool, "definition_version", None),
                "source": "tool_definition",
            },
            api_key=api_key,
        )
    except Exception:
        # The definition update is already committed; losing the audit row must
        # not report the update as failed and invite a duplicate retry.
        logger.exception("Failed to audit approval policy update tool=%s", tool.id)
    return True


async def _decide_approval_record(
    request_id: UUID,
    approver: User,
    *,
    decision: ApprovalVote,
    idempotency_key: str,
    reason: str | None = None,
    now: datetime | None = None,
    api_key: Any | None = None,
    state: dict[str, Any],
) -> ToolApprovalDecision:
    """Record one decision atomically; audit state is reported to the caller.

    This never executes the tool. The last required approval moves the
    execution to ``ready``; the durable worker claims it separately.

    ``api_key`` is the credential used for authentication, if any. A decision
    made with a key is valid only for an execution bound to that exact key,
    its owner and its current Agent scope.
    """
    current = _as_utc(now) or _utcnow()
    try:
        decision = ApprovalVote(decision)
    except ValueError as exc:
        raise _input_invalid("decision must be approve or reject") from exc
    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise _input_invalid("idempotency_key is required (max 128 characters)")
    normalized_reason = _normalize_reason(reason)
    request_hash = _decision_request_hash(request_id, decision, normalized_reason)

    existing = await ToolApprovalDecision.filter(idempotency_key=key).first()
    if existing is not None:
        state["execution_id"] = existing.execution_id
        # A replay is only meaningful for the approver who made the decision;
        # otherwise the key would disclose it to anyone who learns the value.
        if existing.decided_by_id not in (None, approver.id):
            raise _error(
                ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                "You are not an approver for this request",
                msg_key="tool_approval_not_authorized",
                status_code=403,
            )
        if api_key is not None:
            replay_execution = await ToolExecution.filter(
                id=existing.execution_id
            ).first()
            if replay_execution is not None:
                state["execution"] = replay_execution
            if replay_execution is None or not await execution_owned_by_api_key(
                replay_execution, api_key
            ):
                raise _error(
                    ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                    "You are not an approver for this request",
                    msg_key="tool_approval_not_authorized",
                    status_code=403,
                )
        state["replayed"] = True
        return _verify_replay(
            existing, request_id=request_id, request_hash=request_hash
        )

    request_stub = await ToolApprovalRequest.filter(id=request_id).first()
    if request_stub is None:
        raise _not_found()
    execution_id = request_stub.execution_id
    state["execution_id"] = execution_id

    outcome: str | None = None
    created: ToolApprovalDecision | None = None
    try:
        async with in_transaction() as conn:
            execution = (
                await ToolExecution.filter(id=execution_id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            if execution is None:
                raise _not_found(execution=True)
            state["execution"] = execution
            if api_key is not None and not await execution_owned_by_api_key(
                execution, api_key
            ):
                # Fail before disclosing expiry/resolution state.
                raise _error(
                    ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                    "You are not an approver for this request",
                    msg_key="tool_approval_not_authorized",
                    status_code=403,
                )
            request = (
                await ToolApprovalRequest.filter(id=request_id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            if request is None:
                raise _not_found()

            if execution.status != ToolExecutionStatus.AWAITING_APPROVAL:
                if request.status == ApprovalRequestStatus.EXPIRED:
                    outcome = "expired"
                else:
                    raise _error(
                        ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED,
                        "The approval request is already resolved",
                        msg_key="tool_approval_already_decided",
                        status_code=409,
                    )
            elif _is_expired(execution.expires_at, current) or _is_expired(
                request.expires_at, current
            ):
                await _expire_execution_locked(execution, conn, current)
                outcome = "expired"
            elif request.status == ApprovalRequestStatus.EXPIRED:
                await _expire_execution_locked(execution, conn, current)
                outcome = "expired"
            elif request.status != ApprovalRequestStatus.PENDING:
                raise _error(
                    ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED,
                    "The approval request is already resolved",
                    msg_key="tool_approval_already_decided",
                    status_code=409,
                )
            else:
                stored_hash = binding_hash_for_execution(execution)
                if stored_hash != execution.binding_hash:
                    await _cancel_execution_locked(
                        execution,
                        conn,
                        ToolExecutionCancelReason.BINDING_CHANGED,
                        current,
                    )
                    outcome = "binding_changed"
                else:
                    await _assert_can_decide(
                        request, execution, approver, api_key=api_key
                    )
                    request.status = (
                        ApprovalRequestStatus.APPROVED
                        if decision == ApprovalVote.APPROVE
                        else ApprovalRequestStatus.REJECTED
                    )
                    request.resolved_at = current
                    await request.save(
                        using_db=conn,
                        update_fields=["status", "resolved_at", "updated_at"],
                    )
                    created = ToolApprovalDecision(
                        request_id=request.id,
                        execution_id=execution.id,
                        decision=decision,
                        decided_by_id=approver.id,
                        reason=normalized_reason,
                        idempotency_key=key,
                        request_hash=request_hash,
                        binding_hash=execution.binding_hash,
                    )
                    created.validate_invariants()
                    await created.save(using_db=conn)

                    if decision == ApprovalVote.REJECT:
                        await _cancel_execution_locked(
                            execution,
                            conn,
                            ToolExecutionCancelReason.REJECTED,
                            current,
                            preserve_request_id=request.id,
                        )
                        outcome = "rejected"
                    else:
                        remaining = (
                            await ToolApprovalRequest.filter(
                                execution_id=execution.id,
                                status=ApprovalRequestStatus.PENDING,
                            )
                            .using_db(conn)
                            .count()
                        )
                        if remaining == 0:
                            execution.status = ToolExecutionStatus.READY
                            execution.cancel_reason = None
                            execution.finished_at = None
                            await execution.save(
                                using_db=conn,
                                update_fields=[
                                    "status",
                                    "cancel_reason",
                                    "finished_at",
                                    "updated_at",
                                ],
                            )
                            outcome = "ready"
                        else:
                            outcome = "awaiting_approval"
    except IntegrityError as exc:
        replay = await ToolApprovalDecision.filter(idempotency_key=key).first()
        if replay is not None:
            state["execution_id"] = replay.execution_id
            state["replayed"] = True
            # A concurrent insert must not bypass the same identity checks as
            # the pre-transaction replay path: another approver (or another
            # API key of the same owner) may not receive this stored decision.
            if replay.decided_by_id not in (None, approver.id):
                raise _error(
                    ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                    "You are not an approver for this request",
                    msg_key="tool_approval_not_authorized",
                    status_code=403,
                ) from exc
            if api_key is not None:
                replay_execution = await ToolExecution.filter(
                    id=replay.execution_id
                ).first()
                if replay_execution is not None:
                    state["execution"] = replay_execution
                if replay_execution is None or not await execution_owned_by_api_key(
                    replay_execution, api_key
                ):
                    raise _error(
                        ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                        "You are not an approver for this request",
                        msg_key="tool_approval_not_authorized",
                        status_code=403,
                    ) from exc
            return _verify_replay(
                replay, request_id=request_id, request_hash=request_hash
            )
        existing_for_request = await ToolApprovalDecision.filter(
            request_id=request_id
        ).first()
        if existing_for_request is not None:
            raise _error(
                ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED,
                "The approval request is already resolved",
                msg_key="tool_approval_already_decided",
                status_code=409,
            ) from exc
        raise _error(
            ResponseCode.TOOL_APPROVAL_CONFLICT,
            "Approval decision conflicted with another decision",
            msg_key="tool_approval_conflict",
            status_code=409,
        ) from exc

    state["outcome"] = outcome
    if outcome == "expired":
        raise _error(
            ResponseCode.TOOL_APPROVAL_EXPIRED,
            "The approval request has expired",
            msg_key="tool_approval_expired",
            status_code=409,
        )
    if outcome == "binding_changed":
        raise _error(
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
            "The execution binding changed; the approval is no longer valid",
            msg_key="tool_approval_binding_changed",
            status_code=409,
        )
    if created is None:  # pragma: no cover - defensive
        raise _error(
            ResponseCode.TOOL_APPROVAL_CONFLICT,
            "Approval decision was not recorded",
            msg_key="tool_approval_conflict",
            status_code=409,
        )
    return created


async def decide_approval(
    request_id: UUID,
    approver: User,
    *,
    decision: ApprovalVote,
    idempotency_key: str,
    reason: str | None = None,
    now: datetime | None = None,
    api_key: Any | None = None,
    request: Request | None = None,
) -> ToolApprovalDecision:
    """Record one decision and audit it exactly once.

    Successful approvals/rejections and security-relevant failures
    (unauthorized, expired, binding changed, already decided, idempotency
    conflict) produce one audit row. An idempotent replay of an existing
    decision returns the stored row without a second success event. Audit
    metadata never contains tool parameters, credentials, bearer tokens or
    the reviewer's reason text.
    """
    requested_vote = _decision_vote(decision)
    state: dict[str, Any] = {
        "execution": None,
        "execution_id": None,
        "replayed": False,
        "outcome": None,
    }
    try:
        recorded = await _decide_approval_record(
            request_id,
            approver,
            decision=decision,
            idempotency_key=idempotency_key,
            reason=reason,
            now=now,
            api_key=api_key,
            state=state,
        )
    except BusinessError as exc:
        if exc.code in _DECISION_FAILURE_AUDIT_CODES:
            await _audit_decision_event(
                approver=approver,
                vote=requested_vote,
                execution=state["execution"],
                execution_id=state["execution_id"],
                request_id=request_id,
                outcome=state["outcome"],
                status="failed",
                error_message=exc.msg_key or "tool_approval_decision_failed",
                api_key=api_key,
                http_request=request,
            )
        if state["outcome"] in {
            "ready",
            "rejected",
            "expired",
            "binding_changed",
        }:
            await _schedule_run_resume(state["execution_id"])
        raise

    if not state["replayed"]:
        await _audit_decision_event(
            approver=approver,
            vote=_decision_vote(recorded.decision),
            execution=state["execution"],
            execution_id=state["execution_id"],
            request_id=request_id,
            outcome=state["outcome"],
            status="success",
            error_message=None,
            api_key=api_key,
            http_request=request,
        )
    if state["outcome"] in {"ready", "rejected"}:
        await _schedule_run_resume(state["execution_id"])
    return recorded


# ---------------------------------------------------------------------------
# Expiry / cancellation helpers and public operations
# ---------------------------------------------------------------------------


async def _expire_execution_locked(
    execution: ToolExecution, conn: Any, now: datetime
) -> None:
    execution.status = ToolExecutionStatus.CANCELLED
    execution.cancel_reason = ToolExecutionCancelReason.EXPIRED
    execution.finished_at = now
    await execution.save(
        using_db=conn,
        update_fields=["status", "cancel_reason", "finished_at", "updated_at"],
    )
    await (
        ToolApprovalRequest.filter(
            execution_id=execution.id, status=ApprovalRequestStatus.PENDING
        )
        .using_db(conn)
        .update(
            status=ApprovalRequestStatus.EXPIRED,
            resolved_at=now,
            updated_at=now,
        )
    )


async def _cancel_execution_locked(
    execution: ToolExecution,
    conn: Any,
    reason: ToolExecutionCancelReason,
    now: datetime,
    *,
    preserve_request_id: UUID | None = None,
) -> None:
    execution.status = ToolExecutionStatus.CANCELLED
    execution.cancel_reason = reason
    execution.finished_at = now
    await execution.save(
        using_db=conn,
        update_fields=["status", "cancel_reason", "finished_at", "updated_at"],
    )
    pending = ToolApprovalRequest.filter(
        execution_id=execution.id, status=ApprovalRequestStatus.PENDING
    )
    if preserve_request_id is not None:
        pending = pending.exclude(id=preserve_request_id)
    await pending.using_db(conn).update(
        status=ApprovalRequestStatus.CANCELLED,
        resolved_at=now,
        updated_at=now,
    )


async def expire_execution(execution_id: UUID, *, now: datetime | None = None) -> bool:
    """Expire a pending execution; returns False for already-terminal rows."""
    current = _as_utc(now) or _utcnow()
    expired = False
    async with in_transaction() as conn:
        execution = (
            await ToolExecution.filter(id=execution_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if execution is None:
            raise _not_found(execution=True)
        if execution.status not in {
            ToolExecutionStatus.AWAITING_APPROVAL,
            ToolExecutionStatus.READY,
        }:
            return False
        if not _is_expired(execution.expires_at, current):
            return False
        await _expire_execution_locked(execution, conn, current)
        expired = True
    if expired:
        await _schedule_run_resume(execution_id)
    return expired


async def expire_due_executions(
    *, limit: int = 200, now: datetime | None = None
) -> int:
    """Expire up to ``limit`` overdue pending executions."""
    current = _as_utc(now) or _utcnow()
    if limit < 1:
        return 0
    ids = (
        await ToolExecution.filter(
            status__in=[
                ToolExecutionStatus.AWAITING_APPROVAL,
                ToolExecutionStatus.READY,
            ],
            expires_at__isnull=False,
            expires_at__lte=current,
        )
        .order_by("expires_at")
        .limit(limit)
        .values_list("id", flat=True)
    )
    count = 0
    for row in ids:
        execution_id = row[0] if isinstance(row, tuple) else row
        try:
            if await expire_execution(execution_id, now=current):
                count += 1
        except BusinessError:
            continue
    return count


async def cancel_execution(
    execution_id: UUID,
    *,
    reason: ToolExecutionCancelReason = ToolExecutionCancelReason.CANCELLED,
    actor_user_id: UUID | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    """Cancel a not-yet-executing request. Executing calls are never replayed."""
    if reason not in _ALLOWED_CANCEL_REASONS:
        raise _input_invalid("Invalid cancellation reason")
    current = _as_utc(now) or _utcnow()
    cancelled = False
    async with in_transaction() as conn:
        execution = (
            await ToolExecution.filter(id=execution_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if execution is None:
            raise _not_found(execution=True)
        if actor_user_id is not None and actor_user_id != execution.actor_user_id:
            member = await TeamMember.filter(
                team_id=execution.team_id, user_id=actor_user_id
            ).first()
            if member is None or member.role not in {"owner", "admin"}:
                raise _error(
                    ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
                    "You do not have permission to cancel this execution",
                    msg_key="tool_execution_access_denied",
                    status_code=403,
                )
        if execution.status == ToolExecutionStatus.CANCELLED:
            return execution
        if execution.status not in {
            ToolExecutionStatus.AWAITING_APPROVAL,
            ToolExecutionStatus.READY,
        }:
            raise _error(
                ResponseCode.TOOL_EXECUTION_INVALID_STATE,
                "Only an unexecuted request can be cancelled",
                msg_key="tool_execution_invalid_state",
                status_code=409,
            )
        await _cancel_execution_locked(execution, conn, reason, current)
        cancelled = True
    if cancelled:
        await _schedule_run_resume(execution_id)
    return execution


async def cancel_pending_for_run(
    *,
    run_kind: ExecutionRunKind,
    run_id: UUID,
    reason: ToolExecutionCancelReason = ToolExecutionCancelReason.RUN_STOPPED,
    limit: int = 200,
) -> int:
    """Cancel every unexecuted tool request belonging to a stopped run."""
    if reason not in _ALLOWED_CANCEL_REASONS:
        raise _input_invalid("Invalid cancellation reason")
    ids = (
        await ToolExecution.filter(
            run_kind=run_kind,
            run_id=run_id,
            status__in=[
                ToolExecutionStatus.AWAITING_APPROVAL,
                ToolExecutionStatus.READY,
            ],
        )
        .order_by("created_at")
        .limit(max(1, limit))
        .values_list("id", flat=True)
    )
    count = 0
    for row in ids:
        execution_id = row[0] if isinstance(row, tuple) else row
        try:
            await cancel_execution(execution_id, reason=reason)
            count += 1
        except BusinessError:
            continue
    return count


# ---------------------------------------------------------------------------
# Claim and outcome
# ---------------------------------------------------------------------------


async def claim_execution(
    execution_id: UUID,
    *,
    claim_token: str,
    binding: "ConnectionBinding | Mapping[str, Any] | None" = None,
    tool_definition_version: int,
    policy_hash: str | None = None,
    authorizer: Callable[[ToolExecution], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    """Atomically claim a ready execution for one worker.

    Revalidates the definition version, policy hash and the fresh connection
    snapshot before transitioning ``ready -> executing``. Any mismatch cancels
    the execution and raises; no side effect is attempted. The caller MUST
    re-authorize tool/run access (``authorizer``) immediately before claiming.
    """
    token = (claim_token or "").strip()
    if not token or len(token) > MAX_CLAIM_TOKEN_LENGTH:
        raise _input_invalid("claim_token is required (max 64 characters)")
    current = _as_utc(now) or _utcnow()
    if tool_definition_version < 1:
        raise _input_invalid("tool_definition_version must be >= 1")

    if authorizer is not None:
        preflight = await ToolExecution.filter(id=execution_id).first()
        if preflight is None:
            raise _not_found(execution=True)
        await authorizer(preflight)

    outcome: str | None = None
    execution: ToolExecution | None = None
    async with in_transaction() as conn:
        execution = (
            await ToolExecution.filter(id=execution_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if execution is None:
            raise _not_found(execution=True)
        if execution.status != ToolExecutionStatus.READY:
            raise _error(
                ResponseCode.TOOL_EXECUTION_CLAIM_CONFLICT,
                "Tool execution is not claimable",
                msg_key="tool_execution_claim_conflict",
                status_code=409,
                data={"status": execution.status.value},
            )
        legacy_gate_exists = await (
            ToolApprovalRequest.filter(execution_id=execution.id)
            .exclude(gate_kind=ApprovalGateKind.CALLER)
            .using_db(conn)
            .exists()
        )
        if legacy_gate_exists:
            await _cancel_execution_locked(
                execution, conn, ToolExecutionCancelReason.BINDING_CHANGED, current
            )
            outcome = "binding_changed"
        elif _is_expired(execution.expires_at, current):
            await _expire_execution_locked(execution, conn, current)
            outcome = "expired"
        elif binding_hash_for_execution(execution) != execution.binding_hash:
            await _cancel_execution_locked(
                execution,
                conn,
                ToolExecutionCancelReason.BINDING_CHANGED,
                current,
            )
            outcome = "binding_changed"
        elif tool_definition_version != execution.tool_definition_version:
            await _cancel_execution_locked(
                execution,
                conn,
                ToolExecutionCancelReason.BINDING_CHANGED,
                current,
            )
            outcome = "binding_changed"
        elif policy_hash is not None and policy_hash != execution.policy_hash:
            await _cancel_execution_locked(
                execution,
                conn,
                ToolExecutionCancelReason.BINDING_CHANGED,
                current,
            )
            outcome = "binding_changed"
        else:
            facts: _BindingFacts | None = None
            if execution.connection_id is not None:
                if binding is None:
                    await _cancel_execution_locked(
                        execution,
                        conn,
                        ToolExecutionCancelReason.BINDING_CHANGED,
                        current,
                    )
                    outcome = "binding_missing"
                else:
                    try:
                        facts = _normalize_binding(binding)
                    except _BindingSnapshotError:
                        facts = None
                    mismatch = (
                        _binding_matches_execution(execution, facts)
                        if facts is not None
                        else "binding_invalid"
                    )
                    if mismatch:
                        await _cancel_execution_locked(
                            execution,
                            conn,
                            ToolExecutionCancelReason.BINDING_CHANGED,
                            current,
                        )
                        outcome = mismatch
            elif binding is not None:
                await _cancel_execution_locked(
                    execution,
                    conn,
                    ToolExecutionCancelReason.BINDING_CHANGED,
                    current,
                )
                outcome = "connection_unexpected"

            if outcome is None:
                updated = (
                    await ToolExecution.filter(
                        id=execution.id, status=ToolExecutionStatus.READY
                    )
                    .using_db(conn)
                    .update(
                        status=ToolExecutionStatus.EXECUTING,
                        claim_token=token,
                        claimed_at=current,
                        started_at=current,
                        updated_at=current,
                    )
                )
                if not updated:
                    raise _error(
                        ResponseCode.TOOL_EXECUTION_CLAIM_CONFLICT,
                        "Tool execution was claimed by another worker",
                        msg_key="tool_execution_claim_conflict",
                        status_code=409,
                    )
                await execution.refresh_from_db(using_db=conn)

    if outcome == "expired":
        raise _error(
            ResponseCode.TOOL_EXECUTION_INVALID_STATE,
            "The tool execution expired before it could be claimed",
            msg_key="tool_execution_invalid_state",
            status_code=409,
        )
    if outcome is not None:
        raise _error(
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
            "The tool execution binding changed before it could be claimed",
            msg_key="tool_approval_binding_changed",
            status_code=409,
            data={"reason": outcome},
        )
    assert execution is not None
    return execution


async def load_execution_parameters(
    execution_id: UUID, *, claim_token: str
) -> dict[str, Any]:
    """Decrypt parameters for the one worker that currently holds the claim."""
    execution = await ToolExecution.filter(id=execution_id).first()
    if execution is None:
        raise _not_found(execution=True)
    if execution.status != ToolExecutionStatus.EXECUTING:
        raise _error(
            ResponseCode.TOOL_EXECUTION_INVALID_STATE,
            "Tool execution is not executing",
            msg_key="tool_execution_invalid_state",
            status_code=409,
        )
    if not execution.claim_token or execution.claim_token != claim_token:
        raise _error(
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            "The execution claim is not held by this worker",
            msg_key="tool_execution_access_denied",
            status_code=403,
        )
    try:
        raw = decrypt_tool_secret(execution.parameters_cipher)
        parameters = json.loads(raw)
    except (ToolSecretError, ValueError) as exc:
        raise _error(
            ResponseCode.TOOL_EXECUTION_PARAMETERS_UNREADABLE,
            "Tool execution parameters could not be decrypted",
            msg_key="tool_execution_parameters_unreadable",
            status_code=500,
        ) from exc
    if not isinstance(parameters, dict):
        raise _error(
            ResponseCode.TOOL_EXECUTION_PARAMETERS_UNREADABLE,
            "Tool execution parameters are malformed",
            msg_key="tool_execution_parameters_unreadable",
            status_code=500,
        )
    canonical = _canonical_json(parameters)
    if _sha256(canonical) != execution.parameters_digest:
        raise _error(
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED,
            "Decrypted parameters do not match the approved digest",
            msg_key="tool_approval_binding_changed",
            status_code=409,
        )
    return parameters


def _sanitize_result_ref(result_ref: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if result_ref is None:
        return None
    if not isinstance(result_ref, Mapping):
        raise _input_invalid("result_ref must be an object")
    if len(result_ref) > MAX_RESULT_REF_KEYS:
        raise _input_invalid("result_ref has too many keys")
    sanitized: dict[str, Any] = {}
    for key, value in result_ref.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise _input_invalid("result_ref keys must be short strings")
        if value is None or isinstance(value, (bool, int, str)):
            if isinstance(value, str) and len(value) > 1000:
                raise _input_invalid("result_ref value is too long")
            sanitized[key] = value
        else:
            raise _input_invalid(
                "result_ref accepts scalar references only (ids/summary)"
            )
    if _utf8_size(_canonical_json(sanitized)) > MAX_RESULT_REF_BYTES:
        raise _input_invalid("result_ref is too large")
    return sanitized


async def _finish_execution(
    execution_id: UUID,
    *,
    claim_token: str,
    status: ToolExecutionStatus,
    result_ref: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    current = _as_utc(now) or _utcnow()
    token = (claim_token or "").strip()
    if not token:
        raise _input_invalid("claim_token is required")
    sanitized_ref = _sanitize_result_ref(result_ref)
    if error_code is not None:
        error_code = error_code.strip()
        if not error_code or len(error_code) > 100:
            raise _input_invalid("error_code is invalid")
    if error_detail is not None:
        error_detail = error_detail.replace("\x00", "").strip()
        if len(error_detail) > MAX_ERROR_DETAIL_LENGTH:
            raise _input_invalid("error_detail is too long")
        error_detail = error_detail or None

    async with in_transaction() as conn:
        execution = (
            await ToolExecution.filter(id=execution_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if execution is None:
            raise _not_found(execution=True)
        if execution.status != ToolExecutionStatus.EXECUTING:
            raise _error(
                ResponseCode.TOOL_EXECUTION_INVALID_STATE,
                "Tool execution is not executing",
                msg_key="tool_execution_invalid_state",
                status_code=409,
            )
        if execution.claim_token != token:
            raise _error(
                ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
                "The execution claim is not held by this worker",
                msg_key="tool_execution_access_denied",
                status_code=403,
            )
        execution.status = status
        execution.finished_at = current
        execution.result_ref = sanitized_ref
        execution.error_code = error_code
        execution.error_detail = error_detail
        if status == ToolExecutionStatus.OUTCOME_UNKNOWN and not error_code:
            execution.error_code = "outcome_unknown"
        await execution.save(
            using_db=conn,
            update_fields=[
                "status",
                "finished_at",
                "result_ref",
                "error_code",
                "error_detail",
                "updated_at",
            ],
        )
    return execution


async def mark_execution_succeeded(
    execution_id: UUID,
    *,
    claim_token: str,
    result_ref: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    return await _finish_execution(
        execution_id,
        claim_token=claim_token,
        status=ToolExecutionStatus.SUCCEEDED,
        result_ref=result_ref,
        now=now,
    )


async def mark_execution_failed(
    execution_id: UUID,
    *,
    claim_token: str,
    error_code: str,
    error_detail: str | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    return await _finish_execution(
        execution_id,
        claim_token=claim_token,
        status=ToolExecutionStatus.FAILED,
        error_code=error_code,
        error_detail=error_detail,
        now=now,
    )


async def mark_execution_outcome_unknown(
    execution_id: UUID,
    *,
    claim_token: str,
    error_code: str = "outcome_unknown",
    error_detail: str | None = None,
    now: datetime | None = None,
) -> ToolExecution:
    """Record a sent-but-unconfirmed call; never retried automatically."""
    return await _finish_execution(
        execution_id,
        claim_token=claim_token,
        status=ToolExecutionStatus.OUTCOME_UNKNOWN,
        error_code=error_code,
        error_detail=error_detail,
        now=now,
    )


async def mark_stale_executing_outcome_unknown(
    *,
    stale_after_seconds: int = 300,
    limit: int = 200,
    now: datetime | None = None,
) -> int:
    """Mark stale executing claims as outcome unknown, never replay them.

    A worker can crash after ``claim_execution`` and before it records a
    terminal state. We only act once the owning run is terminal/lost (the
    lost-run sweep runs independently) and the claim is older than
    ``stale_after_seconds``; an active run is never disturbed. No retry or
    side-effect replay is attempted.
    """
    current = _as_utc(now) or _utcnow()
    cutoff = current - timedelta(seconds=max(1, stale_after_seconds))
    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.models.workflow import RunStatus as WorkflowRunStatus
    from app.models.workflow import WorkflowRun

    terminal_agent = {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    }
    terminal_workflow = {
        WorkflowRunStatus.SUCCESS,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
        WorkflowRunStatus.TIMEOUT,
    }
    ids = (
        await ToolExecution.filter(
            status=ToolExecutionStatus.EXECUTING,
            claimed_at__isnull=False,
            claimed_at__lte=cutoff,
        )
        .order_by("claimed_at")
        .limit(max(1, limit))
        .values_list("id", flat=True)
    )
    marked = 0
    for row in ids:
        execution_id = row[0] if isinstance(row, tuple) else row
        async with in_transaction() as conn:
            execution = (
                await ToolExecution.filter(id=execution_id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            if (
                execution is None
                or execution.status != ToolExecutionStatus.EXECUTING
                or execution.claimed_at is None
                or _as_utc(execution.claimed_at) > cutoff
            ):
                continue
            run_kind = _enum_value(execution.run_kind)
            run_lost = False
            run_terminal = False
            if run_kind == "agent" and execution.run_id is not None:
                run = await AgentRun.filter(id=execution.run_id).using_db(conn).first()
                if run is None:
                    run_lost = True
                else:
                    run_terminal = run.status in terminal_agent
            elif run_kind == "workflow" and execution.run_id is not None:
                run = (
                    await WorkflowRun.filter(id=execution.run_id).using_db(conn).first()
                )
                if run is None:
                    run_lost = True
                else:
                    run_terminal = run.status in terminal_workflow
            if not run_lost and not run_terminal:
                continue
            execution.status = ToolExecutionStatus.OUTCOME_UNKNOWN
            execution.error_code = "claim_expired"
            execution.error_detail = (
                "Worker claim expired before a terminal result was recorded"
            )
            execution.finished_at = current
            execution.updated_at = current
            await execution.save(
                using_db=conn,
                update_fields=[
                    "status",
                    "error_code",
                    "error_detail",
                    "finished_at",
                    "updated_at",
                ],
            )
            marked += 1
    if marked:
        logger.warning(
            "Marked %s stale tool execution claim(s) as outcome_unknown", marked
        )
    return marked


__all__ = [
    "MAX_INBOX_SCAN",
    "ParameterSnapshot",
    "PolicyConfigurationError",
    "approval_policy_changed",
    "audit_tool_approval_policy_update",
    "binding_hash_for_execution",
    "build_parameter_snapshot",
    "can_view_approval_request",
    "cancel_execution",
    "cancel_pending_for_run",
    "claim_execution",
    "compute_binding_hash",
    "create_execution",
    "decide_approval",
    "evaluate_policy",
    "execution_owned_by_api_key",
    "expire_due_executions",
    "expire_execution",
    "find_execution_by_tool_call",
    "get_approval_request_for_viewer",
    "get_execution",
    "get_execution_for_viewer",
    "list_executions_for_actor",
    "list_pending_approvals_for_user",
    "list_run_executions",
    "load_execution_parameters",
    "mark_execution_failed",
    "mark_execution_outcome_unknown",
    "mark_execution_succeeded",
    "mark_stale_executing_outcome_unknown",
    "normalize_tool_approval_policy",
    "policy_hash",
    "redact_parameters",
    "stored_api_key_id",
    "validate_binding_snapshot",
]
