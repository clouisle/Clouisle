"""Pagination filters and authorization revocation for durable assets.

The cases below exercise the observable contract of the listing and lifecycle
surface: rejected filters, scope isolation for actor-less listings, file-kind
pagination, workflow-run discovery, revoked manifest attachments, expiry, and
bounded reads. They deliberately use the real ORM and storage instead of
asserting call wiring.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
    AssetStatus,
    MessageAsset,
)
from app.models.user import Team, User
from app.schemas.response import BusinessError
from app.services import asset_access
from app.services.asset import AssetService
from app.services.upload_storage import LocalUploadStorage


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


async def create_asset(
    *,
    name="file.png",
    content_type="image/png",
    team_id=None,
    created_by_id=None,
    expires_at=None,
    status=AssetStatus.AVAILABLE,
):
    return await Asset.create(
        id=uuid4(),
        team_id=team_id,
        created_by_id=created_by_id,
        storage_key=f"assets/{uuid4()}",
        original_filename=name,
        display_filename=name,
        content_type=content_type,
        size=12,
        checksum="a" * 64,
        source=AssetSource.UPLOAD,
        status=status,
        expires_at=expires_at,
    )


async def add_ref(*, scope_type, scope_id, asset, ref):
    return await AssetScopeRef.create(
        id=uuid4(),
        scope_type=scope_type,
        scope_id=scope_id,
        asset=asset,
        ref=ref,
    )


@pytest.mark.asyncio
async def test_list_rejects_invalid_query_kind_and_cursor(monkeypatch, database):
    monkeypatch.setattr(
        asset_access, "authorize_asset_scope", AsyncMock(return_value=None)
    )
    args = dict(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=uuid4(),
        user=None,
    )

    with pytest.raises(ValueError, match="filename substring"):
        await asset_access.list_authorized_assets(**args, query="x" * 201)
    with pytest.raises(ValueError, match="kind must be"):
        await asset_access.list_authorized_assets(**args, kind="document")

    for cursor in ("zzzz", "abc", 1234):
        with pytest.raises(ValueError, match="cursor must be a ref"):
            await asset_access.list_authorized_assets(**args, cursor=cursor)


@pytest.mark.asyncio
async def test_actorless_listing_hides_team_and_user_owned_assets(
    monkeypatch, database
):
    monkeypatch.setattr(
        asset_access, "authorize_asset_scope", AsyncMock(return_value=None)
    )
    owner = await User.create(
        id=uuid4(),
        username="owner",
        email="owner@example.test",
        hashed_password="unused",
    )
    team = await Team.create(id=uuid4(), name="private-team")
    scope_id = uuid4()
    await add_ref(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        asset=await create_asset(name="team.png", team_id=team.id),
        ref="0001",
    )
    await add_ref(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        asset=await create_asset(name="owned.png", created_by_id=owner.id),
        ref="0002",
    )
    await add_ref(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        asset=await create_asset(name="global.png"),
        ref="0003",
    )

    result = await asset_access.list_authorized_assets(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        user=None,
    )

    assert [item["name"] for item in result["items"]] == ["global.png"]
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_file_kind_pagination_excludes_media_assets(monkeypatch, database):
    monkeypatch.setattr(
        asset_access, "authorize_asset_scope", AsyncMock(return_value=None)
    )
    scope_id = uuid4()
    for ref, name, content_type in (
        ("0001", "photo.png", "image/png"),
        ("0002", "track.mp3", "audio/mpeg"),
        ("0003", "clip.mp4", "video/mp4"),
        ("0004", "notes.txt", "text/plain"),
        ("0005", "report.pdf", "application/pdf"),
    ):
        await add_ref(
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=scope_id,
            asset=await create_asset(name=name, content_type=content_type),
            ref=ref,
        )

    result = await asset_access.list_authorized_assets(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        user=None,
        kind="file",
    )

    assert [item["name"] for item in result["items"]] == ["notes.txt", "report.pdf"]


@pytest.mark.asyncio
async def test_workflow_scope_pages_do_not_consult_conversation_visibility(
    monkeypatch, database
):
    team = await Team.create(id=uuid4(), name="workflow-team")
    monkeypatch.setattr(
        asset_access, "authorize_asset_scope", AsyncMock(return_value=team.id)
    )
    scope_id = uuid4()
    for ref, name in (("0001", "first.txt"), ("0002", "second.txt")):
        await add_ref(
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=scope_id,
            asset=await create_asset(
                name=name, content_type="text/plain", team_id=team.id
            ),
            ref=ref,
        )

    first = await asset_access.list_authorized_assets(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        user=SimpleNamespace(id=uuid4()),
        limit=1,
    )
    second = await asset_access.list_authorized_assets(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=scope_id,
        user=SimpleNamespace(id=uuid4()),
        limit=1,
        cursor=first["next_cursor"],
    )

    assert [item["name"] for item in first["items"]] == ["first.txt"]
    assert first["has_more"] is True
    assert [item["name"] for item in second["items"]] == ["second.txt"]
    assert second["has_more"] is False


@pytest.mark.asyncio
async def test_manifest_drops_revoked_and_inactive_attachments(database):
    user = await User.create(
        id=uuid4(),
        username="reader",
        email="reader@example.test",
        hashed_password="unused",
    )
    team = await Team.create(id=uuid4(), name="home-team")
    foreign_team = await Team.create(id=uuid4(), name="foreign-team")
    agent = await Agent.create(id=uuid4(), name="reader", team=team)
    conversation = await Conversation.create(id=uuid4(), agent=agent, user=user)
    active_message = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role=MessageRole.USER,
        content="active",
        is_active=True,
    )
    inactive_message = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role=MessageRole.USER,
        content="superseded",
        is_active=False,
    )

    visible = await create_asset(name="visible.txt", content_type="text/plain")
    await MessageAsset.create(
        id=uuid4(), message=active_message, asset=visible, role="attachment"
    )
    foreign = await create_asset(
        name="foreign.txt", content_type="text/plain", team_id=foreign_team.id
    )
    await MessageAsset.create(
        id=uuid4(), message=active_message, asset=foreign, role="attachment"
    )

    inactive_only = await create_asset(name="inactive.txt", content_type="text/plain")
    await MessageAsset.create(
        id=uuid4(), message=inactive_message, asset=inactive_only, role="attachment"
    )
    await add_ref(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=inactive_only,
        ref="0001",
    )

    revoked = await create_asset(
        name="revoked.txt", content_type="text/plain", team_id=foreign_team.id
    )
    await add_ref(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=revoked,
        ref="0002",
    )

    backfilled = await create_asset(name="backfilled.txt", content_type="text/plain")
    await add_ref(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=backfilled,
        ref="0003",
    )

    manifest = await AssetService().build_conversation_manifest(
        conversation_id=conversation.id,
        team_id=team.id,
        user_id=user.id,
    )

    assert {entry["name"] for entry in manifest} == {"visible.txt", "backfilled.txt"}


@pytest.mark.asyncio
async def test_get_authorized_rejects_expired_aware_and_naive_assets(database):
    service = AssetService()
    expired_aware = await create_asset(
        name="expired-aware.txt",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    expired_naive = await create_asset(
        name="expired-naive.txt",
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
    )
    future_naive = await create_asset(
        name="future-naive.txt",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )

    for asset in (expired_aware, expired_naive):
        with pytest.raises(BusinessError) as error:
            await service.get_authorized(asset.id, team_id=None, user_id=None)
        assert error.value.status_code == 404
        assert error.value.msg_key == "file_not_found"

    returned = await service.get_authorized(future_naive.id, team_id=None, user_id=None)
    assert returned.id == future_naive.id


@pytest.mark.asyncio
async def test_attach_to_message_is_idempotent_per_role(database):
    user = await User.create(
        id=uuid4(),
        username="attacher",
        email="attacher@example.test",
        hashed_password="unused",
    )
    team = await Team.create(id=uuid4(), name="attach-team")
    agent = await Agent.create(id=uuid4(), name="attacher", team=team)
    conversation = await Conversation.create(id=uuid4(), agent=agent, user=user)
    message = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role=MessageRole.USER,
        content="attached",
    )
    asset = await create_asset(name="attached.txt", content_type="text/plain")
    service = AssetService()

    first = await service.attach_to_message(
        asset=asset, message_id=message.id, role="attachment", position=2
    )
    second = await service.attach_to_message(
        asset=asset, message_id=message.id, role="attachment", position=9
    )

    assert first.id == second.id
    assert second.position == 2
    assert await MessageAsset.filter(message_id=message.id).count() == 1


@pytest.mark.asyncio
async def test_read_bounded_rejects_oversize_unsupported_and_tampered_storage(
    tmp_path,
):
    service = AssetService()
    content = b"bounded-content"
    storage = LocalUploadStorage(tmp_path)
    await storage.save("bounded.txt", content, "text/plain")
    asset = SimpleNamespace(
        storage_key="bounded.txt",
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
    )

    with pytest.raises(ValueError, match="asset_view_size_limit_exceeded"):
        await service.read_bounded(asset, storage=storage, max_bytes=len(content) - 1)

    with pytest.raises(RuntimeError, match="does not support bounded reads"):
        await service.read_bounded(
            asset, storage=SimpleNamespace(), max_bytes=len(content)
        )

    tampered = SimpleNamespace(
        storage_key="bounded.txt",
        size=len(content),
        checksum="0" * 64,
    )
    with pytest.raises(RuntimeError, match="does not match"):
        await service.read_bounded(tampered, storage=storage, max_bytes=len(content))
