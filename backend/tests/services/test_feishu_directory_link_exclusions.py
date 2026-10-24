"""Manually linked Feishu identities are not directory-managed accounts."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import Request
from tortoise import Tortoise

from app.integrations.feishu import FeishuDepartment, FeishuDirectoryUser
from app.models.feishu_user import FeishuUser
from app.models.integration import Integration
from app.models.user import Team, TeamMember, User
from app.models.user_sso_connection import UserSSOConnection
from app.services.feishu_directory import sync_department_teams, sync_directory_users


@pytest_asyncio.fixture
async def directory(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    monkeypatch.setattr(
        "app.services.feishu_directory.AuditLogService.log", AsyncMock()
    )
    try:
        yield await Integration.create(
            name="feishu", provider_type="feishu", display_name="Feishu"
        )
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_type", ["union_id", "open_id", "user_id"])
async def test_manually_linked_member_is_skipped_without_duplicate_account(
    directory, subject_type
):
    user = await User.create(
        username="local",
        email="local@example.com",
        hashed_password="kept",
        avatar_url="https://example.com/local.png",
    )
    member = FeishuDirectoryUser(
        "directory-user",
        "open-user",
        "union-user",
        "Directory name",
        "different@example.com",
        "https://example.com/remote.png",
        frozenset({"department"}),
    )
    subject = member.union_id if subject_type == "union_id" else member.open_id
    profile = {"user_id": member.user_id} if subject_type == "user_id" else {}
    connection = await UserSSOConnection.create(
        user=user,
        integration=directory,
        provider_user_id=subject,
        provider_data=profile,
    )
    # A login connection and a manual account link carry different ownership.
    await UserSSOConnection.filter(id=connection.id).update(self_service_linked=True)

    result = await sync_directory_users(
        [member], actor=user, request=Request({"type": "http", "headers": []})
    )
    assert (result.created, result.updated, result.skipped) == (0, 0, 1)
    assert await User.all().count() == 1
    assert not await FeishuUser.all().exists()
    refreshed = await User.get(id=user.id)
    assert (
        refreshed.email,
        refreshed.avatar_url,
        refreshed.hashed_password,
        refreshed.auth_source,
    ) == ("local@example.com", "https://example.com/local.png", "kept", "local")


@pytest.mark.asyncio
async def test_previously_directory_mapped_manual_user_keeps_profile_and_memberships(
    directory,
):
    linked = await User.create(
        username="linked", email="linked@example.com", hashed_password="kept"
    )
    managed = await User.create(
        username="managed",
        email="old@example.com",
        hashed_password="",
        auth_source="feishu",
        external_id="managed-id",
    )
    await FeishuUser.create(user=linked, feishu_user_id="linked-id")
    await FeishuUser.create(user=managed, feishu_user_id="managed-id")
    connection = await UserSSOConnection.create(
        user=linked, integration=directory, provider_user_id="old-union"
    )
    await UserSSOConnection.filter(id=connection.id).update(self_service_linked=True)
    existing_team = await Team.create(name="Local team")
    await TeamMember.create(team=existing_team, user=linked, role="admin")
    members = [
        FeishuDirectoryUser(
            "linked-id",
            "new-open",
            "new-union",
            "Linked",
            "changed@example.com",
            None,
            frozenset({"department"}),
        ),
        FeishuDirectoryUser(
            "managed-id",
            "managed-open",
            None,
            "Managed",
            "managed@example.com",
            None,
            frozenset({"department"}),
        ),
    ]

    result = await sync_directory_users(
        members, actor=linked, request=Request({"type": "http", "headers": []})
    )
    assert (result.created, result.updated, result.skipped) == (0, 1, 1)
    assert (await User.get(id=linked.id)).email == "linked@example.com"
    assert (await User.get(id=managed.id)).email == "managed@example.com"
    await sync_department_teams(
        [FeishuDepartment("department", "Department", None)], members
    )
    assert await TeamMember.filter(user=linked).count() == 1
    assert (await TeamMember.get(user=linked)).role == "admin"
    assert await TeamMember.filter(user=managed, team__name="Department").exists()


@pytest.mark.asyncio
async def test_ordinary_sso_login_is_not_a_directory_exclusion(directory, monkeypatch):
    user = await User.create(
        username="login", email="login@example.com", hashed_password="kept"
    )
    connection = await UserSSOConnection.create(
        user=user,
        integration=directory,
        provider_user_id="union-login",
        self_service_linked=True,
    )
    from app.services.sso import SSOService

    restored, created = await SSOService.find_or_create_user(
        provider=directory,
        provider_user_id="union-login",
        user_info={"email": "login@example.com"},
    )
    assert restored.id == user.id and created is False
    member = FeishuDirectoryUser(
        "login-id", "open-login", "union-login", "Login", "changed@example.com", None
    )
    request = Request({"type": "http", "headers": []})
    result = await sync_directory_users([member], actor=user, request=request)
    assert (result.created, result.updated, result.skipped) == (0, 0, 1)
    # Ordinary OAuth connections must not accidentally inherit the exclusion.
    await UserSSOConnection.filter(id=connection.id).update(self_service_linked=False)
    await FeishuUser.create(user=user, feishu_user_id="login-id")
    result = await sync_directory_users([member], actor=user, request=request)
    assert (result.created, result.updated, result.skipped) == (0, 1, 0)
    assert (await User.get(id=user.id)).email == "changed@example.com"
