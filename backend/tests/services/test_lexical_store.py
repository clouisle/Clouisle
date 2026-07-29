from typing import Any

import pytest

from app.services.lexical_store import (
    LEXICAL_INDEX,
    LexicalStore,
    LexicalStoreError,
)


class ConnectionStub:
    def __init__(self):
        self.query_dict_results: list[list[dict[str, Any]]] = []
        self.queries: list[tuple[str, list[Any] | None]] = []
        self.many: list[tuple[str, list[list[Any]]]] = []

    async def execute_query_dict(self, query: str, values=None):
        self.queries.append((query, values))
        return self.query_dict_results.pop(0)

    async def execute_query(self, query: str, values=None):
        self.queries.append((query, values))
        return 1, []

    async def execute_many(self, query: str, values: list[list[Any]]):
        self.many.append((query, values))


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

    assert await store.index_chunks([chunk]) == 1
    query, values = connection.many[0]
    assert "ON CONFLICT (chunk_id) DO UPDATE" in query
    assert values[0][0] == chunk["chunk_id"]
    assert values[0][-1] == ["YUN-117"]
    assert "WHERE EXISTS" in query
    assert "authoritative_chunk.content = $7" in query
    assert "knowledge_lexical_chunks.update_version <= EXCLUDED.update_version" in query
    assert await store.index_chunks([]) == 0


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
    connection.query_dict_results = [[{"count": 7}], [{"count": 7}]]
    store = LexicalStore(connection=connection)

    assert await store.count(team_id=None, kb_id=None, document_id=None) == 7
    result = await store.reconcile(9)
    assert result.actual == 7
    assert result.delta == -2
    assert result.matches is False

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
