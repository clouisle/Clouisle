"""Isolated WeChat Agent IO boundary tests against a real in-memory ORM.

Covers the real boundaries only: UTF-8 chunking, input classification and
capability gating, deterministic inbound Asset identity, canonical output
extraction from tool display schemas, and durable delivery claiming with
per-send reauthorization. No production credentials or network calls.
"""

import json
from datetime import timedelta
from urllib.parse import quote
from uuid import uuid4
from types import SimpleNamespace

from unittest.mock import AsyncMock
import httpx
import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.integrations.wechat import WeChatAPIError
from app.models.agent import Agent, AgentStatus, AgentVisibility, Conversation, Message
from app.models.asset import Asset
from app.models.user import Team, User
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import WeChatKnowledgeBinding
from app.services.wechat_agent_io import (
    ATTACHMENT_CATEGORY,
    chunk_text,
    deliver_pending,
    split_items,
)
from app.services.wechat_connection import utcnow
from app.schemas.response import BusinessError
from tests.services.delivery_fixtures import wechat_delivery_fields


def receipt_message(items, identifier="18446744073709551615"):
    return {
        "message_id": identifier,
        "from_user_id": "wechat-user",
        "message_type": 1,
        "message_state": 2,
        "context_token": "ctx-token",
        "item_list": items,
    }


@pytest_asyncio.fixture
async def io_db():
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
            username="owner",
            email="owner@example.test",
            hashed_password="unused",
            is_superuser=True,
        )
        team = await Team.create(id=uuid4(), name="Agent team")
        agent = await Agent.create(
            id=uuid4(),
            name="Writer",
            team=team,
            created_by=user,
            status=AgentStatus.PUBLISHED,
            visibility=AgentVisibility.PRIVATE,
            enable_attachments=True,
            attachment_config={"max_files": 2, "allowed_extensions": [".txt", ".png"]},
        )
        binding = await WeChatKnowledgeBinding.create(
            id=uuid4(),
            user=user,
            wechat_user_id="wechat-user",
            bot_id="bot",
            token=encrypt_secret("not-real"),
            base_url="https://ilinkai.weixin.qq.com",
            purpose="agent",
        )
        conversation = await Conversation.create(
            id=uuid4(), title="WeChat", agent=agent, user=user
        )
        session = await WeChatAgentSession.create(
            id=uuid4(),
            binding=binding,
            agent=agent,
            conversation=conversation,
            context_token=encrypt_secret("ctx-token"),
        )
        yield user, team, agent, binding, conversation, session


async def make_receipt(binding, user, agent, payload, status="pending"):
    return await WeChatAgentReceipt.create(
        id=uuid4(),
        binding=binding,
        user=user,
        agent=agent,
        variables={},
        message_id=str(uuid4()),
        payload=encrypt_secret(json.dumps(payload)),
        status=status,
    )


@pytest.mark.asyncio
async def test_batch_normalization_keeps_text_assets_and_aggregate_limit(
    io_db, monkeypatch
):
    from app.services import wechat_agent_io as io
    from app.services.wechat_receiver import _merge_agent_receipts
    from tortoise.transactions import in_transaction

    user, _, agent, binding, _, session = io_db
    text = receipt_message([{"type": 1, "text_item": {"text": "总结一下"}}])
    document = receipt_message([{"type": 4, "file_item": {"file_name": "report.txt"}}])
    first = await make_receipt(binding, user, agent, text)
    second = await make_receipt(binding, user, agent, document)
    async with in_transaction() as db:
        await _merge_agent_receipts([(first, text), (second, document)], db)
    first = await WeChatAgentReceipt.get(id=first.id)
    monkeypatch.setattr(io, "_store_upload", AsyncMock())
    client = SimpleNamespace(
        download_media=AsyncMock(
            return_value=(b"report content", "report.txt", "text/plain")
        )
    )
    prepared = await io.normalize_input(first, session, agent, user, client)
    assert prepared.message == "总结一下"
    assert prepared.file_urls[0].filename == "report.txt"
    asset = await Asset.get(id=prepared.file_urls[0].asset_id)
    assert str(second.id) in asset.storage_key
    again = await io.normalize_input(first, session, agent, user, client)
    assert again.file_urls[0].asset_id == prepared.file_urls[0].asset_id

    third = await make_receipt(binding, user, agent, document)
    fourth = await make_receipt(binding, user, agent, document)
    async with in_transaction() as db:
        await _merge_agent_receipts(
            [(first, text), (second, document), (third, document), (fourth, document)],
            db,
        )
    first = await WeChatAgentReceipt.get(id=first.id)
    with pytest.raises(BusinessError) as exc:
        await io.normalize_input(first, session, agent, user, client)
    assert exc.value.msg_key == "wechat_agent_too_many_files"


def test_chunk_text_preserves_every_utf8_byte():
    text = "你好" * 2000
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert all(len(chunk.encode("utf-8")) <= 3500 for chunk in chunks)
    # A multi-byte character is never split across chunks.
    assert all(chunk for chunk in chunks)


def test_chunk_text_short_and_empty():
    assert chunk_text("hello") == ["hello"]
    assert chunk_text("") == []


def test_split_items_media_keeps_caption():
    items = split_items(
        {
            "item_list": [
                {"type": 1, "text_item": {"text": "两份合同"}},
                {"type": 4, "file_item": {"file_name": "a.pdf"}},
                {"type": 4, "file_item": {"file_name": "b.pdf"}},
            ]
        }
    )
    assert [spec["kind"] for spec in items] == ["media", "media"]
    assert all(spec["caption"] == "两份合同" for spec in items)


def test_split_items_plain_text_and_unsupported():
    assert split_items({"item_list": [{"type": 1, "text_item": {"text": "hi"}}]}) == [
        {"kind": "text", "text": "hi"}
    ]
    assert split_items({"item_list": []}) == [{"kind": "unsupported"}]


@pytest.mark.asyncio
async def test_normalize_input_requires_conversation(io_db):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
    )
    from app.services.wechat_agent_io import normalize_input

    # One configured agent per binding, so the real session loses its
    # conversation instead of a second row being created.
    session.conversation = None
    await session.save(update_fields=["conversation_id"])
    with pytest.raises(BusinessError) as exc:
        await normalize_input(receipt, session, agent, user, None)
    assert exc.value.msg_key == "wechat_agent_conversation_missing"


@pytest.mark.asyncio
async def test_normalize_input_attachments_disabled(io_db):
    user, _, agent, binding, _, session = io_db
    agent.enable_attachments = False
    await agent.save(update_fields=["enable_attachments"])
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 4, "file_item": {"file_name": "notes.txt"}}]),
    )
    from app.services.wechat_agent_io import normalize_input

    with pytest.raises(BusinessError) as exc:
        await normalize_input(receipt, session, agent, user, None)
    assert exc.value.msg_key == "wechat_agent_attachments_disabled"


@pytest.mark.asyncio
async def test_normalize_input_plain_text_maps_variables(io_db):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "写一份周报"}}]),
    )
    receipt.variables = {"tone": "formal"}
    await receipt.save(update_fields=["variables"])
    from app.services.wechat_agent_io import normalize_input

    request = await normalize_input(receipt, session, agent, user, None)
    assert request.message == "写一份周报"
    assert request.variables == {"tone": "formal"}
    assert request.conversation_id == session.conversation_id
    assert request.images == [] and request.file_urls == []


@pytest.mark.asyncio
async def test_normalize_input_voice_transcript_is_used_directly(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [{"type": 3, "voice_item": {"text": "转写的文字", "media": {}}}]
        ),
    )
    from app.services import wechat_agent_io

    async def fail_download(*args, **kwargs):
        raise AssertionError("transcript path must not download media")

    monkeypatch.setattr(wechat_agent_io, "_transcribe_voice", fail_download)
    request = await wechat_agent_io.normalize_input(receipt, session, agent, user, None)
    assert request.message == "转写的文字"


