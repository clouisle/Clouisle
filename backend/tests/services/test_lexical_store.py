from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.lexical_store import (
    LEXICAL_INDEX,
    LexicalStore,
    LexicalStoreError,
    chunk_document,
    index_chunk,
    index_document,
)


class ConnectionStub:
    def __init__(self):
        self.query_dict_results: list[list[dict[str, Any]]] = []
        self.queries: list[tuple[str, list[Any] | None]] = []

    async def execute_query_dict(self, query: str, values=None):
        self.queries.append((query, values))
        if self.query_dict_results:
            return self.query_dict_results.pop(0)
        return [{"count": 1}]

    async def execute_query(self, query: str, values=None):
        self.queries.append((query, values))
        return 1, []


@pytest.mark.asyncio
async def test_ensure_index_validates_extension_table_and_index():
    connection = ConnectionStub()
    connection.query_dict_results = [
        [
            {
                "extversion": "0.24.3",
                "lexical_table": "knowledge_lexical_chunks",
                "lexical_index": LEXICAL_INDEX,
            }
        ]
    ]

    assert await LexicalStore(connection=connection).ensure_index() == LEXICAL_INDEX

    connection.query_dict_results = [[]]
    with pytest.raises(LexicalStoreError, match="not initialized"):
        await LexicalStore(connection=connection).ensure_index()


@pytest.mark.asyncio
async def test_index_chunks_uses_parameterized_upsert():
    connection = ConnectionStub()
    store = LexicalStore(connection=connection)
    chunk = {
        "chunk_id": "00000000-0000-0000-0000-000000000001",
        "document_id": "10000000-0000-0000-0000-000000000001",
        "kb_id": "20000000-0000-0000-0000-000000000001",
        "team_id": "30000000-0000-0000-0000-000000000001",
        "status": "completed",
        "name": "guide",
        "content": "answer",
        "metadata": {"language": "en"},
        "chunk_index": 0,
        "update_version": 1,
        "language": "en",
        "section": "intro",
        "title": "Guide",
        "identifiers": ["YUN-117"],
    }

    connection.query_dict_results = [[{"count": 1}]]
    assert await store.index_chunks([chunk, chunk]) == 1
    query, values = connection.queries[0]
    assert "ON CONFLICT (chunk_id) DO UPDATE" in query
    assert "RETURNING chunk_id" in query
    assert "authoritative_chunk.updated_at" in query
    assert "knowledge_lexical_chunks.update_version < EXCLUDED.update_version" in query
    assert values is not None
    assert chunk["chunk_id"] in values[0]
    assert "YUN-117" in values[0]
    assert await store.index_chunks([]) == 0


def test_chunk_document_uses_authoritative_update_timestamp():
    updated_at = datetime(2026, 7, 29, 12, 0, 0, 123456, tzinfo=timezone.utc)
    chunk = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        status="embedded",
        content="answer",
        metadata={},
        chunk_index=0,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=updated_at,
    )
    document = SimpleNamespace(
        id="10000000-0000-0000-0000-000000000001",
        knowledge_base_id="20000000-0000-0000-0000-000000000001",
        knowledge_base=SimpleNamespace(team_id="30000000-0000-0000-0000-000000000001"),
        name="guide",
    )

    payload = chunk_document(chunk, document)

    assert payload["update_version"] == int(updated_at.timestamp() * 1_000_000)


class AwaitableRows(list):
    def __await__(self):
        async def resolve():
            return self

        return resolve().__await__()


class QueryStub:
    def __init__(self, *, first=None, count=0, rows=None):
        self.first_result = first
        self.count_result = count
        self.rows = rows or []

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, offset):
        self.current_offset = offset
        return self

    def limit(self, limit):
        return AwaitableRows(
            self.rows[self.current_offset : self.current_offset + limit]
        )

    async def first(self):
        return self.first_result

    async def count(self):
        return self.count_result


@pytest.mark.asyncio
async def test_index_document_rejects_missing_or_incomplete_document(monkeypatch):
    from app.services import lexical_store

    monkeypatch.setattr(
        lexical_store.Document, "filter", lambda **_kwargs: QueryStub(first=None)
    )
    with pytest.raises(LexicalStoreError, match="Document is not ready"):
        await index_document("document-id")

    document = SimpleNamespace(id="document-id", chunk_count=2)
    monkeypatch.setattr(
        lexical_store.Document,
        "filter",
        lambda **_kwargs: QueryStub(first=document),
    )
    monkeypatch.setattr(
        lexical_store.DocumentChunk,
        "filter",
        lambda **_kwargs: QueryStub(count=1),
    )
    with pytest.raises(LexicalStoreError, match="Document chunks are not ready"):
        await index_document("document-id")


