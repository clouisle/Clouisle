"""Integrity validation for stored approval policy definition rows."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.schemas.tool_approval_policy import (
    ToolApprovalEntrypointKind,
    ToolApprovalPolicyScope,
)

_VALID_HASH = "a" * 64


def _row(
    scope: ToolApprovalPolicyScope,
    *,
    scope_key: str | None = None,
    team_id: UUID | None = None,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    policy_hash: str = _VALID_HASH,
) -> ToolApprovalPolicyDefinition:
    row = ToolApprovalPolicyDefinition(
        scope=scope,
        scope_key=(f"{scope.value}:{uuid4().hex}" if scope_key is None else scope_key),
        policy_hash=policy_hash,
        version=1,
    )
    row.team_id = team_id
    row.entrypoint_kind = entrypoint_kind
    row.entrypoint_id = entrypoint_id
    return row


def test_clean_rejects_scope_fields_that_do_not_match():
    team_id = uuid4()
    rows = (
        _row(ToolApprovalPolicyScope.SITE, team_id=team_id),
        _row(ToolApprovalPolicyScope.SITE, entrypoint_id=uuid4()),
        _row(ToolApprovalPolicyScope.TEAM),
        _row(
            ToolApprovalPolicyScope.TEAM,
            team_id=team_id,
            entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
        ),
        _row(
            ToolApprovalPolicyScope.TEAM,
            team_id=team_id,
            entrypoint_id=uuid4(),
        ),
        _row(ToolApprovalPolicyScope.ENTRYPOINT),
        _row(ToolApprovalPolicyScope.ENTRYPOINT, team_id=team_id),
        _row(
            ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=team_id,
            entrypoint_kind=ToolApprovalEntrypointKind.WORKFLOW,
        ),
        _row(
            ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=team_id,
            entrypoint_id=uuid4(),
        ),
    )

    for row in rows:
        with pytest.raises(ValueError, match="tool_approval_policy_scope_invalid"):
            row.clean()


@pytest.mark.parametrize("policy_hash", ["a" * 63, "z" * 64])
def test_clean_rejects_non_sha256_policy_hash(policy_hash: str):
    with pytest.raises(ValueError, match="approval_policy_invalid"):
        _row(ToolApprovalPolicyScope.SITE, policy_hash=policy_hash).clean()
