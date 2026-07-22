from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberAdd, TeamMemberRole, TeamMemberUpdate, TeamUpdate


class Query:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    def exclude(self, *_args, **_kwargs):
        return self

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def user(*, is_superuser=False):
    return SimpleNamespace(
        id=uuid4(),
        username="member",
        email="member@example.com",
        avatar_url=None,
        locale="en",
        is_superuser=is_superuser,
    )


def team(owner=None):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name="Platform",
        description="Original",
        avatar_url=None,
        is_default=False,
        owner=owner,
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
async def test_get_my_teams_and_get_team_success(monkeypatch):
    current_user = user()
    item = team()
    current_membership = membership(current_user, TeamMemberRole.ADMIN)
    listed_membership = membership(current_user)
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(
            side_effect=[
                Query(
                    [
                        SimpleNamespace(
                            team=item, role="admin", joined_at=datetime.now(UTC)
                        )
                    ]
                ),
                Query(current_membership),
                Query([listed_membership]),
            ]
        ),
    )
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    permission = AsyncMock()
    monkeypatch.setattr(teams.deps, "check_scoped_permission", permission)

    mine = await teams.get_my_teams(current_user)
    detail = await teams.get_team(item.id, current_user)

    assert mine["data"][0]["id"] == item.id
    assert detail["data"]["members"][0]["user_id"] == current_user.id
    permission.assert_awaited_once_with(current_user, "team:read", "team", item.id)


