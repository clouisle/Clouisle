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
        capabilities={"input_modalities": ["text", "image"]},
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
        from app.models.integration import Integration

        await Integration.create(
            name="wechat",
            provider_type="wechat",
            display_name="WeChat iLink",
            enabled_capabilities=["agent_chat", "knowledge_collection"],
        )
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
    accepted = await accept_updates(
        binding,
        {
            "msgs": [message(), message(), message("2", "stranger")],
            "get_updates_buf": "next",
        },
    )
    ids = accepted.knowledge_receipt_ids
    assert accepted.agent_receipt_ids == []
    assert len(ids) == 1
    assert await WeChatKnowledgeReceipt.all().count() == 1
    receipt = await WeChatKnowledgeReceipt.get(id=ids[0])
    assert receipt.knowledge_base_id == kb.id
    await WeChatKnowledgeCollection.filter(binding_id=binding.id).update(
        knowledge_base_id=kb2.id
    )
    await WeChatKnowledgeBinding.filter(id=binding.id).update(generation=uuid4())
    assert (
        await accept_updates(
            binding, {"msgs": [message("new")], "get_updates_buf": "late"}
        )
    ).accepted == 0
    await receipt.refresh_from_db()
    assert receipt.knowledge_base_id == kb.id
    await binding.refresh_from_db()
    await WeChatKnowledgeBinding.filter(id=binding.id).update(status="disconnected")
    assert (
        await accept_updates(binding, {"msgs": [message("after-disconnect")]})
    ).accepted == 0
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
    result = await accept_updates(
        binding, {"msgs": [message(identifier="ignored", sender="fresh-wechat")]}
    )
    assert result.accepted == 0


@pytest.mark.asyncio
async def test_configless_connection_ignores_messages_but_advances_cursor(
    collection_db,
):
    user, _, _, _, _, _ = collection_db
    binding = await connected_binding(user, "silent-wechat", "silent-bot")
    cursor = binding.cursor
    result = await accept_updates(
        binding,
        {
            "msgs": [message(identifier="1", sender="silent-wechat")],
            "get_updates_buf": "advance",
        },
    )
    assert result.accepted == 0
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
    result = await accept_updates(
        binding,
        {
            "msgs": [message(identifier="after-disable")],
            "get_updates_buf": "advance",
        },
    )
    assert result.accepted == 0
    await binding.refresh_from_db()
    assert decrypt_secret(binding.cursor) == "advance"
    assert await WeChatKnowledgeReceipt.all().count() == 0


@pytest.mark.asyncio
async def test_receipt_snapshot_survives_collection_change_and_removal(collection_db):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose

    user, _, kb, kb2, binding, _ = collection_db
    accepted = await accept_updates(
        binding, {"msgs": [message()], "get_updates_buf": "next"}
    )
    receipt = await WeChatKnowledgeReceipt.get(id=accepted.knowledge_receipt_ids[0])
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
    # Mirrors the iLink CDN media format (AES-128-ECB + PKCS7) under test.
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
    result = await accept_updates(binding, {"msgs": [incoming, incoming]})
    assert len(result.agent_receipt_ids) == 1
    assert result.knowledge_receipt_ids == []
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
    assert (await accept_updates(binding, {"msgs": [message("ignored")]})).accepted == 0
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
async def test_agent_variable_change_resets_existing_conversation_but_same_values_do_not(
    collection_db,
):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose
    from app.models.agent import Agent, AgentStatus, Conversation
    from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentSession

    user, _, kb, _, binding, _ = collection_db
    agent = await Agent.create(
        id=uuid4(),
        name="Variable writer",
        team_id=kb.team_id,
        created_by=user,
        status=AgentStatus.PUBLISHED,
        variables=[{"name": "tone", "type": "text", "required": True}],
    )
    await update_purpose(
        binding.id,
        PurposeInput(purpose="agent", agent_id=agent.id, variables={"tone": "formal"}),
        user,
    )
    conversation = await Conversation.create(agent=agent, user=user)
    session = await WeChatAgentSession.create(
        binding=binding,
        agent=agent,
        conversation=conversation,
        pending_answers={"old": "answer"},
        pending_tool_call_id="old-call",
    )

    await update_purpose(
        binding.id,
        PurposeInput(purpose="agent", agent_id=agent.id, variables={"tone": "formal"}),
        user,
    )
    await session.refresh_from_db()
    assert session.conversation_id == conversation.id
    assert session.pending_answers == {"old": "answer"}
    assert session.pending_tool_call_id == "old-call"

    await update_purpose(
        binding.id,
        PurposeInput(purpose="agent", agent_id=agent.id, variables={"tone": "concise"}),
        user,
    )
    await session.refresh_from_db()
    config = await WeChatAgentConfig.get(binding_id=binding.id)
    assert config.variables == {"tone": "concise"}
    assert session.conversation_id is None
    assert session.pending_answers == {}
    assert session.pending_tool_call_id is None


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

    assert wechat_receiver.POLL_WAIT_SECONDS <= 5


