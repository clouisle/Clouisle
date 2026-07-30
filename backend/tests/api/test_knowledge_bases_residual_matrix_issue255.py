from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.knowledge_base import SearchRequest
from app.schemas.response import BusinessError
from app.services.vector_store import DimensionMismatchError


class Query:
    def __init__(self, value=None):
        self.value = value

    def exclude(self, **_kwargs):
        return self

    def prefetch_related(self, *_args):
        return self

    def using_db(self, _connection):
        return self

    def select_for_update(self):
        return self

    async def get(self):
        return self.value

    async def first(self):
        return self.value


@pytest.fixture
def dispatch_transaction(monkeypatch):
    connection = object()

    class Transaction:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(knowledge_bases, "in_transaction", Transaction)
    return connection


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("invalid", knowledge_bases.KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (0, knowledge_bases.KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (10**9, knowledge_bases.KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
        (32, 32),
    ],
)
async def test_issue255_upload_limit_normalizes_configured_value(
    monkeypatch, configured, expected
):
    monkeypatch.setattr(
        knowledge_bases.SiteSetting,
        "get_value",
        AsyncMock(return_value=configured),
    )

    assert await knowledge_bases.get_kb_document_max_upload_size_mb() == expected


@pytest.mark.asyncio
async def test_issue255_dispatch_failure_removes_task_metadata(
    monkeypatch, dispatch_transaction
):
    doc = SimpleNamespace(
        id=uuid4(),
        status=knowledge_bases.DocumentStatus.PENDING.value,
        error_message=None,
        metadata={"kept": True},
        save=AsyncMock(),
    )
    task = SimpleNamespace(name="process", apply_async=Mock(side_effect=RuntimeError))
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )

    with pytest.raises(RuntimeError):
        await knowledge_bases._dispatch_document_task(
            doc,
            task,
            "document-id",
            status=knowledge_bases.DocumentStatus.PROCESSING.value,
        )

    assert doc.metadata == {"kept": True}
    assert doc.save.await_count == 2
    doc.save.assert_awaited_with(
        using_db=dispatch_transaction,
        update_fields=["metadata", "status", "error_message"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["missing_document", "missing_path", "unsafe_path", "missing_object"]
)
async def test_issue255_download_rejects_unavailable_files(monkeypatch, failure):
    doc = SimpleNamespace(
        file_path="uploads/kb/guide.bin", doc_type="bin", name="guide.bin"
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(None if failure == "missing_document" else doc),
    )

    if failure == "missing_path":
        doc.file_path = None
    elif failure == "unsafe_path":
        monkeypatch.setattr(
            knowledge_bases.document_processor,
            "_storage_key",
            Mock(side_effect=ValueError),
        )
    elif failure == "missing_object":
        monkeypatch.setattr(
            knowledge_bases.document_processor,
            "_storage_key",
            Mock(return_value="kb/guide.bin"),
        )
        monkeypatch.setattr(
            knowledge_bases.document_processor,
            "_storage_root",
            Mock(return_value="uploads"),
        )
        storage = SimpleNamespace(exists=AsyncMock(return_value=False))
        monkeypatch.setattr(
            knowledge_bases,
            "get_upload_storage_backend",
            AsyncMock(return_value=storage),
        )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.download_document(uuid4(), uuid4(), SimpleNamespace())

    assert exc.value.status_code == 404
    assert exc.value.msg_key in {"document_not_found", "file_not_found"}


@pytest.mark.asyncio
async def test_issue255_update_rejects_duplicate_name_and_embedding_change(monkeypatch):
    kb_id = uuid4()
    kb = SimpleNamespace(
        embedding_model_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace()),
    )
    update = SimpleNamespace(
        name="duplicate",
        description=None,
        icon=None,
        embedding_model_id=kb.embedding_model_id,
        rerank_model_id=None,
        settings=None,
        status=None,
        model_fields_set=set(),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.update_knowledge_base(
            kb_id=kb_id,
            kb_in=update,
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )
    assert exc.value.msg_key == "kb_name_exists"

    update.name = None
    update.embedding_model_id = uuid4()
    update.model_fields_set = {"embedding_model_id"}
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.update_knowledge_base(
            kb_id=kb_id,
            kb_in=update,
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )
    assert exc.value.msg_key == "embedding_model_locked_after_kb_creation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "msg_key"),
    [
        (DimensionMismatchError("wrong dimension"), "kb_embedding_dimension_mismatch"),
        (OSError("vector backend down"), "vector_search_failed"),
    ],
)
async def test_issue255_search_translates_vector_failures(monkeypatch, error, msg_key):
    kb = SimpleNamespace(
        id=uuid4(),
        name="kb",
        status="active",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        embedding_dimension=None,
        team_id=uuid4(),
    )
    retrieve = AsyncMock(side_effect=error)
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    search_in = SearchRequest(
        query="policy",
        search_mode="hybrid",
        top_k=5,
        score_threshold=0.2,
        rerank_enabled=True,
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.search_knowledge_base(
            uuid4(), search_in, SimpleNamespace()
        )

    assert exc.value.msg_key == msg_key
    assert retrieve.await_args.args[0].rerank_overrides == {"rerank_enabled": True}


@pytest.mark.asyncio
async def test_issue255_preview_rejects_document_without_source(monkeypatch):
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(file_path=None, source_url=None)),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.preview_document_chunks(
            kb_id=uuid4(),
            doc_id=uuid4(),
            preview_in=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )

    assert exc.value.msg_key == "document_no_source"
