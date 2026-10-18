"""Collection boundaries against an isolated real ORM; no production credentials."""

import base64
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from tortoise.context import TortoiseContext
from tortoise.exceptions import IntegrityError

from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.integrations.wechat import WeChatAPIError, WeChatClient, official_url
from app.models.knowledge_base import KnowledgeBase
from app.models.model import Model, ModelType, TeamModel
from app.models.user import User, Team
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeCollection,
    WeChatKnowledgeLogin,
    WeChatKnowledgeReceipt,
)
from app.services.wechat_connection import (
    binding_summary,
    check_binding_target,
    poll_login,
    start_login,
    utcnow,
)
from app.services.wechat_ingestion import split_items
from app.services.wechat_receiver import accept_updates
from app.schemas.response import BusinessError


def connected_binding(user, wechat_user_id="wechat-user", bot_id="bot"):
    return WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id=wechat_user_id,
        bot_id=bot_id,
        token=encrypt_secret("not-real"),
        base_url="https://ilinkai.weixin.qq.com",
    )


async def vision_model_for(team):
    model = await Model.create(
        id=uuid4(),
        name="Vision chat",
        provider="openai",
        model_id="gpt-4o-mini",
        model_type=ModelType.CHAT.value,
        capabilities={"vision": True},
    )
    await TeamModel.create(id=uuid4(), team=team, model=model)
    return model


async def confirmation(
    self, qrcode, verify_code=None, identity="wechat-user", bot="bot"
):
    return {
        "status": "confirmed",
        "bot_token": "new-secret",
        "ilink_user_id": identity,
        "ilink_bot_id": bot,
        "baseurl": "https://ilinkai.weixin.qq.com",
    }


@pytest_asyncio.fixture
async def collection_db():
    # Save/restore Tortoise state so this fixture cannot affect unrelated tests.
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        user = await User.create(
            id=uuid4(),
            username="collector",
            email="collector@example.test",
            hashed_password="unused",
            is_superuser=True,
        )
        other = await User.create(
            id=uuid4(),
            username="other",
            email="other@example.test",
            hashed_password="unused",
        )
        team = await Team.create(id=uuid4(), name="Collection team")
        kb = await KnowledgeBase.create(
            id=uuid4(), name="Target", team=team, created_by=user
        )
        kb2 = await KnowledgeBase.create(
            id=uuid4(), name="Other target", team=team, created_by=user
        )
        binding = await connected_binding(user)
        collection = await WeChatKnowledgeCollection.create(
            binding=binding, knowledge_base=kb
        )
        binding.purpose = "knowledge_collection"
        await binding.save(update_fields=["purpose"])
        yield user, other, kb, kb2, binding, collection


def message(identifier="18446744073709551615", sender="wechat-user"):
    return {
        "message_id": identifier,
        "from_user_id": sender,
        "message_type": 1,
        "message_state": 2,
        "item_list": [{"type": 1, "text_item": {"text": "Original knowledge note"}}],
    }


@pytest.mark.asyncio
async def test_receipts_are_unique_snapshots_and_disconnect_discards_late_poll(
    collection_db,
):
    _, _, kb, kb2, binding, _ = collection_db
    ids = await accept_updates(
        binding,
        {
            "msgs": [message(), message(), message("2", "stranger")],
            "get_updates_buf": "next",
        },
    )
    assert await WeChatKnowledgeReceipt.all().count() == 1
    receipt = await WeChatKnowledgeReceipt.get(id=ids[0])
    assert receipt.message_id == "18446744073709551615"
    assert receipt.knowledge_base_id == kb.id
    await WeChatKnowledgeCollection.filter(binding_id=binding.id).update(
        knowledge_base_id=kb2.id
    )
    await WeChatKnowledgeBinding.filter(id=binding.id).update(generation=uuid4())
    assert (
        await accept_updates(
            binding, {"msgs": [message("new")], "get_updates_buf": "late"}
        )
        == []
    )
    await receipt.refresh_from_db()
    assert receipt.knowledge_base_id == kb.id
    await binding.refresh_from_db()
    await WeChatKnowledgeBinding.filter(id=binding.id).update(status="disconnected")
    assert await accept_updates(binding, {"msgs": [message("after-disconnect")]}) == []
    assert await WeChatKnowledgeReceipt.all().count() == 1


@pytest.mark.asyncio
async def test_many_collectors_same_kb_but_identity_cannot_bind_twice(collection_db):
    user, other, kb, _, _, _ = collection_db
    rival = await connected_binding(other, "other-wechat", "other-bot")
    await WeChatKnowledgeCollection.create(binding=rival, knowledge_base=kb)
    assert await WeChatKnowledgeCollection.filter(knowledge_base_id=kb.id).count() == 2
    with pytest.raises(IntegrityError):
        await connected_binding(user)


