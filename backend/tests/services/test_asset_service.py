from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

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


@pytest.mark.asyncio
async def test_get_authorized_denies_wrong_creator_and_allows_owner(monkeypatch):
    asset = SimpleNamespace(
        id=ASSET_ID,
        team_id=None,
        created_by_id=USER_ID,
        status=AssetStatus.AVAILABLE,
    )
    monkeypatch.setattr(
        asset_module.Asset, "get_or_none", AsyncMock(return_value=asset)
    )
    service = asset_module.AssetService()

    with pytest.raises(BusinessError) as denied:
        await service.get_authorized(ASSET_ID, team_id=None, user_id=uuid4())
    assert denied.value.status_code == 403

    assert (
        await service.get_authorized(ASSET_ID, team_id=None, user_id=USER_ID) is asset
    )


@pytest.mark.asyncio
async def test_get_or_create_ref_returns_existing_and_exhausts_retries(monkeypatch):
    asset = SimpleNamespace(id=ASSET_ID)
    service = asset_module.AssetService()
    existing = SimpleNamespace(ref="00af")
    monkeypatch.setattr(
        asset_module.AssetScopeRef,
        "get_or_none",
        AsyncMock(return_value=existing),
    )

    assert (
        await service.get_or_create_ref(
            scope_type=AssetScopeType.CONVERSATION, scope_id=SCOPE_ID, asset=asset
        )
        is existing
    )

    # IntegrityError on the first attempt is retried, then the loop exhausts.
    get_or_none = AsyncMock(return_value=None)
    create = AsyncMock(side_effect=[IntegrityError()] * 32)
    monkeypatch.setattr(asset_module.AssetScopeRef, "get_or_none", get_or_none)
    monkeypatch.setattr(asset_module.AssetScopeRef, "create", create)
    choices = iter("0123456789abcdef" * 8)
    monkeypatch.setattr(asset_module.secrets, "choice", lambda _alphabet: next(choices))

    with pytest.raises(RuntimeError, match="Unable to allocate"):
        await service.get_or_create_ref(
            scope_type=AssetScopeType.CONVERSATION, scope_id=SCOPE_ID, asset=asset
        )


@pytest.mark.asyncio
async def test_get_or_create_ref_retries_collision_then_creates(monkeypatch):
    asset = SimpleNamespace(id=ASSET_ID)
    service = asset_module.AssetService()
    created = SimpleNamespace(ref="12ab")
    get_or_none = AsyncMock(return_value=None)
    create = AsyncMock(side_effect=[IntegrityError(), created])
    monkeypatch.setattr(asset_module.AssetScopeRef, "get_or_none", get_or_none)
    monkeypatch.setattr(asset_module.AssetScopeRef, "create", create)
    choices = iter("000012ab")
    monkeypatch.setattr(asset_module.secrets, "choice", lambda _alphabet: next(choices))

    result = await service.get_or_create_ref(
        scope_type=AssetScopeType.CONVERSATION, scope_id=SCOPE_ID, asset=asset
    )

    assert result is created


@pytest.mark.asyncio
async def test_resolve_ref_delegates_to_authorization(monkeypatch):
    asset = SimpleNamespace(
        id=ASSET_ID,
        team_id=TEAM_ID,
        created_by_id=USER_ID,
        status=AssetStatus.AVAILABLE,
    )
    binding = SimpleNamespace(asset_id=ASSET_ID)
    monkeypatch.setattr(
        asset_module.AssetScopeRef,
        "get_or_none",
        AsyncMock(return_value=binding),
    )
    monkeypatch.setattr(
        asset_module.Asset, "get_or_none", AsyncMock(return_value=asset)
    )

    result = await asset_module.AssetService().resolve_ref(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=SCOPE_ID,
        ref="a123",
        team_id=TEAM_ID,
        user_id=USER_ID,
    )

    assert result is asset


@pytest.mark.parametrize(
    ("content_type", "filename", "expected_read", "expected_parse"),
    [
        ("text/plain", "notes.txt", True, True),
        ("application/pdf", "plan.pdf", False, True),
        ("application/json", "data.json", True, True),
        ("image/png", "photo.png", False, False),
    ],
)
def test_capabilities_classifies_content_types(
    content_type, filename, expected_read, expected_parse
):
    capabilities = asset_module.AssetService.capabilities(
        SimpleNamespace(content_type=content_type, original_filename=filename)
    )

    assert ("read" in capabilities) is expected_read
    assert ("parse" in capabilities) is expected_parse
    if content_type.startswith("image/"):
        assert "vision" in capabilities
        assert "generate" in capabilities
    else:
        assert "vision" not in capabilities


@pytest.mark.asyncio
async def test_build_conversation_manifest_dedupes_and_backfills(monkeypatch):
    asset = SimpleNamespace(
        id=ASSET_ID,
        team_id=None,
        created_by_id=None,
        status=AssetStatus.AVAILABLE,
        display_filename="file.txt",
        original_filename="file.txt",
        content_type="text/plain",
        size=4,
        source=SimpleNamespace(value="upload"),
    )
    other_id = UUID("00000000-0000-0000-0000-000000000007")
    monkeypatch.setattr(
        asset_module.Asset, "get_or_none", AsyncMock(return_value=asset)
    )
    monkeypatch.setattr(
        asset_module.AssetScopeRef,
        "get_or_none",
        AsyncMock(return_value=SimpleNamespace(ref="a1b2")),
    )
    monkeypatch.setattr(asset_module.AssetScopeRef, "create", AsyncMock())

    def query(rows):
        q = MagicMock()
        q.prefetch_related = MagicMock(return_value=q)
        q.order_by = MagicMock(return_value=q)
        q.limit = AsyncMock(return_value=rows)
        return q

    links = [
        SimpleNamespace(asset_id=ASSET_ID),
        SimpleNamespace(asset_id=ASSET_ID),
    ]
    message_query = query(links)
    monkeypatch.setattr(
        asset_module.MessageAsset, "filter", MagicMock(return_value=message_query)
    )
    bindings = [
        SimpleNamespace(asset_id=other_id, ref="b2c3"),
        SimpleNamespace(asset_id=other_id, ref="b2c3"),
    ]
    binding_query = query(bindings)
    monkeypatch.setattr(
        asset_module.AssetScopeRef, "filter", MagicMock(return_value=binding_query)
    )
    service = asset_module.AssetService()

    manifest = await service.build_conversation_manifest(
        conversation_id=SCOPE_ID, team_id=None, user_id=USER_ID
    )

    assert len(manifest) == 2
    assert manifest[0]["ref"] == "a1b2"
    assert manifest[1]["ref"] == "b2c3"
    for entry in manifest:
        assert entry["name"] == "file.txt"
        assert entry["origin"] == "upload"
        assert "read" in entry["capabilities"]
    binding_query.limit.assert_awaited_once_with(11)

    message_query.limit = AsyncMock(return_value=links)
    full = await service.build_conversation_manifest(
        conversation_id=SCOPE_ID, team_id=None, user_id=USER_ID, limit=1
    )

    assert len(full) == 1
    binding_query.limit.assert_awaited_once_with(11)


def test_format_manifest_renders_item_rows():
    manifest = [
        {
            "ref": "a1b2",
            "name": "report.xlsx",
            "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 2048,
            "origin": "upload",
            "capabilities": ["inspect", "read", "parse", "sandbox"],
        }
    ]

    rendered = asset_module.AssetService.format_manifest(manifest)

    assert "a1b2 | report.xlsx | " in rendered
    assert "2048B | upload | inspect,read,parse,sandbox" in rendered