@pytest.mark.asyncio
async def test_index_document_indexes_multiple_batches(monkeypatch):
    from app.services import lexical_store

    document = SimpleNamespace(id="document-id", chunk_count=501)
    chunks = [SimpleNamespace(id=index) for index in range(501)]
    monkeypatch.setattr(
        lexical_store.Document,
        "filter",
        lambda **_kwargs: QueryStub(first=document),
    )
    monkeypatch.setattr(
        lexical_store.DocumentChunk,
        "filter",
        lambda **_kwargs: QueryStub(count=len(chunks), rows=chunks),
    )
    monkeypatch.setattr(
        lexical_store,
        "chunk_document",
        lambda chunk, _document: {"chunk_id": chunk.id},
    )
    ensure_index = AsyncMock()
    index_chunks = AsyncMock(side_effect=[500, 1])
    monkeypatch.setattr(lexical_store.LexicalStore, "ensure_index", ensure_index)
    monkeypatch.setattr(lexical_store.LexicalStore, "index_chunks", index_chunks)

    assert await index_document("document-id") == 501
    ensure_index.assert_awaited_once()
    assert [len(call.args[0]) for call in index_chunks.await_args_list] == [500, 1]


@pytest.mark.asyncio
async def test_index_chunk_rejects_missing_chunk(monkeypatch):
    from app.services import lexical_store

    monkeypatch.setattr(
        lexical_store.DocumentChunk,
        "filter",
        lambda **_kwargs: QueryStub(first=None),
    )

    with pytest.raises(LexicalStoreError, match="Chunk is not ready"):
        await index_chunk("chunk-id")


@pytest.mark.asyncio
async def test_index_document_rejects_disappearing_batch(monkeypatch):
    from app.services import lexical_store

    document = SimpleNamespace(id="document-id", chunk_count=1)
    monkeypatch.setattr(
        lexical_store.Document,
        "filter",
        lambda **_kwargs: QueryStub(first=document),
    )
    monkeypatch.setattr(
        lexical_store.DocumentChunk,
        "filter",
        lambda **_kwargs: QueryStub(count=1),
    )
    monkeypatch.setattr(lexical_store.LexicalStore, "ensure_index", AsyncMock())

    with pytest.raises(LexicalStoreError, match="chunks changed"):
        await index_document("document-id")


@pytest.mark.asyncio
async def test_index_chunk_indexes_ready_chunk(monkeypatch):
    from app.services import lexical_store

    chunk = SimpleNamespace(id="chunk-id", document=SimpleNamespace(id="document-id"))
    monkeypatch.setattr(
        lexical_store.DocumentChunk,
        "filter",
        lambda **_kwargs: QueryStub(first=chunk),
    )
    monkeypatch.setattr(
        lexical_store,
        "chunk_document",
        lambda value, document: {
            "chunk_id": value.id,
            "document_id": document.id,
        },
    )
    monkeypatch.setattr(lexical_store.LexicalStore, "ensure_index", AsyncMock())
    index_chunks = AsyncMock(return_value=1)
    monkeypatch.setattr(lexical_store.LexicalStore, "index_chunks", index_chunks)

    assert await index_chunk("chunk-id") == 1
    index_chunks.assert_awaited_once_with(
        [{"chunk_id": "chunk-id", "document_id": "document-id"}]
    )


@pytest.mark.asyncio
async def test_search_is_scoped_parameterized_and_parses_hits():
    connection = ConnectionStub()
    connection.query_dict_results = [
        [
            {
                "extversion": "0.24.3",
                "lexical_table": "knowledge_lexical_chunks",
                "lexical_index": LEXICAL_INDEX,
            }
        ],
        [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "kb_id": "k1",
                "team_id": "t1",
                "content": "answer",
                "metadata": '{"source": "frontend_preview"}',
                "identifiers": ["YUN-117"],
                "score": 3.25,
            }
        ],
    ]
    store = LexicalStore(connection=connection)

    hits = await store.search(
        "YUN-117",
        team_id="30000000-0000-0000-0000-000000000001",
        kb_ids=["20000000-0000-0000-0000-000000000001"],
        document_ids=["10000000-0000-0000-0000-000000000001"],
        limit=5,
        offset=2,
    )

    assert [(hit.chunk_id, hit.score) for hit in hits] == [("c1", 3.25)]
    assert hits[0].source["metadata"] == {"source": "frontend_preview"}
    query, values = connection.queries[1]
    assert "team_id = $2::uuid" in query
    assert "pdb.score(chunk_id)" in query
    assert "pdb.boost(2)" in query
    assert values[-3:] == [["YUN-117"], 5, 2]


