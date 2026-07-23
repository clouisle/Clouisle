import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBaseStatus,
)


INDEX_VERSION = 1

INDEX_MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "chunk_id": {"type": "keyword"},
        "document_id": {"type": "keyword"},
        "kb_id": {"type": "keyword"},
        "team_id": {"type": "keyword"},
        "status": {"type": "keyword"},
        "name": {"type": "text"},
        "content": {"type": "text"},
        "metadata": {"type": "object", "dynamic": True},
        "chunk_index": {"type": "integer"},
        "update_version": {"type": "long"},
        "language": {"type": "keyword"},
        "section": {"type": "text"},
        "title": {"type": "text"},
        "identifiers": {"type": "keyword"},
    },
}


class LexicalStoreError(RuntimeError):
    pass


class BulkIndexError(LexicalStoreError):
    def __init__(self, failures: list[dict[str, Any]]):
        self.failures = failures
        super().__init__(f"OpenSearch bulk request failed for {len(failures)} item(s)")


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    score: float
    source: dict[str, Any]


@dataclass(frozen=True)
class ReconciliationResult:
    expected: int
    actual: int

    @property
    def matches(self) -> bool:
        return self.expected == self.actual

    @property
    def delta(self) -> int:
        return self.actual - self.expected


@dataclass(frozen=True)
class BackfillResult:
    indexed: int
    checkpoint: str | None


def chunk_document(chunk: DocumentChunk, document: Document) -> dict[str, Any]:
    """Build one lexical document from authoritative PostgreSQL records."""
    metadata = chunk.metadata or {}
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(document.id),
        "kb_id": str(document.knowledge_base_id),
        "team_id": str(document.knowledge_base.team_id),
        "status": chunk.status,
        "name": document.name,
        "content": chunk.content,
        "metadata": metadata,
        "chunk_index": chunk.chunk_index,
        "update_version": int(chunk.created_at.timestamp() * 1_000_000),
        "language": metadata.get("language"),
        "section": metadata.get("section"),
        "title": metadata.get("title") or document.name,
        "identifiers": metadata.get("identifiers", []),
    }


async def index_document(document_id: UUID | str) -> int:
    """Index a document only after its PostgreSQL lifecycle is authoritative."""
    document = (
        await Document.filter(
            id=document_id,
            status=DocumentStatus.COMPLETED.value,
            knowledge_base__status=KnowledgeBaseStatus.ACTIVE.value,
        )
        .prefetch_related("knowledge_base")
        .first()
    )
    if not document:
        raise LexicalStoreError("Document is not ready for lexical indexing")
    chunks = await DocumentChunk.filter(document_id=document.id).order_by("chunk_index")
    if len(chunks) != document.chunk_count:
        raise LexicalStoreError("Document chunks are not ready for lexical indexing")
    async with LexicalStore() as store:
        await store.ensure_index()
        return await store.index_chunks(
            [chunk_document(chunk, document) for chunk in chunks]
        )


async def index_chunk(chunk_id: UUID | str) -> int:
    """Index one embedded chunk belonging to a completed active document."""
    chunk = (
        await DocumentChunk.filter(
            id=chunk_id,
            document__status=DocumentStatus.COMPLETED.value,
            document__knowledge_base__status=KnowledgeBaseStatus.ACTIVE.value,
        )
        .prefetch_related("document__knowledge_base")
        .first()
    )
    if not chunk:
        raise LexicalStoreError("Chunk is not ready for lexical indexing")
    async with LexicalStore() as store:
        await store.ensure_index()
        return await store.index_chunks([chunk_document(chunk, chunk.document)])


async def delete_document(document_id: UUID | str, team_id: UUID | str) -> int:
    async with LexicalStore() as store:
        return await store.delete_document(str(document_id), team_id=str(team_id))


async def delete_kb(kb_id: UUID | str, team_id: UUID | str) -> int:
    async with LexicalStore() as store:
        return await store.delete_kb(str(kb_id), team_id=str(team_id))


