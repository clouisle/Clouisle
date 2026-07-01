from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import team_role_sync


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

    membership = SimpleNamespace(role="viewer")
    sync_scoped_role_assignment = AsyncMock()

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.Team, "filter", lambda **kwargs: TeamQuery())
    monkeypatch.setattr(
        team_role_sync, "sync_scoped_role_assignment", sync_scoped_role_assignment
    )
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
    sync_scoped_role_assignment.assert_awaited_once_with(membership)


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

    membership = SimpleNamespace(role="member")
    sync_scoped_role_assignment = AsyncMock()

    monkeypatch.setattr(team_role_sync.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(team_role_sync.Team, "filter", lambda **kwargs: TeamQuery())
    monkeypatch.setattr(
        team_role_sync, "sync_scoped_role_assignment", sync_scoped_role_assignment
    )
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
    sync_scoped_role_assignment.assert_awaited_once_with(membership)


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
