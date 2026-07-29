import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tortoise import Tortoise
from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBaseStatus,
)


INDEX_VERSION = 2
LEXICAL_BATCH_SIZE = 500
LEXICAL_TABLE = "knowledge_lexical_chunks"
LEXICAL_INDEX = "knowledge_lexical_chunks_bm25_idx"
_IDENTIFIER_RE = re.compile(r"[\w./:+-]+", re.UNICODE)


class LexicalStoreError(RuntimeError):
    pass


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
        "update_version": int(chunk.updated_at.timestamp() * 1_000_000),
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
    chunk_count = await DocumentChunk.filter(document_id=document.id).count()
    if chunk_count != document.chunk_count:
        raise LexicalStoreError("Document chunks are not ready for lexical indexing")
    indexed = 0
    offset = 0
    async with LexicalStore() as store:
        await store.ensure_index()
        while offset < chunk_count:
            chunks = await (
                DocumentChunk.filter(document_id=document.id)
                .order_by("chunk_index", "id")
                .offset(offset)
                .limit(LEXICAL_BATCH_SIZE)
            )
            if not chunks:
                raise LexicalStoreError(
                    "Document chunks changed during lexical indexing"
                )
            indexed += await store.index_chunks(
                [chunk_document(chunk, document) for chunk in chunks]
            )
            offset += len(chunks)
    return indexed


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
    """PostgreSQL pg_search projection; authoritative chunks remain unchanged."""

    def __init__(self, *, connection: Any | None = None) -> None:
        self._connection = connection

    @property
    def connection(self) -> Any:
        return self._connection or Tortoise.get_connection("default")

    async def __aenter__(self) -> "LexicalStore":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ensure_index(self, version: int = INDEX_VERSION) -> str:
        del version
        try:
            rows = await self.connection.execute_query_dict(
                """
                SELECT extversion,
                       to_regclass('public.knowledge_lexical_chunks') AS lexical_table,
                       to_regclass('public.knowledge_lexical_chunks_bm25_idx') AS lexical_index
                FROM pg_extension
                WHERE extname = 'pg_search'
                """
            )
        except Exception as exc:
            raise LexicalStoreError("PostgreSQL lexical search is unavailable") from exc
        if (
            not rows
            or rows[0]["lexical_table"] is None
            or rows[0]["lexical_index"] is None
        ):
            raise LexicalStoreError("PostgreSQL lexical search is not initialized")
        return LEXICAL_INDEX

    async def index_chunks(self, chunks: Sequence[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        unique_chunks = {str(chunk["chunk_id"]): chunk for chunk in chunks}
        payload = [
            {
                "chunk_id": str(chunk["chunk_id"]),
                "document_id": str(chunk["document_id"]),
                "kb_id": str(chunk["kb_id"]),
                "team_id": str(chunk["team_id"]),
                "status": str(chunk["status"]),
                "name": str(chunk["name"]),
                "content": str(chunk["content"]),
                "metadata": chunk.get("metadata") or {},
                "chunk_index": int(chunk["chunk_index"]),
                "update_version": int(chunk["update_version"]),
                "language": chunk.get("language"),
                "section": chunk.get("section"),
                "title": str(chunk["title"]),
                "identifiers": [str(value) for value in chunk.get("identifiers") or []],
            }
            for chunk in unique_chunks.values()
        ]
        try:
            rows = await self.connection.execute_query_dict(
                """
                WITH incoming AS (
                    SELECT *
                    FROM jsonb_to_recordset($1::jsonb) AS value (
                        chunk_id uuid,
                        document_id uuid,
                        kb_id uuid,
                        team_id uuid,
                        status text,
                        name text,
                        content text,
                        metadata jsonb,
                        chunk_index integer,
                        update_version bigint,
                        language text,
                        section text,
                        title text,
                        identifiers jsonb
                    )
                ), upserted AS (
                    INSERT INTO knowledge_lexical_chunks (
                        chunk_id, document_id, kb_id, team_id, status, name, content,
                        metadata, chunk_index, update_version, language, section, title,
                        identifiers
                    )
                    SELECT
                        incoming.chunk_id,
                        incoming.document_id,
                        incoming.kb_id,
                        incoming.team_id,
                        incoming.status,
                        incoming.name,
                        incoming.content,
                        incoming.metadata,
                        incoming.chunk_index,
                        incoming.update_version,
                        incoming.language,
                        incoming.section,
                        incoming.title,
                        ARRAY(
                            SELECT jsonb_array_elements_text(incoming.identifiers)
                        )
                    FROM incoming
                    WHERE EXISTS (
                        SELECT 1
                        FROM document_chunks AS authoritative_chunk
                        JOIN documents AS authoritative_document
                          ON authoritative_document.id = authoritative_chunk.document_id
                        JOIN knowledge_bases AS authoritative_kb
                          ON authoritative_kb.id = authoritative_document.knowledge_base_id
                        WHERE authoritative_chunk.id = incoming.chunk_id
                          AND authoritative_chunk.document_id = incoming.document_id
                          AND authoritative_document.knowledge_base_id = incoming.kb_id
                          AND authoritative_kb.team_id = incoming.team_id
                          AND authoritative_chunk.status = incoming.status
                          AND authoritative_document.name = incoming.name
                          AND authoritative_chunk.content = incoming.content
                          AND COALESCE(authoritative_chunk.metadata, '{}'::jsonb) = incoming.metadata
                          AND authoritative_chunk.chunk_index = incoming.chunk_index
                          AND floor(extract(epoch FROM authoritative_chunk.updated_at) * 1000000)::bigint = incoming.update_version
                          AND authoritative_document.status = 'completed'
                          AND authoritative_kb.status = 'active'
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        kb_id = EXCLUDED.kb_id,
                        team_id = EXCLUDED.team_id,
                        status = EXCLUDED.status,
                        name = EXCLUDED.name,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        chunk_index = EXCLUDED.chunk_index,
                        update_version = EXCLUDED.update_version,
                        language = EXCLUDED.language,
                        section = EXCLUDED.section,
                        title = EXCLUDED.title,
                        identifiers = EXCLUDED.identifiers
                    WHERE knowledge_lexical_chunks.update_version < EXCLUDED.update_version
                    RETURNING chunk_id
                )
                SELECT count(*) AS count FROM upserted
                """,
                [json.dumps(payload, default=str)],
            )
        except Exception as exc:
            raise LexicalStoreError("PostgreSQL lexical indexing failed") from exc
        return int(rows[0]["count"])

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
        normalized_query = query.strip()
        if not normalized_query or limit <= 0 or offset < 0:
            return []
        if kb_ids is not None and not kb_ids:
            return []
        if document_ids is not None and not document_ids:
            return []
        await self.ensure_index()
        identifiers = [
            token
            for token in _IDENTIFIER_RE.findall(normalized_query)
            if any(char.isdigit() for char in token)
        ]
        try:
            rows = await self.connection.execute_query_dict(
                """
                SELECT chunk_id::text,
                       document_id::text,
                       kb_id::text,
                       team_id::text,
                       status,
                       name,
                       content,
                       metadata,
                       chunk_index,
                       update_version,
                       language,
                       section,
                       title,
                       identifiers,
                       pdb.score(chunk_id) AS score
                FROM knowledge_lexical_chunks
                WHERE team_id = $2::uuid
                  AND ($3::uuid[] IS NULL OR kb_id = ANY($3::uuid[]))
                  AND ($4::uuid[] IS NULL OR document_id = ANY($4::uuid[]))
                  AND (
                      content ||| $1::pdb.jieba
                      OR title ||| ($1::pdb.jieba)::pdb.boost(2)
                      OR name ||| ($1::pdb.jieba)::pdb.boost(2)
                      OR section ||| $1::pdb.jieba
                      OR identifiers && $5::text[]
                  )
                ORDER BY (identifiers && $5::text[]) DESC,
                         pdb.score(chunk_id) DESC,
                         document_id,
                         chunk_id
                LIMIT $6 OFFSET $7
                """,
                [
                    normalized_query,
                    str(team_id),
                    [str(value) for value in kb_ids] if kb_ids is not None else None,
                    [str(value) for value in document_ids]
                    if document_ids is not None
                    else None,
                    identifiers,
                    limit,
                    offset,
                ],
            )
        except Exception as exc:
            raise LexicalStoreError("PostgreSQL lexical search failed") from exc
        for row in rows:
            if isinstance(row.get("metadata"), str):
                row["metadata"] = json.loads(row["metadata"])
        return [
            SearchHit(
                chunk_id=str(row["chunk_id"]),
                score=float(row.pop("score") or 0),
                source=row,
            )
            for row in rows
        ]

    async def _delete(self, field: str, value: str, *, team_id: str) -> int:
        if field not in {"document_id", "kb_id", "chunk_id"}:
            raise ValueError("Unsupported lexical delete scope")
        try:
            count, _ = await self.connection.execute_query(
                f"DELETE FROM {LEXICAL_TABLE} WHERE team_id = $1::uuid "
                f"AND {field} = $2::uuid",
                [str(team_id), str(value)],
            )
        except Exception as exc:
            raise LexicalStoreError("PostgreSQL lexical deletion failed") from exc
        return int(count)

    async def delete_document(self, document_id: str, *, team_id: str) -> int:
        return await self._delete("document_id", document_id, team_id=team_id)

    async def delete_kb(self, kb_id: str, *, team_id: str) -> int:
        return await self._delete("kb_id", kb_id, team_id=team_id)

    async def delete_chunk(self, chunk_id: str, *, team_id: str) -> int:
        return await self._delete("chunk_id", chunk_id, team_id=team_id)

    async def count(
        self,
        *,
        team_id: str | None = None,
        kb_id: str | None = None,
        document_id: str | None = None,
    ) -> int:
        rows = await self.connection.execute_query_dict(
            """
            SELECT count(*) AS count
            FROM knowledge_lexical_chunks
            WHERE ($1::uuid IS NULL OR team_id = $1::uuid)
              AND ($2::uuid IS NULL OR kb_id = $2::uuid)
              AND ($3::uuid IS NULL OR document_id = $3::uuid)
            """,
            [team_id, kb_id, document_id],
        )
        return int(rows[0]["count"])

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