@pytest.mark.asyncio
async def test_normalize_input_voice_without_stt_is_rejected(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {
                    "type": 3,
                    "voice_item": {
                        "media": {"aes_key": "k", "encrypt_query_param": "p"}
                    },
                }
            ]
        ),
    )
    from app.services import wechat_agent_io

    class FakeClient:
        async def download_media(self, item, max_bytes):
            return b"silk-bytes", "voice.silk", "audio/silk"

    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io.normalize_input(
            receipt, session, agent, user, FakeClient()
        )
    assert exc.value.msg_key == "wechat_stt_required"


@pytest.mark.asyncio
async def test_normalize_input_file_registers_private_asset_once(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "请看附件"}},
                {"type": 4, "file_item": {"file_name": "notes.txt"}},
            ]
        ),
    )
    from app.services import wechat_agent_io

    stored = {}

    class FakeClient:
        async def download_media(self, item, max_bytes):
            return b"attachment-bytes", "notes.txt", "text/plain"

    async def fake_store(content, storage_key, content_type):
        stored[storage_key] = content

    monkeypatch.setattr(wechat_agent_io, "_store_upload", fake_store)
    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, FakeClient()
    )
    # The caption is preserved in the prompt text.
    assert "请看附件" in request.message
    assert len(request.file_urls) == 1
    entry = request.file_urls[0]
    assert entry.filename == "notes.txt"
    assert entry.mime_type == "text/plain"
    assert entry.asset_ref
    asset = await Asset.get(id=entry.asset_id)
    # Inbound originals stay private: no team, owned by the binding user.
    assert asset.team_id is None
    assert asset.created_by_id == user.id
    # Deterministic identity inside the route-served filename.
    assert f"{receipt.id}-" in asset.storage_key
    assert asset.storage_key.startswith(f"{ATTACHMENT_CATEGORY}/")
    assert asset.storage_key.endswith("-notes.txt")
    # Retrying normalization reuses the same durable Asset.
    again = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, FakeClient()
    )
    assert again.file_urls[0].asset_id == entry.asset_id
    assert await Asset.all().count() == 1


@pytest.mark.asyncio
async def test_normalize_input_rejects_disallowed_extension(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 4, "file_item": {"file_name": "malware.exe"}}]),
    )
    from app.services import wechat_agent_io

    class FakeClient:
        async def download_media(self, item, max_bytes):
            return b"MZ", "malware.exe", "application/octet-stream"

    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io.normalize_input(
            receipt, session, agent, user, FakeClient()
        )
    assert exc.value.msg_key == "wechat_agent_file_type_unsupported"


@pytest.mark.asyncio
async def test_build_output_emits_text_chunks_then_generated_assets(io_db):
    user, _, agent, binding, conversation, session = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    long_text = "报告" * 2000
    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content=long_text,
        round_id=uuid4(),
        is_round_canonical=True,
    )
    run.canonical_message_id = canonical.id
    await run.save(update_fields=["canonical_message_id"])
    asset = await Asset.create(
        id=uuid4(),
        storage_key="generated-images/x.png",
        original_filename="chart.png",
        display_filename="chart.png",
        content_type="image/png",
        size=10,
        checksum="0" * 64,
        source="generated_media",
        team_id=agent.team_id,
        created_by_id=user.id,
    )
    from app.models.asset import AssetScopeRef, AssetScopeType

    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref="abcd",
    )
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps(
            {
                "kind": "media.image",
                "success": True,
                "images": [{"image": {"asset_ref": "abcd"}}],
            }
        ),
        round_id=canonical.round_id,
        round_role="tool_result",
    )
    from app.services import wechat_agent_io

    payloads = await wechat_agent_io.build_output(
        run,
        await make_receipt(binding, user, agent, receipt_message([])),
        session,
        user,
    )
    kinds = [payload["kind"] for payload in payloads]
    assert kinds[0] == "text" and kinds[-1] == "asset"
    assert (
        "".join(payload["text"] for payload in payloads if payload["kind"] == "text")
        == long_text
    )
    assert all(
        len(payload["text"].encode("utf-8")) <= 3500
        for payload in payloads
        if payload["kind"] == "text"
    )


@pytest.mark.asyncio
async def test_deliver_pending_claims_and_sends_with_stable_client_id(
    io_db, monkeypatch
):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
        status="completed",
    )
    sent = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send_text(self, to, text, context_token, *, client_id=None):
            sent.append((to, text, context_token, client_id))

    monkeypatch.setattr(
        "app.services.wechat_agent_io.WeChatClient",
        lambda *args, **kwargs: FakeClient(),
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "最终答复"},
    )
    await deliver_pending(binding, user)
    assert len(sent) == 1
    assert sent[0][0] == binding.wechat_user_id
    assert sent[0][1] == "最终答复"
    assert sent[0][2] == "ctx-token"
    assert sent[0][3] == str(delivery.id)
    row = await IntegrationDelivery.get(id=delivery.id)
    assert row.status == "sent"
    # A second pass never resends an already-submitted row.
    await deliver_pending(binding, user)
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_deliver_pending_marks_unavailable_when_disconnected(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
        status="completed",
    )
    await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "答复"},
    )

    def refuse(*args, **kwargs):
        raise AssertionError("must not open a client for a disconnected binding")

    monkeypatch.setattr("app.services.wechat_agent_io.WeChatClient", refuse)
    binding.status = "disconnected"
    await binding.save(update_fields=["status"])
    await deliver_pending(binding, user)
    row = await IntegrationDelivery.first()
    assert row.status == "unavailable"
    assert row.error == "wechat_agent_binding_disconnected"


@pytest.mark.asyncio
async def test_deliver_pending_timeout_becomes_unknown(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
        status="completed",
    )
    await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "答复"},
    )

    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send_text(self, to, text, context_token, *, client_id=None):
            raise TimeoutError

    monkeypatch.setattr(
        "app.services.wechat_agent_io.WeChatClient",
        lambda *args, **kwargs: TimeoutClient(),
    )
    await deliver_pending(binding, user)
    row = await IntegrationDelivery.first()
    assert row.status == "unknown"
    # Unknown rows are never blind-resent.
    await deliver_pending(binding, user)
    assert row.status == "unknown"


@pytest.mark.asyncio
async def test_stale_sending_rows_expire_to_unknown(io_db):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
        status="completed",
    )
    row = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "答复"},
        status="sending",
    )
    stale_at = utcnow() - timedelta(seconds=3600)
    await IntegrationDelivery.filter(id=row.id).update(updated_at=stale_at)
    await deliver_pending(binding, user)
    row = await IntegrationDelivery.get(id=row.id)
    assert row.status == "unknown"


# ---------- Transport boundary: real CDN upload protocol ----------


def _aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    # Mirrors the iLink CDN media format (AES-128-ECB + PKCS7) under test.
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


@pytest.mark.asyncio
async def test_upload_media_encrypts_and_posts_without_bearer(monkeypatch):
    import app.integrations.wechat as transport
    from app.services.wechat_agent_io import _encrypt_media

    captured = {}

    async def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = await request.aread()
        return httpx.Response(200, headers={"X-Encrypted-Param": "download-param"})

    monkeypatch.setattr(
        transport,
        "ensure_external_http_url_allowed",
        AsyncMock(side_effect=lambda value: value),
    )
    plaintext = b"generated image bytes \xe4\xb8\xad\xe6\x96\x87"
    ciphertext, aeskey_hex, raw_md5 = _encrypt_media(plaintext)
    async with transport.WeChatClient() as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        param = await client.upload_media(
            "https://novac2c.cdn.weixin.qq.com/c2c/upload?encrypted_query_param=x",
            ciphertext,
        )
    assert param == "download-param"
    # The ciphertext really is AES-128-ECB with the generated key.
    assert _aes_ecb_decrypt(captured["body"], bytes.fromhex(aeskey_hex)) == plaintext
    # The bot bearer token never reaches the CDN.
    assert captured["authorization"] is None
    assert captured["content_type"] == "application/octet-stream"
    assert captured["url"].startswith("https://novac2c.cdn.weixin.qq.com/")