@pytest.mark.anyio
async def test_get_team_rejects_missing_team_and_non_member(monkeypatch):
    current_user = user()
    item = team()
    monkeypatch.setattr(
        teams.Team, "filter", MagicMock(side_effect=[Query(None), Query(item)])
    )
    monkeypatch.setattr(teams.TeamMember, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as missing:
        await teams.get_team(item.id, current_user)
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as denied:
        await teams.get_team(item.id, current_user)
    assert_error(denied, ResponseCode.NOT_TEAM_MEMBER, 403)


@pytest.mark.anyio
async def test_update_team_authorization_duplicate_and_success(monkeypatch):
    current_user = user()
    item = team(current_user)
    admin = membership(current_user, TeamMemberRole.ADMIN)
    reloaded = team(current_user)
    reloaded.id = item.id
    team_filter = MagicMock(
        side_effect=[Query(None), Query(item), Query(None), Query(item), Query(None)]
    )
    monkeypatch.setattr(teams.Team, "filter", team_filter)
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(None), Query(admin), Query(admin)]),
    )
    monkeypatch.setattr(teams.Team, "get", MagicMock(return_value=Query(reloaded)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())
    audit = AsyncMock()
    monkeypatch.setattr(teams.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as missing:
        await teams.update_team(
            request=object(),
            team_id=item.id,
            team_in=TeamUpdate(),
            current_user=current_user,
        )
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as denied:
        await teams.update_team(
            request=object(),
            team_id=item.id,
            team_in=TeamUpdate(),
            current_user=current_user,
        )
    assert_error(denied, ResponseCode.TEAM_ADMIN_REQUIRED, 403)

    team_filter.side_effect = [Query(item), Query(object()), Query(item), Query(None)]
    with pytest.raises(BusinessError) as duplicate:
        await teams.update_team(
            request=object(),
            team_id=item.id,
            team_in=TeamUpdate(name="Taken"),
            current_user=current_user,
        )
    assert_error(duplicate, ResponseCode.TEAM_NAME_EXISTS)

    response = await teams.update_team(
        request=object(),
        team_id=item.id,
        team_in=TeamUpdate(name="Renamed", description="New", avatar_url="avatar"),
        current_user=current_user,
    )
    assert response["data"] is reloaded
    assert (item.name, item.description, item.avatar_url) == (
        "Renamed",
        "New",
        "avatar",
    )
    item.save.assert_awaited_once()
    assert audit.await_args.kwargs["metadata"]["fields_updated"] == [
        "name",
        "description",
        "avatar_url",
    ]


@pytest.mark.anyio
async def test_update_member_rejects_non_owner_and_missing_target(monkeypatch):
    current_user = user()
    item = team()
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(return_value=Query(membership(current_user, TeamMemberRole.ADMIN))),
    )
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(None)))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as denied:
        await teams.update_team_member(
            team_id=item.id,
            user_id=uuid4(),
            member_in=TeamMemberUpdate(role=TeamMemberRole.VIEWER),
            current_user=current_user,
        )
    assert_error(denied, ResponseCode.TEAM_OWNER_REQUIRED, 403)

    current_user.is_superuser = True
    with pytest.raises(BusinessError) as missing:
        await teams.update_team_member(
            team_id=item.id,
            user_id=uuid4(),
            member_in=TeamMemberUpdate(role=TeamMemberRole.VIEWER),
            current_user=current_user,
        )
    assert_error(missing, ResponseCode.USER_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_update_member_role_guards_and_success_without_real_notifications(
    monkeypatch,
):
    current_user = user(is_superuser=True)
    target = user()
    item = team()
    owner_membership = membership(target, TeamMemberRole.OWNER)
    regular_membership = membership(target, TeamMemberRole.MEMBER)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(target)))
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(
            side_effect=[
                Query(owner_membership),
                Query(regular_membership),
                Query(regular_membership),
            ]
        ),
    )
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())
    notify = AsyncMock()
    sync = AsyncMock()
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(teams, "sync_user_role_from_teams", sync)

    with pytest.raises(BusinessError) as owner_guard:
        await teams.update_team_member(
            team_id=item.id,
            user_id=target.id,
            member_in=TeamMemberUpdate(role=TeamMemberRole.ADMIN),
            current_user=current_user,
        )
    assert_error(owner_guard, ResponseCode.CANNOT_CHANGE_OWNER_ROLE)

    with pytest.raises(BusinessError) as promotion_guard:
        await teams.update_team_member(
            team_id=item.id,
            user_id=target.id,
            member_in=TeamMemberUpdate(role=TeamMemberRole.OWNER),
            current_user=current_user,
        )
    assert_error(promotion_guard, ResponseCode.CANNOT_PROMOTE_TO_OWNER)

    response = await teams.update_team_member(
        team_id=item.id,
        user_id=target.id,
        member_in=TeamMemberUpdate(role=TeamMemberRole.VIEWER),
        current_user=current_user,
    )
    assert response["data"]["role"] == TeamMemberRole.VIEWER
    regular_membership.save.assert_awaited_once()
    notify.assert_awaited_once()
    sync.assert_awaited_once_with(target)


