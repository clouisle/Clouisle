import json
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services.lexical_store import (
    INDEX_MAPPINGS,
    BulkIndexError,
    LexicalStore,
    LexicalStoreError,
)


class OpenSearchStub:
    def __init__(self, responses: list[tuple[int, Any]]):
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, payload = self.responses.pop(0)
        if isinstance(payload, str):
            return httpx.Response(status, text=payload)
        return httpx.Response(status, json=payload)


def client_for(stub: OpenSearchStub) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://opensearch:9200", transport=httpx.MockTransport(stub)
    )


def body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


@pytest.mark.asyncio
async def test_default_client_configures_api_key_and_timeout(monkeypatch):
    captured: dict[str, Any] = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(settings, "OPENSEARCH_VERIFY_SSL", False)
    LexicalStore(
        base_url="https://search.example/",
        api_key="secret",
        timeout=4.5,
        index_prefix="chunks",
    )

    assert captured["base_url"] == "https://search.example"
    assert captured["headers"]["Authorization"] == "ApiKey secret"
    assert captured["auth"] is None
    assert captured["timeout"] == 4.5
    assert captured["verify"] is False


@pytest.mark.asyncio
async def test_default_client_uses_basic_auth_without_api_key(monkeypatch):
    captured: dict[str, Any] = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    LexicalStore(username="user", password="pass")

    assert isinstance(captured["auth"], httpx.BasicAuth)
    assert "Authorization" not in captured["headers"]


@pytest.mark.asyncio
async def test_request_translates_timeout_and_http_errors():
    async def timeout(_request):
        raise httpx.ReadTimeout("late")

    store = LexicalStore(
        client=httpx.AsyncClient(
            base_url="http://search", transport=httpx.MockTransport(timeout)
        )
    )
    with pytest.raises(LexicalStoreError, match="timed out"):
        await store.count(team_id="team")

    stub = OpenSearchStub([(503, "unavailable")])
    store = LexicalStore(client=client_for(stub))
    with pytest.raises(LexicalStoreError, match="503.*unavailable"):
        await store.count(team_id="team")


@pytest.mark.asyncio
async def test_ensure_index_creates_v1_mapping_and_aliases_atomically():
    stub = OpenSearchStub([(404, ""), (201, {}), (404, {}), (200, {})])
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await store.ensure_index() == "chunks-v1"
    assert [(r.method, r.url.path) for r in stub.requests] == [
        ("HEAD", "/chunks-v1"),
        ("PUT", "/chunks-v1"),
        ("GET", "/_alias/chunks-read,chunks-write"),
        ("POST", "/_aliases"),
    ]
    assert body(stub.requests[1]) == {"mappings": INDEX_MAPPINGS}
    assert set(INDEX_MAPPINGS["properties"]) == {
        "chunk_id",
        "document_id",
        "kb_id",
        "team_id",
        "status",
        "name",
        "content",
        "metadata",
        "chunk_index",
        "update_version",
        "language",
        "section",
        "title",
        "identifiers",
    }
    assert body(stub.requests[3]) == {
        "actions": [
            {"add": {"index": "chunks-v1", "alias": "chunks-read"}},
            {"add": {"index": "chunks-v1", "alias": "chunks-write"}},
        ]
    }


@pytest.mark.asyncio
async def test_ensure_index_is_idempotent_when_index_and_aliases_exist():
    aliases = {"chunks-v1": {"aliases": {"chunks-read": {}, "chunks-write": {}}}}
    stub = OpenSearchStub([(200, ""), (200, aliases)])
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    await store.ensure_index()

    assert [request.method for request in stub.requests] == ["HEAD", "GET"]


@pytest.mark.asyncio
async def test_cutover_moves_aliases_atomically_and_retains_old_index():
    stub = OpenSearchStub(
        [
            (200, ""),
            (200, {"chunks-v1": {"aliases": {"chunks-read": {}}}}),
            (200, {"chunks-v1": {"aliases": {"chunks-write": {}}}}),
            (200, {}),
            (200, [{"index": "chunks-v1"}, {"index": "chunks-v2"}]),
            (200, {}),
        ]
    )
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    await store.cutover(2)
    assert body(stub.requests[3]) == {
        "actions": [
            {"remove": {"index": "chunks-v1", "alias": "chunks-read"}},
            {"add": {"index": "chunks-v2", "alias": "chunks-read"}},
            {"remove": {"index": "chunks-v1", "alias": "chunks-write"}},
            {"add": {"index": "chunks-v2", "alias": "chunks-write"}},
        ]
    }
    assert await store.list_versions() == ["chunks-v1", "chunks-v2"]
    await store.delete_version(1)
    assert stub.requests[-1].url.path == "/chunks-v1"


@pytest.mark.asyncio
async def test_bulk_indexes_chunks_as_ndjson_and_detects_partial_failure():
    chunks = [
        {"chunk_id": "c1", "content": "one", "team_id": "t"},
        {"chunk_id": "c2", "content": "two", "team_id": "t"},
    ]
    stub = OpenSearchStub([(200, {"errors": False, "items": []})])
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await store.index_chunks(chunks) == 2
    lines = stub.requests[0].content.decode().splitlines()
    assert json.loads(lines[0]) == {"index": {"_index": "chunks-write", "_id": "c1"}}
    assert json.loads(lines[1]) == chunks[0]
    assert stub.requests[0].headers["content-type"] == "application/x-ndjson"
    assert await store.index_chunks([]) == 0

    failure = {
        "errors": True,
        "items": [
            {"index": {"_id": "c1", "status": 201}},
            {"index": {"_id": "c2", "status": 429, "error": {"type": "busy"}}},
        ],
    }
    stub = OpenSearchStub([(200, failure)])
    store = LexicalStore(client=client_for(stub))
    with pytest.raises(BulkIndexError) as exc_info:
        await store.index_chunks(chunks)
    assert exc_info.value.failures == [failure["items"][1]["index"]]


