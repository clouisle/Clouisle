from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import DocumentUpdate, KnowledgeBaseUpdate


@pytest.fixture(autouse=True)
def lexical_store_calls(monkeypatch):
    calls = SimpleNamespace(document=AsyncMock(), index=AsyncMock())
    monkeypatch.setattr(knowledge_bases, "delete_lexical_document", calls.document)
    monkeypatch.setattr(knowledge_bases, "index_lexical_chunk", calls.index)
    return calls


class Query:
    def __init__(self, items=(), total=None, first=None):
        self.items = list(items)
        self.total = len(self.items) if total is None else total
        self.first_value = first
        self.calls = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, **kwargs):
        return self._record("filter", **kwargs)

    def exclude(self, **kwargs):
        return self._record("exclude", **kwargs)

    def prefetch_related(self, *args):
        return self._record("prefetch_related", *args)

    def offset(self, value):
        return self._record("offset", value)

    def limit(self, value):
        return self._record("limit", value)

    def __await__(self):
        async def resolve():
            return self.first_value if self.first_value is not None else self.items

        return resolve().__await__()

    async def count(self):
        return self.total

    async def first(self):
        return self.first_value


def _user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def _request():
    return SimpleNamespace()


@pytest.mark.anyio
async def test_list_knowledge_bases_filters_and_hydrates_models():
    embedding_id, rerank_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=uuid4(), embedding_model_id=embedding_id, rerank_model_id=rerank_id
    )
    query = Query([kb], total=3)
    model_query = Query(
        [
            SimpleNamespace(
                id=embedding_id, name="embed", provider="local", model_id="e1"
            ),
            SimpleNamespace(
                id=rerank_id, name="rerank", provider="local", model_id="r1"
            ),
        ]
    )
    model_query.all = AsyncMock(return_value=model_query.items)
    memberships = AsyncMock(return_value=[uuid4()])
    kb_schema = MagicMock()
    kb_schema.model_validate.return_value.model_dump.return_value = {"id": kb.id}

    with (
        patch.object(knowledge_bases.KnowledgeBase, "all", return_value=query),
        patch.object(
            knowledge_bases.TeamMember,
            "filter",
            return_value=SimpleNamespace(values_list=memberships),
        ),
        patch.object(knowledge_bases.Model, "filter", return_value=model_query),
        patch.object(knowledge_bases, "KnowledgeBaseList", kb_schema),
        patch.object(knowledge_bases, "success", side_effect=lambda **kw: kw),
    ):
        result = await knowledge_bases.list_knowledge_bases(
            search="docs",
            status=["active"],
            own_only=True,
            page=2,
            page_size=5,
            current_user=_user(),
        )

    filters = [kwargs for name, _, kwargs in query.calls if name == "filter"]
    assert {"team_id__in": memberships.return_value} in filters
    assert any("created_by" in values for values in filters)
    assert {"name__icontains": "docs"} in filters
    assert {"status__in": ["active"]} in filters
    assert result["data"]["items"][0]["embedding_model"]["name"] == "embed"
    assert result["data"]["items"][0]["rerank_model"]["name"] == "rerank"
    assert ("offset", (5,), {}) in query.calls


@pytest.mark.anyio
async def test_knowledge_base_detail_update_and_delete_lifecycle(
    lexical_store_calls,
):
    kb_id = uuid4()
    team = SimpleNamespace(id=uuid4())
    kb = SimpleNamespace(
        id=kb_id,
        name="old",
        description="old description",
        icon="old",
        team=team,
        team_id=team.id,
        embedding_model_id=uuid4(),
        rerank_model_id=None,
        settings={},
        status="active",
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    reloaded = SimpleNamespace(id=kb_id, name="new")
    get_query = Query(first=reloaded)
    audit = AsyncMock()

    with (
        patch.object(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb)),
        patch.object(
            knowledge_bases, "kb_with_model_info", AsyncMock(return_value={"id": kb_id})
        ),
        patch.object(knowledge_bases.KnowledgeBase, "filter", return_value=Query()),
        patch.object(knowledge_bases.KnowledgeBase, "get", return_value=get_query),
        patch.object(
            knowledge_bases,
            "ensure_team_authorized_model",
            AsyncMock(return_value=SimpleNamespace()),
        ) as authorize,
        patch.object(knowledge_bases.AuditLogService, "log", audit),
        patch.object(knowledge_bases, "success", side_effect=lambda **kw: kw),
    ):
        detail = await knowledge_bases.get_knowledge_base(kb_id, _user())
        updated = await knowledge_bases.update_knowledge_base(
            kb_id=kb_id,
            kb_in=KnowledgeBaseUpdate(
                name="new",
                description="new description",
                icon="new-icon",
                rerank_model_id=uuid4(),
                status="archived",
            ),
            request=_request(),
            current_user=_user(),
        )
        deleted = await knowledge_bases.delete_knowledge_base(
            kb_id, _request(), _user()
        )

    assert detail["data"]["id"] == kb_id
    assert (kb.name, kb.description, kb.icon, kb.status) == (
        "new",
        "new description",
        "new-icon",
        "archived",
    )
    authorize.assert_awaited_once()
    kb.save.assert_awaited_once()
    kb.delete.assert_awaited_once()
    assert updated["msg_key"] == "kb_updated"
    assert deleted["data"] == {"id": str(kb_id)}
    assert audit.await_count == 2


