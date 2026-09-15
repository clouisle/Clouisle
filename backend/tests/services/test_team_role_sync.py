from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import team_role_sync


class QueryMock:
    def __init__(self, first=None):
        self.first_result = first
        self.first = AsyncMock(return_value=first)
        self.delete = AsyncMock()
        self.exclude = MagicMock(return_value=self)
        self.prefetch_related = MagicMock(return_value=self)

    def __await__(self):
        async def result():
            return self.first_result

        return result().__await__()


@pytest.mark.asyncio
async def test_assign_default_team_skips_empty_setting(monkeypatch):
    async def get_value(key: str, default=None):
        return "" if key == "default_team_id" else default

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.TeamMember, "get_or_create", AsyncMock())

    assigned = await team_role_sync.assign_default_team(SimpleNamespace(id=uuid4()))

    assert assigned is False
    team_role_sync.TeamMember.get_or_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_default_team_skips_invalid_team_id(monkeypatch):
    async def get_value(key: str, default=None):
        return "not-a-uuid" if key == "default_team_id" else default

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    team_filter = MagicMock()
    monkeypatch.setattr(team_role_sync.Team, "filter", team_filter)

    assigned = await team_role_sync.assign_default_team(SimpleNamespace(id=uuid4()))

    assert assigned is False
    team_filter.assert_not_called()


@pytest.mark.asyncio
async def test_assign_default_team_does_not_resync_existing_membership(monkeypatch):
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    team = SimpleNamespace(id=team_id)
    membership = SimpleNamespace(role="member", user=user, team=team)

    async def get_value(key: str, default=None):
        return str(team_id) if key == "default_team_id" else default

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        team_role_sync.Team, "filter", MagicMock(return_value=QueryMock(team))
    )
    monkeypatch.setattr(
        team_role_sync.TeamMember,
        "get_or_create",
        AsyncMock(return_value=(membership, False)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("default_role_id", ["", "missing"])
async def test_assign_default_role_skips_empty_or_missing_role(
    monkeypatch, default_role_id
):
    user = SimpleNamespace(roles=SimpleNamespace(add=AsyncMock()))
    monkeypatch.setattr(
        team_role_sync.SiteSetting,
        "get_value",
        AsyncMock(return_value=default_role_id),
    )
    get_or_none = AsyncMock(return_value=None)
    monkeypatch.setattr(team_role_sync.Role, "get_or_none", get_or_none)

    await team_role_sync.assign_default_role(user)

    if default_role_id:
        get_or_none.assert_awaited_once_with(id=default_role_id)
    else:
        get_or_none.assert_not_awaited()
    user.roles.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_default_role_adds_configured_role(monkeypatch):
    role = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(roles=SimpleNamespace(add=AsyncMock()))
    monkeypatch.setattr(
        team_role_sync.SiteSetting, "get_value", AsyncMock(return_value=str(role.id))
    )
    monkeypatch.setattr(
        team_role_sync.Role, "get_or_none", AsyncMock(return_value=role)
    )

    await team_role_sync.assign_default_role(user)

    user.roles.add.assert_awaited_once_with(role)


@pytest.mark.asyncio
async def test_assign_default_team_creates_membership(monkeypatch):
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    team = SimpleNamespace(id=team_id)

    async def get_value(key: str, default=None):
        values = {
            "default_team_id": str(team_id),
            "default_team_role": "viewer",
        }
        return values.get(key, default)

    class TeamQuery:
        async def first(self):
            return team

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.Team, "filter", lambda **_kwargs: TeamQuery())

    membership = SimpleNamespace(role="viewer")
    monkeypatch.setattr(
        team_role_sync.TeamMember,
        "get_or_create",
        AsyncMock(return_value=(membership, True)),
    )

    assigned = await team_role_sync.assign_default_team(user)

    assert assigned is True
    team_role_sync.TeamMember.get_or_create.assert_awaited_once_with(
        team=team,
        user=user,
        defaults={"role": "viewer"},
    )


@pytest.mark.asyncio
async def test_assign_default_team_falls_back_invalid_role(monkeypatch):
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    team = SimpleNamespace(id=team_id)

    async def get_value(key: str, default=None):
        values = {
            "default_team_id": str(team_id),
            "default_team_role": "owner",
        }
        return values.get(key, default)

    class TeamQuery:
        async def first(self):
            return team

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.Team, "filter", lambda **_kwargs: TeamQuery())

    membership = SimpleNamespace(role="member")
    monkeypatch.setattr(
        team_role_sync.TeamMember,
        "get_or_create",
        AsyncMock(return_value=(membership, True)),
    )

    assigned = await team_role_sync.assign_default_team(user)

    assert assigned is True
    team_role_sync.TeamMember.get_or_create.assert_awaited_once_with(
        team=team,
        user=user,
        defaults={"role": "member"},
    )


@pytest.mark.asyncio
async def test_assign_default_team_skips_missing_team(monkeypatch):
    team_id = uuid4()

    async def get_value(key: str, default=None):
        values = {
            "default_team_id": str(team_id),
            "default_team_role": "admin",
        }
        return values.get(key, default)

    class TeamQuery:
        async def first(self):
            return None

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.Team, "filter", lambda **kwargs: TeamQuery())
    monkeypatch.setattr(team_role_sync.TeamMember, "get_or_create", AsyncMock())

    assigned = await team_role_sync.assign_default_team(SimpleNamespace(id=uuid4()))

    assert assigned is False
    team_role_sync.TeamMember.get_or_create.assert_not_awaited()