@pytest.mark.asyncio
async def test_private_target_and_other_users_login_fail_closed(collection_db):
    _, other, kb, _, _, _ = collection_db
    # kb is PRIVATE and owned by another account: no write grant.
    with pytest.raises(BusinessError) as denied:
        await check_binding_target(kb.id, other)
    assert denied.value.status_code == 403
    user = await User.get(username="collector")
    login = await WeChatKnowledgeLogin.create(
        user=user,
        qrcode=encrypt_secret("not-real"),
        qrcode_content="not-real",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    with pytest.raises(BusinessError) as missing:
        await poll_login(login.id, other)
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_login_starts_without_any_knowledge_base(collection_db, monkeypatch):
    import app.services.wechat_connection as service

    user, _, _, _, _, _ = collection_db

    async def qrcode(self):
        return {"qrcode": "qr-secret", "qrcode_img_content": "qr-code"}

    monkeypatch.setattr(service.WeChatClient, "get_qrcode", qrcode)
    login = await start_login(user)
    assert login.status == "wait" and login.qrcode_content == "qr-code"
    # A pending login carries no collection target or recognition models; the
    # model no longer declares those columns at all.
    assert "knowledge_base_id" not in login._meta.fields_map
    assert "vision_model_id" not in login._meta.fields_map
    assert "stt_model_id" not in login._meta.fields_map
    assert login.binding_id is None
    assert await WeChatKnowledgeLogin.all().count() == 1
    # Authorization capacity stays bounded per account.
    for _ in range(2):
        await start_login(user)
    with pytest.raises(BusinessError) as limited:
        await start_login(user)
    assert limited.value.status_code == 429


@pytest.mark.asyncio
async def test_brand_new_identity_connects_without_collection(
    collection_db, monkeypatch
):
    import app.services.wechat_connection as service

    user, _, _, _, _, _ = collection_db

    async def qrcode(self):
        return {"qrcode": "qr-secret", "qrcode_img_content": "qr-code"}

    monkeypatch.setattr(service.WeChatClient, "get_qrcode", qrcode)
    login = await start_login(user)
    monkeypatch.setattr(
        service.WeChatClient,
        "get_qrcode_status",
        lambda self, qrcode, verify_code=None: confirmation(
            self, qrcode, verify_code, identity="fresh-wechat", bot="fresh-bot"
        ),
    )
    confirmed = await poll_login(login.id, user)
    assert confirmed["status"] == "confirmed"
    binding = await WeChatKnowledgeBinding.get(wechat_user_id="fresh-wechat")
    assert binding.status == "connected" and binding.user_id == user.id
    # Authorization alone never enables collection.
    assert not await WeChatKnowledgeCollection.filter(binding_id=binding.id).exists()
    assert confirmed["binding"]["collection"] is None
    assert (
        await accept_updates(
            binding, {"msgs": [message(identifier="ignored", sender="fresh-wechat")]}
        )
        == []
    )


@pytest.mark.asyncio
async def test_configless_connection_ignores_messages_but_advances_cursor(
    collection_db,
):
    user, _, _, _, _, _ = collection_db
    binding = await connected_binding(user, "silent-wechat", "silent-bot")
    cursor = binding.cursor
    assert (
        await accept_updates(
            binding,
            {
                "msgs": [message(identifier="1", sender="silent-wechat")],
                "get_updates_buf": "advance",
            },
        )
        == []
    )
    assert await WeChatKnowledgeReceipt.all().count() == 0
    await binding.refresh_from_db()
    assert binding.cursor != cursor
    assert decrypt_secret(binding.cursor) == "advance"
    # Still connected and eligible for later configuration.
    assert binding.status == "connected"
    assert binding.last_received_at is None


@pytest.mark.asyncio
async def test_endpoint_configures_replaces_and_disables_optional_collection(
    collection_db,
):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose

    user, _, kb, kb2, binding, _ = collection_db
    vision = await vision_model_for(await Team.get(id=kb.team_id))
    generation = binding.generation
    response = await update_purpose(
        binding.id,
        PurposeInput(
            purpose="knowledge_collection",
            knowledge_base_id=kb2.id,
            vision_model_id=vision.id,
            stt_model_id=None,
        ),
        user,
    )
    summary = response["data"]
    assert summary["purpose"] == "knowledge_collection"
    assert summary["agent_config"] is None
    assert summary["collection"] == {
        "knowledge_base_id": str(kb2.id),
        "knowledge_base_name": "Other target",
        "vision_model_id": str(vision.id),
        "stt_model_id": None,
    }
    collection = await WeChatKnowledgeCollection.get(binding_id=binding.id)
    assert collection.knowledge_base_id == kb2.id
    await binding.refresh_from_db()
    assert binding.generation != generation
    assert binding.status == "connected" and binding.token != ""

    # Replacing keeps exactly one configuration row for the connection.
    await update_purpose(
        binding.id,
        PurposeInput(purpose="knowledge_collection", knowledge_base_id=kb.id),
        user,
    )
    assert await WeChatKnowledgeCollection.filter(binding_id=binding.id).count() == 1
    assert (
        await WeChatKnowledgeCollection.get(binding_id=binding.id)
    ).knowledge_base_id == kb.id

    disabled = await update_purpose(binding.id, PurposeInput(purpose="none"), user)
    assert disabled["data"]["purpose"] == "none"
    assert disabled["data"]["collection"]["knowledge_base_id"] == str(kb.id)
    assert await WeChatKnowledgeCollection.filter(binding_id=binding.id).exists()
    await binding.refresh_from_db()
    # Disabling collection keeps the connection itself authorized and usable.
    assert binding.status == "connected"
    assert binding.token and decrypt_secret(binding.token) == "not-real"
    # Messages are ignored without a receipt, but the cursor still advances.
    assert (
        await accept_updates(
            binding,
            {
                "msgs": [message(identifier="after-disable")],
                "get_updates_buf": "advance",
            },
        )
        == []
    )
    await binding.refresh_from_db()
    assert decrypt_secret(binding.cursor) == "advance"
    assert await WeChatKnowledgeReceipt.all().count() == 0


@pytest.mark.asyncio
async def test_receipt_snapshot_survives_collection_change_and_removal(collection_db):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose

    user, _, kb, kb2, binding, _ = collection_db
    ids = await accept_updates(
        binding, {"msgs": [message()], "get_updates_buf": "next"}
    )
    receipt = await WeChatKnowledgeReceipt.get(id=ids[0])
    # A purpose switch waits until previously accepted work finishes.
    with pytest.raises(BusinessError) as busy:
        await update_purpose(
            binding.id,
            PurposeInput(purpose="knowledge_collection", knowledge_base_id=kb2.id),
            user,
        )
    assert busy.value.status_code == 409
    receipt.status = "completed"
    await receipt.save(update_fields=["status"])
    await update_purpose(
        binding.id,
        PurposeInput(purpose="knowledge_collection", knowledge_base_id=kb2.id),
        user,
    )
    await receipt.refresh_from_db()
    assert receipt.knowledge_base_id == kb.id
    await update_purpose(binding.id, PurposeInput(purpose="none"), user)
    await receipt.refresh_from_db()
    assert receipt.knowledge_base_id == kb.id
    assert receipt.vision_model_id is None and receipt.stt_model_id is None
    assert await WeChatKnowledgeReceipt.all().count() == 1


@pytest.mark.asyncio
async def test_unauthorized_collection_updates_fail_closed(collection_db):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose
    from app.models.user import TeamMember

    user, other, kb, _, binding, _ = collection_db
    # Another account cannot read or reconfigure someone else's connection.
    with pytest.raises(BusinessError) as foreign:
        await update_purpose(
            binding.id,
            PurposeInput(purpose="knowledge_collection", knowledge_base_id=kb.id),
            other,
        )
    assert foreign.value.status_code == 404
    with pytest.raises(BusinessError) as foreign_disable:
        await update_purpose(binding.id, PurposeInput(purpose="none"), other)
    assert foreign_disable.value.status_code == 404
    # A team member still cannot point a connection at another owner's private
    # knowledge base, even though the connection itself is their own.
    rival = await connected_binding(other, "rival-wechat", "rival-bot")
    await TeamMember.create(
        team=await Team.get(id=kb.team_id), user=other, role="member"
    )
    with pytest.raises(BusinessError) as unwritable:
        await update_purpose(
            rival.id,
            PurposeInput(purpose="knowledge_collection", knowledge_base_id=kb.id),
            other,
        )
    assert unwritable.value.status_code == 403
    # Ungranted recognition models are rejected before any write.
    with pytest.raises(BusinessError) as unauthorized_model:
        await update_purpose(
            binding.id,
            PurposeInput(
                purpose="knowledge_collection",
                knowledge_base_id=kb.id,
                vision_model_id=uuid4(),
            ),
            user,
        )
    assert unauthorized_model.value.msg_key == "wechat_model_unavailable"
    collection = await WeChatKnowledgeCollection.get(binding_id=binding.id)
    assert collection.knowledge_base_id == kb.id
    assert collection.vision_model_id is None
    assert not await WeChatKnowledgeCollection.filter(binding_id=rival.id).exists()


def test_text_links_and_all_attachments_keep_user_intent():
    text = split_items(
        {"item_list": [{"type": 1, "text_item": {"text": "会议纪要：预算 42 元"}}]}
    )
    assert text == [{"kind": "text", "text": "会议纪要：预算 42 元"}]
    links = split_items(
        {
            "item_list": [
                {
                    "type": 1,
                    "text_item": {
                        "text": "参考 https://example.com/a https://example.com/b"
                    },
                }
            ]
        }
    )
    assert [item["url"] for item in links] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    parts = [
        {"type": 1, "text_item": {"text": "两份合同"}},
        {"type": 4, "file_item": {"file_name": "a.pdf"}},
        {"type": 4, "file_item": {"file_name": "b.pdf"}},
    ]
    items = split_items({"item_list": parts})
    assert [item["item"]["file_item"]["file_name"] for item in items] == [
        "a.pdf",
        "b.pdf",
    ]
    assert all(item["caption"] == "两份合同" for item in items)


@pytest.mark.parametrize(
    "url",
    [
        "http://ilinkai.weixin.qq.com",
        "https://evil.example",
        "https://weixin.qq.com.evil.example",
        "https://user:secret@ilinkai.weixin.qq.com",
        "https://ilinkai.weixin.qq.com:8443",
    ],
)
def test_credentials_never_target_nonofficial_endpoint(url):
    with pytest.raises(WeChatAPIError):
        official_url(url)


@pytest.mark.asyncio
async def test_real_media_decryption_and_size_boundary(monkeypatch):
    import app.integrations.wechat as transport

    monkeypatch.setattr(transport, "validate_external_http_url", lambda value: value)
    key = b"0123456789abcdef"
    plaintext = b"The original file bytes"
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    async def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, content=encrypted)

    async with WeChatClient() as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        item = {
            "type": 4,
            "file_item": {
                "file_name": "../contract.txt",
                "media": {
                    "full_url": "https://novac2c.cdn.weixin.qq.com/c2c/download",
                    "aes_key": base64.b64encode(key).decode(),
                },
            },
        }
        data, name, mime = await client.download_media(item, len(plaintext))
        assert data == plaintext and name == "contract.txt" and mime == "text/plain"
        with pytest.raises(WeChatAPIError) as large:
            await client.download_media(item, 1)
        assert large.value.code == "file_too_large"


