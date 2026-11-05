from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints import im as im_endpoints
from app.core import init_data
from app.models.asset import AssetScopeType
from app.models.im import ImConversationType, ImMessageType
from app.models.user import User
from app.schemas.im import ImAttachmentOut, SendMessageRequest
from app.schemas.response import BusinessError
from app.services import asset_access, im_service


@pytest.fixture
def fake_user() -> User:
    return User(
        id=uuid4(),
        username="alice",
        email="alice@example.com",
        is_active=True,
    )


def _attachment_out(asset_id) -> ImAttachmentOut:
    return ImAttachmentOut(
        asset_id=str(asset_id),
        filename="a.png",
        size=12,
        content_type="image/png",
        url="/api/v1/upload/files/im/2026/11/a.png",
    )


# --- 契约校验：文本 / 图片 / 文件三态互斥 ---


def test_text_message_requires_content_and_no_asset() -> None:
    req = SendMessageRequest(content="hello")
    assert req.content == "hello"
    with pytest.raises(ValidationError):
        SendMessageRequest(content="")
    with pytest.raises(ValidationError):
        SendMessageRequest(content="hello", asset_id=uuid4())


def test_attachment_message_requires_asset_and_empty_content() -> None:
    asset_id = uuid4()
    file_msg = SendMessageRequest(msg_type=ImMessageType.FILE, asset_id=asset_id)
    assert file_msg.content == "" and file_msg.asset_id == asset_id

    with pytest.raises(ValidationError):
        SendMessageRequest(msg_type=ImMessageType.FILE)
    with pytest.raises(ValidationError):
        SendMessageRequest(
            msg_type=ImMessageType.FILE, content="caption", asset_id=asset_id
        )
    with pytest.raises(ValidationError):
        SendMessageRequest(content="hello", asset_id=asset_id)


# --- 附件元信息批量组装（避免 N+1） ---


@pytest.mark.asyncio
async def test_build_attachment_map_no_assets() -> None:
    assert await im_endpoints._build_attachment_map([]) == {}
    assert await im_endpoints._build_attachment_map([MagicMock(asset_id=None)]) == {}


@pytest.mark.asyncio
async def test_build_attachment_map_fetches_once() -> None:
    asset_id = uuid4()
    asset = MagicMock(
        id=asset_id,
        display_filename="a.png",
        original_filename="a.png",
        size=12,
        content_type="image/png",
        storage_key="im/2026/11/a.png",
    )
    qs = MagicMock()
    qs.all = AsyncMock(return_value=[asset])
    with patch("app.api.v1.endpoints.im.Asset.filter", return_value=qs) as flt:
        result = await im_endpoints._build_attachment_map(
            [MagicMock(asset_id=asset_id), MagicMock(asset_id=asset_id)]
        )
    assert flt.call_count == 1
    assert result[asset_id].url == "/api/v1/upload/files/im/2026/11/a.png"
    assert result[asset_id].filename == "a.png"


@pytest.mark.asyncio
async def test_send_message_endpoint_passes_asset_id(fake_user: User) -> None:
    conv_id, asset_id = uuid4(), uuid4()
    fake_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=fake_user.id,
        client_msg_id="client-uuid",
        seq=3,
        msg_type=MagicMock(value="file"),
        content="",
        payload=None,
        asset_id=asset_id,
        status=MagicMock(value="normal"),
        created_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
    )
    payload = SendMessageRequest(
        msg_type=ImMessageType.FILE, asset_id=asset_id, client_msg_id="client-uuid"
    )
    with (
        patch(
            "app.services.im_service.send_direct_message",
            new_callable=AsyncMock,
            return_value=fake_msg,
        ) as send,
        patch(
            "app.api.v1.endpoints.im._build_attachment_map",
            new_callable=AsyncMock,
            return_value={asset_id: _attachment_out(asset_id)},
        ),
    ):
        resp = await im_endpoints.send_message(conv_id, payload, fake_user)
    assert send.call_args.kwargs["asset_id"] == asset_id
    assert resp["data"].attachment is not None
    assert resp["data"].attachment.filename == "a.png"