@pytest.mark.asyncio
async def test_empty_unchanged_poll_is_transaction_free(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    await binding.refresh_from_db()
    cursor = binding.cursor

    async def no_transaction():
        raise AssertionError("unchanged empty response must not open a transaction")

    monkeypatch.setattr(wechat_receiver, "in_transaction", no_transaction)
    result = await wechat_receiver.accept_updates(
        binding,
        {"msgs": [], "get_updates_buf": decrypt_secret(cursor) if cursor else ""},
    )
    assert result.accepted == 0
    await binding.refresh_from_db()
    assert binding.cursor == cursor


@pytest.mark.asyncio
async def test_empty_poll_clears_old_error_without_advancing_cursor(collection_db):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    await WeChatKnowledgeBinding.filter(id=binding.id).update(last_error="old failure")
    await binding.refresh_from_db()
    cursor = binding.cursor
    result = await wechat_receiver.accept_updates(
        binding,
        {"msgs": [], "get_updates_buf": decrypt_secret(cursor) if cursor else ""},
    )
    assert result.accepted == 0
    await binding.refresh_from_db()
    assert binding.last_error is None
    assert binding.cursor == cursor


@pytest.mark.asyncio
async def test_poll_binding_dispatches_only_new_agent_receipts(
    collection_db, monkeypatch
):
    from app.api.v1.endpoints.wechat_knowledge import PurposeInput, update_purpose
    from app.models.agent import Agent, AgentStatus
    from app.services import wechat_receiver

    user, _, kb, _, binding, _ = collection_db
    agent = await Agent.create(
        id=uuid4(),
        name="Polling agent",
        team_id=kb.team_id,
        created_by=user,
        status=AgentStatus.PUBLISHED,
    )
    await update_purpose(
        binding.id, PurposeInput(purpose="agent", agent_id=agent.id), user
    )
    await binding.refresh_from_db()
    incoming = message("agent-poll-receipt")

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get_updates(self, *_args, **_kwargs):
            return {"msgs": [incoming]}

    redis = _FakeRedis()
    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)
    monkeypatch.setattr("app.services.wechat_agent_dispatch.enqueue_binding", dispatch)
    result = await wechat_receiver.poll_binding(binding)
    assert result["accepted"] == 1
    dispatch.assert_awaited_once_with(binding.id)

    result = await wechat_receiver.poll_binding(binding)
    assert result["accepted"] == 0
    dispatch.assert_awaited_once_with(binding.id)


@pytest.mark.asyncio
async def test_poll_binding_borrows_shared_http_client(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    redis = _FakeRedis()
    shared = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )

    class Client:
        def __init__(self, *_args, **kwargs):
            assert kwargs["http"] is shared

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get_updates(self, *_args, **_kwargs):
            return {"msgs": []}

    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)
    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    result = await wechat_receiver.poll_binding(binding, http=shared)
    assert result["polled"] is True
    assert not shared.is_closed
    await shared.aclose()