@pytest.mark.asyncio
async def test_voice_transcript_does_not_require_a_missing_audio_payload(collection_db):
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services.wechat_ingestion import text_for_input

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="voice",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    text, name, metadata = await text_for_input(
        {
            "kind": "media",
            "item": {"type": 3, "voice_item": {"text": "会议决定下周上线。"}},
            "caption": "",
        },
        receipt,
        kb,
        None,
        item,
    )
    assert text == "会议决定下周上线。"
    assert metadata["wechat_extraction"] == "wechat_transcript"


@pytest.mark.asyncio
async def test_disconnected_actor_cannot_process_snapshot(collection_db):
    from app.services.wechat_ingestion import actor_target

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="revoked",
        payload=encrypt_secret("{}"),
    )
    await WeChatKnowledgeBinding.filter(id=binding.id).update(status="disconnected")
    with pytest.raises(BusinessError) as stopped:
        await actor_target(receipt)
    assert stopped.value.msg_key == "wechat_binding_disconnected"


@pytest.mark.asyncio
async def test_media_redirect_cannot_escape_official_cdn(monkeypatch):
    import app.integrations.wechat as transport

    monkeypatch.setattr(transport, "validate_external_http_url", lambda value: value)
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    async with WeChatClient() as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(WeChatAPIError) as rejected:
            await client.download_media(
                {
                    "type": 4,
                    "file_item": {
                        "file_name": "a.txt",
                        "media": {
                            "full_url": "https://novac2c.cdn.weixin.qq.com/c2c/download",
                            "aes_key": base64.b64encode(b"0123456789abcdef").decode(),
                        },
                    },
                },
                100,
            )
        assert rejected.value.code == "invalid_host"
    assert calls == ["https://novac2c.cdn.weixin.qq.com/c2c/download"]