@pytest.mark.anyio
async def test_document_list_detail_and_update_branches():
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(id=doc_id, name="old", save=AsyncMock())
    list_query = Query([doc], total=4)
    detail_query = Query(first=doc)
    reloaded_query = Query(first=doc)

    with (
        patch.object(knowledge_bases, "check_kb_access", AsyncMock()),
        patch.object(
            knowledge_bases.Document,
            "filter",
            side_effect=[list_query, detail_query, detail_query],
        ),
        patch.object(knowledge_bases.Document, "get", return_value=reloaded_query),
        patch.object(
            knowledge_bases,
            "serialize_document",
            AsyncMock(return_value={"id": doc_id}),
        ),
        patch.object(knowledge_bases.AuditLogService, "log", AsyncMock()) as audit,
        patch.object(knowledge_bases, "success", side_effect=lambda **kw: kw),
    ):
        listed = await knowledge_bases.list_documents(
            kb_id,
            search="report",
            status=["completed"],
            doc_type=["pdf"],
            page=2,
            page_size=10,
            current_user=_user(),
        )
        detail = await knowledge_bases.get_document(kb_id, doc_id, _user())
        updated = await knowledge_bases.update_document(
            kb_id=kb_id,
            doc_id=doc_id,
            doc_in=DocumentUpdate(name="renamed"),
            request=_request(),
            current_user=_user(),
        )

    filters = [kwargs for name, _, kwargs in list_query.calls if name == "filter"]
    assert filters == [
        {"name__icontains": "report"},
        {"status__in": ["completed"]},
        {"doc_type__in": ["pdf"]},
    ]
    assert listed["data"]["total"] == 4
    assert detail["data"]["id"] == doc_id
    assert updated["msg_key"] == "document_updated"
    assert doc.name == "renamed"
    doc.save.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_document_cleans_task_vectors_media_file_and_stats(
    lexical_store_calls,
):
    kb_id, doc_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        team_id=uuid4(),
        document_count=1,
        total_chunks=2,
        total_tokens=6,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(
        id=doc_id,
        name="report.pdf",
        status=DocumentStatus.PROCESSING.value,
        metadata={"task_id": "task-1"},
        file_path="uploads/report.pdf",
        chunk_count=3,
        token_count=9,
        delete=AsyncMock(),
    )
    vector_store = SimpleNamespace(delete_document_vectors=AsyncMock())
    celery_app = MagicMock()

    with (
        patch.object(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb)),
        patch.object(knowledge_bases.Document, "filter", return_value=Query(first=doc)),
        patch.object(knowledge_bases, "VectorStore", return_value=vector_store),
        patch.object(
            knowledge_bases.document_processor,
            "delete_media_assets",
            AsyncMock(),
        ) as media_delete,
        patch.object(
            knowledge_bases.document_processor, "delete_file", AsyncMock()
        ) as file_delete,
        patch.object(knowledge_bases.AuditLogService, "log", AsyncMock()),
        patch("app.core.celery.celery_app", celery_app),
        patch.object(knowledge_bases, "success", side_effect=lambda **kw: kw),
    ):
        result = await knowledge_bases.delete_document(
            kb_id, doc_id, _request(), _user()
        )

    celery_app.control.revoke.assert_called_once_with("task-1", terminate=True)
    lexical_store_calls.document.assert_not_awaited()
    vector_store.delete_document_vectors.assert_awaited_once_with(doc_id)
    media_delete.assert_awaited_once_with(kb_id, doc_id)
    file_delete.assert_awaited_once_with("uploads/report.pdf")
    assert (kb.document_count, kb.total_chunks, kb.total_tokens) == (0, 0, 0)
    kb.save.assert_awaited_once()
    doc.delete.assert_awaited_once()
    assert result["msg_key"] == "document_deleted"


@pytest.mark.anyio
async def test_reprocess_document_revokes_old_task_and_dispatches_new_one():
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="report.pdf",
        status=DocumentStatus.PROCESSING.value,
        metadata={"task_id": "old-task"},
        error_message="failed",
        save=AsyncMock(),
    )
    reloaded_query = Query(first=doc)
    celery_app = MagicMock()

    with (
        patch.object(knowledge_bases, "check_kb_access", AsyncMock()),
        patch.object(knowledge_bases.Document, "filter", return_value=Query(first=doc)),
        patch.object(knowledge_bases.Document, "get", return_value=reloaded_query),
        patch.object(
            knowledge_bases, "_dispatch_document_task", AsyncMock()
        ) as dispatch,
        patch.object(knowledge_bases.AuditLogService, "log", AsyncMock()),
        patch.object(
            knowledge_bases,
            "serialize_document",
            AsyncMock(return_value={"id": doc_id}),
        ),
        patch("app.core.celery.celery_app", celery_app),
        patch.object(knowledge_bases, "success", side_effect=lambda **kw: kw),
    ):
        result = await knowledge_bases.reprocess_document(
            kb_id, doc_id, _request(), _user()
        )

    celery_app.control.revoke.assert_called_once_with("old-task", terminate=True)
    assert doc.status == DocumentStatus.PENDING.value
    assert doc.error_message is None
    doc.save.assert_awaited_once()
    dispatch.assert_awaited_once()
    assert result["msg_key"] == "document_reprocess_started"
