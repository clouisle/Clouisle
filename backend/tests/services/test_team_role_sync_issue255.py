from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.services import team_role_sync as service


class Query:
    def __init__(self, result=None):
        self.result = result
        self.delete = AsyncMock()
        self.exclude = MagicMock(return_value=self)

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


@pytest.mark.asyncio
async def test_scoped_role_sync_skips_unknown_role_and_missing_mapping(monkeypatch):
    role_filter = MagicMock(return_value=Query())
    assignment_filter = MagicMock()
    monkeypatch.setattr(service.Role, "filter", role_filter)
    monkeypatch.setattr(service.ScopedRoleAssignment, "filter", assignment_filter)

    unknown = SimpleNamespace(role="guest")
    await service.sync_scoped_role_assignment(unknown)

    missing = SimpleNamespace(role="owner")
    await service.sync_scoped_role_assignment(missing)

    role_filter.assert_called_once_with(name="Admin")
    assignment_filter.assert_not_called()


@pytest.mark.asyncio
async def test_scoped_role_sync_replaces_system_assignment(monkeypatch):
    user = object()
    team_id = uuid4()
    membership = SimpleNamespace(
        role="viewer", user=user, team=SimpleNamespace(id=team_id)
    )
    role = SimpleNamespace(id=uuid4())
    delete_query = Query()
    monkeypatch.setattr(service.Role, "filter", lambda **_kwargs: Query(role))
    assignment_filter = MagicMock(return_value=delete_query)
    get_or_create = AsyncMock()
    monkeypatch.setattr(service.ScopedRoleAssignment, "filter", assignment_filter)
    monkeypatch.setattr(service.ScopedRoleAssignment, "get_or_create", get_or_create)

    await service.sync_scoped_role_assignment(membership)

    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", scope_id=team_id, source="system"
    )
    delete_query.delete.assert_awaited_once()
    get_or_create.assert_awaited_once_with(
        user=user,
        role=role,
        scope_type="team",
        scope_id=team_id,
        defaults={"source": "system"},
    )


@pytest.mark.asyncio
async def test_remove_scoped_role_assignment_deletes_all_team_assignments(monkeypatch):
    query = Query()
    assignment_filter = MagicMock(return_value=query)
    monkeypatch.setattr(service.ScopedRoleAssignment, "filter", assignment_filter)
    user = object()
    team_id = uuid4()

    await service.remove_scoped_role_assignment(user, team_id)

    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", scope_id=team_id
    )
    query.delete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("role_exists", [False, True])
async def test_assign_default_role_handles_missing_and_configured_role(
    monkeypatch, role_exists
):
    role = SimpleNamespace(id=uuid4()) if role_exists else None
    monkeypatch.setattr(
        service.SiteSetting,
        "get_value",
        AsyncMock(return_value="role-id"),
    )
    get_role = AsyncMock(return_value=role)
    monkeypatch.setattr(service.Role, "get_or_none", get_role)
    user = SimpleNamespace(roles=SimpleNamespace(add=AsyncMock()))

    await service.assign_default_role(user)

    get_role.assert_awaited_once_with(id="role-id")
    if role_exists:
        user.roles.add.assert_awaited_once_with(role)
    else:
        user.roles.add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("team_setting", ["", "not-a-uuid", str(uuid4())])
async def test_assign_default_team_rejects_unusable_configuration(
    monkeypatch, team_setting
):
    settings = AsyncMock(side_effect=[team_setting, "invalid-role"])
    monkeypatch.setattr(service.SiteSetting, "get_value", settings)
    team_filter = MagicMock(return_value=Query())
    monkeypatch.setattr(service.Team, "filter", team_filter)
    get_or_create = AsyncMock()
    monkeypatch.setattr(service.TeamMember, "get_or_create", get_or_create)

    assert await service.assign_default_team(object()) is False

    get_or_create.assert_not_awaited()
    if not team_setting:
        settings.assert_awaited_once_with("default_team_id", "")
        team_filter.assert_not_called()
    elif team_setting == "not-a-uuid":
        team_filter.assert_not_called()
    else:
        team_filter.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [False, True])
async def test_assign_default_team_syncs_only_new_membership(monkeypatch, created):
    team_id = uuid4()
    team = SimpleNamespace(id=team_id)
    membership = SimpleNamespace(team=team)
    monkeypatch.setattr(
        service.SiteSetting,
        "get_value",
        AsyncMock(side_effect=[str(team_id), "viewer"]),
    )
    monkeypatch.setattr(service.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(
        service.TeamMember,
        "get_or_create",
        AsyncMock(return_value=(membership, created)),
    )
    sync = AsyncMock()
    monkeypatch.setattr(service, "sync_scoped_role_assignment", sync)
    user = object()

    assert await service.assign_default_team(user) is created

    service.TeamMember.get_or_create.assert_awaited_once_with(
        team=team, user=user, defaults={"role": "viewer"}
    )
    if created:
        sync.assert_awaited_once_with(membership)
    else:
        sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_user_roles_updates_memberships_and_removes_stale_assignments(
    monkeypatch,
):
    user = object()
    memberships = [
        SimpleNamespace(team=SimpleNamespace(id=uuid4())),
        SimpleNamespace(team=SimpleNamespace(id=uuid4())),
    ]
    membership_query = MagicMock()
    membership_query.prefetch_related = AsyncMock(return_value=memberships)
    monkeypatch.setattr(
        service.TeamMember, "filter", MagicMock(return_value=membership_query)
    )
    sync = AsyncMock()
    monkeypatch.setattr(service, "sync_scoped_role_assignment", sync)
    cleanup_query = Query()
    assignment_filter = MagicMock(return_value=cleanup_query)
    monkeypatch.setattr(service.ScopedRoleAssignment, "filter", assignment_filter)

    await service.sync_user_role_from_teams(user)

    assert sync.await_args_list == [call(item) for item in memberships]
    assignment_filter.assert_called_once_with(
        user=user, scope_type="team", source="system"
    )
    cleanup_query.exclude.assert_called_once_with(
        scope_id__in={item.team.id for item in memberships}
    )
    cleanup_query.delete.assert_awaited_once()