@pytest.mark.asyncio
async def test_get_messages_endpoint_includes_attachment(fake_user: User) -> None:
    conv_id, asset_id = uuid4(), uuid4()
    msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=fake_user.id,
        client_msg_id=None,
        seq=1,
        msg_type=MagicMock(value="file"),
        content="",
        payload=None,
        asset_id=asset_id,
        status=MagicMock(value="normal"),
        created_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
    )
    with (
        patch("app.services.im_service.get_messages", return_value=([msg], False)),
        patch(
            "app.api.v1.endpoints.im._build_attachment_map",
            new_callable=AsyncMock,
            return_value={asset_id: _attachment_out(asset_id)},
        ),
    ):
        resp = await im_endpoints.get_messages(conv_id, current_user=fake_user)
    assert resp["data"].messages[0].attachment is not None


# --- 上传端点：团队绑定与作用域 ---


@pytest.mark.asyncio
async def test_upload_im_attachment_binds_team_and_scope(fake_user: User) -> None:
    conv_id = uuid4()
    conv = MagicMock(
        id=conv_id,
        type=ImConversationType.DIRECT,
        user1_id=fake_user.id,
        user2_id=uuid4(),
        team_id=uuid4(),
    )
    qs = MagicMock()
    qs.first = AsyncMock(return_value=conv)
    file = MagicMock()
    file.read = AsyncMock(return_value=b"hello")
    file.filename = "a.png"
    file.content_type = "image/png"
    asset = MagicMock(
        id=uuid4(),
        display_filename="a.png",
        original_filename="a.png",
        size=5,
        content_type="image/png",
    )
    upload_info = {
        "storage_key": "im/2026/11/a.png",
        "url": "/api/v1/upload/files/im/2026/11/a.png",
        "filename": "a.png",
    }
    with (
        patch("app.api.v1.endpoints.im.ImConversation.filter", return_value=qs),
        patch(
            "app.services.im_service.check_users_in_same_team", new_callable=AsyncMock
        ) as check_team,
        patch("app.api.v1.endpoints.im._validate_upload_size") as validate_size,
        patch(
            "app.api.v1.endpoints.im.save_generated_upload",
            new_callable=AsyncMock,
            return_value=upload_info,
        ),
        patch(
            "app.api.v1.endpoints.im.asset_service.register_bytes",
            new_callable=AsyncMock,
            return_value=asset,
        ) as register,
        patch(
            "app.services.asset.asset_service.get_or_create_ref", new_callable=AsyncMock
        ) as create_ref,
    ):
        resp = await im_endpoints.upload_im_attachment(conv_id, file, fake_user)

    assert validate_size.call_count == 1
    assert check_team.call_args.args == (conv.team_id, conv.user1_id, conv.user2_id)
    assert register.call_args.kwargs["team_id"] == conv.team_id
    assert create_ref.call_args.kwargs["scope_type"] == AssetScopeType.IM_CONVERSATION
    assert create_ref.call_args.kwargs["scope_id"] == conv_id
    assert resp["data"].asset_id == str(asset.id)
    assert resp["data"].url == upload_info["url"]


