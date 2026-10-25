"""Ingestion branch boundaries for the WeChat knowledge collection pipeline.

Every case here drives a real production function against an isolated in-memory
ORM; only genuine IO boundaries (upstream media download, storage backend,
internal upload gateway, outbound reply client, indexing task, audit sink) are
replaced. The assertions describe consumer-visible behavior: what is persisted,
what is sent back to the phone, and which errors abort versus retry.
"""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.core.i18n import t
from app.integrations.credentials import encrypt_secret
from app.models.knowledge_base import Document, KnowledgeBase
from app.models.user import Team, User
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeContent,
    WeChatKnowledgeItem,
    WeChatKnowledgeReceipt,
)
from app.services import wechat_ingestion as ingestion
from app.services.wechat_connection import utcnow
from app.services.wechat_ingestion import save_content as real_save_content
from app.schemas.response import BusinessError

MESSAGE = {
    "message_id": "18446744073709551615",
    "from_user_id": "wechat-user",
    "message_type": 1,
    "message_state": 2,
    "item_list": [{"type": 1, "text_item": {"text": "Original knowledge note"}}],
}


class NoStorage:
    """Capture durable content writes instead of touching real storage."""

    def __init__(self):
        self.writes = []

    async def __call__(self, path, content):
        self.writes.append((path, bytes(content)))


class ReplyClient:
    """Records outbound WeChat replies; never opens a socket."""

    def __init__(self, *args):
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send_text(self, recipient, text, token):
        self.sent.append((recipient, text, token))


class StopHeartbeat(Exception):
    """Sentinel that ends the otherwise infinite heartbeat loop after one pass."""


@pytest_asyncio.fixture
async def ingestion_db(monkeypatch):
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
        team = await Team.create(id=uuid4(), name="Collection team")
        kb = await KnowledgeBase.create(
            id=uuid4(), name="Target", team=team, created_by=user
        )
        binding = await WeChatKnowledgeBinding.create(
            user=user,
            wechat_user_id="wechat-user",
            bot_id="bot",
            token=encrypt_secret("not-real"),
            base_url="https://ilinkai.weixin.qq.com",
            purpose="knowledge_collection",
        )
        storage = NoStorage()
        monkeypatch.setattr(ingestion, "save_content", storage)
        yield SimpleNamespace(
            user=user, team=team, kb=kb, binding=binding, storage=storage
        )


async def make_receipt(world, message_id, *, context_token=None, **fields):
    payload = (
        MESSAGE if context_token is None else dict(MESSAGE, context_token=context_token)
    )
    return await WeChatKnowledgeReceipt.create(
        binding=world.binding,
        user=world.user,
        knowledge_base=world.kb,
        message_id=message_id,
        payload=encrypt_secret(json.dumps(payload)),
        **fields,
    )


def index_document(status="completed", chunk_count=1):
    """Stand-in for the Celery indexing task, which is outside this process."""

    async def _index(document_id, _):
        await Document.filter(id=document_id).update(
            status=status, chunk_count=chunk_count
        )

    return _index


@pytest.mark.asyncio
async def test_local_storage_write_handles_content_and_path(ingestion_db, monkeypatch):
    processor = ingestion.document_processor
    saved = AsyncMock(return_value=11)
    monkeypatch.setattr(processor, "_remote_mode", lambda: False)
    monkeypatch.setattr(processor, "save_file", saved)
    await real_save_content("documents/kb/item/original/a.txt", b"payload")
    saved.assert_awaited_once_with(b"payload", "documents/kb/item/original/a.txt")


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway_status", [200, 503])
async def test_remote_storage_routes_through_upload_gateway(
    ingestion_db, monkeypatch, gateway_status
):
    processor = ingestion.document_processor
    from app.services import upload_gateway

    path = "documents/kb/item/original/a.txt"
    calls = []

    class Gateway:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def put(self, url, params=None, content=None):
            calls.append((url, params, content))
            return httpx.Response(
                gateway_status, request=httpx.Request("PUT", "https://api.internal")
            )

    monkeypatch.setattr(ingestion, "save_content", real_save_content)
    monkeypatch.setattr(processor, "_remote_mode", lambda: True)
    monkeypatch.setattr(upload_gateway, "client", lambda: Gateway())
    if gateway_status == 200:
        await real_save_content(path, b"payload")
        assert calls == [("/internal/uploads/save", {"key": path}, b"payload")]
    else:
        # A rejected gateway write must surface as retryable transport failure.
        with pytest.raises(httpx.HTTPStatusError):
            await real_save_content(path, b"payload")
        assert calls == [("/internal/uploads/save", {"key": path}, b"payload")]