@pytest.mark.asyncio
async def test_upload_media_rejects_nonofficial_host(monkeypatch):
    import app.integrations.wechat as transport

    async def handler(request):
        raise AssertionError("must not upload to a non-official host")

    async with transport.WeChatClient() as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(WeChatAPIError):
            await client.upload_media("https://evil.example/upload", b"x" * 16)


@pytest.mark.asyncio
async def test_send_media_item_shape_matches_protocol(monkeypatch):
    import app.integrations.wechat as transport

    payloads = []

    async def handler(request):
        payloads.append(await request.aread())
        return httpx.Response(200, text='{"ret":0}')

    monkeypatch.setattr(
        transport,
        "ensure_external_http_url_allowed",
        AsyncMock(side_effect=lambda value: value),
    )
    item = {
        "type": 2,
        "image_item": {
            "media": {"encrypt_query_param": "p", "aes_key": "k"},
            "mid_size": 32,
        },
    }
    async with transport.WeChatClient("https://ilinkai.weixin.qq.com", "tok") as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.send_media("wechat-user", "ctx", item=item, client_id="stable-id")
    payload = json.loads(payloads[0])
    msg = payload["msg"]
    assert msg["client_id"] == "stable-id"
    assert msg["item_list"] == [item]
    # No stray top-level media field outside the typed item.
    assert "media" not in msg["item_list"][0]


@pytest.mark.asyncio
async def test_send_text_uses_stable_client_id(monkeypatch):
    import app.integrations.wechat as transport

    bodies = []

    async def handler(request):
        bodies.append(await request.aread())
        return httpx.Response(200, text='{"ret":0}')

    monkeypatch.setattr(
        transport,
        "ensure_external_http_url_allowed",
        AsyncMock(side_effect=lambda value: value),
    )
    async with transport.WeChatClient("https://ilinkai.weixin.qq.com", "tok") as client:
        await client.http.aclose()
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.send_text("wechat-user", "hi", "ctx", client_id="fixed")
        await client.send_text("wechat-user", "hi", "ctx")
    assert json.loads(bodies[0])["msg"]["client_id"] == "fixed"
    assert json.loads(bodies[1])["msg"]["client_id"] != "fixed"


# ---------- Output authorization: conversation + team scoping ----------


async def _asset_for(team, user, key="generated-images/a.png", name="a.png"):
    return await Asset.create(
        id=uuid4(),
        storage_key=key,
        original_filename=name,
        display_filename=name,
        content_type="image/png",
        size=4,
        checksum="0" * 64,
        source="generated_media",
        team_id=team.id if team else None,
        created_by_id=user.id,
    )


@pytest.mark.asyncio
async def test_output_asset_same_conversation_is_authorized(io_db):
    from app.services import channel_artifacts

    user, team, agent, binding, conversation, _ = io_db
    asset = await _asset_for(team, user)
    from app.models.asset import AssetScopeRef, AssetScopeType

    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref="bbbb",
    )
    context = {
        "user": user,
        "agent": agent,
        "conversation_id": conversation.id,
    }
    authorized = await channel_artifacts.authorize_output_asset(
        asset.id,
        conversation_id=context["conversation_id"],
        agent=context["agent"],
        user=context["user"],
    )
    assert authorized is not None and authorized.id == asset.id


@pytest.mark.asyncio
async def test_output_asset_foreign_conversation_is_rejected(io_db):
    from app.models.asset import AssetScopeRef, AssetScopeType
    from app.services import channel_artifacts

    user, team, agent, binding, conversation, _ = io_db
    asset = await _asset_for(team, user)
    other_conversation = await Conversation.create(
        id=uuid4(), title="Other", agent=agent, user=user
    )
    # The asset is only scoped to the original conversation.
    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref="aaaa",
    )
    context = {"user": user, "agent": agent, "conversation_id": other_conversation.id}
    assert (
        await channel_artifacts.authorize_output_asset(
            asset.id,
            conversation_id=context["conversation_id"],
            agent=agent,
            user=user,
        )
        is None
    )
    # The same asset is authorized for its own conversation.
    own = {"user": user, "agent": agent, "conversation_id": conversation.id}
    assert (
        await channel_artifacts.authorize_output_asset(
            asset.id,
            conversation_id=own["conversation_id"],
            agent=agent,
            user=user,
        )
        is not None
    )


@pytest.mark.asyncio
async def test_output_asset_foreign_team_is_rejected(io_db):
    from app.services import channel_artifacts

    user, team, agent, binding, conversation, _ = io_db
    other_team = await Team.create(id=uuid4(), name="Other team")
    asset = await _asset_for(other_team, user)
    context = {"user": user, "agent": agent, "conversation_id": conversation.id}
    assert (
        await channel_artifacts.authorize_output_asset(
            asset.id,
            conversation_id=context["conversation_id"],
            agent=agent,
            user=user,
        )
        is None
    )


@pytest.mark.asyncio
async def test_build_output_never_leaks_reasoning_or_tool_text(io_db):
    """Only the canonical assistant text and generated assets are delivered."""
    user, _, agent, binding, conversation, session = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    round_id = uuid4()
    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content="最终答复",
        reasoning_content="SECRET-CHAIN-OF-THOUGHT",
        round_id=round_id,
        is_round_canonical=True,
    )
    run.canonical_message_id = canonical.id
    await run.save(update_fields=["canonical_message_id"])
    # A tool result in the same round carries debug text and no asset refs.
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps({"kind": "media.image", "success": True, "images": []}),
        tool_name="generate_image",
        round_id=round_id,
        round_role="tool_result",
    )
    from app.services.wechat_agent_io import build_output

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
    )
    payloads = await build_output(run, receipt, session, user)
    assert payloads == [{"kind": "text", "text": "最终答复"}]
    assert all("SECRET" not in json.dumps(payload) for payload in payloads)
    assert all("generate_image" not in json.dumps(payload) for payload in payloads)


@pytest.mark.asyncio
async def test_normalize_input_voice_download_transcribes_and_keeps_original(
    io_db, monkeypatch
):
    """Without a provider transcript the download is transcribed and retained."""
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "听一下"}},
                {"type": 3, "voice_item": {"media": {"aes_key": "k"}}},
            ]
        ),
    )

    class VoiceClient:
        async def download_media(self, item, max_bytes):
            assert item["type"] == 3 and max_bytes == 10 * 1024 * 1024
            return b"voice-bytes", "voice.silk", "audio/silk"

    stored = {}
    transcribe_calls = []

    async def fake_store(content, storage_key, content_type):
        stored[storage_key] = (content, content_type)

    async def fake_transcribe(path_bytes, filename, team_id, stt_model_id):
        transcribe_calls.append((path_bytes, filename, team_id, stt_model_id))
        return "语音识别结果"

    monkeypatch.setattr(wechat_agent_io, "_store_upload", fake_store)
    monkeypatch.setattr(wechat_agent_io, "_transcribe_voice", fake_transcribe)
    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, VoiceClient()
    )
    assert request.message == "语音识别结果\n\n听一下"
    assert request.file_urls == [] and request.images == []
    # The original voice is retained as a private attachment, not delivered.
    assert len(stored) == 1
    assert next(iter(stored.values()))[0] == b"voice-bytes"
    assert transcribe_calls == [
        (b"voice-bytes", "voice.silk", str(agent.team_id), None)
    ]