@pytest.mark.asyncio
async def test_reauthorization_does_not_revive_pre_disconnect_receipts(collection_db):
    from app.services.wechat_ingestion import actor_target

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="old",
        payload=encrypt_secret("{}"),
    )
    await WeChatKnowledgeBinding.filter(id=binding.id).update(
        status="connected", disconnected_at=utcnow()
    )
    with pytest.raises(BusinessError) as stopped:
        await actor_target(receipt)
    assert stopped.value.msg_key == "wechat_binding_disconnected"


@pytest.mark.asyncio
async def test_duplicate_content_is_scoped_to_target_and_keeps_both_contributors(
    collection_db, monkeypatch
):
    from app.models.knowledge_base import Document
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion

    # Storage is external to the claim transaction; the invariant under test is
    # actual document/receipt identity, not a mocked indexing echo.
    monkeypatch.setattr(wechat_ingestion, "save_content", AsyncSave())
    user, other, kb, kb2, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="first",
        payload=encrypt_secret("{}"),
    )
    first = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    document, duplicate = await wechat_ingestion.claim_document(
        receipt, first, kb, "Exact contract text", "Contract", {"source": "wechat"}
    )
    assert not duplicate
    await Document.filter(id=document.id).update(status="completed", chunk_count=1)
    next_receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=other,
        knowledge_base=kb,
        message_id="second",
        payload=encrypt_secret("{}"),
    )
    second = await WeChatKnowledgeItem.create(receipt=next_receipt, item_index=0)
    reused, duplicate = await wechat_ingestion.claim_document(
        next_receipt, second, kb, "Exact contract text", "Another name", {}
    )
    assert duplicate and reused.id == document.id
    await second.refresh_from_db()
    assert second.status == "duplicate" and next_receipt.user_id == other.id
    other_receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb2,
        message_id="third",
        payload=encrypt_secret("{}"),
    )
    third = await WeChatKnowledgeItem.create(receipt=other_receipt, item_index=0)
    separate, duplicate = await wechat_ingestion.claim_document(
        other_receipt, third, kb2, "Exact contract text", "Contract", {}
    )
    assert not duplicate and separate.id != document.id
    assert await Document.filter(knowledge_base_id=kb.id).count() == 1
    assert await Document.filter(knowledge_base_id=kb2.id).count() == 1


