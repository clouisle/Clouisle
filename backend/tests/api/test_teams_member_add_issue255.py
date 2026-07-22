from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberAdd, TeamMemberRole


class Query:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


def user(*, role=None, superuser=False):
    return SimpleNamespace(
        id=uuid4(),
        username="operator",
        email="operator@example.com",
        avatar_url=None,
        locale="en",
        is_superuser=superuser,
        role=role,
    )


@pytest.fixture
def permission(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(teams.deps, "check_scoped_permission", check)
    return check


@pytest.mark.anyio
async def test_add_member_rejects_missing_team(monkeypatch, permission):
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=uuid4(),
            member_in=TeamMemberAdd(user_id=uuid4()),
            current_user=user(superuser=True),
        )

    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND
    permission.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "membership", [None, SimpleNamespace(role=TeamMemberRole.MEMBER)]
)
async def test_add_member_requires_team_admin(monkeypatch, permission, membership):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(
        teams.TeamMember, "filter", MagicMock(return_value=Query(membership))
    )

    with pytest.raises(BusinessError) as exc_info:
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=uuid4()),
            current_user=user(),
        )

    assert exc_info.value.code == ResponseCode.TEAM_ADMIN_REQUIRED


@pytest.mark.anyio
async def test_add_member_rejects_missing_user(monkeypatch, permission):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=uuid4()),
            current_user=user(superuser=True),
        )

    assert exc_info.value.code == ResponseCode.USER_NOT_FOUND


@pytest.mark.anyio
async def test_add_member_rejects_existing_member(monkeypatch, permission):
    team = SimpleNamespace(id=uuid4())
    target = user()
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(target)))
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(return_value=Query(SimpleNamespace(role=TeamMemberRole.MEMBER))),
    )

    with pytest.raises(BusinessError) as exc_info:
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=target.id),
            current_user=user(superuser=True),
        )

    assert exc_info.value.code == ResponseCode.ALREADY_TEAM_MEMBER


@pytest.mark.anyio
async def test_add_member_rejects_owner_role(monkeypatch, permission):
    team = SimpleNamespace(id=uuid4())
    target = user()
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(target)))
    monkeypatch.setattr(teams.TeamMember, "filter", MagicMock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=target.id, role=TeamMemberRole.OWNER),
            current_user=user(superuser=True),
        )

    assert exc_info.value.code == ResponseCode.CANNOT_ADD_AS_OWNER


@pytest.mark.anyio
async def test_add_member_persists_audits_notifies_and_syncs(monkeypatch, permission):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    operator = user()
    target = user()
    membership = SimpleNamespace(
        id=uuid4(),
        role=TeamMemberRole.MEMBER,
        joined_at=SimpleNamespace(),
    )
    create = AsyncMock(return_value=membership)
    audit = AsyncMock()
    notify_user = AsyncMock()
    notify_team = AsyncMock()
    sync_roles = AsyncMock()

    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(target)))
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(
            side_effect=[Query(SimpleNamespace(role=TeamMemberRole.ADMIN)), Query(None)]
        ),
    )
    monkeypatch.setattr(teams.TeamMember, "create", create)
    monkeypatch.setattr(teams.AuditLogService, "log", audit)
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_user", notify_user)
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_team", notify_team)
    monkeypatch.setattr(teams, "sync_user_role_from_teams", sync_roles)
    monkeypatch.setattr(teams, "get_default_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(teams, "t", lambda key, **_kwargs: key)

    response = await teams.add_team_member(
        request=SimpleNamespace(),
        team_id=team.id,
        member_in=TeamMemberAdd(user_id=target.id),
        current_user=operator,
    )

    assert response["data"]["user_id"] == target.id
    create.assert_awaited_once_with(team=team, user=target, role=TeamMemberRole.MEMBER)
    audit.assert_awaited_once()
    notify_user.assert_awaited_once()
    notify_team.assert_awaited_once()
    sync_roles.assert_awaited_once_with(target)