@pytest.mark.asyncio
async def test_upload_im_attachment_rejects_non_participant(fake_user: User) -> None:
    conv_id = uuid4()
    conv = MagicMock(
        id=conv_id,
        type=ImConversationType.DIRECT,
        user1_id=uuid4(),
        user2_id=uuid4(),
        team_id=uuid4(),
    )
    qs = MagicMock()
    qs.first = AsyncMock(return_value=conv)
    with patch("app.api.v1.endpoints.im.ImConversation.filter", return_value=qs):
        with pytest.raises(BusinessError) as exc:
            await im_endpoints.upload_im_attachment(conv_id, MagicMock(), fake_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_im_attachment_rejects_system_conversation(
    fake_user: User,
) -> None:
    conv = MagicMock(
        id=uuid4(),
        type=ImConversationType.SYSTEM,
        user1_id=fake_user.id,
        user2_id=None,
        team_id=uuid4(),
    )
    qs = MagicMock()
    qs.first = AsyncMock(return_value=conv)
    with patch("app.api.v1.endpoints.im.ImConversation.filter", return_value=qs):
        with pytest.raises(BusinessError) as exc:
            await im_endpoints.upload_im_attachment(conv.id, MagicMock(), fake_user)
    assert exc.value.status_code == 400


# --- 幂等与资产校验 ---


def test_ensure_same_asset_rejects_conflicting_retry() -> None:
    im_service._ensure_same_asset(MagicMock(asset_id=None), None)
    with pytest.raises(BusinessError):
        im_service._ensure_same_asset(MagicMock(asset_id=uuid4()), uuid4())


@pytest.mark.asyncio
async def test_resolve_im_attachment_validates_team_type_and_scope() -> None:
    conv = MagicMock(id=uuid4(), team_id=uuid4())
    asset_id = uuid4()
    asset = MagicMock(content_type="image/png")
    asset_qs = MagicMock()
    asset_qs.first = AsyncMock(return_value=asset)
    scope_qs = MagicMock()
    scope_qs.exists = AsyncMock(return_value=True)

    with (
        patch("app.models.asset.Asset.filter", return_value=asset_qs),
        patch("app.models.asset.AssetScopeRef.filter", return_value=scope_qs),
    ):
        resolved = await im_service._resolve_im_attachment(
            conv, asset_id, ImMessageType.FILE
        )
    assert resolved is asset

    # 资产不存在 / 跨团队
    missing_qs = MagicMock()
    missing_qs.first = AsyncMock(return_value=None)
    with patch("app.models.asset.Asset.filter", return_value=missing_qs):
        with pytest.raises(BusinessError) as exc:
            await im_service._resolve_im_attachment(conv, asset_id, ImMessageType.FILE)
    assert exc.value.status_code == 404

    # 未绑定会话作用域
    unbound_scope = MagicMock()
    unbound_scope.exists = AsyncMock(return_value=False)
    with (
        patch("app.models.asset.Asset.filter", return_value=asset_qs),
        patch("app.models.asset.AssetScopeRef.filter", return_value=unbound_scope),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service._resolve_im_attachment(conv, asset_id, ImMessageType.FILE)
    assert exc.value.status_code == 404


# --- 资产访问授权新增分支 ---


@pytest.mark.asyncio
async def test_authorize_asset_scope_im_conversation(fake_user: User) -> None:
    conv = MagicMock(
        id=uuid4(), user1_id=fake_user.id, user2_id=uuid4(), team_id=uuid4()
    )
    qs = MagicMock()
    qs.first = AsyncMock(return_value=conv)
    with patch("app.models.im.ImConversation.filter", return_value=qs):
        team_id = await asset_access.authorize_asset_scope(
            scope_type=AssetScopeType.IM_CONVERSATION,
            scope_id=conv.id,
            user=fake_user,
        )
    assert team_id == conv.team_id

    admin = User(
        id=uuid4(),
        username="root",
        email="root@example.com",
        is_active=True,
        is_superuser=True,
    )
    with patch("app.models.im.ImConversation.filter", return_value=qs):
        assert (
            await asset_access.authorize_asset_scope(
                scope_type=AssetScopeType.IM_CONVERSATION,
                scope_id=conv.id,
                user=admin,
            )
            == conv.team_id
        )

    outsider = User(id=uuid4(), username="bob", email="bob@example.com", is_active=True)
    with patch("app.models.im.ImConversation.filter", return_value=qs):
        with pytest.raises(BusinessError) as exc:
            await asset_access.authorize_asset_scope(
                scope_type=AssetScopeType.IM_CONVERSATION,
                scope_id=conv.id,
                user=outsider,
            )
    assert exc.value.status_code == 403


# --- 启动迁移幂等 ---


@pytest.mark.asyncio
async def test_init_im_rich_media_columns_is_additive() -> None:
    with (
        patch("app.core.init_data.Tortoise.get_connection", return_value=MagicMock()),
        patch(
            "app.core.init_data.execute_startup_migration_query",
            new_callable=AsyncMock,
        ) as run,
    ):
        await init_data.init_im_rich_media_columns()
    statements = [call.args[1] for call in run.call_args_list]
    assert any("ADD COLUMN IF NOT EXISTS asset_id" in sql for sql in statements)
    assert any(
        "UPDATE im_messages SET msg_type = 'file' WHERE msg_type = 'image'" in sql
        for sql in statements
    )


# --- 发送路径：附件消息落在单行且 SSE 载荷带附件元数据 ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "summary"),
    [("image/png", "[图片]"), ("application/pdf", "[文件]")],
)
async def test_send_direct_message_with_attachment(
    content_type: str, summary: str
) -> None:
    sender_id, receiver_id, conv_id, asset_id = uuid4(), uuid4(), uuid4(), uuid4()
    conv = MagicMock(
        id=conv_id,
        type=ImConversationType.DIRECT,
        user1_id=sender_id,
        user2_id=receiver_id,
        save=AsyncMock(),
    )
    asset = MagicMock(
        id=asset_id,
        display_filename="a.bin",
        size=7,
        content_type=content_type,
        storage_key="im/2026/11/a.bin",
    )
    msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=sender_id,
        seq=5,
        msg_type=ImMessageType.FILE,
        content="",
        payload=None,
        asset_id=asset_id,
        created_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
    )
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.services.im_redis.get_cached_message_result", return_value=None),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch(
            "app.services.im_service._resolve_im_attachment",
            new_callable=AsyncMock,
            return_value=asset,
        ) as resolve,
        patch("app.services.im_redis.generate_next_seq", return_value=5),
        patch("app.models.im.ImMessage.create", return_value=msg) as create,
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as unread,
        patch(
            "app.services.im_redis.publish_im_event", new_callable=AsyncMock
        ) as publish,
    ):
        result = await im_service.send_direct_message(
            conv_id, sender_id, "", msg_type=ImMessageType.FILE, asset_id=asset_id
        )

    assert result is msg
    assert resolve.await_args.args == (conv, asset_id, ImMessageType.FILE)
    assert create.await_args.kwargs["asset_id"] == asset_id
    assert conv.last_message_content == summary
    unread.assert_awaited_once_with(receiver_id, conv_id, 1)
    event = publish.await_args.args[2]
    assert event["asset_id"] == str(asset_id)
    assert event["attachment"]["filename"] == "a.bin"
    assert event["attachment"]["url"] == "/api/v1/upload/files/im/2026/11/a.bin"