@pytest.mark.asyncio
async def test_normalize_input_rejects_unknown_item_type(io_db):
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 9, "location_item": {"text": "here"}}]),
    )
    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io.normalize_input(receipt, session, agent, user, None)
    assert exc.value.msg_key == "wechat_agent_media_unsupported"


@pytest.mark.asyncio
async def test_normalize_input_image_maps_conversation_scoped_asset(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 2, "image_item": {"media": {}}}]),
    )
    monkeypatch.setattr(wechat_agent_io, "_store_upload", AsyncMock())
    from app.llm.types import ContentType

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.model_utils.resolve_agent_chat_model",
        AsyncMock(
            return_value=SimpleNamespace(
                input_capabilities=SimpleNamespace(modalities={ContentType.IMAGE})
            )
        ),
    )
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(b"png-bytes", "photo.png", "image/png"))
    )
    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, client
    )
    assert len(request.images) == 1
    image = request.images[0]
    assert request.file_urls == []
    asset = await Asset.get(id=image.asset_id)
    assert image.url == f"/api/v1/upload/files/{quote(asset.storage_key, safe='/')}"
    assert asset.content_type == "image/png"
    assert asset.created_by_id == user.id and asset.team_id is None
    # The ref binds the asset to the session's conversation scope.
    from app.models.asset import AssetScopeRef, AssetScopeType

    ref = await AssetScopeRef.get(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=session.conversation_id,
        asset_id=asset.id,
    )
    assert image.asset_ref == ref.ref


@pytest.mark.asyncio
async def test_normalize_input_video_extraction_error_is_remapped(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 5, "video_item": {"media": {}}}]),
    )
    monkeypatch.setattr(
        wechat_agent_io,
        "_agent_vision_model_id",
        AsyncMock(return_value="vision-model"),
    )
    monkeypatch.setattr(wechat_agent_io, "_retain_original", AsyncMock())

    def fail_extract(*_args):
        raise BusinessError(code=400, msg_key="wechat_media_duration")

    monkeypatch.setattr(wechat_agent_io, "extract_media", fail_extract)
    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io.normalize_input(
            receipt,
            session,
            agent,
            user,
            SimpleNamespace(
                download_media=AsyncMock(
                    return_value=(b"video", "clip.mp4", "video/mp4")
                )
            ),
        )
    assert exc.value.msg_key == "wechat_media_duration"


@pytest.mark.asyncio
async def test_transcribe_voice_converts_then_transcribes(monkeypatch):
    from app.services import wechat_agent_io

    tool_calls = []
    transcribed = []

    async def fake_tool(*args):
        tool_calls.append(args)
        return b""

    async def fake_audio_text(path, team_id, model_id):
        transcribed.append((path.name, team_id, str(model_id)))
        return "对话内容"

    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )
    monkeypatch.setattr("app.services.wechat_media.run_media_tool", fake_tool)
    monkeypatch.setattr("app.services.wechat_media.audio_text", fake_audio_text)
    result = await wechat_agent_io._transcribe_voice(
        b"silk-bytes", "voice.silk", "team-id", "stt-model"
    )
    assert result == "对话内容"
    assert len(tool_calls) == 1
    assert tool_calls[0][0] == "/usr/bin/ffmpeg"
    args = list(tool_calls[0])
    assert args[5:9] == ["file,pipe", "-i", args[7], "-vn"]
    assert args[7].endswith("input.silk")
    assert args[9:13] == ["-ac", "1", "-ar", "16000"]
    assert args[-3:] == ["-b:a", "48k", args[-1]]
    assert args[-1].endswith("audio.mp3")
    # The converted MP3 path is handed to the transcriber with the team/model ids.
    assert transcribed == [("audio.mp3", "team-id", "stt-model")]


@pytest.mark.asyncio
async def test_transcribe_voice_requires_ffmpeg(monkeypatch):
    from app.services import wechat_agent_io

    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io._transcribe_voice(
            b"silk-bytes", "voice.silk", "team-id", "stt-model"
        )
    assert exc.value.msg_key == "wechat_agent_media_unsupported"


@pytest.mark.asyncio
async def test_transcribe_voice_conversion_failure_propagates(monkeypatch):
    from app.services import wechat_agent_io

    async def failing_tool(*_args):
        raise BusinessError(code=400, msg_key="wechat_media_conversion_failed")

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("transcription must not run after a failed conversion")

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.wechat_media.run_media_tool", failing_tool)
    monkeypatch.setattr("app.services.wechat_media.audio_text", must_not_run)
    with pytest.raises(BusinessError) as exc:
        await wechat_agent_io._transcribe_voice(
            b"silk-bytes", "voice.silk", "team-id", "stt-model"
        )
    assert exc.value.msg_key == "wechat_media_conversion_failed"


@pytest.mark.asyncio
async def test_resolve_run_assets_handles_duplicates_and_unreadable_display(
    io_db, monkeypatch
):
    user, _, agent, binding, conversation, _ = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.models.asset import AssetScopeRef, AssetScopeType
    from app.services import channel_artifacts

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    round_id = uuid4()
    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content="ok",
        round_id=round_id,
        is_round_canonical=True,
    )
    run.canonical_message_id = canonical.id
    await run.save(update_fields=["canonical_message_id"])
    asset = await _asset_for(agent.team, user)
    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref="cccc",
    )
    # A malformed tool payload is skipped; a non-dict display is skipped too.
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content="not-json",
        round_id=round_id,
        round_role="tool_result",
    )
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps([{"asset_ref": "cccc"}]),
        round_id=round_id,
        round_role="tool_result",
    )
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps(
            {
                "kind": "media.image",
                "success": True,
                "images": [{"image": {"asset_ref": "cccc"}}],
            }
        ),
        round_id=round_id,
        round_role="tool_result",
    )
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps(
            {"kind": "media.video", "success": True, "video": {"asset_ref": "cccc"}}
        ),
        round_id=round_id,
        round_role="tool_result",
    )
    resolved = await channel_artifacts.resolve_run_assets(run, agent, user)
    assert [item.id for item in resolved] == [asset.id]


@pytest.mark.asyncio
async def test_build_output_ignores_missing_agent_row(io_db):
    user, _, agent, binding, conversation, session = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.services import wechat_agent_io

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    run.canonical_message_id = None
    await run.save(update_fields=["canonical_message_id"])
    await run.delete()
    payloads = await wechat_agent_io.build_output(
        run,
        await make_receipt(binding, user, agent, receipt_message([])),
        session,
        user,
    )
    assert payloads == []


@pytest.mark.asyncio
async def test_upload_asset_media_builds_typed_image_and_video_items(monkeypatch):
    from app.services import wechat_agent_io

    captured = {}

    async def reserve(**kwargs):
        captured.update(kwargs)
        return "https://cdn.weixin.qq.com/upload", "unused"

    async def upload(url, ciphertext):
        captured["url"] = url
        captured["ciphertext"] = ciphertext
        return "download-param"

    client = SimpleNamespace(
        get_upload_url=AsyncMock(side_effect=reserve),
        upload_media=AsyncMock(side_effect=upload),
    )
    monkeypatch.setattr(
        wechat_agent_io, "read_asset_bytes", AsyncMock(return_value=b"media bytes")
    )
    image_item = await wechat_agent_io._upload_asset_media(
        client,
        SimpleNamespace(
            storage_key="generated/a.png",
            content_type="image/png",
            display_filename="a.png",
        ),
        "wechat-user",
    )
    assert image_item["type"] == wechat_agent_io.ITEM_IMAGE
    assert image_item["image_item"]["mid_size"] == len(captured["ciphertext"])
    assert image_item["image_item"]["media"]["encrypt_type"] == 1

    captured.clear()
    video_item = await wechat_agent_io._upload_asset_media(
        client,
        SimpleNamespace(
            storage_key="generated/b.mp4",
            content_type="video/mp4",
            display_filename="b.mp4",
        ),
        "wechat-user",
    )
    assert video_item["type"] == wechat_agent_io.ITEM_VIDEO
    assert video_item["video_item"]["video_size"] == len(captured["ciphertext"])
    assert video_item["video_item"]["media"]["encrypt_query_param"] == "download-param"
    assert captured["media_type"] == 2


