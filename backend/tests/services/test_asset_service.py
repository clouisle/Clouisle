from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from tortoise.exceptions import IntegrityError

from app.models.asset import AssetScopeType, AssetSource, AssetStatus
from app.schemas.response import BusinessError, ResponseCode
from app.services import asset as asset_module


ASSET_ID = UUID("00000000-0000-0000-0000-000000000001")
TEAM_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000003")
SCOPE_ID = UUID("00000000-0000-0000-0000-000000000004")


@pytest.mark.asyncio
async def test_register_bytes_computes_metadata(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(id=ASSET_ID))
    monkeypatch.setattr(asset_module.Asset, "create", create)

    await asset_module.AssetService().register_bytes(
        storage_key="general/2026/08/file.txt",
        original_filename="file.txt",
        content_type="text/plain",
        content=b"hello",
        source=AssetSource.UPLOAD,
        team_id=TEAM_ID,
        created_by_id=USER_ID,
    )

    assert create.await_args.kwargs["size"] == 5
    assert create.await_args.kwargs["checksum"] == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert create.await_args.kwargs["display_filename"] == "file.txt"


@pytest.mark.asyncio
async def test_register_rejects_invalid_metadata():
    with pytest.raises(BusinessError) as error:
        await asset_module.AssetService().register(
            storage_key="key",
            original_filename="file.txt",
            content_type="text/plain",
            size=-1,
            checksum="short",
            source=AssetSource.UPLOAD,
            team_id=TEAM_ID,
            created_by_id=USER_ID,
        )
    assert error.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_get_authorized_enforces_team_and_status(monkeypatch):
    asset = SimpleNamespace(
        id=ASSET_ID,
        team_id=TEAM_ID,
        created_by_id=USER_ID,
        status=AssetStatus.AVAILABLE,
    )
    monkeypatch.setattr(
        asset_module.Asset, "get_or_none", AsyncMock(return_value=asset)
    )

    assert (
        await asset_module.AssetService().get_authorized(
            ASSET_ID, team_id=TEAM_ID, user_id=USER_ID
        )
        is asset
    )
    with pytest.raises(BusinessError) as error:
        await asset_module.AssetService().get_authorized(
            ASSET_ID, team_id=None, user_id=USER_ID
        )
    assert error.value.status_code == 403

    asset.status = AssetStatus.EXPIRED
    with pytest.raises(BusinessError) as error:
        await asset_module.AssetService().get_authorized(
            ASSET_ID, team_id=TEAM_ID, user_id=USER_ID
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_scoped_ref_is_stable_and_retries_collision(monkeypatch):
    asset = SimpleNamespace(id=ASSET_ID)
    existing = SimpleNamespace(ref="00af")
    get_or_none = AsyncMock(side_effect=[None, existing])
    create = AsyncMock(side_effect=[IntegrityError(), SimpleNamespace(ref="12ab")])
    monkeypatch.setattr(asset_module.AssetScopeRef, "get_or_none", get_or_none)
    monkeypatch.setattr(asset_module.AssetScopeRef, "create", create)
    choices = iter("000012ab")
    monkeypatch.setattr(asset_module.secrets, "choice", lambda _alphabet: next(choices))

    result = await asset_module.AssetService().get_or_create_ref(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=SCOPE_ID,
        asset=asset,
    )

    assert result is existing
    assert create.await_args.kwargs["ref"] == "0000"


@pytest.mark.asyncio
async def test_resolve_ref_validates_format_and_scope(monkeypatch):
    service = asset_module.AssetService()
    with pytest.raises(BusinessError) as error:
        await service.resolve_ref(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=SCOPE_ID,
            ref="G123",
            team_id=TEAM_ID,
            user_id=USER_ID,
        )
    assert error.value.code == ResponseCode.VALIDATION_ERROR

    monkeypatch.setattr(
        asset_module.AssetScopeRef, "get_or_none", AsyncMock(return_value=None)
    )
    with pytest.raises(BusinessError) as error:
        await service.resolve_ref(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=SCOPE_ID,
            ref="a123",
            team_id=TEAM_ID,
            user_id=USER_ID,
        )
    assert error.value.status_code == 404


def test_format_manifest_reports_no_available_attachments():
    manifest = asset_module.AssetService.format_manifest([])

    assert manifest == (
        "<available_assets>\n"
        "No attachments are available in this conversation. "
        "Do not call Asset tools or guess refs.\n"
        "</available_assets>"
    )


@pytest.mark.asyncio
async def test_read_verifies_checksum_and_size():
    content = b"hello"
    storage = SimpleNamespace(read=AsyncMock(return_value=content))
    asset = SimpleNamespace(
        storage_key="key",
        size=len(content),
        checksum=("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"),
    )
    service = asset_module.AssetService()

    assert await service.read(asset, storage=storage) == content
    asset.checksum = "0" * 64
    with pytest.raises(RuntimeError, match="does not match"):
        await service.read(asset, storage=storage)


@pytest.mark.asyncio
async def test_copy_message_attachments_preserves_roles_and_positions(monkeypatch):
    source_message_id = UUID("00000000-0000-0000-0000-000000000005")
    target_message_id = UUID("00000000-0000-0000-0000-000000000006")
    links = [
        SimpleNamespace(asset_id=ASSET_ID, role="attachment", position=2),
    ]
    query = SimpleNamespace(order_by=AsyncMock(return_value=links))
    filter_attachments = MagicMock(return_value=query)
    create_attachment = AsyncMock()
    monkeypatch.setattr(asset_module.MessageAsset, "filter", filter_attachments)
    monkeypatch.setattr(asset_module.MessageAsset, "get_or_create", create_attachment)

    await asset_module.AssetService().copy_message_attachments(
        source_message_id=source_message_id,
        target_message_id=target_message_id,
    )

    filter_attachments.assert_called_once_with(message_id=source_message_id)
    query.order_by.assert_awaited_once_with("position")
    create_attachment.assert_awaited_once_with(
        message_id=target_message_id,
        asset_id=ASSET_ID,
        role="attachment",
        defaults={"position": 2},
    )