@pytest.mark.anyio
async def test_remove_member_requires_admin_for_other_user(monkeypatch):
    current_user = user()
    target = user()
    item = team()
    target_membership = membership(target)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(teams.User, "filter", MagicMock(return_value=Query(target)))
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(target_membership), Query(None)]),
    )
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())

    with pytest.raises(BusinessError) as denied:
        await teams.remove_team_member(object(), item.id, target.id, current_user)
    assert_error(denied, ResponseCode.TEAM_ADMIN_REQUIRED, 403)
    target_membership.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_remove_member_self_service_mocks_all_side_effects(monkeypatch):
    current_user = user()
    item = team()
    target_membership = membership(current_user)
    monkeypatch.setattr(teams.Team, "filter", MagicMock(return_value=Query(item)))
    monkeypatch.setattr(
        teams.User, "filter", MagicMock(return_value=Query(current_user))
    )
    monkeypatch.setattr(
        teams.TeamMember, "filter", MagicMock(return_value=Query(target_membership))
    )
    permission = AsyncMock()
    monkeypatch.setattr(teams.deps, "check_scoped_permission", permission)
    audit = AsyncMock()
    notify_user = AsyncMock()
    notify_team = AsyncMock()
    sync = AsyncMock()
    monkeypatch.setattr(teams.AuditLogService, "log", audit)
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_user", notify_user)
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_team", notify_team)
    monkeypatch.setattr(teams, "get_default_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(teams, "sync_user_role_from_teams", sync)

    response = await teams.remove_team_member(
        object(), item.id, current_user.id, current_user
    )

    assert response["data"] == {"user_id": str(current_user.id)}
    permission.assert_not_awaited()
    audit.assert_awaited_once()
    notify_user.assert_awaited_once()
    notify_team.assert_awaited_once()
    target_membership.delete.assert_awaited_once()
    sync.assert_awaited_once_with(current_user)


@pytest.mark.anyio
async def test_leave_team_error_branches_and_success(monkeypatch):
    current_user = user()
    item = team()
    owner = membership(current_user, TeamMemberRole.OWNER)
    regular = membership(current_user)
    monkeypatch.setattr(
        teams.Team,
        "filter",
        MagicMock(side_effect=[Query(None), Query(item), Query(item), Query(item)]),
    )
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(None), Query(owner), Query(regular)]),
    )
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())
    sync = AsyncMock()
    monkeypatch.setattr(teams, "sync_user_role_from_teams", sync)

    with pytest.raises(BusinessError) as missing_team:
        await teams.leave_team(item.id, current_user)
    assert_error(missing_team, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as not_member:
        await teams.leave_team(item.id, current_user)
    assert_error(not_member, ResponseCode.NOT_TEAM_MEMBER, 404)

    with pytest.raises(BusinessError) as owner_guard:
        await teams.leave_team(item.id, current_user)
    assert_error(owner_guard, ResponseCode.OWNER_CANNOT_LEAVE)

    response = await teams.leave_team(item.id, current_user)
    assert response["data"] == {"team_id": str(item.id)}
    regular.delete.assert_awaited_once()
    sync.assert_awaited_once_with(current_user)


@pytest.mark.anyio
async def test_add_member_error_branches_and_success(monkeypatch):
    operator = user(is_superuser=True)
    target = user()
    item = team()
    created = membership(target)
    monkeypatch.setattr(
        teams.Team,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(item),
                Query(item),
                Query(item),
                Query(item),
            ]
        ),
    )
    monkeypatch.setattr(
        teams.User,
        "filter",
        MagicMock(
            side_effect=[Query(None), Query(target), Query(target), Query(target)]
        ),
    )
    monkeypatch.setattr(
        teams.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(object()), Query(None), Query(None)]),
    )
    monkeypatch.setattr(teams.TeamMember, "create", AsyncMock(return_value=created))
    monkeypatch.setattr(teams.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(teams.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_user", AsyncMock())
    monkeypatch.setattr(teams.AutoNotificationService, "send_to_team", AsyncMock())
    monkeypatch.setattr(teams, "get_default_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(teams, "sync_user_role_from_teams", AsyncMock())

    cases = [
        (ResponseCode.TEAM_NOT_FOUND, TeamMemberAdd(user_id=target.id)),
        (ResponseCode.USER_NOT_FOUND, TeamMemberAdd(user_id=target.id)),
        (ResponseCode.ALREADY_TEAM_MEMBER, TeamMemberAdd(user_id=target.id)),
        (
            ResponseCode.CANNOT_ADD_AS_OWNER,
            TeamMemberAdd(user_id=target.id, role=TeamMemberRole.OWNER),
        ),
    ]
    for code, payload in cases:
        with pytest.raises(BusinessError) as exc_info:
            await teams.add_team_member(
                request=object(),
                team_id=item.id,
                member_in=payload,
                current_user=operator,
            )
        assert exc_info.value.code == code

    response = await teams.add_team_member(
        request=object(),
        team_id=item.id,
        member_in=TeamMemberAdd(user_id=target.id),
        current_user=operator,
    )
    assert response["data"]["user_id"] == target.id