@pytest.mark.asyncio
async def test_media_with_unknown_document_type_is_rejected(ingestion_db, monkeypatch):
    from app.api.v1.endpoints import knowledge_bases

    world = ingestion_db
    receipt = await make_receipt(world, "unknown-media")
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    monkeypatch.setattr(
        knowledge_bases,
        "get_kb_document_max_upload_size_mb",
        AsyncMock(return_value=10),
    )
    extract = AsyncMock(side_effect=AssertionError("unroutable bytes reached a parser"))
    monkeypatch.setattr(ingestion, "extract_media", extract)
    client = SimpleNamespace(
        download_media=AsyncMock(
            return_value=(b"\x01\x02", "payload.bin", "application/octet-stream")
        )
    )
    with pytest.raises(BusinessError) as rejected:
        await ingestion.text_for_input(
            {"kind": "media", "item": {"type": 4}, "caption": "Snapshot"},
            receipt,
            world.kb,
            client,
            item,
        )
    assert rejected.value.msg_key == "wechat_type_unsupported"
    extract.assert_not_awaited()
    await item.refresh_from_db()
    assert item.document_id is None


@pytest.mark.asyncio
async def test_blank_content_is_rejected_before_any_persistence(ingestion_db):
    world = ingestion_db
    receipt = await make_receipt(world, "blank")
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    with pytest.raises(BusinessError) as blank:
        await ingestion.claim_document(receipt, item, world.kb, "  \n\n ", "Blank", {})
    assert blank.value.msg_key == "wechat_empty_content"
    assert world.storage.writes == []
    assert await Document.filter(knowledge_base=world.kb).count() == 0
    assert await WeChatKnowledgeContent.filter(knowledge_base=world.kb).count() == 0
    await item.refresh_from_db()
    assert item.document_id is None and item.status == "pending"


@pytest.mark.asyncio
async def test_source_fields_separate_url_original_and_markdown_identity(
    ingestion_db, monkeypatch
):
    world = ingestion_db
    content_path = f"documents/{world.kb.id}/wechat/item/content.md"

    url_fields = await ingestion.document_source_fields(
        "Article title", {"source_url": "https://example.com/article"}, content_path
    )
    assert url_fields == {
        "name": "Article title",
        "doc_type": "url",
        "file_path": None,
        "file_size": None,
    }

    original_fields = await ingestion.document_source_fields(
        "Extracted text",
        {
            "wechat_original_path": "documents/kb/item/original/report.pdf",
            "wechat_original_name": "report.pdf",
            "wechat_original_mime": "application/pdf",
            "wechat_original_size": 42,
        },
        content_path,
    )
    assert original_fields == {
        "name": "report.pdf",
        "doc_type": "pdf",
        "file_path": "documents/kb/item/original/report.pdf",
        "file_size": 42,
    }

    read = AsyncMock(return_value=b"1234567")
    monkeypatch.setattr(ingestion.document_processor, "read_file", read)
    unknown_fields = await ingestion.document_source_fields(
        "Clip",
        {
            "wechat_original_path": "documents/kb/item/original/clip.bin",
            "wechat_original_name": "clip.bin",
            "wechat_original_mime": "application/octet-stream",
            "wechat_original_size": None,
        },
        content_path,
    )
    # An unclassifiable original must not be re-read; the Markdown copy is the
    # canonical stored representation instead.
    assert unknown_fields == {
        "name": "Clip.md",
        "doc_type": "markdown",
        "file_path": content_path,
    }
    read.assert_not_awaited()

    sized = await ingestion.document_source_fields(
        "Extracted text",
        {
            "wechat_original_path": "documents/kb/item/original/note.txt",
            "wechat_original_name": "note.txt",
            "wechat_original_mime": "text/plain",
        },
        content_path,
    )
    assert sized["file_size"] == 7
    assert sized["name"] == "note.txt" and sized["doc_type"] == "txt"
    read.assert_awaited_once_with("documents/kb/item/original/note.txt")

    markdown_named = await ingestion.document_source_fields(
        "Digest.md", {}, content_path
    )
    plain_named = await ingestion.document_source_fields("Digest", {}, content_path)
    assert markdown_named["name"] == "Digest.md"
    assert plain_named["name"] == "Digest.md"


