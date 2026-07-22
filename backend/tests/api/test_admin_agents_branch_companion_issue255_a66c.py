from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import agents
from app.models.agent import AgentStatus, AgentVisibility


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "initial_status", "expected_status", "notification_type"),
    [
        (
            agents.publish_agent,
            AgentStatus.DRAFT,
            AgentStatus.PUBLISHED,
            agents.AutoNotificationType.AGENT_PUBLISHED,
        ),
        (
            agents.unpublish_agent,
            AgentStatus.PUBLISHED,
            AgentStatus.DRAFT,
            agents.AutoNotificationType.AGENT_UNPUBLISHED,
        ),
    ],
)
async def test_agent_status_transition_notifies_only_when_team_exists(
    function, initial_status, expected_status, notification_type
):
    notify = AsyncMock()

    for team_id in (uuid4(), None):
        agent = SimpleNamespace(
            id=uuid4(),
            name="Branch Agent",
            status=initial_status,
            team_id=team_id,
            visibility=AgentVisibility.PRIVATE,
            save=AsyncMock(),
        )
        with (
            patch.object(agents, "_get_agent", AsyncMock(return_value=agent)),
            patch.object(agents.AuditLogService, "log", AsyncMock()),
            patch.object(agents.AutoNotificationService, "send_to_team", notify),
            patch.object(agents, "build_agent_out", AsyncMock(return_value={})),
            patch.object(agents, "t", return_value="translated"),
        ):
            response = await function(
                MagicMock(), agent.id, current_user=SimpleNamespace(id=uuid4())
            )

        assert response["data"] == {}
        assert agent.status == expected_status
        agent.save.assert_awaited_once()

    assert notify.await_count == 1
    assert notify.await_args.kwargs["notification_type"] == notification_type