class AsyncSave:
    async def __call__(self, path, content):
        return None


@pytest.mark.asyncio
async def test_reauthorization_preserves_collection_without_replacing_it(
    collection_db, monkeypatch
):
    import app.services.wechat_connection as service

    user, other, kb, _, binding, _ = collection_db

    monkeypatch.setattr(
        service.WeChatClient,
        "get_qrcode_status",
        lambda self, qrcode, verify_code=None: confirmation(self, qrcode, verify_code),
    )
    login = await WeChatKnowledgeLogin.create(
        user=user,
        qrcode=encrypt_secret("qr"),
        qrcode_content="qr",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    confirmed = await poll_login(login.id, user)
    assert confirmed["status"] == "confirmed"
    assert confirmed["binding"]["id"] == str(binding.id)
    await binding.refresh_from_db()
    assert decrypt_secret(binding.token) == "new-secret"
    # Re-authorizing refreshes credentials only; collection stays configured.
    assert confirmed["binding"]["collection"]["knowledge_base_id"] == str(kb.id)
    assert (
        await WeChatKnowledgeBinding.filter(wechat_user_id="wechat-user").count() == 1
    )
    assert await WeChatKnowledgeCollection.filter(binding_id=binding.id).count() == 1
    assert (
        await WeChatKnowledgeCollection.get(binding_id=binding.id)
    ).knowledge_base_id == kb.id

    rival = await WeChatKnowledgeLogin.create(
        user=other,
        qrcode=encrypt_secret("rival"),
        qrcode_content="qr",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    # Confirmed identity ownership is a real locked DB boundary and must reject
    # another platform account without touching the surviving configuration.
    with pytest.raises(BusinessError) as conflict:
        await poll_login(rival.id, other)
    assert conflict.value.status_code == 409
    await binding.refresh_from_db()
    assert binding.user_id == user.id
    assert await WeChatKnowledgeCollection.filter(binding_id=binding.id).count() == 1
    assert (
        await WeChatKnowledgeCollection.get(binding_id=binding.id)
    ).knowledge_base_id == kb.id
    summary = await binding_summary(binding)
    assert summary["collection"]["knowledge_base_name"] == "Target"


@pytest.mark.asyncio
async def test_existing_binding_table_upgrade_preserves_rows_and_restores_queries(
    collection_db,
):
    from tortoise import Tortoise
    from app.core.wechat_migration import migrate_wechat_knowledge_schema
    from app.api.v1.endpoints.wechat_knowledge import bindings

    user, _, _, _, binding, _ = collection_db
    connection = Tortoise.get_connection("default")
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" DROP COLUMN "disconnected_at"'
    )
    await migrate_wechat_knowledge_schema()
    await migrate_wechat_knowledge_schema()
    restored = await WeChatKnowledgeBinding.get(id=binding.id)
    assert restored.user_id == user.id
    assert restored.disconnected_at is None
    response = await bindings(user)
    assert [row["id"] for row in response["data"]] == [str(binding.id)]


@pytest.mark.asyncio
async def test_legacy_target_columns_migrate_once_and_disable_survives_rerun(
    collection_db,
):
    """Legacy coupling columns are copied into the optional collection once."""
    from tortoise import Tortoise
    from app.core.wechat_migration import migrate_wechat_knowledge_schema

    user, _, kb, _, binding, collection = collection_db
    vision = await vision_model_for(await Team.get(id=kb.team_id))
    legacy = await connected_binding(user, "legacy-wechat", "legacy-bot")
    receipt = await WeChatKnowledgeReceipt.create(
        binding=legacy,
        user=user,
        knowledge_base=kb,
        message_id="legacy",
        payload=encrypt_secret("{}"),
    )
    connection = Tortoise.get_connection("default")
    # Recreate the pre-decoupling schema on the current tables.
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" ADD COLUMN "knowledge_base_id" VARCHAR(36) NULL'
    )
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" ADD COLUMN "vision_model_id" VARCHAR(36) NULL'
    )
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" ADD COLUMN "stt_model_id" VARCHAR(36) NULL'
    )
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_logins" ADD COLUMN "knowledge_base_id" '
        "VARCHAR(36) NOT NULL DEFAULT ''"
    )
    await connection.execute_query(
        'UPDATE "wechat_knowledge_bindings" SET "knowledge_base_id" = ?, '
        '"vision_model_id" = ? WHERE "id" = ?',
        [str(kb.id), str(vision.id), str(legacy.id)],
    )

    await migrate_wechat_knowledge_schema()
    await migrate_wechat_knowledge_schema()

    migrated = await WeChatKnowledgeCollection.get(binding_id=legacy.id)
    assert migrated.knowledge_base_id == kb.id
    assert migrated.vision_model_id == vision.id
    assert migrated.stt_model_id is None
    # The connection itself is untouched and still authorized.
    restored = await WeChatKnowledgeBinding.get(id=legacy.id)
    assert restored.status == "connected" and restored.user_id == user.id
    assert decrypt_secret(restored.token) == "not-real"
    # The rebuild must not cascade-delete receipts that reference the binding.
    assert await WeChatKnowledgeReceipt.filter(binding_id=legacy.id).count() == 1
    preserved = await WeChatKnowledgeReceipt.get(id=receipt.id)
    assert preserved.knowledge_base_id == kb.id
    assert preserved.user_id == user.id
    # Existing configuration rows are never duplicated or overwritten.
    assert (await WeChatKnowledgeCollection.get(binding_id=binding.id)).id == (
        collection.id
    )

    for table in ("wechat_knowledge_bindings", "wechat_knowledge_logins"):
        columns = await connection.execute_query_dict(f'PRAGMA table_info("{table}")')
        names = {row["name"] for row in columns}
        assert "knowledge_base_id" not in names
        assert "vision_model_id" not in names
        assert "stt_model_id" not in names

    # A later migration after disabling collection must not recreate it.
    await WeChatKnowledgeCollection.filter(binding_id=legacy.id).delete()
    await migrate_wechat_knowledge_schema()
    assert not await WeChatKnowledgeCollection.filter(binding_id=legacy.id).exists()
    assert (await WeChatKnowledgeBinding.get(id=legacy.id)).status == "connected"