@pytest.mark.asyncio
async def test_item_with_claim_resumes_without_reprocessing_input(
    ingestion_db, monkeypatch
):
    from app.tasks import knowledge_base as tasks

    world = ingestion_db
    receipt = await make_receipt(world, "resume")
    document = await Document.create(
        id=uuid4(),
        knowledge_base=world.kb,
        name="Half indexed",
        doc_type="txt",
        status="pending",
        uploaded_by=world.user,
    )
    item = await WeChatKnowledgeItem.create(
        receipt=receipt, item_index=0, document=document
    )
    monkeypatch.setattr(tasks, "_process_document", index_document(chunk_count=3))
    # An unsupported spec proves the retry reads the persisted claim, not input.
    resumed = await ingestion.process_item(receipt, 0, {"kind": "unsupported"})
    assert resumed.id == item.id
    assert resumed.document_id == document.id
    assert resumed.status == "completed"
    await document.refresh_from_db()
    assert document.chunk_count == 3 and document.status == "completed"
    assert await Document.filter(knowledge_base=world.kb).count() == 1


@pytest.mark.asyncio
async def test_text_that_cleans_to_nothing_is_not_indexed(ingestion_db):
    world = ingestion_db
    receipt = await make_receipt(world, "blank-after-clean")
    with pytest.raises(BusinessError) as blank:
        await ingestion.process_item(receipt, 0, {"kind": "text", "text": "\x00\x00"})
    assert blank.value.msg_key == "wechat_empty_content"
    assert world.storage.writes == []
    assert await Document.filter(knowledge_base=world.kb).count() == 0


@pytest.mark.asyncio
async def test_duplicate_claim_drops_temporary_content_and_keeps_one_document(
    ingestion_db, monkeypatch
):
    from app.tasks import knowledge_base as tasks

    world = ingestion_db
    first_receipt = await make_receipt(world, "duplicate-first")
    second_receipt = await make_receipt(world, "duplicate-second")
    monkeypatch.setattr(tasks, "_process_document", index_document())
    deleted = AsyncMock(return_value=True)
    monkeypatch.setattr(ingestion.document_processor, "delete_file", deleted)

    first = await ingestion.process_item(
        first_receipt, 0, {"kind": "text", "text": "Shared contract text"}
    )
    assert first.status == "completed"
    assert deleted.await_count == 0

    second = await ingestion.process_item(
        second_receipt, 0, {"kind": "text", "text": "Shared contract text"}
    )
    assert second.status == "duplicate"
    assert second.document_id == first.document_id
    assert second.content_hash == first.content_hash
    # The scratch Markdown copy is removed for a duplicate; the durable original
    # document and its single index entry are untouched.
    assert deleted.await_args_list[0].args == (
        f"documents/{world.kb.id}/wechat/{second.id}/content.md",
    )
    assert await Document.filter(knowledge_base=world.kb).count() == 1
    await world.kb.refresh_from_db()
    assert world.kb.document_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_matches", [True, False])