# --- 上传失败时回收半成品（避免无作用域引用的孤儿资产） ---


def _upload_fixture(fake_user: User):
    conv = MagicMock(
        id=uuid4(),
        type=ImConversationType.DIRECT,
        user1_id=fake_user.id,
        user2_id=uuid4(),
        team_id=uuid4(),
    )
    qs = MagicMock()
    qs.first = AsyncMock(return_value=conv)
    file = MagicMock()
    file.read = AsyncMock(return_value=b"hello")
    file.filename = "a.png"
    file.content_type = "image/png"
    asset = MagicMock(
        id=uuid4(),
        display_filename="a.png",
        original_filename="a.png",
        size=5,
        content_type="image/png",
    )
    upload_info = {
        "storage_key": "im/2026/11/a.png",
        "url": "/api/v1/upload/files/im/2026/11/a.png",
        "filename": "a.png",
    }
    return conv, qs, file, asset, upload_info


def _upload_patches(
    qs, upload_info, register, create_ref, *, asset_filter=None, storage=None
):
    stack = [
        patch("app.api.v1.endpoints.im.ImConversation.filter", return_value=qs),
        patch(
            "app.services.im_service.check_users_in_same_team", new_callable=AsyncMock
        ),
        patch("app.api.v1.endpoints.im._validate_upload_size"),
        patch(
            "app.api.v1.endpoints.im.save_generated_upload",
            new_callable=AsyncMock,
            return_value=upload_info,
        ),
        patch(
            "app.api.v1.endpoints.im.asset_service.register_bytes",
            new_callable=AsyncMock,
            side_effect=register,
        ),
        patch(
            "app.services.asset.asset_service.get_or_create_ref",
            new_callable=AsyncMock,
            side_effect=create_ref,
        ),
        patch(
            "app.api.v1.endpoints.im._upload_storage",
            new_callable=AsyncMock,
            return_value=storage,
        ),
    ]
    if asset_filter is not None:
        stack.append(
            patch("app.api.v1.endpoints.im.Asset.filter", return_value=asset_filter)
        )
    return stack