@pytest.mark.asyncio
async def test_changed_empty_cursor_is_committed(collection_db, monkeypatch):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    result = await wechat_receiver.accept_updates(
        binding, {"msgs": [], "get_updates_buf": "changed-empty-cursor"}
    )
    assert result.accepted == 0
    await binding.refresh_from_db()
    assert decrypt_secret(binding.cursor) == "changed-empty-cursor"


@pytest.mark.asyncio
async def test_replaced_or_expired_batch_cannot_commit_cursor(collection_db):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    old_claim = uuid4()
    await WeChatKnowledgeBinding.filter(id=binding.id).update(
        poll_claim=old_claim, poll_claim_expires_at=utcnow() + timedelta(seconds=90)
    )
    await binding.refresh_from_db()
    await WeChatKnowledgeBinding.filter(id=binding.id).update(poll_claim=uuid4())
    assert (
        await wechat_receiver.accept_updates(
            binding,
            {"msgs": [message("late-batch")], "get_updates_buf": "must-not-commit"},
        )
    ).accepted == 0
    assert not await WeChatKnowledgeReceipt.all().exists()
    assert (await WeChatKnowledgeBinding.get(id=binding.id)).cursor == ""
    await WeChatKnowledgeBinding.filter(id=binding.id).update(
        poll_claim=old_claim, poll_claim_expires_at=utcnow() - timedelta(seconds=1)
    )
    assert (
        await wechat_receiver.accept_updates(
            binding, {"msgs": [], "get_updates_buf": "expired-cursor"}
        )
    ).accepted == 0
    assert (await WeChatKnowledgeBinding.get(id=binding.id)).cursor == ""


@pytest.mark.asyncio
async def test_poll_binding_does_not_dispatch_duplicate_knowledge_receipt(
    collection_db, monkeypatch
):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    incoming = message("duplicate-poll")
    accepted = await wechat_receiver.accept_updates(binding, {"msgs": [incoming]})
    assert len(accepted.knowledge_receipt_ids) == 1
    redis = _FakeRedis()
    dispatched = []

    async def duplicate_updates(self, *_args, **_kwargs):
        return {"msgs": [incoming]}

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        get_updates = duplicate_updates

    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)
    monkeypatch.setattr(
        wechat_receiver.celery_app,
        "send_task",
        lambda *args, **kwargs: dispatched.append(kwargs),
    )
    result = await wechat_receiver.poll_binding(binding)
    assert result["accepted"] == 0
    assert dispatched == []


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


@pytest.mark.asyncio
async def test_accept_updates_rejects_invalid_batch_and_skips_malformed_messages(
    collection_db,
):
    _, _, _, _, binding, _ = collection_db
    with pytest.raises(WeChatAPIError):
        await accept_updates(binding, {"msgs": {"not": "a list"}})

    malformed = message(identifier=None)
    oversized = message(identifier="x" * 129)
    accepted = await accept_updates(
        binding,
        {
            "msgs": [None, {}, malformed, oversized, message("valid-after-invalid")],
            "get_updates_buf": "advance-after-invalid",
        },
    )

    assert accepted.accepted == 1
    assert accepted.agent_receipt_ids == []
    assert await WeChatKnowledgeReceipt.filter(
        message_id="valid-after-invalid"
    ).exists()
    await binding.refresh_from_db()
    assert decrypt_secret(binding.cursor) == "advance-after-invalid"


@pytest.mark.asyncio
async def test_poll_binding_discards_batch_when_lease_expires_before_commit(
    collection_db, monkeypatch
):
    from app.services import wechat_receiver

    _, _, _, _, binding, _ = collection_db
    redis = _FakeRedis()

    async def lost_lease(*_args, **_kwargs):
        return 0

    redis.eval = lost_lease

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get_updates(self, *_args, **_kwargs):
            return {"msgs": [message("lease-lost")], "get_updates_buf": "uncommitted"}

    monkeypatch.setattr(wechat_receiver, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(wechat_receiver, "WeChatClient", Client)

    result = await wechat_receiver.poll_binding(binding)

    assert result == {"polled": False, "reason": "lease_lost"}
    assert not await WeChatKnowledgeReceipt.filter(message_id="lease-lost").exists()
    await binding.refresh_from_db()
    assert binding.cursor == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["环境异常", "访问过于频繁", "完成验证后即可继续访问"])