@pytest.mark.asyncio
async def test_search_rejects_empty_query_and_empty_explicit_scopes():
    connection = ConnectionStub()
    store = LexicalStore(connection=connection)

    assert await store.search(" ", team_id="team") == []
    assert await store.search("answer", team_id="team", kb_ids=[]) == []
    assert await store.search("answer", team_id="team", document_ids=[]) == []
    assert connection.queries == []


@pytest.mark.asyncio
async def test_search_preserves_mapping_metadata():
    connection = ConnectionStub()
    connection.query_dict_results = [
        [
            {
                "extversion": "0.24.3",
                "lexical_table": "knowledge_lexical_chunks",
                "lexical_index": LEXICAL_INDEX,
            }
        ],
        [
            {
                "chunk_id": "c1",
                "metadata": {"source": "database"},
                "score": 1,
            }
        ],
    ]

    hits = await LexicalStore(connection=connection).search("answer", team_id="team")

    assert hits[0].source["metadata"] == {"source": "database"}


@pytest.mark.asyncio
async def test_delete_rejects_unsupported_scope():
    with pytest.raises(ValueError, match="Unsupported lexical delete scope"):
        await LexicalStore(connection=ConnectionStub())._delete(
            "team_id", "value", team_id="team"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "field", "value"),
    [
        ("delete_document", "document_id", "10000000-0000-0000-0000-000000000001"),
        ("delete_kb", "kb_id", "20000000-0000-0000-0000-000000000001"),
        ("delete_chunk", "chunk_id", "00000000-0000-0000-0000-000000000001"),
    ],
)
async def test_deletes_are_team_scoped(method: str, field: str, value: str):
    connection = ConnectionStub()
    store = LexicalStore(connection=connection)

    assert (
        await getattr(store, method)(
            value, team_id="30000000-0000-0000-0000-000000000001"
        )
        == 1
    )
    query, values = connection.queries[0]
    assert f"AND {field} = $2::uuid" in query
    assert values[1] == value


@pytest.mark.asyncio
async def test_count_reconcile_and_resumable_backfill():
    connection = ConnectionStub()
    connection.query_dict_results = [
        [{"count": 7}],
        [{"expected": 9, "repaired": 2, "deleted": 0}],
        [{"count": 9}],
    ]
    store = LexicalStore(connection=connection)

    assert await store.count(team_id=None, kb_id=None, document_id=None) == 7
    result = await store.reconcile(9)
    assert result.actual == 9
    assert result.repaired == 2
    assert result.deleted == 0
    assert result.matches is True
    reconcile_query, _ = connection.queries[1]
    assert "knowledge_lexical_chunks IS DISTINCT FROM EXCLUDED" in reconcile_query
    assert "NOT EXISTS" in reconcile_query

    batch = await store.backfill_batch(
        [
            {
                "chunk_id": "00000000-0000-0000-0000-000000000001",
                "document_id": "10000000-0000-0000-0000-000000000001",
                "kb_id": "20000000-0000-0000-0000-000000000001",
                "team_id": "30000000-0000-0000-0000-000000000001",
                "status": "completed",
                "name": "guide",
                "content": "answer",
                "chunk_index": 0,
                "update_version": 1,
                "title": "guide",
            }
        ]
    )
    assert batch.indexed == 1
    assert batch.checkpoint == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_reconcile_rejects_changed_authoritative_count():
    connection = ConnectionStub()
    connection.query_dict_results = [
        [{"expected": 8, "repaired": 0, "deleted": 0}],
        [{"count": 8}],
    ]

    with pytest.raises(LexicalStoreError, match="Authoritative lexical count changed"):
        await LexicalStore(connection=connection).reconcile(expected=9)