@pytest.mark.asyncio
async def test_upload_scoping_failure_deletes_asset_and_bytes(fake_user: User) -> None:
    conv, qs, file, asset, upload_info = _upload_fixture(fake_user)
    asset_delete = MagicMock()
    asset_delete.delete = AsyncMock()
    storage = MagicMock()
    storage.delete = AsyncMock()
    stack = _upload_patches(
        qs,
        upload_info,
        register=[asset],
        create_ref=RuntimeError("scope write failed"),
        asset_filter=asset_delete,
        storage=storage,
    )
    with (
        stack[0],
        stack[1],
        stack[2],
        stack[3],
        stack[4],
        stack[5],
        stack[6],
        stack[7],
    ):
        with pytest.raises(RuntimeError, match="scope write failed"):
            await im_endpoints.upload_im_attachment(conv.id, file, fake_user)

    asset_delete.delete.assert_awaited_once()
    storage.delete.assert_awaited_once_with(upload_info["storage_key"])


@pytest.mark.asyncio
async def test_upload_registration_failure_deletes_bytes_only(fake_user: User) -> None:
    conv, qs, file, _asset, upload_info = _upload_fixture(fake_user)
    asset_delete = MagicMock()
    asset_delete.delete = AsyncMock()
    storage = MagicMock()
    storage.delete = AsyncMock()
    stack = _upload_patches(
        qs,
        upload_info,
        register=RuntimeError("insert failed"),
        create_ref=None,
        asset_filter=asset_delete,
        storage=storage,
    )
    with (
        stack[0],
        stack[1],
        stack[2],
        stack[3],
        stack[4],
        stack[5],
        stack[6],
        stack[7],
    ):
        with pytest.raises(RuntimeError, match="insert failed"):
            await im_endpoints.upload_im_attachment(conv.id, file, fake_user)

    asset_delete.delete.assert_not_awaited()
    storage.delete.assert_awaited_once_with(upload_info["storage_key"])


@pytest.mark.asyncio
async def test_upload_cleanup_failures_do_not_mask_the_original_error(
    fake_user: User,
) -> None:
    conv, qs, file, asset, upload_info = _upload_fixture(fake_user)
    asset_delete = MagicMock()
    asset_delete.delete = AsyncMock(side_effect=OSError("row delete failed"))
    storage = MagicMock()
    storage.delete = AsyncMock(side_effect=OSError("storage offline"))
    stack = _upload_patches(
        qs,
        upload_info,
        register=[asset],
        create_ref=RuntimeError("scope write failed"),
        asset_filter=asset_delete,
        storage=storage,
    )
    with (
        stack[0],
        stack[1],
        stack[2],
        stack[3],
        stack[4],
        stack[5],
        stack[6],
        stack[7],
    ):
        with pytest.raises(RuntimeError, match="scope write failed"):
            await im_endpoints.upload_im_attachment(conv.id, file, fake_user)

    asset_delete.delete.assert_awaited_once()
    storage.delete.assert_awaited_once()
