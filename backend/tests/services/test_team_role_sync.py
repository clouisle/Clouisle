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
    sync = AsyncMock()
    monkeypatch.setattr(team_role_sync, "sync_scoped_role_assignment", sync)

    assigned = await team_role_sync.assign_default_team(user)

    assert assigned is False
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_user_role_from_teams_syncs_and_prunes(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    memberships = [
        SimpleNamespace(team=SimpleNamespace(id=uuid4())),
        SimpleNamespace(team=SimpleNamespace(id=uuid4())),
    ]
    membership_query = QueryMock(memberships)
    assignment_query = QueryMock()
    monkeypatch.setattr(
        team_role_sync.TeamMember,
        "filter",
        MagicMock(return_value=membership_query),
    )
    assignment_filter = MagicMock(return_value=assignment_query)
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "filter", assignment_filter
    )
    sync = AsyncMock()
    monkeypatch.setattr(team_role_sync, "sync_scoped_role_assignment", sync)

    await team_role_sync.sync_user_role_from_teams(user)

    membership_query.prefetch_related.assert_called_once_with("team", "user")
    assert [call.args for call in sync.await_args_list] == [
        (membership,) for membership in memberships
    ]
    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", source="system"
    )
    assignment_query.exclude.assert_called_once_with(
        scope_id__in={membership.team.id for membership in memberships}
    )
    assignment_query.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_sync_scoped_role_assignment_skips_unknown_and_missing_roles(
    monkeypatch,
):
    membership = SimpleNamespace(
        role="unknown",
        user=SimpleNamespace(id=uuid4()),
        team=SimpleNamespace(id=uuid4()),
    )
    role_filter = MagicMock(return_value=QueryMock())
    assignment_filter = MagicMock(return_value=QueryMock())
    get_or_create = AsyncMock()
    monkeypatch.setattr(team_role_sync.Role, "filter", role_filter)
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "filter", assignment_filter
    )
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "get_or_create", get_or_create
    )

    await team_role_sync.sync_scoped_role_assignment(membership)
    role_filter.assert_not_called()

    membership.role = "admin"
    await team_role_sync.sync_scoped_role_assignment(membership)

    role_filter.assert_called_once_with(name="Admin")
    assignment_filter.assert_not_called()
    get_or_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_scoped_role_assignment_replaces_system_assignment(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    team = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(id=uuid4())
    membership = SimpleNamespace(role="viewer", user=user, team=team)
    role_query = QueryMock(role)
    assignment_query = QueryMock()
    assignment_filter = MagicMock(return_value=assignment_query)
    get_or_create = AsyncMock()
    monkeypatch.setattr(
        team_role_sync.Role, "filter", MagicMock(return_value=role_query)
    )
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "filter", assignment_filter
    )
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "get_or_create", get_or_create
    )

    await team_role_sync.sync_scoped_role_assignment(membership)

    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", scope_id=team.id, source="system"
    )
    assignment_query.delete.assert_awaited_once_with()
    get_or_create.assert_awaited_once_with(
        user=user,
        role=role,
        scope_type="team",
        scope_id=team.id,
        defaults={"source": "system"},
    )


@pytest.mark.asyncio
async def test_remove_scoped_role_assignment(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    team_id = uuid4()
    query = QueryMock()
    assignment_filter = MagicMock(return_value=query)
    monkeypatch.setattr(
        team_role_sync.ScopedRoleAssignment, "filter", assignment_filter
    )

    await team_role_sync.remove_scoped_role_assignment(user, team_id)

    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", scope_id=team_id
    )
    query.delete.assert_awaited_once_with()


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