async def test_article_challenge_is_not_indexed_as_content(
    collection_db, monkeypatch, body
):
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="challenge",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    monkeypatch.setattr(
        ingestion.document_processor,
        "fetch_url_content",
        AsyncMock(return_value=(body, {})),
    )
    with pytest.raises(BusinessError) as blocked:
        await ingestion.text_for_input(
            {"kind": "url", "url": "https://mp.weixin.qq.com/s/article"},
            receipt,
            kb,
            None,
            item,
        )
    assert blocked.value.msg_key == "wechat_article_blocked"
    await item.refresh_from_db()
    assert item.document_id is None


@pytest.mark.asyncio
async def test_article_source_retains_title_url_and_caption(collection_db, monkeypatch):
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="article-source",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    monkeypatch.setattr(
        ingestion.document_processor,
        "fetch_url_content",
        AsyncMock(return_value=("Article body", {"title": "Article title"})),
    )
    text, title, source = await ingestion.text_for_input(
        {
            "kind": "url",
            "url": "https://example.com/article",
            "caption": "Save for onboarding",
        },
        receipt,
        kb,
        None,
        item,
    )
    assert (text, title) == ("Article body", "Article title")
    assert source["source_url"] == "https://example.com/article"
    assert source["wechat_caption"] == "Save for onboarding"
    assert source["wechat_receipt_id"] == str(receipt.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        (OSError("storage unavailable"), "pending"),
        (ValueError("bad content"), "error"),
        (WeChatAPIError("file_too_large"), "error"),
    ],
)
async def test_receipt_distinguishes_retryable_storage_from_terminal_content_errors(
    collection_db, monkeypatch, failure, expected
):
    import json
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion
    from app.services.audit_log import AuditLogService

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="receipt-error",
        payload=encrypt_secret(json.dumps(message())),
    )

    async def fail_item(current, index, spec):
        await WeChatKnowledgeItem.get_or_create(receipt=current, item_index=index)
        raise failure

    monkeypatch.setattr(ingestion, "process_item", fail_item)
    monkeypatch.setattr(ingestion, "reply_result", AsyncMock())
    monkeypatch.setattr(AuditLogService, "log", AsyncMock())
    result = await ingestion._process_receipt(str(receipt.id))
    assert result["status"] == expected
    await receipt.refresh_from_db()
    assert receipt.lease_owner is None and receipt.lease_expires_at is None
    item = await WeChatKnowledgeItem.get(receipt=receipt, item_index=0)
    if expected == "pending":
        assert item.status == "pending"
        assert receipt.results == []
    else:
        assert item.status == "error"
        assert item.last_error == (
            "file_too_large"
            if isinstance(failure, WeChatAPIError)
            else "wechat_processing_failed"
        )
        assert receipt.results[0]["status"] == "error"