@pytest.mark.asyncio
async def test_search_builds_bm25_scopes_and_parses_hits():
    response = {
        "hits": {
            "hits": [
                {
                    "_id": "fallback",
                    "_score": 3.25,
                    "_source": {"chunk_id": "c1", "content": "answer"},
                },
                {"_id": "c2", "_score": None, "_source": {}},
            ]
        }
    }
    aliases = {"chunks-v1": {"aliases": {"chunks-read": {}, "chunks-write": {}}}}
    stub = OpenSearchStub([(200, ""), (200, aliases), (200, response)])
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    hits = await store.search(
        "answer",
        team_id="team-1",
        kb_ids=["kb-1"],
        document_ids=["doc-1", "doc-2"],
        limit=5,
        offset=10,
    )

    assert [(hit.chunk_id, hit.score) for hit in hits] == [("c1", 3.25), ("c2", 0)]
    query = body(stub.requests[2])
    assert query["from"] == 10
    assert query["size"] == 5
    assert query["query"]["bool"]["must"][0]["multi_match"]["query"] == "answer"
    assert query["query"]["bool"]["filter"] == [
        {"term": {"team_id": "team-1"}},
        {"terms": {"kb_id": ["kb-1"]}},
        {"terms": {"document_id": ["doc-1", "doc-2"]}},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "field", "value"),
    [
        ("delete_document", "document_id", "doc"),
        ("delete_kb", "kb_id", "kb"),
        ("delete_chunk", "chunk_id", "chunk"),
    ],
)
async def test_deletes_are_team_scoped(method: str, field: str, value: str):
    stub = OpenSearchStub([(200, {"deleted": 4})])
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await getattr(store, method)(value, team_id="team") == 4
    assert stub.requests[0].url.path == "/chunks-write/_delete_by_query"
    assert stub.requests[0].url.params["conflicts"] == "proceed"
    assert body(stub.requests[0])["query"]["bool"]["filter"] == [
        {"term": {"team_id": "team"}},
        {"term": {field: value}},
    ]


@pytest.mark.asyncio
async def test_count_reconcile_and_resumable_backfill():
    stub = OpenSearchStub(
        [
            (200, {"count": 7}),
            (200, {"count": 7}),
            (200, {"errors": False, "items": []}),
        ]
    )
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await store.count(team_id="team", kb_id="kb", document_id="doc") == 7
    result = await store.reconcile(9, team_id="team", kb_id="kb")
    assert result.actual == 7
    assert result.delta == -2
    assert result.matches is False

    batch = await store.backfill_batch([{"chunk_id": "cursor-2", "content": "x"}])
    assert batch.indexed == 1
    assert batch.checkpoint == "cursor-2"
    empty = await store.backfill_batch([])
    assert empty.indexed == 0
    assert empty.checkpoint is None


@pytest.mark.asyncio
async def test_cutover_handles_missing_aliases_and_skips_target_removal():
    stub = OpenSearchStub(
        [
            (200, ""),
            (404, {}),
            (200, {"chunks-v2": {"aliases": {"chunks-write": {}}}}),
            (200, {}),
        ]
    )
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    await store.cutover(2)

    assert body(stub.requests[3]) == {
        "actions": [
            {"add": {"index": "chunks-v2", "alias": "chunks-read"}},
            {"add": {"index": "chunks-v2", "alias": "chunks-write"}},
        ]
    }


@pytest.mark.asyncio
async def test_first_search_initializes_missing_index_and_aliases():
    stub = OpenSearchStub(
        [
            (404, ""),
            (201, {}),
            (404, {}),
            (200, {}),
            (200, {"hits": {"hits": []}}),
        ]
    )
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await store.search("answer", team_id="team") == []
    assert [(request.method, request.url.path) for request in stub.requests] == [
        ("HEAD", "/chunks-v1"),
        ("PUT", "/chunks-v1"),
        ("GET", "/_alias/chunks-read,chunks-write"),
        ("POST", "/_aliases"),
        ("POST", "/chunks-read/_search"),
    ]


@pytest.mark.asyncio
async def test_search_and_count_allow_global_optional_scopes():
    aliases = {"chunks-v1": {"aliases": {"chunks-read": {}, "chunks-write": {}}}}
    stub = OpenSearchStub(
        [
            (200, ""),
            (200, aliases),
            (200, {"hits": {"hits": []}}),
            (200, {"count": 3}),
        ]
    )
    store = LexicalStore(client=client_for(stub), index_prefix="chunks")

    assert await store.search("answer", team_id="team") == []
    assert body(stub.requests[2])["query"]["bool"]["filter"] == [
        {"term": {"team_id": "team"}}
    ]

    assert await store.count() == 3
    assert body(stub.requests[3])["query"]["bool"]["filter"] == []