@pytest.mark.asyncio
async def test_send_payload_sends_authorized_asset_as_media_item(io_db, monkeypatch):
    from app.services import wechat_agent_io

    user, team, agent, binding, conversation, _ = io_db
    asset = await _asset_for(team, user)
    sent = {}

    class AssetClient:
        async def send_media(self, to_user, context_token, *, item, client_id):
            sent["to_user"] = to_user
            sent["context_token"] = context_token
            sent["item"] = item
            sent["client_id"] = client_id

    async def authorized_upload(client, authorized, to_user_id):
        sent["uploaded"] = (to_user_id, client is not None)
        return {"type": 2, "image_item": {"mid_size": 4}}

    monkeypatch.setattr(
        wechat_agent_io, "authorize_output_asset", AsyncMock(return_value=asset)
    )
    monkeypatch.setattr(
        wechat_agent_io, "_upload_asset_media", AsyncMock(side_effect=authorized_upload)
    )
    context = {
        "context_token": "ctx-token",
        "conversation_id": conversation.id,
        "user": user,
        "agent": agent,
    }
    await wechat_agent_io._send_payload(
        AssetClient(),
        {"kind": "asset", "asset_id": str(asset.id)},
        context,
        "client-1",
        binding,
    )
    assert sent["to_user"] == binding.wechat_user_id
    assert sent["context_token"] == "ctx-token"
    assert sent["client_id"] == "client-1"
    assert sent["item"] == {"type": 2, "image_item": {"mid_size": 4}}
    assert sent["uploaded"] == (binding.wechat_user_id, True)


@pytest.mark.asyncio
async def test_send_payload_rejects_unauthorized_asset(io_db, monkeypatch):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    monkeypatch.setattr(
        wechat_agent_io, "authorize_output_asset", AsyncMock(return_value=None)
    )
    client = SimpleNamespace(send_media=AsyncMock(), send_text=AsyncMock())
    with pytest.raises(WeChatAPIError) as exc:
        await wechat_agent_io._send_payload(
            client,
            {"kind": "asset", "asset_id": str(uuid4())},
            {
                "context_token": "ctx",
                "conversation_id": uuid4(),
                "agent": agent,
                "user": user,
            },
            "client-2",
            binding,
        )
    assert exc.value.code == "asset_unavailable"
    client.send_media.assert_not_awaited()
    client.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_pending_skips_bindings_without_receipts(io_db):
    user, _, agent, binding, _, session = io_db
    await deliver_pending(binding, user)
    assert await IntegrationDelivery.all().count() == 0


@pytest.mark.asyncio
async def test_deliver_pending_lost_claim_never_resends(io_db, monkeypatch):
    """A row claimed by a concurrent worker between query and update is skipped."""
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 1, "text_item": {"text": "hi"}}]),
        status="completed",
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "答复"},
    )
    sent = []

    class NeverUsedClient:
        async def __aenter__(self):
            raise AssertionError("a lost claim must not open a client")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.wechat_agent_io.WeChatClient",
        lambda *args, **kwargs: NeverUsedClient(),
    )

    from tortoise.queryset import QuerySet

    original_update = QuerySet.update

    async def always_lose_update(self, *args, **kwargs):
        if self.model is IntegrationDelivery:
            # The row was claimed by a concurrent worker before this pass.
            return 0
        return await original_update(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "update", always_lose_update)
    await deliver_pending(binding, user)
    assert sent == []
    await delivery.refresh_from_db()
    assert delivery.status == "pending"


def test_attachment_configuration_and_safe_filenames_have_stable_defaults():
    from types import SimpleNamespace

    from app.services import wechat_agent_io

    assert wechat_agent_io._attachment_limits(
        SimpleNamespace(attachment_config=None)
    ) == (
        10 * 1024 * 1024,
        5,
        set(),
    )
    assert wechat_agent_io._attachment_limits(
        SimpleNamespace(attachment_config={"max_files": None})
    ) == (
        10 * 1024 * 1024,
        5,
        set(),
    )
    assert wechat_agent_io._attachment_limits(
        SimpleNamespace(attachment_config={"max_files": "many"})
    ) == (
        10 * 1024 * 1024,
        5,
        set(),
    )
    configured = SimpleNamespace(
        attachment_config={
            "max_file_size": "invalid",
            "max_files": None,
            "allowed_extensions": [".TXT", "pdf", ".PNG"],
        }
    )
    assert wechat_agent_io._attachment_limits(configured) == (
        10 * 1024 * 1024,
        5,
        {".txt", ".png"},
    )
    assert (
        wechat_agent_io._sanitize_name("../folder\\notes.txt", "fallback.bin")
        == "notes.txt"
    )
    assert wechat_agent_io._sanitize_name("../", "fallback.bin") == "fallback.bin"
    assert wechat_agent_io._ensure_extension("image", "image/png") == "image.png"
    assert wechat_agent_io._ensure_extension("notes.txt", "image/png") == "notes.txt"


def test_media_types_map_to_wechat_cdn_envelopes():
    from app.services import wechat_agent_io

    assert wechat_agent_io._media_item_type("image/png") == (2, 1, "image_item")
    assert wechat_agent_io._media_item_type("video/mp4") == (5, 2, "video_item")
    assert wechat_agent_io._media_item_type("application/pdf") == (4, 3, "file_item")


@pytest.mark.asyncio
async def test_run_asset_resolution_skips_missing_and_foreign_assets(
    io_db, monkeypatch
):
    user, _, agent, binding, conversation, session = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.services import channel_artifacts

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    assert (
        await channel_artifacts.resolve_run_assets(
            SimpleNamespace(conversation_id=None, canonical_message_id=None),
            agent,
            user,
        )
        == []
    )
    assert await channel_artifacts.resolve_run_assets(run, agent, user) == []


@pytest.mark.asyncio
async def test_asset_read_uses_storage_backend_for_local_mode(monkeypatch):
    from app.services import channel_artifacts

    class Storage:
        async def read(self, key):
            assert key == "agent-attachments/asset.txt"
            return b"private bytes"

    async def storage_backend(_root):
        return Storage()

    from app.services import document_processor, upload_storage

    monkeypatch.setattr(document_processor, "_remote_mode", lambda: False)
    monkeypatch.setattr(upload_storage, "get_upload_storage_backend", storage_backend)
    asset = SimpleNamespace(storage_key="agent-attachments/asset.txt")
    assert await channel_artifacts.read_asset_bytes(asset) == b"private bytes"


@pytest.mark.asyncio
async def test_normalize_input_rejects_attachment_count_and_byte_limits(io_db):
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    agent.attachment_config = {"max_files": 1}
    await agent.save(update_fields=["attachment_config"])
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 3, "voice_item": {"text": "transcribed"}},
                {"type": 4, "file_item": {"file_name": "b.txt"}},
            ]
        ),
    )

    class MustNotDownload:
        async def download_media(self, *_args):
            raise AssertionError("file count is rejected before download")

    with pytest.raises(BusinessError) as too_many:
        await wechat_agent_io.normalize_input(
            receipt, session, agent, user, MustNotDownload()
        )
    assert too_many.value.msg_key == "wechat_agent_too_many_files"

    agent.attachment_config = {"max_file_size": 2}
    await agent.save(update_fields=["attachment_config"])
    one_file = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 4, "file_item": {"file_name": "a.txt"}}]),
    )

    class Oversized:
        async def download_media(self, _item, _limit):
            return b"large", "a.txt", "text/plain"

    with pytest.raises(BusinessError) as too_large:
        await wechat_agent_io.normalize_input(
            one_file, session, agent, user, Oversized()
        )
    assert too_large.value.msg_key == "wechat_agent_file_too_large"