async def delete_chunk(chunk_id: UUID | str, team_id: UUID | str) -> int:
    async with LexicalStore() as store:
        return await store.delete_chunk(str(chunk_id), team_id=str(team_id))


class LexicalStore:
    """OpenSearch lexical index; PostgreSQL remains the source of truth."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        index_prefix: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.index_prefix = index_prefix or settings.OPENSEARCH_INDEX_PREFIX
        self._owns_client = client is None
        if client is not None:
            self._client = client
            return

        headers = {"Accept": "application/json"}
        configured_api_key = api_key or settings.OPENSEARCH_API_KEY
        if configured_api_key:
            headers["Authorization"] = f"ApiKey {configured_api_key}"
        configured_username = username or settings.OPENSEARCH_USERNAME
        configured_password = password or settings.OPENSEARCH_PASSWORD
        auth = (
            httpx.BasicAuth(configured_username, configured_password)
            if configured_username and configured_password and not configured_api_key
            else None
        )
        self._client = httpx.AsyncClient(
            base_url=(base_url or settings.OPENSEARCH_URL).rstrip("/"),
            headers=headers,
            auth=auth,
            timeout=timeout or settings.OPENSEARCH_TIMEOUT_SECONDS,
        )

    @property
    def read_alias(self) -> str:
        return f"{self.index_prefix}-read"

    @property
    def write_alias(self) -> str:
        return f"{self.index_prefix}-write"

    def index_name(self, version: int = INDEX_VERSION) -> str:
        return f"{self.index_prefix}-v{version}"

    async def __aenter__(self) -> "LexicalStore":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise LexicalStoreError("OpenSearch request timed out") from exc
        except httpx.HTTPError as exc:
            raise LexicalStoreError(f"OpenSearch request failed: {exc}") from exc
        if response.status_code not in expected:
            raise LexicalStoreError(
                f"OpenSearch {method} {path} returned {response.status_code}: "
                f"{response.text}"
            )
        return response

    async def ensure_index(self, version: int = INDEX_VERSION) -> str:
        index = self.index_name(version)
        response = await self._request("HEAD", f"/{index}", expected=(200, 404))
        if response.status_code == 404:
            await self._request(
                "PUT",
                f"/{index}",
                expected=(200, 201),
                json={"mappings": INDEX_MAPPINGS},
            )
        await self.ensure_aliases(index)
        return index

    async def ensure_aliases(self, index: str) -> None:
        response = await self._request(
            "GET", f"/_alias/{self.read_alias},{self.write_alias}", expected=(200, 404)
        )
        aliases = response.json() if response.status_code == 200 else {}
        actions: list[dict[str, Any]] = []
        for alias in (self.read_alias, self.write_alias):
            if not any(alias in data.get("aliases", {}) for data in aliases.values()):
                actions.append({"add": {"index": index, "alias": alias}})
        if actions:
            await self._request("POST", "/_aliases", json={"actions": actions})

    async def cutover(self, version: int) -> None:
        """Atomically move both aliases while retaining old indices for rollback."""
        target = self.index_name(version)
        await self._request("HEAD", f"/{target}")
        actions: list[dict[str, Any]] = []
        for alias in (self.read_alias, self.write_alias):
            response = await self._request(
                "GET", f"/_alias/{alias}", expected=(200, 404)
            )
            if response.status_code == 200:
                actions.extend(
                    {"remove": {"index": index, "alias": alias}}
                    for index in response.json()
                    if index != target
                )
            actions.append({"add": {"index": target, "alias": alias}})
        await self._request("POST", "/_aliases", json={"actions": actions})

    async def list_versions(self) -> list[str]:
        response = await self._request(
            "GET", f"/_cat/indices/{self.index_prefix}-v*", params={"format": "json"}
        )
        return sorted(item["index"] for item in response.json())

    async def delete_version(self, version: int) -> None:
        await self._request(
            "DELETE", f"/{self.index_name(version)}", expected=(200, 404)
        )

    async def index_chunks(self, chunks: Sequence[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        lines: list[str] = []
        for chunk in chunks:
            chunk_id = str(chunk["chunk_id"])
            lines.append(
                json.dumps({"index": {"_index": self.write_alias, "_id": chunk_id}})
            )
            lines.append(json.dumps(chunk, default=str))
        response = await self._request(
            "POST",
            "/_bulk",
            headers={"Content-Type": "application/x-ndjson"},
            content="\n".join(lines) + "\n",
        )
        payload = response.json()
        failures = [
            item["index"]
            for item in payload.get("items", [])
            if item.get("index", {}).get("status", 500) >= 300
        ]
        if payload.get("errors") or failures:
            raise BulkIndexError(failures)
        return len(chunks)

    async def backfill_batch(self, chunks: Sequence[dict[str, Any]]) -> BackfillResult:
        indexed = await self.index_chunks(chunks)
        checkpoint = str(chunks[-1]["chunk_id"]) if chunks else None
        return BackfillResult(indexed=indexed, checkpoint=checkpoint)

    async def search(
        self,
        query: str,
        *,
        team_id: str,
        kb_ids: Sequence[str] | None = None,
        document_ids: Sequence[str] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SearchHit]:
        filters: list[dict[str, Any]] = [{"term": {"team_id": str(team_id)}}]
        if kb_ids:
            filters.append({"terms": {"kb_id": [str(value) for value in kb_ids]}})
        if document_ids:
            filters.append(
                {"terms": {"document_id": [str(value) for value in document_ids]}}
            )
        response = await self._request(
            "POST",
            f"/{self.read_alias}/_search",
            json={
                "from": offset,
                "size": limit,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "content",
                                        "title^2",
                                        "name^2",
                                        "section",
                                    ],
                                    "type": "best_fields",
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
            },
        )
        return [
            SearchHit(
                chunk_id=str(hit.get("_source", {}).get("chunk_id", hit["_id"])),
                score=float(hit.get("_score") or 0),
                source=hit.get("_source", {}),
            )
            for hit in response.json().get("hits", {}).get("hits", [])
        ]

    async def _delete_by_query(self, filters: Iterable[dict[str, Any]]) -> int:
        response = await self._request(
            "POST",
            f"/{self.write_alias}/_delete_by_query",
            params={"conflicts": "proceed", "refresh": "true"},
            json={"query": {"bool": {"filter": list(filters)}}},
        )
        return int(response.json().get("deleted", 0))

    async def delete_document(self, document_id: str, *, team_id: str) -> int:
        return await self._delete_by_query(
            [
                {"term": {"team_id": str(team_id)}},
                {"term": {"document_id": str(document_id)}},
            ]
        )

    async def delete_kb(self, kb_id: str, *, team_id: str) -> int:
        return await self._delete_by_query(
            [
                {"term": {"team_id": str(team_id)}},
                {"term": {"kb_id": str(kb_id)}},
            ]
        )

    async def delete_chunk(self, chunk_id: str, *, team_id: str) -> int:
        return await self._delete_by_query(
            [
                {"term": {"team_id": str(team_id)}},
                {"term": {"chunk_id": str(chunk_id)}},
            ]
        )

    async def count(
        self,
        *,
        team_id: str | None = None,
        kb_id: str | None = None,
        document_id: str | None = None,
    ) -> int:
        filters: list[dict[str, Any]] = []
        if team_id is not None:
            filters.append({"term": {"team_id": str(team_id)}})
        if kb_id is not None:
            filters.append({"term": {"kb_id": str(kb_id)}})
        if document_id is not None:
            filters.append({"term": {"document_id": str(document_id)}})
        response = await self._request(
            "POST",
            f"/{self.read_alias}/_count",
            json={"query": {"bool": {"filter": filters}}},
        )
        return int(response.json()["count"])

    async def reconcile(
        self,
        expected: int,
        *,
        team_id: str | None = None,
        kb_id: str | None = None,
        document_id: str | None = None,
    ) -> ReconciliationResult:
        actual = await self.count(team_id=team_id, kb_id=kb_id, document_id=document_id)
        return ReconciliationResult(expected=expected, actual=actual)
