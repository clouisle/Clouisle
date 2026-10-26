"""Scope-local asset discovery with real ORM pagination and branch isolation."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.agent import Agent, Conversation, Message, MessageRole
from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetSource,
    MessageAsset,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError
from app.services.asset_access import list_authorized_assets
from app.api.v1.endpoints.chat_tools import execute_tool_call


async def _grant_team_read(user, team):
    permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"Asset user {uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    await TeamMember.create(team=team, user=user, role="owner")


@pytest_asyncio.fixture
async def scope():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        user = await User.create(
            id=uuid4(),
            username="owner",
            email="owner@example.test",
            hashed_password="unused",
        )
        team = await Team.create(id=uuid4(), name="assets")
        agent = await Agent.create(
            id=uuid4(), name="reader", team=team, enable_attachments=True
        )
        conversation = await Conversation.create(id=uuid4(), agent=agent, user=user)
        yield user, team, agent, conversation


async def add_asset(
    scope, ref, name, *, active=True, linked=True, expired=False, conversation=None
):
    user, team, agent, current = scope
    conversation = conversation or current
    asset = await Asset.create(
        id=uuid4(),
        team=team,
        created_by=user,
        storage_key=f"private/{uuid4()}",
        original_filename=name,
        display_filename=name,
        content_type="image/png",
        size=12,
        checksum="abc",
        source=AssetSource.UPLOAD,
        expires_at=datetime.now(UTC) - timedelta(seconds=1) if expired else None,
    )
    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref=ref,
    )
    if linked:
        message = await Message.create(
            id=uuid4(),
            conversation=conversation,
            role=MessageRole.USER,
            content="attachment",
            is_active=active,
        )
        await MessageAsset.create(id=uuid4(), message=message, asset=asset)
    return asset


@pytest.mark.asyncio
async def test_discovers_older_assets_with_stable_pages_and_filename_search(scope):
    user, team, agent, conversation = scope
    await _grant_team_read(user, team)
    for index in range(25):
        await add_asset(scope, f"{index:04x}", f"Screenshot-{index:02}.png")
    args = dict(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        user=user,
        expected_team_id=team.id,
    )
    first = await list_authorized_assets(**args, limit=12)
    second = await list_authorized_assets(**args, limit=12, cursor=first["next_cursor"])
    third = await list_authorized_assets(**args, limit=12, cursor=second["next_cursor"])
    default_page = await list_authorized_assets(**args)
    assert len(default_page["items"]) == 10
    assert len((await list_authorized_assets(**args, limit=30))["items"]) == 25
    with pytest.raises(ValueError):
        await list_authorized_assets(**args, limit=31)
    refs = [item["ref"] for page in (first, second, third) for item in page["items"]]
    assert refs == [f"{index:04x}" for index in range(25)]
    assert third["has_more"] is False and third["next_cursor"] is None

    from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope

    # Trusted read-only internal tools execute without an approval gate.
    identity = RuntimeToolIdentity(
        run_id=uuid4(),
        tool_call_id="call-list",
        entrypoint="chat",
        entrypoint_id=str(conversation.id),
        interactive=True,
    )
    with tool_identity_scope(identity):
        result = json.loads(
            await execute_tool_call(
                "list_assets",
                {"query": "SCREENSHOT-24", "kind": "image"},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
            )
        )
    assert [item["ref"] for item in result["items"]] == ["0018"]
    assert "url" not in result["items"][0] and "base64" not in result["items"][0]


@pytest.mark.asyncio
async def test_discovery_excludes_hidden_expired_and_other_scope_assets(scope):
    user, team, agent, conversation = scope
    await add_asset(scope, "0001", "visible.png")
    await add_asset(scope, "0002", "hidden.png", active=False)
    await add_asset(scope, "0003", "expired.png", expired=True)
    await add_asset(scope, "0004", "sandbox.png", linked=False)
    other = await Conversation.create(id=uuid4(), agent=agent, user=user)
    await add_asset(scope, "0005", "other.png", conversation=other)
    result = await list_authorized_assets(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        user=user,
        expected_team_id=team.id,
    )
    assert [item["name"] for item in result["items"]] == ["visible.png", "sandbox.png"]
    outsider = await User.create(
        id=uuid4(),
        username="outsider",
        email="outsider@example.test",
        hashed_password="unused",
    )
    outsider = await User.get(id=outsider.id).prefetch_related("roles__permissions")
    with pytest.raises(BusinessError):
        await list_authorized_assets(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation.id,
            user=outsider,
            expected_team_id=team.id,
        )