@pytest.mark.asyncio
async def test_normalize_input_rejects_images_without_vision(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    from app.services import wechat_agent_io

    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 2, "image_item": {"media": {}}}]),
    )
    monkeypatch.setattr(
        wechat_agent_io, "_agent_supports_vision", AsyncMock(return_value=False)
    )

    class DownloadImage:
        async def download_media(self, *_args):
            return b"image", "photo.png", "image/png"

    with pytest.raises(BusinessError) as unavailable:
        await wechat_agent_io.normalize_input(
            receipt, session, agent, user, DownloadImage()
        )
    assert unavailable.value.msg_key == "wechat_agent_vision_required"


def test_display_asset_refs_only_accepts_successful_known_schemas():
    from app.services.channel_artifacts import display_asset_refs

    assert display_asset_refs(
        {
            "kind": "media.image",
            "success": True,
            "images": [{"image": {"asset_ref": "image-ref"}}, None],
            "artifacts": [{"asset_ref": "artifact-ref"}],
        }
    ) == ["image-ref", "artifact-ref"]
    assert display_asset_refs(
        {"kind": "media.video", "success": True, "video": {"asset_ref": "video-ref"}}
    ) == ["video-ref"]
    assert (
        display_asset_refs(
            {
                "kind": "media.image",
                "success": False,
                "images": [{"image": {"asset_ref": "hidden"}}],
            }
        )
        == []
    )


@pytest.mark.asyncio
async def test_send_one_marks_explicit_provider_rejection_as_error(io_db, monkeypatch):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding, user, agent, receipt_message([]), status="completed"
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="rejected-final",
        sequence=0,
        payload={"kind": "text", "text": "reply"},
        status="sending",
    )

    async def resolved(*_args):
        return (
            {
                "binding": binding,
                "user": user,
                "agent": agent,
                "agent_id": agent.id,
                "session": session,
                "conversation_id": session.conversation_id,
                "context_token": "ctx-token",
            },
            "",
        )

    class RejectClient:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def send_text(self, *_args, **_kwargs):
            raise WeChatAPIError("permission_denied")

    monkeypatch.setattr(wechat_agent_io, "_delivery_context", resolved)
    monkeypatch.setattr(wechat_agent_io, "WeChatClient", RejectClient)
    await wechat_agent_io._send_one(delivery, binding)
    await delivery.refresh_from_db()
    assert delivery.status == "error"
    assert delivery.error == "permission_denied"
    assert (
        delivery.error_detail
        == "WeChatAPIError: WeChat request failed | code permission_denied"
    )


@pytest.mark.asyncio
async def test_upload_asset_media_rejects_empty_or_oversized_bytes(monkeypatch):
    from app.services import wechat_agent_io

    asset = SimpleNamespace(
        storage_key="generated/x.bin",
        content_type="application/octet-stream",
        display_filename="x.bin",
    )

    async def no_bytes(_asset):
        return b""

    monkeypatch.setattr(wechat_agent_io, "read_asset_bytes", no_bytes)
    with pytest.raises(WeChatAPIError) as empty:
        await wechat_agent_io._upload_asset_media(SimpleNamespace(), asset, "wechat")
    assert empty.value.code == "empty_media"

    async def too_many_bytes(_asset):
        return b"x" * (wechat_agent_io.WECHAT_MEDIA_LIMIT + 1)

    monkeypatch.setattr(wechat_agent_io, "read_asset_bytes", too_many_bytes)
    with pytest.raises(WeChatAPIError) as oversized:
        await wechat_agent_io._upload_asset_media(SimpleNamespace(), asset, "wechat")
    assert oversized.value.code == "file_too_large"


@pytest.mark.asyncio
async def test_upload_asset_media_builds_typed_file_payload(monkeypatch):
    from app.services import wechat_agent_io

    asset = SimpleNamespace(
        storage_key="generated/report.pdf",
        content_type="application/pdf",
        display_filename="report.pdf",
    )
    monkeypatch.setattr(
        wechat_agent_io, "read_asset_bytes", AsyncMock(return_value=b"PDF bytes")
    )
    captured = {}

    async def reserve(**kwargs):
        captured.update(kwargs)
        return "https://cdn.weixin.qq.com/upload", "unused"

    async def upload(url, ciphertext):
        captured["url"] = url
        captured["ciphertext"] = ciphertext
        return "download-param"

    client = SimpleNamespace(
        get_upload_url=AsyncMock(side_effect=reserve),
        upload_media=AsyncMock(side_effect=upload),
    )
    item = await wechat_agent_io._upload_asset_media(client, asset, "wechat-user")
    assert item["type"] == wechat_agent_io.ITEM_FILE
    payload = item["file_item"]
    assert payload["file_name"] == "report.pdf"
    assert payload["len"] == "9"
    assert payload["media"]["encrypt_query_param"] == "download-param"
    assert captured["raw_size"] == 9
    assert captured["file_size"] == len(captured["ciphertext"])
    assert captured["to_user_id"] == "wechat-user"


@pytest.mark.asyncio
@pytest.mark.parametrize("vision", [None, "vision-model"])
async def test_video_input_requires_vision_and_preserves_caption_once(
    io_db, monkeypatch, vision
):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "Summarize this clip"}},
                {"type": 5, "video_item": {"media": {}}},
            ]
        ),
    )
    monkeypatch.setattr(
        wechat_agent_io, "_agent_vision_model_id", AsyncMock(return_value=vision)
    )
    retain = AsyncMock()
    monkeypatch.setattr(wechat_agent_io, "_retain_original", retain)
    monkeypatch.setattr(
        wechat_agent_io, "extract_media", AsyncMock(return_value="A train arrives.")
    )
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(b"video", "clip.mp4", "video/mp4"))
    )
    if vision is None:
        with pytest.raises(BusinessError) as unavailable:
            await wechat_agent_io.normalize_input(receipt, session, agent, user, client)
        assert unavailable.value.msg_key == "wechat_agent_video_unsupported"
        retain.assert_not_awaited()
    else:
        request = await wechat_agent_io.normalize_input(
            receipt, session, agent, user, client
        )
        assert request.message == "A train arrives.\n\nSummarize this clip"
        assert request.images == [] and request.file_urls == []
        retain.assert_awaited_once()


