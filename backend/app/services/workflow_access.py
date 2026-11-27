"""Evaluate a workflow's access policy against one principal.

Enforcement lives here so every entry point asks the same question: the policy
narrows, and never widens, what the legacy rules already allow. A workflow with
no policy (or with this operation missing) returns ``None`` and the caller keeps
its existing checks; that is what makes the feature safe to roll out.

Fail closed: a stored policy that no longer validates denies the operation
instead of falling back to "inherit".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.schemas.response import BusinessError, ResponseCode
from app.schemas.workflow_access import (
    AccessDecision,
    AccessGate,
    AccessGateKind,
    WorkflowAccessPolicy,
    WorkflowOperation,
    WorkflowOperationPolicy,
    normalize_workflow_access_policy,
)

logger = logging.getLogger(__name__)


class AccessReason(str, Enum):
    """Why a decision was reached; surfaced in logs and the evaluate preview."""

    SUPERUSER = "superuser"
    INHERIT = "inherit"
    DENIED_BY_POLICY = "denied_by_policy"
    ALLOWED_BY_POLICY = "allowed_by_policy"
    ALLOWED_BY_GATE = "allowed_by_gate"
    NOT_IN_AUDIENCE = "not_in_audience"
    INVALID_POLICY = "invalid_policy"


@dataclass(frozen=True)
class AccessPrincipal:
    """The caller a policy is evaluated for.

    ``team_role`` is the member's role in the workflow's team (``None`` for a
    non-member), and ``api_key_id`` is set only when the request authenticated
    with that exact credential.
    """

    user_id: UUID | None
    team_role: str | None
    api_key_id: UUID | None = None
    is_superuser: bool = False

    @classmethod
    def from_parts(
        cls,
        user: Any = None,
        *,
        team_role: str | None = None,
        api_key: Any = None,
    ) -> "AccessPrincipal":
        key_id = getattr(api_key, "id", None)
        return cls(
            user_id=getattr(user, "id", None),
            team_role=str(team_role) if team_role is not None else None,
            api_key_id=UUID(str(key_id)) if key_id else None,
            is_superuser=bool(getattr(user, "is_superuser", False)),
        )


@dataclass(frozen=True)
class AccessDecisionResult:
    """Outcome for one operation.

    ``allowed`` is the answer to enforce; ``decision`` is the policy value that
    applied (or ``None`` when the operation is inherited).
    """

    operation: WorkflowOperation
    allowed: bool
    decision: AccessDecision | None
    reason: AccessReason
    matched_gate: int | None = None


def _gate_matches(gate: AccessGate, principal: AccessPrincipal) -> bool:
    if gate.kind is AccessGateKind.TEAM_ROLE:
        return principal.team_role is not None and any(
            principal.team_role == str(role) for role in gate.roles
        )
    if gate.kind is AccessGateKind.USER:
        return principal.user_id is not None and principal.user_id in gate.user_ids
    return principal.api_key_id is not None and principal.api_key_id in gate.api_key_ids


def _decide(
    policy: WorkflowOperationPolicy, principal: AccessPrincipal
) -> tuple[bool, AccessReason, int | None]:
    if policy.decision is AccessDecision.DENY:
        return False, AccessReason.DENIED_BY_POLICY, None
    if not policy.gates:
        return True, AccessReason.ALLOWED_BY_POLICY, None
    for index, gate in enumerate(policy.gates):
        if _gate_matches(gate, principal):
            return True, AccessReason.ALLOWED_BY_GATE, index
    return False, AccessReason.NOT_IN_AUDIENCE, None


def evaluate_workflow_access(
    workflow: Any,
    operation: WorkflowOperation,
    principal: AccessPrincipal,
) -> AccessDecisionResult | None:
    """Decide one operation, or ``None`` when the workflow inherits it."""
    raw = getattr(workflow, "access_policy", None)
    try:
        policy: WorkflowAccessPolicy = normalize_workflow_access_policy(raw)
    except ValueError:
        logger.error(
            "Workflow %s has an invalid access policy; denying %s",
            getattr(workflow, "id", None),
            operation.value,
        )
        return AccessDecisionResult(
            operation=operation,
            allowed=False,
            decision=None,
            reason=AccessReason.INVALID_POLICY,
        )

    operation_policy = policy.for_operation(operation)
    if operation_policy is None:
        if principal.is_superuser:
            return AccessDecisionResult(
                operation=operation,
                allowed=True,
                decision=None,
                reason=AccessReason.SUPERUSER,
            )
        return None
    if principal.is_superuser:
        return AccessDecisionResult(
            operation=operation,
            allowed=True,
            decision=operation_policy.decision,
            reason=AccessReason.SUPERUSER,
        )

    allowed, reason, matched = _decide(operation_policy, principal)
    return AccessDecisionResult(
        operation=operation,
        allowed=allowed,
        decision=operation_policy.decision,
        reason=reason,
        matched_gate=matched,
    )


def describe_effective_access(
    workflow: Any, principal: AccessPrincipal
) -> dict[str, dict[str, Any]]:
    """Per-operation answer for one principal, including inherited operations.

    Used by the policy editor's preview so an administrator can see, before
    saving, exactly what changes for the principal being asked about.
    """
    described: dict[str, dict[str, Any]] = {}
    try:
        policy = normalize_workflow_access_policy(
            getattr(workflow, "access_policy", None)
        )
        policy_valid = True
    except ValueError:
        policy = WorkflowAccessPolicy()
        policy_valid = False

    for operation in WorkflowOperation:
        result = evaluate_workflow_access(workflow, operation, principal)
        # An operation the policy does not name stays inherited even for a
        # superuser; the reason records that the bypass, not the policy, decided.
        decided_by_policy = policy_valid and policy.for_operation(operation) is not None
        if result is None:
            described[operation.value] = {
                "source": "inherit",
                "allowed": None,
                "decision": None,
                "reason": AccessReason.INHERIT.value,
            }
            continue
        described[operation.value] = {
            "source": "policy" if decided_by_policy else "inherit",
            "allowed": result.allowed,
            "decision": result.decision.value if result.decision else None,
            "reason": result.reason.value,
            "matched_gate": result.matched_gate,
        }
    return described


async def ensure_workflow_operation(
    workflow: Any,
    operation: WorkflowOperation | str,
    *,
    user: Any = None,
    api_key: Any = None,
) -> AccessDecisionResult | None:
    """Enforce one operation for a user and/or an API key principal.

    Entry points that do not pass through ``check_workflow_access`` (embed, API
    key, webhook, subworkflow) call this so the policy applies to them too. The
    team role is resolved from the workflow's team, and an API key contributes
    its own identity in addition to its owner's user entry.
    """
    from app.models.user import TeamMember

    operation = WorkflowOperation(operation)
    team_role = None
    team_id = getattr(workflow, "team_id", None)
    user_id = getattr(user, "id", None)
    if team_id and user_id:
        member = await TeamMember.filter(team_id=team_id, user_id=user_id).first()
        team_role = str(member.role) if member is not None else None
    return assert_workflow_access(
        workflow,
        operation,
        AccessPrincipal.from_parts(user, team_role=team_role, api_key=api_key),
        hidden=operation in {WorkflowOperation.VIEW, WorkflowOperation.RUN},
    )


def assert_workflow_access(
    workflow: Any,
    operation: WorkflowOperation,
    principal: AccessPrincipal,
    *,
    hidden: bool = False,
) -> AccessDecisionResult | None:
    """Enforce the policy, raising when it denies.

    ``hidden`` reports the denial as ``404`` for operations whose existence must
    not leak (view/run); management operations use ``403`` because the caller
    can already see the workflow.
    """
    result = evaluate_workflow_access(workflow, operation, principal)
    if result is None or result.allowed:
        return result
    if hidden:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )
    raise BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="workflow_access_denied",
        status_code=403,
        data={"operation": operation.value, "reason": result.reason.value},
    )
