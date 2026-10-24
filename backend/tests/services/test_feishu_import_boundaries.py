from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services import feishu_knowledge as service


class Query:
    def __init__(self, value=None, exists=False):
        self.value = value
        self.exists_value = exists

    def __await__(self):
        async def result():
            return self.value

        return result().__await__()

    def first(self):
        return self

    def using_db(self, _connection):
        return self

    def select_for_update(self):
        return self

    async def get(self):
        return self.value

    def exclude(self, **_kwargs):
        return self

    async def exists(self):
        return self.exists_value


@asynccontextmanager
async def transaction():
    yield object()


@pytest.fixture
def import_setup(monkeypatch):
    kb_id = uuid4()
    kb = SimpleNamespace(id=kb_id, team_id=uuid4())
    source = SimpleNamespace(id=uuid4(), knowledge_base_id=kb_id, name="Source")
    mapping = SimpleNamespace(
        id=uuid4(),
        obj_token="obj",
        obj_type="docx",
        document_id=None,
        content_hash=None,
        staging_document_id=None,
        pending_file_path=None,
        obsolete_file_path=None,
        cleanup_chunk_ids=[],
        node_token=None,
        last_error=None,
        save=AsyncMock(),
        refresh_from_db=AsyncMock(),
    )
    stage = SimpleNamespace(
        id=uuid4(),
        status="completed",
        chunk_count=1,
        metadata={"feishu_staging": True},
        save=AsyncMock(),
        refresh_from_db=AsyncMock(),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(service.KnowledgeBase, "get", AsyncMock(return_value=kb))
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(service, "_cleanup_pending", AsyncMock())
    monkeypatch.setattr(
        service.document_processor, "get_document_type", Mock(return_value="md")
    )
    monkeypatch.setattr(
        service.document_processor, "get_storage_path", Mock(return_value="stage.md")
    )
    monkeypatch.setattr(service, "_save_import_file", AsyncMock())
    monkeypatch.setattr(service, "in_transaction", lambda: transaction())
    monkeypatch.setattr(service.Document, "create", AsyncMock(return_value=stage))
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(None)))
    monkeypatch.setattr(service.DocumentChunk, "filter", Mock(return_value=Query(None)))
    monkeypatch.setattr(service, "_promote_media", AsyncMock())
    monkeypatch.setattr(service, "index_document", AsyncMock())
    monkeypatch.setattr(service, "_recount_kb", AsyncMock())
    monkeypatch.setattr(service, "delete_lexical_document", AsyncMock())
    monkeypatch.setattr(service, "_delete_projection", AsyncMock())
    monkeypatch.setattr(service, "_delete_import_file", AsyncMock())
    import app.tasks.knowledge_base as knowledge_base

    monkeypatch.setattr(
        knowledge_base,
        "_process_document",
        AsyncMock(return_value={"status": "success"}),
    )
    return source, mapping, kb, stage


@pytest.mark.asyncio
async def test_import_stages_and_promotes_only_after_index_success(import_setup):
    source, mapping, _kb, stage = import_setup
    changed = await service.import_content(
        source,
        mapping,
        {"node_token": "node/a", "title": "Imported"},
        service.FeishuContent("source.md", b"body"),
    )
    assert changed is True
    assert mapping.document_id == stage.id
    assert mapping.node_token == "node/a"
    assert mapping.content_hash
    assert mapping.pending_file_path is None
    assert stage.metadata == {}
    service.index_document.assert_awaited_once_with(stage.id)
    service._recount_kb.assert_awaited_once_with(source.knowledge_base_id)
    assert service._cleanup_pending.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["pipeline", "incomplete"])
