from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams
from app.schemas.team import TeamMemberRole


class _TeamQuery:
    def __init__(self, team):
        self._team = team

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self._team

    def __await__(self):
        async def resolve():
            return self._team

        return resolve().__await__()


class _TeamFilter:
    def __init__(self, team):
        self._team = team

    async def first(self):
        return self._team


class _MembershipQuery:
    def __init__(self, membership):
        self._membership = membership

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self._membership


class _UserQuery:
    def __init__(self, user):
        self._user = user

    async def first(self):
        return self._user


class _TeamModel:
    @staticmethod
    def filter(**_kwargs):
        return _TeamFilter(_TEAM)

    @staticmethod
    def get(**_kwargs):
        return _TeamQuery(_TEAM)


class _TeamMemberModel:
    @staticmethod
    def filter(**kwargs):
        if kwargs.get("role") == TeamMemberRole.OWNER:
            return _MembershipQuery(_OWNER_MEMBERSHIP)
        user = kwargs["user"]
        return _MembershipQuery(_MEMBERSHIPS.get(user.id))


class _UserModel:
    @staticmethod
    def filter(**kwargs):
        return _UserQuery(_USERS.get(kwargs["id"]))


_USERS = {}
_MEMBERSHIPS = {}
_TEAM = None
_OWNER_MEMBERSHIP = None


@pytest.mark.anyio
async def test_superuser_can_transfer_team_ownership():
    global _USERS, _MEMBERSHIPS, _TEAM, _OWNER_MEMBERSHIP

    superuser = SimpleNamespace(
        id=uuid4(), username="super", locale="en", is_superuser=True
    )
    old_owner = SimpleNamespace(
        id=uuid4(), username="old-owner", locale="en", is_superuser=False
    )
    new_owner = SimpleNamespace(
        id=uuid4(), username="new-owner", locale="en", is_superuser=False
    )
    _TEAM = SimpleNamespace(id=uuid4(), name="Team", owner=old_owner, save=AsyncMock())
    _OWNER_MEMBERSHIP = SimpleNamespace(
        user=old_owner,
        role=TeamMemberRole.OWNER,
        save=AsyncMock(),
    )
    new_owner_membership = SimpleNamespace(
        user=new_owner,
        role=TeamMemberRole.ADMIN,
        save=AsyncMock(),
    )
    _USERS = {new_owner.id: new_owner}
    _MEMBERSHIPS = {old_owner.id: _OWNER_MEMBERSHIP, new_owner.id: new_owner_membership}

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_user",
            new=AsyncMock(),
        ),
        patch(
            "app.api.v1.endpoints.teams.sync_user_role_from_teams",
            new=AsyncMock(),
        ) as sync_roles,
    ):
        response = await teams.transfer_ownership(
            team_id=_TEAM.id,
            new_owner_id=new_owner.id,
            current_user=superuser,
        )

    assert response["code"] == 0
    assert _OWNER_MEMBERSHIP.role == TeamMemberRole.ADMIN
    assert new_owner_membership.role == TeamMemberRole.OWNER
    assert _TEAM.owner is new_owner
    sync_roles.assert_any_await(old_owner)
    sync_roles.assert_any_await(new_owner)


@pytest.mark.anyio
async def test_transfer_ownership_rejects_existing_owner():
    global _USERS, _MEMBERSHIPS, _TEAM, _OWNER_MEMBERSHIP

    superuser = SimpleNamespace(
        id=uuid4(), username="super", locale="en", is_superuser=True
    )
    old_owner = SimpleNamespace(
        id=uuid4(), username="old-owner", locale="en", is_superuser=False
    )
    _TEAM = SimpleNamespace(id=uuid4(), name="Team", owner=old_owner, save=AsyncMock())
    _OWNER_MEMBERSHIP = SimpleNamespace(
        user=old_owner,
        role=TeamMemberRole.OWNER,
        save=AsyncMock(),
    )
    _USERS = {old_owner.id: old_owner}
    _MEMBERSHIPS = {old_owner.id: _OWNER_MEMBERSHIP}

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        pytest.raises(teams.BusinessError) as error,
    ):
        await teams.transfer_ownership(
            team_id=_TEAM.id,
            new_owner_id=old_owner.id,
            current_user=superuser,
        )

    assert error.value.msg_key == "cannot_promote_to_owner"
    _OWNER_MEMBERSHIP.save.assert_not_awaited()


@pytest.mark.anyio
async def test_superuser_transfer_handles_missing_previous_owner():
    global _USERS, _MEMBERSHIPS, _TEAM, _OWNER_MEMBERSHIP

    superuser = SimpleNamespace(
        id=uuid4(), username="super", locale="en", is_superuser=True
    )
    new_owner = SimpleNamespace(
        id=uuid4(), username="new-owner", locale="en", is_superuser=False
    )
    _TEAM = SimpleNamespace(id=uuid4(), name="Team", owner=None, save=AsyncMock())
    _OWNER_MEMBERSHIP = None
    new_owner_membership = SimpleNamespace(
        user=new_owner,
        role=TeamMemberRole.ADMIN,
        save=AsyncMock(),
    )
    _USERS = {new_owner.id: new_owner}
    _MEMBERSHIPS = {new_owner.id: new_owner_membership}

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_user",
            new=AsyncMock(),
        ) as notify_user,
        patch(
            "app.api.v1.endpoints.teams.sync_user_role_from_teams",
            new=AsyncMock(),
        ) as sync_roles,
    ):
        response = await teams.transfer_ownership(
            team_id=_TEAM.id,
            new_owner_id=new_owner.id,
            current_user=superuser,
        )

    assert response["code"] == 0
    assert new_owner_membership.role == TeamMemberRole.OWNER
    assert _TEAM.owner is new_owner
    assert notify_user.await_count == 1
    sync_roles.assert_awaited_once_with(new_owner)