@pytest.mark.asyncio
async def test_markdown_upgrade_preserves_content_and_matches_canonical_filter(
    collection_db,
):
    from app.core.wechat_migration import migrate_wechat_knowledge_schema
    from app.models.knowledge_base import Document, DocumentType

    user, _, kb, _, _, _ = collection_db
    document = await Document.create(
        id=uuid4(),
        knowledge_base=kb,
        uploaded_by=user,
        name="Collected.md",
        doc_type="md",
        file_path="documents/collected.md",
        metadata={"source": "wechat"},
        status="completed",
        chunk_count=2,
    )
    await migrate_wechat_knowledge_schema()
    await migrate_wechat_knowledge_schema()
    found = await Document.filter(
        knowledge_base_id=kb.id, doc_type=DocumentType.MD.value
    ).get()
    assert found.id == document.id
    assert found.file_path == "documents/collected.md"
    assert found.status == "completed" and found.chunk_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("source_type", ["pptx", "url", "txt"])
async def test_collection_preserves_source_identity_and_migrates_legacy(
    collection_db, monkeypatch, tmp_path, source_type
):
    from app.core.wechat_migration import restore_wechat_document_sources
    from app.models.knowledge_base import Document
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id=source_type,
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    metadata = {"source": "wechat"}
    name = "Article" if source_type == "url" else f"Original.{source_type}"
    original = f"documents/{kb.id}/wechat/{item.id}/original/{name}"
    raw = b"Original bytes, not converted Markdown"
    if source_type == "url":
        metadata["source_url"] = "https://example.com/article"
    else:
        metadata.update(
            wechat_original_path=original,
            wechat_original_name=name,
            wechat_original_mime="application/octet-stream",
        )

    async def save(path, content):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def read(path):
        return (tmp_path / path).read_bytes()

    monkeypatch.setattr(ingestion, "save_content", save)
    monkeypatch.setattr(ingestion.document_processor, "read_file", read)
    if source_type != "url":
        await save(original, raw)
    document, duplicate = await ingestion.claim_document(
        receipt, item, kb, "# Parsed content", name, metadata
    )
    assert not duplicate
    assert document.doc_type == source_type and document.name == name
    assert document.file_path == (None if source_type == "url" else original)
    assert document.source_url == metadata.get("source_url")
    if source_type != "url":
        assert await read(document.file_path) == raw
        assert document.file_size == len(raw)
    document.doc_type = "markdown"
    document.name = name + ".md"
    document.file_path = f"documents/{kb.id}/wechat/{item.id}/content.md"
    document.status = "completed"
    document.chunk_count = 14
    await document.save()
    await restore_wechat_document_sources()
    await restore_wechat_document_sources()
    restored = await Document.get(id=document.id)
    assert restored.doc_type == source_type
    assert restored.name == name
    assert restored.file_path == (None if source_type == "url" else original)
    assert restored.status == "completed" and restored.chunk_count == 14