@pytest.mark.asyncio
async def test_retried_asset_reuses_private_identity_and_rejects_changed_bytes(
    io_db, monkeypatch
):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    store = AsyncMock()
    monkeypatch.setattr(wechat_agent_io, "_store_upload", store)
    args = dict(
        filename="note.txt",
        content_type="text/plain",
        user=user,
        receipt=receipt,
        index=0,
    )
    first = await wechat_agent_io._save_asset(b"original", **args)
    same = await wechat_agent_io._save_asset(b"original", **args)
    assert same.id == first.id
    assert first.created_by_id == user.id and first.team_id is None
    with pytest.raises(BusinessError) as changed:
        await wechat_agent_io._save_asset(b"tampered", **args)
    assert changed.value.msg_key == "wechat_agent_media_unsupported"
    store.assert_awaited_once()
    assert await Asset.filter(storage_key=first.storage_key).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation,expected",
    [
        ("inactive_user", "wechat_agent_binding_disconnected"),
        ("unapproved_user", "wechat_agent_binding_disconnected"),
        ("missing_agent", "wechat_agent_config_missing"),
        ("unpublished_agent", "agent_access_denied"),
        ("missing_conversation", "wechat_agent_conversation_missing"),
        ("missing_context", "wechat_agent_context_missing"),
        ("reauthorized", "wechat_agent_binding_disconnected"),
    ],
)
async def test_delivery_context_rechecks_revoked_state(io_db, revocation, expected):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    if revocation == "inactive_user":
        user.is_active = False
        await user.save(update_fields=["is_active"])
    elif revocation == "unapproved_user":
        user.approval_status = "pending"
        await user.save(update_fields=["approval_status"])
    elif revocation == "missing_agent":
        receipt.agent_id = None
    elif revocation == "unpublished_agent":
        agent.status = "draft"
        await agent.save(update_fields=["status"])
    elif revocation == "missing_conversation":
        session.conversation_id = None
        await session.save(update_fields=["conversation_id"])
    elif revocation == "missing_context":
        session.context_token = ""
        await session.save(update_fields=["context_token"])
    elif revocation == "reauthorized":
        binding.disconnected_at = utcnow()
        await binding.save(update_fields=["disconnected_at"])
    context, error = await wechat_agent_io._delivery_context(
        binding, None, receipt, user
    )
    assert context is None and error == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        ("wrapped_timeout", "unknown"),
        ("business_error", "error"),
        ("cancelled", "sending"),
    ],
)
async def test_delivery_preserves_ambiguous_or_cancelled_send_state(
    io_db, monkeypatch, failure, expected
):
    import asyncio
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(
        binding, user, agent, receipt_message([]), status="completed"
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="failure",
        sequence=0,
        payload={"kind": "text", "text": "reply"},
        status="sending",
    )

    async def send(*args, **kwargs):
        if failure == "wrapped_timeout":
            raise WeChatAPIError("transport_error") from TimeoutError("lost response")
        if failure == "business_error":
            raise BusinessError(code=400, msg_key="wechat_agent_media_unsupported")
        raise asyncio.CancelledError()

    monkeypatch.setattr(wechat_agent_io, "_send_payload", send)
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await wechat_agent_io._send_one(delivery, binding)
    else:
        await wechat_agent_io._send_one(delivery, binding)
    await delivery.refresh_from_db()
    assert delivery.status == expected
    if failure == "business_error":
        assert delivery.error == "wechat_agent_media_unsupported"


@pytest.mark.asyncio
async def test_normalize_transcribed_voice_keeps_caption_once_without_download(
    io_db, monkeypatch
):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "Context"}},
                {"type": 3, "voice_item": {"text": "Transcript", "media": {}}},
            ]
        ),
    )
    from app.services import wechat_agent_io

    client = SimpleNamespace(download_media=AsyncMock(side_effect=AssertionError))
    monkeypatch.setattr(wechat_agent_io, "_transcribe_voice", AsyncMock())

    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, client
    )

    assert request.message == "Transcript\n\nContext"
    client.download_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_asset_resolution_skips_unauthorized_generated_artifact(
    io_db, monkeypatch
):
    user, _, agent, binding, conversation, _ = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.models.asset import AssetScopeRef, AssetScopeType
    from app.services import channel_artifacts, wechat_agent_io

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    round_id = uuid4()
    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content="answer",
        round_id=round_id,
        is_round_canonical=True,
    )
    run.canonical_message_id = canonical.id
    await run.save(update_fields=["canonical_message_id"])
    asset = await _asset_for(agent.team, user)
    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref="dead",
    )
    await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="tool",
        content=json.dumps(
            {
                "kind": "media.image",
                "success": True,
                "images": [{"image": {"asset_ref": "dead"}}],
            }
        ),
        round_id=round_id,
        round_role="tool_result",
    )
    monkeypatch.setattr(
        wechat_agent_io.asset_service,
        "resolve_ref",
        AsyncMock(side_effect=BusinessError(msg_key="asset_unavailable")),
    )

    assert await channel_artifacts.resolve_run_assets(run, agent, user) == []


@pytest.mark.asyncio
async def test_send_one_marks_missing_receipt_unavailable(io_db, monkeypatch):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(
        binding, user, agent, receipt_message([]), status="completed"
    )
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="orphaned",
        sequence=0,
        payload={"kind": "text", "text": "must not send"},
        status="sending",
    )
    missing = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(
        wechat_agent_io.WeChatAgentReceipt, "filter", lambda **_kwargs: missing
    )

    await wechat_agent_io._send_one(delivery, binding)

    await delivery.refresh_from_db()
    assert delivery.status == "unavailable"
    assert delivery.error == "wechat_agent_binding_disconnected"


@pytest.mark.asyncio
async def test_remote_asset_storage_uses_upload_gateway(monkeypatch):
    from app.services import document_processor, upload_gateway, wechat_agent_io

    calls = []

    class Gateway:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def put(self, path, *, params, content):
            calls.append((path, params, content))
            return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(document_processor, "_remote_mode", lambda: True)
    monkeypatch.setattr(upload_gateway, "client", lambda: Gateway())

    await wechat_agent_io._store_upload(b"private", "agent-attachments/a", "text/plain")

    assert calls == [
        ("/internal/uploads/save", {"key": "agent-attachments/a"}, b"private")
    ]


@pytest.mark.asyncio
async def test_remote_asset_read_uses_upload_gateway(monkeypatch):
    from app.services import channel_artifacts, document_processor, upload_gateway

    read = AsyncMock(return_value=b"private bytes")
    monkeypatch.setattr(document_processor, "_remote_mode", lambda: True)
    monkeypatch.setattr(upload_gateway, "read", read)

    result = await channel_artifacts.read_asset_bytes(
        SimpleNamespace(storage_key="agent-attachments/a")
    )

    assert result == b"private bytes"
    read.assert_awaited_once_with("agent-attachments/a")


@pytest.mark.asyncio
async def test_run_asset_resolution_deduplicates_refs_to_the_same_asset(
    io_db, monkeypatch
):
    user, _, agent, _, conversation, _ = io_db
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.services import wechat_agent_io

    run = await AgentRun.create(
        id=uuid4(),
        agent=agent,
        conversation=conversation,
        user=user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content="answer",
        round_id=uuid4(),
        is_round_canonical=True,
    )
    run.canonical_message_id = canonical.id
    await run.save(update_fields=["canonical_message_id"])
    asset = await _asset_for(agent.team, user)
    round_id = canonical.round_id
    for ref in ("image-ref", "artifact-ref"):
        display = (
            {
                "kind": "media.image",
                "success": True,
                "images": [{"image": {"asset_ref": ref}}],
            }
            if ref == "image-ref"
            else {"success": True, "artifacts": [{"asset_ref": ref}]}
        )
        await Message.create(
            id=uuid4(),
            conversation=conversation,
            role="tool",
            content=json.dumps(display),
            round_id=round_id,
            round_role="tool_result",
        )
    resolve_ref = AsyncMock(return_value=asset)
    monkeypatch.setattr(wechat_agent_io.asset_service, "resolve_ref", resolve_ref)

    from app.services import channel_artifacts

    resolved = await channel_artifacts.resolve_run_assets(run, agent, user)

    assert [entry.id for entry in resolved] == [asset.id]
    assert resolve_ref.await_count == 2


