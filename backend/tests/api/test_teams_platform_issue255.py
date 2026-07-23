from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams
from app.schemas.team import TeamMemberRole, TeamUpdate


class Query:
    def __init__(self, result=None, *, first=None):
        self.result = [] if result is None else result
        self.first_value = first

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    def prefetch_related(self, *_args):
        return self

    def exclude(self, **_kwargs):
        return self

    async def first(self):
        return self.first_value


def user(*, superuser=False):
    return SimpleNamespace(
        id=uuid4(),
        username="actor",
        email="actor@example.com",
        avatar_url=None,
        locale="en",
        is_superuser=superuser,
    )


def team():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name="Platform",
        description="Original",
        avatar_url=None,
        is_default=False,
        owner=None,
        created_at=now,
        updated_at=now,
        save=AsyncMock(),
    )


def membership(member_user, role=TeamMemberRole.MEMBER):
    return SimpleNamespace(
        id=uuid4(),
        user=member_user,
        team=team(),
        role=role,
        joined_at=datetime.now(UTC),
        save=AsyncMock(),
        delete=AsyncMock(),
    )


@pytest.mark.anyio
async def test_get_my_teams_serializes_memberships():
    current_user = user()
    member = membership(current_user)
    member.team.name = "Docs"

    with patch.object(teams.TeamMember, "filter", return_value=Query([member])):
        response = await teams.get_my_teams(current_user=current_user)

    assert response["data"] == [
        {
            "id": member.team.id,
            "name": "Docs",
            "description": member.team.description,
            "avatar_url": member.team.avatar_url,
            "role": TeamMemberRole.MEMBER,
            "joined_at": member.joined_at,
        }
    ]


@pytest.mark.anyio
async def test_get_team_rejects_non_member_after_team_lookup():
    current_user = user()
    existing_team = team()

    with (
        patch.object(teams.deps, "check_scoped_permission", AsyncMock()),
        patch.object(teams.Team, "filter", return_value=Query(first=existing_team)),
        patch.object(teams.TeamMember, "filter", return_value=Query(first=None)),
        pytest.raises(teams.BusinessError) as error,
    ):
        await teams.get_team(team_id=existing_team.id, current_user=current_user)

    assert error.value.msg_key == "not_team_member"
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_update_team_rejects_duplicate_name_before_save():
    current_user = user(superuser=True)
    existing_team = team()
    duplicate = team()

    def team_filter(**kwargs):
        if "name" in kwargs:
            return Query(first=duplicate)
        return Query(first=existing_team)

    with (
        patch.object(teams.deps, "check_scoped_permission", AsyncMock()),
        patch.object(teams.Team, "filter", side_effect=team_filter),
        pytest.raises(teams.BusinessError) as error,
    ):
        await teams.update_team(
            request=SimpleNamespace(),
            team_id=existing_team.id,
            team_in=TeamUpdate(name="Taken"),
            current_user=current_user,
        )

    assert error.value.msg_key == "team_name_exists"
    existing_team.save.assert_not_awaited()


@pytest.mark.anyio
async def test_remove_team_member_self_removal_skips_manage_permission_and_notifications():
    current_user = user()
    existing_team = team()
    current_membership = membership(current_user)

    with (
        patch.object(teams.deps, "check_scoped_permission", AsyncMock()) as scoped,
        patch.object(teams.Team, "filter", return_value=Query(first=existing_team)),
        patch.object(teams.User, "filter", return_value=Query(first=current_user)),
        patch.object(
            teams.TeamMember, "filter", return_value=Query(first=current_membership)
        ),
        patch.object(teams.AuditLogService, "log", AsyncMock()),
        patch.object(teams.AutoNotificationService, "send_to_user", AsyncMock()),
        patch.object(teams.AutoNotificationService, "send_to_team", AsyncMock()),
        patch.object(teams, "get_default_language", AsyncMock(return_value="en")),
        patch.object(teams, "sync_user_role_from_teams", AsyncMock()) as sync_roles,
    ):
        response = await teams.remove_team_member(
            request=SimpleNamespace(),
            team_id=existing_team.id,
            user_id=current_user.id,
            current_user=current_user,
        )

    scoped.assert_not_awaited()
    current_membership.delete.assert_awaited_once()
    sync_roles.assert_awaited_once_with(current_user)
    assert response["data"] == {"user_id": str(current_user.id)}


@pytest.mark.anyio
async def test_leave_team_rejects_owner_and_deletes_member():
    current_user = user()
    existing_team = team()
    owner_membership = membership(current_user, TeamMemberRole.OWNER)
    member_membership = membership(current_user, TeamMemberRole.MEMBER)

    with (
        patch.object(teams.deps, "check_scoped_permission", AsyncMock()),
        patch.object(teams.Team, "filter", return_value=Query(first=existing_team)),
        patch.object(
            teams.TeamMember, "filter", return_value=Query(first=owner_membership)
        ),
        pytest.raises(teams.BusinessError) as error,
    ):
        await teams.leave_team(team_id=existing_team.id, current_user=current_user)

    assert error.value.msg_key == "owner_cannot_leave"

    with (
        patch.object(teams.deps, "check_scoped_permission", AsyncMock()),
        patch.object(teams.Team, "filter", return_value=Query(first=existing_team)),
        patch.object(
            teams.TeamMember, "filter", return_value=Query(first=member_membership)
        ),
        patch.object(teams, "sync_user_role_from_teams", AsyncMock()) as sync_roles,
    ):
        response = await teams.leave_team(
            team_id=existing_team.id, current_user=current_user
        )

    member_membership.delete.assert_awaited_once()
    sync_roles.assert_awaited_once_with(current_user)
    assert response["data"] == {"team_id": str(existing_team.id)}