async def test_heartbeat_only_extends_the_leases_it_still_owns(
    ingestion_db, monkeypatch, owner_matches
):
    world = ingestion_db
    receipt = await make_receipt(
        world,
        f"heartbeat-{owner_matches}",
        lease_owner=uuid4(),
        lease_expires_at=utcnow() - timedelta(minutes=1),
    )
    item = await WeChatKnowledgeItem.create(receipt=receipt, item_index=0)
    claim = await WeChatKnowledgeContent.create(
        knowledge_base=world.kb,
        content_hash="a" * 64,
        owner_item_id=item.id,
        lease_expires_at=utcnow() - timedelta(minutes=1),
    )

    sleeps = []

    async def paced_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > 1:
            raise StopHeartbeat

    monkeypatch.setattr(
        ingestion,
        "asyncio",
        SimpleNamespace(
            sleep=paced_sleep,
            create_task=asyncio.create_task,
            gather=asyncio.gather,
        ),
    )
    if owner_matches:
        with pytest.raises(StopHeartbeat):
            await ingestion.heartbeat(receipt.id, receipt.lease_owner)
        await receipt.refresh_from_db()
        await claim.refresh_from_db()
        assert sleeps == [30, 30]
        assert receipt.lease_expires_at > utcnow()
        assert claim.lease_expires_at > utcnow()
    else:
        # A stolen or released receipt must stop the old worker's heartbeat
        # instead of extending a lease it no longer holds.
        with pytest.raises(ingestion.CollectionBusy):
            await ingestion.heartbeat(receipt.id, uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("target_lost", ["target_unavailable", "binding_gone"])
async def test_reply_hides_titles_when_the_target_is_no_longer_writable(
    ingestion_db, monkeypatch, target_lost
):
    world = ingestion_db
    receipt = await make_receipt(
        world,
        f"reply-{target_lost}",
        context_token="context",
        results=[{"index": 0, "status": "completed", "name": "Saved note"}],
    )
    if target_lost == "target_unavailable":
        await KnowledgeBase.filter(id=world.kb.id).update(status="archived")
    else:
        await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
            status="disconnected"
        )
    client = ReplyClient()
    monkeypatch.setattr(ingestion, "WeChatClient", lambda *args: client)

    await ingestion.reply_result(receipt, {"context_token": "context"})
    await receipt.refresh_from_db()
    if target_lost == "target_unavailable":
        assert receipt.reply_status == "submitted"
        assert len(client.sent) == 1
        recipient, text, token = client.sent[0]
        assert recipient == world.binding.wechat_user_id
        assert token == "context"
        assert text == t("wechat_target_unavailable")
        assert world.kb.name not in text
        assert "Saved note" not in text
    else:
        # Without a live connection there is no one to tell; nothing is sent and
        # the reply is left unclaimed rather than marked delivered.
        assert client.sent == []
        assert receipt.reply_status == "pending"


@pytest.mark.asyncio
async def test_committed_reply_is_not_resent_from_a_stale_receipt(
    ingestion_db, monkeypatch
):
    world = ingestion_db
    receipt = await make_receipt(
        world,
        "stale-reply",
        context_token="context",
        results=[{"index": 0, "status": "completed", "name": "Saved note"}],
    )
    client = ReplyClient()
    monkeypatch.setattr(ingestion, "WeChatClient", lambda *args: client)

    await ingestion.reply_result(receipt, {"context_token": "context"})
    assert len(client.sent) == 1
    # A worker holding a pre-send copy of the receipt must not re-transmit: the
    # conditional update finds no pending row and stops.
    await ingestion.reply_result(receipt, {"context_token": "context"})
    assert len(client.sent) == 1
    await receipt.refresh_from_db()
    assert receipt.reply_status == "submitted"


@pytest.mark.asyncio
async def test_receipt_lock_contention_reports_busy_without_claiming(
    ingestion_db,
):
    from app.services.wechat_locks import _SQLITE_LOCKS

    world = ingestion_db
    receipt = await make_receipt(world, "lock-contended")
    lock = _SQLITE_LOCKS.setdefault(f"receipt:{receipt.id}", asyncio.Lock())
    await lock.acquire()
    try:
        assert await ingestion.process_receipt(str(receipt.id)) == {"status": "busy"}
    finally:
        lock.release()
        _SQLITE_LOCKS.pop(f"receipt:{receipt.id}", None)
    await receipt.refresh_from_db()
    assert receipt.lease_owner is None and receipt.lease_expires_at is None
    assert receipt.results == []


@pytest.mark.asyncio
async def test_live_foreign_lease_blocks_reprocessing(ingestion_db):
    world = ingestion_db
    receipt = await make_receipt(world, "foreign-lease")
    rival = uuid4()
    await WeChatKnowledgeReceipt.filter(id=receipt.id).update(
        lease_owner=rival, lease_expires_at=utcnow() + timedelta(minutes=2)
    )
    assert await ingestion._process_receipt(str(receipt.id)) == {"status": "busy"}
    await receipt.refresh_from_db()
    assert receipt.lease_owner == rival
    assert receipt.results == []
    assert await WeChatKnowledgeItem.filter(receipt=receipt).count() == 0


@pytest.mark.asyncio
async def test_finished_receipt_replies_once_without_reprocessing_items(
    ingestion_db, monkeypatch
):
    world = ingestion_db
    receipt = await make_receipt(
        world,
        "finished",
        context_token="context",
        status="completed",
        results=[{"index": 0, "status": "completed", "name": "Saved note"}],
    )
    client = ReplyClient()
    monkeypatch.setattr(ingestion, "WeChatClient", lambda *args: client)
    assert await ingestion._process_receipt(str(receipt.id)) == {"status": "completed"}
    # A terminal receipt only re-delivers its recorded summary.
    assert await WeChatKnowledgeItem.filter(receipt=receipt).count() == 0
    assert len(client.sent) == 1
    _, text, _ = client.sent[0]
    assert world.kb.name in text and "Saved note" in text
    await receipt.refresh_from_db()
    assert receipt.reply_status == "submitted"
    assert receipt.lease_owner is None


