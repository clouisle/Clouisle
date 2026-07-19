from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agents
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError, ResponseCode


def agent_query(result: object | None) -> MagicMock:
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.first = AsyncMock(return_value=result)
    return query


@pytest.mark.anyio
async def test_check_agent_access_returns_not_found_for_missing_agent() -> None:
    with patch.object(agents.Agent, "filter", return_value=agent_query(None)):
        with pytest.raises(BusinessError) as error:
            await agents.check_agent_access(
                uuid4(), SimpleNamespace(is_superuser=False)
            )

    assert error.value.code == ResponseCode.AGENT_NOT_FOUND
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_check_agent_access_rejects_non_owner_of_private_agent() -> None:
    agent = SimpleNamespace(
        created_by=SimpleNamespace(id=uuid4()),
        visibility=AgentVisibility.PRIVATE,
    )
    user = SimpleNamespace(id=uuid4(), is_superuser=False)

    with patch.object(agents.Agent, "filter", return_value=agent_query(agent)):
        with pytest.raises(BusinessError) as error:
            await agents.check_agent_access(uuid4(), user)

    assert error.value.code == ResponseCode.AGENT_ACCESS_DENIED
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_check_agent_access_requires_team_admin_for_non_owner_write() -> None:
    team_id = uuid4()
    agent = SimpleNamespace(
        created_by=SimpleNamespace(id=uuid4()),
        team=SimpleNamespace(id=team_id),
        visibility=AgentVisibility.TEAM,
    )
    user = SimpleNamespace(id=uuid4(), is_superuser=False)

    with (
        patch.object(agents.Agent, "filter", return_value=agent_query(agent)),
        patch.object(agents, "check_team_access", new=AsyncMock()) as check_access,
    ):
        assert (
            await agents.check_agent_access(uuid4(), user, require_write=True) is agent
        )

    assert check_access.await_args_list[0].args == (team_id, user)
    assert check_access.await_args_list[1].args == (team_id, user)
    assert check_access.await_args_list[1].kwargs == {"require_admin": True}


@pytest.mark.anyio
async def test_video_status_rejects_agent_without_video_generation() -> None:
    with patch.object(
        agents,
        "check_agent_access",
        new=AsyncMock(return_value=SimpleNamespace(enable_video_generation=False)),
    ):
        with pytest.raises(BusinessError) as error:
            await agents.get_agent_video_generation_status(
                uuid4(), "task-id", SimpleNamespace()
            )

    assert error.value.code == ResponseCode.BAD_REQUEST
    assert error.value.status_code == 400