@pytest.mark.asyncio
async def test_build_output_keeps_text_when_agent_row_is_missing(io_db, monkeypatch):
    user, _, _, _, conversation, _ = io_db
    from app.services import wechat_agent_io

    canonical = await Message.create(
        id=uuid4(),
        conversation=conversation,
        role="assistant",
        content="Still deliver this answer",
        is_round_canonical=True,
    )
    query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(wechat_agent_io.Agent, "filter", lambda **_kwargs: query)

    payloads = await wechat_agent_io.build_output(
        SimpleNamespace(
            canonical_message_id=canonical.id,
            agent_id=uuid4(),
            conversation_id=conversation.id,
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        user,
    )

    assert payloads == [{"kind": "text", "text": "Still deliver this answer"}]


@pytest.mark.asyncio
async def test_voice_caption_is_not_repeated_after_transcription(io_db, monkeypatch):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "Meeting notes"}},
                {"type": 3, "voice_item": {"media": {}}},
                {"type": 3, "voice_item": {"media": {}}},
            ]
        ),
    )
    from app.services import wechat_agent_io

    client = SimpleNamespace(
        download_media=AsyncMock(
            side_effect=[
                (b"voice-one", "voice-one.silk", "audio/silk"),
                (b"voice-two", "voice-two.silk", "audio/silk"),
            ]
        )
    )
    monkeypatch.setattr(wechat_agent_io, "_store_upload", AsyncMock())
    monkeypatch.setattr(
        wechat_agent_io,
        "_transcribe_voice",
        AsyncMock(side_effect=["First transcript", "Second transcript"]),
    )

    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, client
    )

    assert request.message == "First transcript\n\nMeeting notes\n\nSecond transcript"


@pytest.mark.asyncio
async def test_normalize_input_rejects_media_when_attachments_disabled(io_db):
    user, _, agent, binding, _, session = io_db
    agent.enable_attachments = False
    await agent.save(update_fields=["enable_attachments"])
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 9, "location_item": {"text": "here"}}]),
    )

    with pytest.raises(BusinessError) as denied:
        await __import__(
            "app.services.wechat_agent_io", fromlist=["normalize_input"]
        ).normalize_input(receipt, session, agent, user, None)

    assert denied.value.msg_key == "wechat_agent_attachments_disabled"


@pytest.mark.asyncio
async def test_missing_video_model_is_distinguished_from_nonvision_model(
    io_db, monkeypatch
):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 5, "video_item": {"media": {}}}]),
    )
    from app.services import wechat_agent_io

    monkeypatch.setattr(
        wechat_agent_io, "_agent_vision_model_id", AsyncMock(return_value=None)
    )
    client = SimpleNamespace(
        download_media=AsyncMock(return_value=(b"video", "clip.mp4", "video/mp4"))
    )

    with pytest.raises(BusinessError) as unsupported:
        await wechat_agent_io.normalize_input(receipt, session, agent, user, client)

    assert unsupported.value.msg_key == "wechat_agent_video_unsupported"
    client.download_media.assert_awaited_once_with(
        {"type": 5, "video_item": {"media": {}}}, 10 * 1024 * 1024
    )


@pytest.mark.asyncio
async def test_text_only_receipt_ignores_unused_model_and_preserves_all_text(io_db):
    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message(
            [
                {"type": 1, "text_item": {"text": "First"}},
                {"type": 1, "text_item": {"text": "Second"}},
            ]
        ),
    )
    from app.services import wechat_agent_io

    request = await wechat_agent_io.normalize_input(
        receipt, session, agent, user, SimpleNamespace()
    )

    assert request.message == "First\n\nSecond"
    assert request.images == [] and request.file_urls == []


@pytest.mark.asyncio
async def test_invalid_saved_delivery_context_agent_is_unavailable(io_db):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    agent.status = AgentStatus.DRAFT
    await agent.save(update_fields=["status"])

    context, reason = await wechat_agent_io._delivery_context(
        binding, None, receipt, user
    )

    assert context is None
    assert reason == "agent_access_denied"


@pytest.mark.asyncio
async def test_delivery_without_active_agent_session_stays_unavailable(io_db):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    await session.delete()

    context, reason = await wechat_agent_io._delivery_context(
        binding, None, receipt, user
    )

    assert context is None
    assert reason == "wechat_agent_conversation_missing"


@pytest.mark.asyncio
async def test_normalize_input_rejects_noncommand_media_payloads(io_db):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        {"item_list": [{"type": 99, "location_item": {"text": "not a command"}}]},
    )
    with pytest.raises(BusinessError) as unsupported:
        await wechat_agent_io.normalize_input(receipt, session, agent, user, None)
    assert unsupported.value.msg_key == "wechat_agent_media_unsupported"


@pytest.mark.asyncio
async def test_normalize_input_maps_failed_media_download_to_io_boundary(io_db):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, session = io_db
    receipt = await make_receipt(
        binding,
        user,
        agent,
        receipt_message([{"type": 4, "file_item": {"file_name": "notes.txt"}}]),
    )
    client = SimpleNamespace(
        download_media=AsyncMock(side_effect=WeChatAPIError("media_missing"))
    )

    with pytest.raises(WeChatAPIError) as unavailable:
        await wechat_agent_io.normalize_input(receipt, session, agent, user, client)
    assert unavailable.value.code == "media_missing"
    client.download_media.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_one_requeues_delivery_when_feature_revoked_during_send(
    io_db, monkeypatch
):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="feature-revoked-during-send",
        sequence=0,
        payload={"kind": "text", "text": "answer"},
        status="sending",
    )
    monkeypatch.setattr(
        wechat_agent_io,
        "_send_payload",
        AsyncMock(
            side_effect=BusinessError(code=400, msg_key="integration_feature_disabled")
        ),
    )
    monkeypatch.setattr(
        wechat_agent_io, "enabled_features", AsyncMock(return_value={"agent_chat"})
    )
    monkeypatch.setattr(
        wechat_agent_io,
        "_delivery_context",
        AsyncMock(return_value=({"binding": binding}, "")),
    )

    await wechat_agent_io._send_one(delivery, binding)

    await delivery.refresh_from_db()
    assert delivery.status == "pending"


@pytest.mark.asyncio
async def test_register_inbound_media_rejects_non_media_item(io_db):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    with pytest.raises(BusinessError) as unsupported:
        await wechat_agent_io._register_inbound_media(
            {"type": 3},
            agent=agent,
            user=user,
            receipt=receipt,
            index=0,
            raw=(b"voice", "voice.silk", "audio/silk"),
        )
    assert unsupported.value.msg_key == "wechat_agent_media_unsupported"


@pytest.mark.asyncio
async def test_delivery_context_uses_session_when_receipt_run_is_missing(
    io_db, monkeypatch
):
    from app.services import wechat_agent_io

    user, _, agent, binding, conversation, session = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    receipt_context = SimpleNamespace(
        binding_id=binding.id,
        user_id=user.id,
        agent_id=agent.id,
        run_id=uuid4(),
        created_at=receipt.created_at,
    )
    monkeypatch.setattr(wechat_agent_io, "_run_row", AsyncMock(return_value=None))

    context, reason = await wechat_agent_io._delivery_context(
        binding, None, receipt_context, user
    )

    assert reason == ""
    assert context["conversation_id"] == conversation.id
    assert context["session"].id == session.id


@pytest.mark.asyncio
async def test_delivery_retries_when_feature_is_disabled_mid_send(io_db, monkeypatch):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="feature-retry",
        sequence=0,
        payload={"kind": "text", "text": "answer"},
        status="sending",
    )
    monkeypatch.setattr(
        wechat_agent_io,
        "enabled_features",
        AsyncMock(return_value={"knowledge_collection"}),
    )

    await wechat_agent_io._send_one(delivery, binding)

    await delivery.refresh_from_db()
    assert delivery.status == "pending"


@pytest.mark.asyncio
async def test_delivery_feature_revocation_after_claim_keeps_pending_for_retry(
    io_db, monkeypatch
):
    from app.services import wechat_agent_io

    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    delivery = await IntegrationDelivery.create(
        id=uuid4(),
        **wechat_delivery_fields(receipt),
        event_key="revoked-feature",
        sequence=0,
        payload={"kind": "text", "text": "answer"},
    )
    monkeypatch.setattr(
        wechat_agent_io,
        "enabled_features",
        AsyncMock(side_effect=[{"agent_chat"}, set()]),
    )
    await wechat_agent_io.deliver_pending(binding, user)

    await delivery.refresh_from_db()
    assert delivery.status == "pending"
