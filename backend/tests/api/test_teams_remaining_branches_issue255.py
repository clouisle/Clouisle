from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberRole, TeamMemberUpdate, TeamUpdate


class Query:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def exclude(self, **_kwargs):
        return self

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


def user(*, is_superuser=False):
    return SimpleNamespace(
        id=uuid4(),
        username="tester",
        email="tester@example.com",
        avatar_url=None,
        locale="en",
        is_superuser=is_superuser,
    )


def team():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name="Platform",
        description=None,
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
        role=role,
        joined_at=datetime.now(UTC),
        save=AsyncMock(),
        delete=AsyncMock(),
    )


def assert_error(exc_info, code, status_code=400):
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.anyio
async def test_get_team_superuser_skips_membership_lookup(monkeypatch):
    current_user = user(is_superuser=True)
    item = team()
    listed_member = membership(user())
    member_filter = MagicMock(return_value=Query([listed_member]))
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.TeamMember, "filter", member_filter)
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    response = await teams.get_team(item.id, current_user)

    assert response["data"]["id"] == item.id
    member_filter.assert_called_once_with(team=item)


@pytest.mark.anyio
async def test_update_team_accepts_no_changed_fields(monkeypatch):
    current_user = user(is_superuser=True)
    item = team()
    reloaded = team()
    reloaded.id = item.id
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.Team, "get", MagicMock(return_value=Query(reloaded)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())
    audit = AsyncMock()
    monkeypatch.setattr(teams.AuditLogService, "log", audit)

    response = await teams.update_team(
        request=object(),
        team_id=item.id,
        team_in=TeamUpdate(),
        current_user=current_user,
    )

    assert response["data"] is reloaded
    item.save.assert_awaited_once()
    assert audit.await_args.kwargs["metadata"] == {"fields_updated": []}


@pytest.mark.anyio
async def test_update_member_missing_team(monkeypatch):
    current_user = user(is_superuser=True)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.update_team_member(
            team_id=uuid4(),
            user_id=uuid4(),
            member_in=TeamMemberUpdate(role=TeamMemberRole.ADMIN),
            current_user=current_user,
        )

    assert_error(exc_info, ResponseCode.TEAM_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_owner_update_rejects_missing_membership(monkeypatch):
    current_user = user()
    target_user = user()
    item = team()
    owner_membership = membership(current_user, TeamMemberRole.OWNER)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(
        teams.User, "filter", MagicMock(return_value=Query(target_user))
    )
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(owner_membership), Query(None)]),
    )
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.update_team_member(
            team_id=item.id,
            user_id=target_user.id,
            member_in=TeamMemberUpdate(role=TeamMemberRole.ADMIN),
            current_user=current_user,
        )

    assert_error(exc_info, ResponseCode.TEAM_MEMBER_NOT_FOUND, 404)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("found_team", "found_user", "found_membership", "expected_code", "status_code"),
    [
        (False, True, True, ResponseCode.TEAM_NOT_FOUND, 404),
        (True, False, True, ResponseCode.USER_NOT_FOUND, 404),
        (True, True, False, ResponseCode.TEAM_MEMBER_NOT_FOUND, 404),
        (True, True, "owner", ResponseCode.CANNOT_REMOVE_OWNER, 400),
    ],
)
async def test_remove_member_lookup_and_owner_guards(
    monkeypatch,
    found_team,
    found_user,
    found_membership,
    expected_code,
    status_code,
):
    current_user = user(is_superuser=True)
    target_user = user()
    item = team()
    target_membership = membership(
        target_user,
        TeamMemberRole.OWNER if found_membership == "owner" else TeamMemberRole.MEMBER,
    )
    monkeypatch.setattr(
        teams.Team,
        "filter",
        MagicMock(return_value=Query(item if found_team else None)),
    )
    monkeypatch.setattr(
        teams.User,
        "filter",
        MagicMock(return_value=Query(target_user if found_user else None)),
    )
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(return_value=Query(target_membership if found_membership else None)),
    )
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.remove_team_member(object(), item.id, target_user.id, current_user)

    assert_error(exc_info, expected_code, status_code)
    target_membership.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_transfer_ownership_missing_team(monkeypatch):
    current_user = user(is_superuser=True)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.transfer_ownership(
            team_id=uuid4(), new_owner_id=uuid4(), current_user=current_user
        )

    assert_error(exc_info, ResponseCode.TEAM_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_transfer_ownership_requires_current_owner(monkeypatch):
    current_user = user()
    item = team()
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.TeamMember, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.transfer_ownership(
            team_id=item.id, new_owner_id=uuid4(), current_user=current_user
        )

    assert_error(exc_info, ResponseCode.TEAM_OWNER_REQUIRED, 403)


@pytest.mark.anyio
async def test_transfer_ownership_rejects_missing_new_member(monkeypatch):
    current_user = user(is_superuser=True)
    item = team()
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.TeamMember, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await teams.transfer_ownership(
            team_id=item.id, new_owner_id=uuid4(), current_user=current_user
        )

    assert_error(exc_info, ResponseCode.TEAM_MEMBER_NOT_FOUND, 404)
