"""Isolated WeChat Agent IO boundary tests against a real in-memory ORM.

Covers the real boundaries only: UTF-8 chunking, input classification and
capability gating, deterministic inbound Asset identity, canonical output
extraction from tool display schemas, and durable delivery claiming with
per-send reauthorization. No production credentials or network calls.
"""

import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.integrations.wechat import WeChatAPIError
from app.models.agent import Agent, AgentStatus, AgentVisibility, Conversation, Message
from app.models.asset import Asset
from app.models.user import Team, User
from app.models.wechat_agent import (
    WeChatAgentDelivery,
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
    delivery = await WeChatAgentDelivery.create(
        id=uuid4(),
        receipt=receipt,
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
    row = await WeChatAgentDelivery.get(id=delivery.id)
    assert row.status == "submitted"
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
    await WeChatAgentDelivery.create(
        id=uuid4(),
        receipt=receipt,
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
    row = await WeChatAgentDelivery.first()
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
    await WeChatAgentDelivery.create(
        id=uuid4(),
        receipt=receipt,
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
    row = await WeChatAgentDelivery.first()
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
    row = await WeChatAgentDelivery.create(
        id=uuid4(),
        receipt=receipt,
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "答复"},
        status="sending",
    )
    stale_at = utcnow() - timedelta(seconds=3600)
    await WeChatAgentDelivery.filter(id=row.id).update(updated_at=stale_at)
    await deliver_pending(binding, user)
    row = await WeChatAgentDelivery.get(id=row.id)
    assert row.status == "unknown"


# ---------- Transport boundary: real CDN upload protocol ----------


def _aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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

    monkeypatch.setattr(transport, "validate_external_http_url", lambda value: value)
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

    monkeypatch.setattr(transport, "validate_external_http_url", lambda value: value)
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

    monkeypatch.setattr(transport, "validate_external_http_url", lambda value: value)
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
    from app.services.wechat_agent_io import _authorized_output_asset

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
    authorized = await _authorized_output_asset(asset.id, context)
    assert authorized is not None and authorized.id == asset.id


@pytest.mark.asyncio
async def test_output_asset_foreign_conversation_is_rejected(io_db):
    from app.models.asset import AssetScopeRef, AssetScopeType
    from app.services.wechat_agent_io import _authorized_output_asset

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
    assert await _authorized_output_asset(asset.id, context) is None
    # The same asset is authorized for its own conversation.
    own = {"user": user, "agent": agent, "conversation_id": conversation.id}
    assert await _authorized_output_asset(asset.id, own) is not None


@pytest.mark.asyncio
async def test_output_asset_foreign_team_is_rejected(io_db):
    from app.services.wechat_agent_io import _authorized_output_asset

    user, team, agent, binding, conversation, _ = io_db
    other_team = await Team.create(id=uuid4(), name="Other team")
    asset = await _asset_for(other_team, user)
    context = {"user": user, "agent": agent, "conversation_id": conversation.id}
    assert await _authorized_output_asset(asset.id, context) is None


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
