from uuid import uuid4

import pytest

from app.models.tool_approval import ToolApprovalRequest
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalGateKind,
    ApprovalRequestStatus,
    ExecutionEntrypoint,
    ToolExecutionStatus,
)
from app.services import tool_approvals as service
from tests.services.test_tool_approvals import (
    _allow_policy,
    _database,
    _team,
    _tool,
    _user,
)


@pytest.mark.asyncio
async def test_previously_approved_external_gate_cannot_be_claimed():
    async with _database():
        actor = await _user("legacy_claim")
        team = await _team("legacy_claim", actor)
        tool = await _tool(team, _allow_policy())
        execution = await service.create_execution(
            tool=tool,
            operation="read",
            parameters={},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        await ToolApprovalRequest.create(
            id=uuid4(),
            execution_id=execution.id,
            stage_index=0,
            stage_key="legacy-user",
            gate_kind=ApprovalGateKind.USER,
            approver_user_ids=[str(actor.id)],
            approver_roles=[],
            status=ApprovalRequestStatus.APPROVED,
        )
        with pytest.raises(BusinessError) as error:
            await service.claim_execution(
                execution.id,
                claim_token="claim",
                tool_definition_version=tool.definition_version,
            )
        assert error.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.CANCELLED