@pytest.mark.asyncio
async def test_expired_content_lease_reuses_document_without_double_counting(
    collection_db, monkeypatch
):
    from app.models.knowledge_base import Document
    from app.models.wechat_knowledge import WeChatKnowledgeItem, WeChatKnowledgeContent
    from app.services import wechat_ingestion as ingestion

    monkeypatch.setattr(ingestion, "save_content", AsyncSave())
    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="lease",
        payload=encrypt_secret("{}"),
    )
    first = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    second = await WeChatKnowledgeItem.create(receipt=receipt, item_index=1)
    document, duplicate = await ingestion.claim_document(
        receipt, first, kb, "Same body", "Note", {}
    )
    assert not duplicate
    with pytest.raises(ingestion.CollectionBusy):
        await ingestion.claim_document(receipt, second, kb, "Same body", "Note", {})
    await WeChatKnowledgeContent.filter(document_id=document.id).update(
        lease_expires_at=utcnow() - timedelta(seconds=1)
    )
    resumed, duplicate = await ingestion.claim_document(
        receipt, second, kb, "Same body", "Note", {}
    )
    assert resumed.id == document.id and not duplicate
    await kb.refresh_from_db()
    assert kb.document_count == 1
    assert await Document.filter(knowledge_base=kb).count() == 1
    claim = await WeChatKnowledgeContent.get(document_id=document.id)
    assert claim.owner_item_id == second.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_token,fail_send,expected",
    [
        (None, False, "unavailable"),
        ("context", False, "submitted"),
        ("context", True, "unknown"),
    ],
)
async def test_collection_reply_is_not_replayed_after_ambiguous_send(
    collection_db, monkeypatch, context_token, fail_send, expected
):
    from app.services import wechat_ingestion as ingestion

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="reply",
        payload=encrypt_secret("{}"),
        results=[{"index": 0, "status": "completed", "name": "Saved note"}],
    )
    sends = []

    class Client:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send_text(self, recipient, text, token):
            sends.append((recipient, text, token))
            if fail_send:
                raise TimeoutError("response lost")

    monkeypatch.setattr(ingestion, "WeChatClient", Client)
    await ingestion.reply_result(receipt, {"context_token": context_token})
    await receipt.refresh_from_db()
    assert receipt.reply_status == expected
    await ingestion.reply_result(receipt, {"context_token": context_token})
    assert len(sends) == (1 if context_token else 0)
    if sends:
        assert sends[0][0] == binding.wechat_user_id
        assert "Saved note" in sends[0][1]
        assert sends[0][2] == context_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,mime,raw,error",
    [
        ("bad.txt", "text/plain", b"\xff", "wechat_text_encoding"),
        ("bad.txt", "text/plain", b"hidden\x00binary", "wechat_binary_content"),
        ("bad.pdf", "application/pdf", b"not a pdf", "wechat_binary_content"),
        (
            "bad.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"not a zip",
            "wechat_binary_content",
        ),
    ],
)
async def test_media_rejects_binary_disguised_as_document(
    collection_db, monkeypatch, filename, mime, raw, error
):
    from types import SimpleNamespace
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion
    from app.api.v1.endpoints import knowledge_bases

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="binary",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    monkeypatch.setattr(
        knowledge_bases,
        "get_kb_document_max_upload_size_mb",
        AsyncMock(return_value=10),
    )
    monkeypatch.setattr(ingestion, "save_content", AsyncSave())
    extract = AsyncMock(side_effect=AssertionError("invalid bytes reached parser"))
    monkeypatch.setattr(ingestion.document_processor, "extract_text", extract)
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(raw, filename, mime))
    )
    with pytest.raises(BusinessError) as rejected:
        await ingestion.text_for_input(
            {"kind": "media", "item": {"type": 4}}, receipt, kb, client, item
        )
    assert rejected.value.msg_key == error
    extract.assert_not_awaited()
    await item.refresh_from_db()
    assert item.original_path.endswith("/" + filename)
    assert item.document_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,filename,mime,raw,transcript,expected",
    [
        (4, "note.txt", "text/plain", b"Note", "", "Parsed note"),
        (
            3,
            "voice.silk",
            "audio/silk",
            b"audio",
            "Provider transcript",
            "Provider transcript",
        ),
        (2, "photo.png", "image/png", b"image", "", "Image description"),
    ],
)
async def test_media_extraction_preserves_private_original_provenance(
    collection_db, monkeypatch, kind, filename, mime, raw, transcript, expected
):
    from types import SimpleNamespace
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion
    from app.api.v1.endpoints import knowledge_bases

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="valid-media",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    monkeypatch.setattr(
        knowledge_bases,
        "get_kb_document_max_upload_size_mb",
        AsyncMock(return_value=10),
    )
    monkeypatch.setattr(ingestion, "save_content", AsyncSave())
    monkeypatch.setattr(
        ingestion.document_processor,
        "extract_text",
        AsyncMock(return_value=("Parsed note", {"pages": 1})),
    )
    monkeypatch.setattr(
        ingestion, "extract_media", AsyncMock(return_value="Image description")
    )
    incoming = {
        "type": kind,
        "voice_item": {"text": transcript, "media": {"key": "audio"}},
    }
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(raw, filename, mime))
    )
    text, name, source = await ingestion.text_for_input(
        {"kind": "media", "item": incoming, "caption": "Context"},
        receipt,
        kb,
        client,
        item,
    )
    assert (text, name) == (expected, filename)
    assert source["wechat_original_size"] == len(raw)
    assert source["wechat_original_mime"] == mime
    assert source["wechat_caption"] == "Context"
    await item.refresh_from_db()
    assert source["wechat_original_path"] == item.original_path
    assert item.original_path.startswith(
        f"documents/{kb.id}/wechat/{item.id}/original/"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [False, True])
