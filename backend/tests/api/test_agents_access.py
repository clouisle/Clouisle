from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints.agents import check_agent_access
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError


class _Query:
    def __init__(self, agent):
        self.agent = agent

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.agent


class _AgentModel:
    agent = None

    @classmethod
    def filter(cls, **_kwargs):
        return _Query(cls.agent)


@pytest.mark.anyio
async def test_private_agent_owner_can_access(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    agent = SimpleNamespace(
        id=uuid4(),
        visibility=AgentVisibility.PRIVATE,
        created_by=user,
        team=SimpleNamespace(id=uuid4()),
    )
    _AgentModel.agent = agent
    check_team = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.agents.Agent", _AgentModel)
    monkeypatch.setattr("app.api.v1.endpoints.agents.check_team_access", check_team)

    assert await check_agent_access(agent.id, user) is agent
    check_team.assert_not_awaited()


@pytest.mark.anyio
async def test_private_agent_rejects_unrelated_user(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        visibility=AgentVisibility.PRIVATE,
        created_by=SimpleNamespace(id=uuid4()),
        team=SimpleNamespace(id=uuid4()),
    )
    _AgentModel.agent = agent
    monkeypatch.setattr("app.api.v1.endpoints.agents.Agent", _AgentModel)

    with pytest.raises(BusinessError) as error:
        await check_agent_access(
            agent.id, SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert error.value.msg_key == "agent_access_denied"
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_team_agent_write_requires_team_admin(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(),
        visibility=AgentVisibility.TEAM,
        created_by=SimpleNamespace(id=uuid4()),
        team=team,
    )
    _AgentModel.agent = agent
    check_team = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.agents.Agent", _AgentModel)
    monkeypatch.setattr("app.api.v1.endpoints.agents.check_team_access", check_team)

    assert await check_agent_access(agent.id, user, require_write=True) is agent
    check_team.assert_any_await(team.id, user)
    check_team.assert_any_await(team.id, user, require_admin=True)


@pytest.mark.anyio
async def test_agent_access_reports_not_found(monkeypatch):
    _AgentModel.agent = None
    monkeypatch.setattr("app.api.v1.endpoints.agents.Agent", _AgentModel)

    with pytest.raises(BusinessError) as error:
        await check_agent_access(uuid4(), SimpleNamespace(is_superuser=False))

    assert error.value.msg_key == "agent_not_found"
    assert error.value.status_code == 404