@pytest.mark.asyncio
async def test_item_level_contention_leaves_the_receipt_recoverable(
    ingestion_db, monkeypatch
):
    world = ingestion_db
    receipt = await make_receipt(world, "item-busy")

    async def contended(current, index, spec):
        raise ingestion.CollectionBusy("another worker owns this content")

    monkeypatch.setattr(ingestion, "process_item", contended)
    assert await ingestion._process_receipt(str(receipt.id)) == {"status": "pending"}
    await receipt.refresh_from_db()
    # Not terminal: the receipt stays claimable for the retry that follows.
    assert receipt.status == "processing"
    assert receipt.results == []
    assert receipt.lease_owner is None and receipt.lease_expires_at is None


@pytest.mark.asyncio
async def test_lost_target_permission_marks_the_receipt_error_and_notifies(
    ingestion_db, monkeypatch
):
    from app.services.audit_log import AuditLogService

    world = ingestion_db
    receipt = await make_receipt(world, "target-lost", context_token="context")
    replies = []
    real_reply = ingestion.reply_result

    async def spy(current, payload):
        replies.append(payload)
        return await real_reply(current, payload)

    monkeypatch.setattr(ingestion, "reply_result", spy)
    monkeypatch.setattr(AuditLogService, "log", AsyncMock())
    client = ReplyClient()
    monkeypatch.setattr(ingestion, "WeChatClient", lambda *args: client)
    # Access to the target is revoked while the receipt is being processed.
    await KnowledgeBase.filter(id=world.kb.id).update(status="archived")

    assert await ingestion._process_receipt(str(receipt.id)) == {"status": "error"}
    await receipt.refresh_from_db()
    assert receipt.status == "error"
    assert receipt.last_error == "wechat_kb_inactive"
    assert receipt.results == []
    assert receipt.lease_owner is None and receipt.lease_expires_at is None
    assert len(replies) == 1
    assert len(client.sent) == 1
    assert client.sent[0][1] == t("wechat_target_unavailable")


@pytest.mark.asyncio
async def test_document_cleanup_deletes_only_bound_wechat_originals(
    ingestion_db, monkeypatch
):
    from app.services import wechat_cleanup

    world = ingestion_db
    receipt = await make_receipt(world, "cleanup")
    document = await Document.create(
        id=uuid4(),
        knowledge_base=world.kb,
        name="Collected article",
        doc_type="url",
        status="completed",
        metadata={"source": "wechat"},
    )
    valid_id = uuid4()
    valid = await WeChatKnowledgeItem.create(
        id=valid_id,
        receipt=receipt,
        item_index=0,
        document=document,
        original_path=(
            f"documents/{world.kb.id}/wechat/{valid_id}/original/article.html"
        ),
    )
    outside = await WeChatKnowledgeItem.create(
        receipt=receipt,
        item_index=1,
        document=document,
        original_path="documents/another-kb/wechat/foreign/original/article.html",
    )
    absent = await WeChatKnowledgeItem.create(
        receipt=receipt, item_index=2, document=document
    )
    delete_file = AsyncMock()
    monkeypatch.setattr(wechat_cleanup.document_processor, "delete_file", delete_file)

    await wechat_cleanup.delete_collection_originals(document)

    delete_file.assert_awaited_once_with(valid.original_path)
    for item in (valid, outside, absent):
        await item.refresh_from_db()
        assert item.original_path is None


@pytest.mark.asyncio
async def test_document_cleanup_ignores_non_wechat_document(ingestion_db, monkeypatch):
    from app.services import wechat_cleanup

    world = ingestion_db
    document = await Document.create(
        id=uuid4(),
        knowledge_base=world.kb,
        name="Uploaded file",
        doc_type="txt",
        metadata={"source": "upload"},
    )
    query = AsyncMock(side_effect=AssertionError("non-WeChat rows must not be queried"))
    monkeypatch.setattr(WeChatKnowledgeItem, "filter", query)

    await wechat_cleanup.delete_collection_originals(document)

    query.assert_not_called()
