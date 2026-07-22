from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError


class Query:
    def __init__(self, *, first=None, items=None, count=0):
        self.first_value = first
        self.items = items or []
        self.count_value = count
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def all(self):
        return self.items

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@pytest.mark.asyncio
@pytest.mark.parametrize("use_team", [False, True])
async def test_list_covers_filters_memberships_and_model_mapping(monkeypatch, use_team):
    team_id = uuid4()
    embedding_id, rerank_id = uuid4(), uuid4()
    user = SimpleNamespace(is_superuser=False)
    kbs = [
        SimpleNamespace(embedding_model_id=embedding_id, rerank_model_id=rerank_id),
        SimpleNamespace(embedding_model_id=None, rerank_model_id=None),
    ]
    query = Query(items=kbs, count=2)
    models = [
        SimpleNamespace(
            id=embedding_id, name="embed", provider="local", model_id="embed-v1"
        ),
        SimpleNamespace(
            id=rerank_id, name="rerank", provider="local", model_id="rerank-v1"
        ),
    ]

    monkeypatch.setattr(knowledge_bases.KnowledgeBase, "all", lambda: query)
    monkeypatch.setattr(
        knowledge_bases.TeamMember,
        "filter",
        lambda **_kwargs: SimpleNamespace(
            values_list=AsyncMock(return_value=[team_id])
        ),
    )
    monkeypatch.setattr(
        knowledge_bases.Model, "filter", lambda **_kwargs: Query(items=models)
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBaseList,
        "model_validate",
        lambda kb: SimpleNamespace(model_dump=lambda: {"marker": id(kb)}),
    )
    check_team = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "check_team_access", check_team)

    result = await knowledge_bases.list_knowledge_bases(
        team_id=team_id if use_team else None,
        search="guide",
        status=["active"],
        own_only=True,
        page=2,
        page_size=1,
        current_user=user,
    )

    assert result["data"]["total"] == 2
    assert result["data"]["items"][0]["embedding_model"]["name"] == "embed"
    assert result["data"]["items"][0]["rerank_model"]["name"] == "rerank"
    assert result["data"]["items"][1]["embedding_model"] is None
    assert result["data"]["items"][1]["rerank_model"] is None
    if use_team:
        check_team.assert_awaited_once_with(team_id, user)
    else:
        assert {"team_id__in": [team_id]} in query.filters
    assert {"created_by": user} in query.filters
    assert {"name__icontains": "guide"} in query.filters
    assert {"status__in": ["active"]} in query.filters


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_matches", [False, True])
async def test_stats_groups_documents_and_only_syncs_stale_cache(
    monkeypatch, cached_matches
):
    kb_id = uuid4()
    docs = [
        SimpleNamespace(
            status="completed", doc_type="pdf", chunk_count=2, token_count=8
        ),
        SimpleNamespace(
            status="completed", doc_type="url", chunk_count=1, token_count=3
        ),
    ]
    expected = (2, 3, 11)
    cached = expected if cached_matches else (0, 0, 0)
    kb = SimpleNamespace(
        id=kb_id,
        name="kb",
        document_count=cached[0],
        total_chunks=cached[1],
        total_tokens=cached[2],
        embedding_dimension=4,
        save=AsyncMock(),
    )
    vectors = SimpleNamespace(
        get_embedding_stats=AsyncMock(return_value={"embedded": 3})
    )

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(items=docs)
    )
    monkeypatch.setattr(knowledge_bases, "VectorStore", lambda: vectors)

    result = await knowledge_bases.get_knowledge_base_stats(kb_id, SimpleNamespace())

    assert result["data"]["documents_by_status"] == {"completed": 2}
    assert result["data"]["documents_by_type"] == {"pdf": 1, "url": 1}
    assert result["data"]["embedding_stats"] == {"embedded": 3}
    assert kb.save.await_count == (0 if cached_matches else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("get_document", "document_not_found"),
        ("update_document", "document_not_found"),
        ("delete_document", "document_not_found"),
        ("get_document_media", "document_not_found"),
        ("process_document_with_chunks", "document_not_found"),
        ("reprocess_document", "document_not_found"),
        ("retry_failed_chunks", "document_not_found"),
        ("retry_failed_chunk", "document_not_found"),
        ("delete_document_chunk", "document_not_found"),
        ("create_document_chunk", "document_not_found"),
        ("rechunk_document", "document_not_found"),
    ],
)
async def test_document_endpoints_reject_missing_document(
    monkeypatch, endpoint, expected
):
    kb_id, doc_id = uuid4(), uuid4()
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=None)
    )
    common = {
        "kb_id": kb_id,
        "doc_id": doc_id,
        "current_user": SimpleNamespace(),
    }
    kwargs = {
        "get_document": common,
        "update_document": {
            **common,
            "doc_in": SimpleNamespace(),
            "request": SimpleNamespace(),
        },
        "delete_document": {**common, "request": SimpleNamespace()},
        "get_document_media": {**common, "filename": "image.png"},
        "process_document_with_chunks": {
            **common,
            "request": SimpleNamespace(),
            "process_request": SimpleNamespace(chunks=[]),
        },
        "reprocess_document": {**common, "request": SimpleNamespace()},
        "retry_failed_chunks": {**common, "request": SimpleNamespace()},
        "retry_failed_chunk": {
            **common,
            "chunk_id": uuid4(),
            "request": SimpleNamespace(),
        },
        "delete_document_chunk": {
            **common,
            "chunk_id": uuid4(),
            "request": SimpleNamespace(),
        },
        "create_document_chunk": {
            **common,
            "chunk_in": SimpleNamespace(content="text"),
            "request": SimpleNamespace(),
        },
        "rechunk_document": {
            **common,
            "rechunk_in": SimpleNamespace(),
            "request": SimpleNamespace(),
        },
    }[endpoint]

    with pytest.raises(BusinessError) as caught:
        await getattr(knowledge_bases, endpoint)(**kwargs)

    assert caught.value.msg_key == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "doc_type", "size", "expected"),
    [
        (None, "txt", 1, "file_name_required"),
        ("guide.exe", None, 1, "invalid_document_type"),
        ("guide.txt", "txt", 2, "file_too_large"),
    ],
)
async def test_upload_rejects_invalid_file_boundaries(
    monkeypatch, filename, doc_type, size, expected
):
    file = SimpleNamespace(
        filename=filename,
        content_type="text/plain",
        read=AsyncMock(return_value=b"xx"[:size]),
    )
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor,
        "get_document_type",
        lambda *_args: doc_type,
    )
    monkeypatch.setattr(
        knowledge_bases, "get_kb_document_max_upload_size_mb", AsyncMock(return_value=0)
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.upload_document(
            uuid4(), SimpleNamespace(), file, SimpleNamespace()
        )

    assert caught.value.msg_key == expected