async def test_failed_staging_rolls_back_and_cleans_pending_projection(
    import_setup, monkeypatch, failure
):
    source, mapping, _kb, stage = import_setup
    import app.tasks.knowledge_base as knowledge_base

    if failure == "pipeline":
        knowledge_base._process_document.side_effect = RuntimeError("processing failed")
    else:
        stage.chunk_count = 0
    with pytest.raises((RuntimeError, service._ImportIndexingError)):
        await service.import_content(
            source,
            mapping,
            {"node_token": "node", "title": "Imported"},
            service.FeishuContent("source.md", b"body"),
        )
    mapping.refresh_from_db.assert_awaited_once()
    assert service._cleanup_pending.await_count == 2
    service.index_document.assert_not_awaited()
    service._recount_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_hash_short_circuits_staging(import_setup, monkeypatch):
    import hashlib

    source, mapping, _kb, _stage = import_setup
    content = service.FeishuContent("source.md", b"unchanged")
    original = SimpleNamespace(
        id=uuid4(),
        status="completed",
        name="Old",
        metadata={"keep": True},
        save=AsyncMock(),
    )
    mapping.document_id = original.id
    mapping.content_hash = hashlib.sha256(content.content).hexdigest()
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(original)))
    changed = await service.import_content(
        source, mapping, {"node_token": "node/a", "title": "Renamed"}, content
    )
    assert changed is False
    assert original.name == "Renamed"
    assert original.metadata["keep"] is True
    assert mapping.node_token == "node/a"
    service._save_import_file.assert_not_awaited()
    service.Document.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["pipeline_status", "document_status", "unembedded_chunk"]
)
async def test_partial_index_never_promotes_import(import_setup, monkeypatch, failure):
    source, mapping, _, stage = import_setup
    from app.tasks import knowledge_base

    if failure == "pipeline_status":
        knowledge_base._process_document.return_value = {"status": "error"}
    elif failure == "document_status":
        stage.status = "error"
    else:
        monkeypatch.setattr(
            service.DocumentChunk, "filter", Mock(return_value=Query(exists=True))
        )
    with pytest.raises(service._ImportIndexingError):
        await service.import_content(
            source,
            mapping,
            {"node_token": "node", "title": "Partial"},
            service.FeishuContent("source.md", b"body"),
        )
    assert mapping.document_id is None
    service.index_document.assert_not_awaited()
    service._promote_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_import_leaves_existing_document_unchanged(
    import_setup, monkeypatch
):
    source, mapping, _, _ = import_setup
    identifier = uuid4()
    mapping.document_id = identifier
    mapping.content_hash = "old"
    monkeypatch.setattr(
        service.document_processor, "get_document_type", Mock(return_value=None)
    )
    with pytest.raises(service.UnsupportedContentError):
        await service.import_content(
            source,
            mapping,
            {"node_token": "node"},
            service.FeishuContent("file.unknown", b"bytes"),
        )
    assert mapping.document_id == identifier and mapping.content_hash == "old"
    service._save_import_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_promotes_new_chunks_under_existing_document_identity(
    import_setup, monkeypatch
):
    source, mapping, kb, stage = import_setup
    original = SimpleNamespace(id=uuid4(), file_path="old.md", save=AsyncMock())
    mapping.document_id = original.id
    mapping.content_hash = "old-content"
    for field, value in dict(
        name="Fresh",
        doc_type="markdown",
        file_path="fresh.md",
        file_size=4,
        error_message=None,
        token_count=2,
        processed_at=None,
    ).items():
        setattr(stage, field, value)

    class Chunks(Query):
        def __init__(self):
            super().__init__(exists=False)
            self.delete = AsyncMock()
            self.update = AsyncMock()

        async def values_list(self, *args, **kwargs):
            return [old_chunk]

    old_chunk = uuid4()
    chunks = Chunks()
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(original)))
    monkeypatch.setattr(service.DocumentChunk, "filter", Mock(return_value=chunks))
    assert await service.import_content(
        source,
        mapping,
        {"node_token": "node", "title": "Fresh"},
        service.FeishuContent("source.md", b"fresh"),
    )
    assert mapping.document_id == original.id
    assert mapping.obsolete_file_path == "old.md"
    assert mapping.cleanup_chunk_ids == [str(old_chunk)]
    assert original.file_path == "fresh.md" and original.name == "Fresh"
    chunks.update.assert_awaited_once_with(document_id=original.id)
    stage.delete.assert_awaited_once()
    service.index_document.assert_awaited_once_with(original.id)