async def test_item_completion_requires_real_indexed_chunks(
    collection_db, monkeypatch, indexed
):
    from app.models.knowledge_base import Document
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion
    from app.tasks import knowledge_base as tasks

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="index-result",
        payload=encrypt_secret("{}"),
    )
    monkeypatch.setattr(ingestion, "save_content", AsyncSave())

    async def index(document_id, _):
        await Document.filter(id=document_id).update(
            status="completed", chunk_count=int(indexed)
        )

    monkeypatch.setattr(tasks, "_process_document", index)
    if indexed:
        item = await ingestion.process_item(
            receipt, 0, {"kind": "text", "text": "Durable knowledge"}
        )
        assert item.status == "completed"
        repeated = await ingestion.process_item(
            receipt, 0, {"kind": "text", "text": "Different retry payload"}
        )
        assert repeated.id == item.id and repeated.document_id == item.document_id
        assert await Document.filter(knowledge_base=kb).count() == 1
    else:
        with pytest.raises(BusinessError) as failed:
            await ingestion.process_item(
                receipt, 0, {"kind": "text", "text": "Durable knowledge"}
            )
        assert failed.value.msg_key == "wechat_index_failed"
        item = await WeChatKnowledgeItem.get(receipt=receipt, item_index=0)
        assert item.status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec,error",
    [
        (
            {"kind": "url", "url": "https://example.com/" + "x" * 1024},
            "wechat_url_invalid",
        ),
        ({"kind": "unsupported"}, "wechat_type_unsupported"),
        ({"kind": "media", "item": {"type": 99}}, "wechat_type_unsupported"),
    ],
)
async def test_invalid_input_is_rejected_before_download(
    collection_db, monkeypatch, spec, error
):
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import wechat_ingestion as ingestion

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="invalid",
        payload=encrypt_secret("{}"),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    with pytest.raises(BusinessError) as rejected:
        await ingestion.text_for_input(spec, receipt, kb, None, item)
    assert rejected.value.msg_key == error
    assert item.document_id is None and item.original_path is None


@pytest.mark.asyncio
async def test_revoked_target_after_indexing_cannot_report_success(
    collection_db, monkeypatch
):
    from app.models.knowledge_base import Document
    from app.services import wechat_ingestion as ingestion
    from app.tasks import knowledge_base as tasks

    user, _, kb, _, binding, _ = collection_db
    receipt = await WeChatKnowledgeReceipt.create(
        binding=binding,
        user=user,
        knowledge_base=kb,
        message_id="revoked-during-index",
        payload=encrypt_secret("{}"),
    )
    monkeypatch.setattr(ingestion, "save_content", AsyncSave())

    async def index(document_id, _):
        await Document.filter(id=document_id).update(status="completed", chunk_count=1)
        await WeChatKnowledgeBinding.filter(id=binding.id).update(status="disconnected")

    monkeypatch.setattr(tasks, "_process_document", index)
    with pytest.raises(BusinessError) as denied:
        await ingestion.process_item(
            receipt, 0, {"kind": "text", "text": "Revoked document"}
        )
    assert denied.value.msg_key == "wechat_binding_disconnected"
    document = await Document.get(knowledge_base=kb)
    assert document.status == "error"
    assert document.error_message == "wechat_target_unavailable"