@pytest.mark.asyncio
async def test_exclusive_agent_purpose_routes_once_and_preserves_inactive_collection(
    collection_db,
):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose
    from app.models.agent import Agent, AgentStatus
    from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentReceipt

    user, _, kb, _, binding, _ = collection_db
    agent = await Agent.create(
        id=uuid4(),
        name="Wechat agent",
        team_id=kb.team_id,
        created_by=user,
        status=AgentStatus.PUBLISHED,
    )
    await update_purpose(
        binding.id, PurposeInput(purpose="agent", agent_id=agent.id), user
    )
    await binding.refresh_from_db()
    assert binding.purpose == "agent"
    assert await WeChatKnowledgeCollection.filter(binding_id=binding.id).exists()
    incoming = message("agent-input")
    assert await accept_updates(binding, {"msgs": [incoming, incoming]}) == []
    assert await WeChatAgentReceipt.filter(binding_id=binding.id).count() == 1
    assert await WeChatKnowledgeReceipt.filter(binding_id=binding.id).count() == 0
    receipt = await WeChatAgentReceipt.get(binding_id=binding.id)
    assert receipt.agent_id == agent.id and receipt.user_id == user.id
    with pytest.raises(BusinessError) as busy:
        await update_purpose(binding.id, PurposeInput(purpose="none"), user)
    assert busy.value.status_code == 409
    receipt.status = "completed"
    await receipt.save(update_fields=["status"])
    await update_purpose(binding.id, PurposeInput(purpose="none"), user)
    assert await WeChatAgentConfig.filter(binding_id=binding.id).exists()
    await binding.refresh_from_db()
    assert binding.status == "connected" and binding.purpose == "none"
    assert await accept_updates(binding, {"msgs": [message("ignored")]}) == []
    assert await WeChatAgentReceipt.filter(binding_id=binding.id).count() == 1
    await update_purpose(binding.id, PurposeInput(purpose="knowledge_collection"), user)
    await binding.refresh_from_db()
    await accept_updates(binding, {"msgs": [incoming]})
    assert not await WeChatKnowledgeReceipt.filter(
        binding_id=binding.id, message_id="agent-input"
    ).exists()
    await accept_updates(binding, {"msgs": [message("collect")]})
    assert await WeChatKnowledgeReceipt.filter(binding_id=binding.id).count() == 1
    assert await WeChatAgentReceipt.filter(binding_id=binding.id).count() == 1


@pytest.mark.asyncio
async def test_agent_purpose_rejects_unpublished_private_and_missing_required_variables(
    collection_db,
):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose
    from app.models.agent import Agent, AgentStatus

    user, other, kb, _, binding, _ = collection_db
    private = await Agent.create(
        id=uuid4(),
        name="Private",
        team_id=kb.team_id,
        created_by=other,
        status=AgentStatus.PUBLISHED,
        variables=[{"name": "project", "type": "text", "required": True}],
    )
    rival = await connected_binding(other, "other-agent", "other-agent")
    with pytest.raises(BusinessError):
        await update_purpose(
            rival.id, PurposeInput(purpose="agent", agent_id=private.id), user
        )
    with pytest.raises(BusinessError) as required:
        await update_purpose(
            binding.id, PurposeInput(purpose="agent", agent_id=private.id), user
        )
    assert required.value.msg_key == "wechat_agent_variables_invalid"
    await update_purpose(
        binding.id,
        PurposeInput(
            purpose="agent", agent_id=private.id, variables={"project": "demo"}
        ),
        user,
    )
    private.status = AgentStatus.DRAFT
    await private.save(update_fields=["status"])
    with pytest.raises(BusinessError) as unpublished:
        await update_purpose(
            binding.id,
            PurposeInput(
                purpose="agent", agent_id=private.id, variables={"project": "demo"}
            ),
            user,
        )
    assert unpublished.value.status_code == 403


@pytest.mark.asyncio
async def test_purpose_migration_preserves_active_collection_once(collection_db):
    from tortoise import Tortoise
    from app.core.wechat_migration import migrate_wechat_purpose

    _, _, _, _, binding, _ = collection_db
    connection = Tortoise.get_connection("default")
    await connection.execute_query(
        "ALTER TABLE wechat_knowledge_bindings DROP COLUMN purpose"
    )
    await migrate_wechat_purpose()
    await binding.refresh_from_db()
    assert binding.purpose == "knowledge_collection"
    binding.purpose = "none"
    await binding.save(update_fields=["purpose"])
    await migrate_wechat_purpose()
    await binding.refresh_from_db()
    assert binding.purpose == "none"


class _FakeRedis:
    """Minimal Redis surface used by the polling lease."""

    def __init__(self):
        self.values: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def eval(self, script, numkeys, key, *args):
        current = self.values.get(key)
        if current != args[0]:
            return 0
        if "del" in script:
            del self.values[key]
            return 1
        return 1


@pytest.mark.asyncio
async def test_poll_binding_stores_receipts_and_dispatches(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    redis = _FakeRedis()
    dispatched = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.wait = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_updates(self, cursor, *, wait_seconds=None):
            self.wait = wait_seconds
            return {"msgs": [message("poll-1")], "get_updates_buf": "next"}

    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)
    monkeypatch.setattr(
        wechat_receiver.celery_app,
        "send_task",
        lambda *args, **kwargs: dispatched.append(kwargs),
    )

    result = await wechat_receiver.poll_binding(binding)

    assert result == {"polled": True, "accepted": 1}
    assert await WeChatKnowledgeReceipt.filter(binding_id=binding.id).count() == 1
    assert dispatched and dispatched[0]["queue"] == "knowledge"
    # The scheduled tick must not hold a worker for the full long-poll.
    assert wechat_receiver.POLL_WAIT_SECONDS <= 5


@pytest.mark.asyncio
async def test_poll_binding_skips_when_lease_is_held(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    redis = _FakeRedis()
    redis.values[f"wechat:poll:{binding.id}"] = "another-worker"
    opened = []

    class Client:
        def __init__(self, *args, **kwargs):
            opened.append(True)

    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)

    result = await wechat_receiver.poll_binding(binding)

    assert result == {"polled": False, "reason": "leased"}
    assert opened == [], "a leased binding must not call upstream"


@pytest.mark.asyncio
async def test_poll_binding_marks_expired_authorization(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    redis = _FakeRedis()

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_updates(self, cursor, *, wait_seconds=None):
            raise WeChatAPIError(-14)

    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)

    result = await wechat_receiver.poll_binding(binding)

    assert result["polled"] is False and result["code"] == -14
    await binding.refresh_from_db()
    assert binding.status == "error"
    assert binding.last_error == "wechat_authorization_expired"
    # The lease is released even when the poll fails.
    assert f"wechat:poll:{binding.id}" not in redis.values
