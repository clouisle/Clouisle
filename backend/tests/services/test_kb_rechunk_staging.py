from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBase,
)
from app.models.user import Team
from app.services import kb_rechunk_staging as staging


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest_asyncio.fixture
async def completed_document(database):
    team = await Team.create(id=uuid4(), name=f"team-{uuid4()}")
    kb = await KnowledgeBase.create(
        id=uuid4(),
        team=team,
        name=f"kb-{uuid4()}",
        document_count=1,
        total_chunks=1,
        total_tokens=3,
    )
    old_media_id = uuid4()
    document = await Document.create(
        id=uuid4(),
        knowledge_base=kb,
        name="source.md",
        doc_type="markdown",
        status=DocumentStatus.COMPLETED.value,
        chunk_count=1,
        token_count=3,
        metadata={
            "task_id": "rechunk-task",
            "media_storage_document_id": str(old_media_id),
            "media_assets": [
                {
                    "path": f"documents/{kb.id}/media/{old_media_id}/old.png",
                    "url": f"/api/v1/knowledge-bases/{kb.id}/documents/{document_id}/media/old.png",
                }
                for document_id in ["old-document"]
            ],
        },
    )
    old_chunk = await DocumentChunk.create(
        id=uuid4(),
        document=document,
        content="previous complete content",
        chunk_index=0,
        token_count=3,
        status="embedded",
    )
    return team, kb, document, old_chunk, old_media_id


@pytest.mark.asyncio
async def test_embedding_error_preserves_published_document_and_chunks(
    completed_document, monkeypatch
):
    _team, kb, document, old_chunk, old_media_id = completed_document
    media_deletes: list[tuple[object, object]] = []

    async def extract(_source, _stage, *, clean_text):
        current_document = await Document.get(id=document.id)
        current_chunks = await DocumentChunk.filter(document_id=document.id).all()
        assert current_document.status == DocumentStatus.COMPLETED.value
        assert [chunk.content for chunk in current_chunks] == [
            "previous complete content"
        ]
        assert clean_text is True
        return "replacement text", {"format": "markdown"}

    class FailingVectors:
        def __init__(self, **_kwargs):
            pass

        async def embed_texts(self, _texts):
            raise RuntimeError("embedding provider failed")

    async def delete_media(kb_id, document_id):
        media_deletes.append((kb_id, document_id))

    monkeypatch.setattr(staging, "_extract_and_enrich", extract)
    monkeypatch.setattr(staging, "VectorStore", FailingVectors)
    monkeypatch.setattr(staging.document_processor, "delete_media_assets", delete_media)

    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="rechunk-task",
        chunk_size=100,
        chunk_overlap=0,
    )

    assert result["status"] == "error"
    assert len(media_deletes) == 1
    assert media_deletes[0][0] == kb.id
    assert media_deletes[0][1] != old_media_id
    refreshed = await Document.get(id=document.id)
    assert refreshed.error_message is None
    assert refreshed.chunk_count == 1
    assert refreshed.token_count == 3
    remaining_chunks = await DocumentChunk.filter(document_id=document.id).all()
    assert [(chunk.id, chunk.content) for chunk in remaining_chunks] == [
        (old_chunk.id, "previous complete content")
    ]
    refreshed_kb = await KnowledgeBase.get(id=kb.id)
    assert (refreshed_kb.total_chunks, refreshed_kb.total_tokens) == (1, 3)
    assert await Document.filter(status=staging.STAGING_STATUS).count() == 0
    assert media_deletes == [(kb.id, media_deletes[0][1])]
    assert media_deletes[0][1] != old_media_id


@pytest.mark.asyncio
async def test_edited_chunks_promote_transactionally_and_keep_document_media(
    completed_document, monkeypatch
):
    _team, kb, document, old_chunk, old_media_id = completed_document
    deleted_media_ids: list[object] = []

    class Vectors:
        def __init__(self, **_kwargs):
            pass

        async def embed_texts(self, texts):
            return [[0.1, 0.2] for _ in texts]

        async def _batch_store_embeddings(self, *_args, **_kwargs):
            return None

    class Lexical:
        def __init__(self, *, connection):
            self.connection = connection

        async def delete_document(self, *_args, **_kwargs):
            return 1

        async def index_chunks(self, chunks):
            return len(chunks)

    async def delete_media(_kb_id, document_id):
        deleted_media_ids.append(document_id)

    monkeypatch.setattr(staging, "VectorStore", Vectors)
    monkeypatch.setattr(staging, "LexicalStore", Lexical)
    monkeypatch.setattr(staging, "_strict_vector_cleanup", AsyncMock())
    monkeypatch.setattr(staging.document_processor, "delete_media_assets", delete_media)
    monkeypatch.setattr(
        staging, "_extract_and_enrich", AsyncMock(side_effect=AssertionError)
    )

    preview_asset = {
        "path": f"documents/{kb.id}/media/{document.id}/preview.png",
        "url": (
            f"/api/v1/knowledge-bases/{kb.id}/documents/{document.id}/media/preview.png"
        ),
        "filename": "preview.png",
        "content_type": "image/png",
        "size": 3,
    }
    document.metadata = {
        **(document.metadata or {}),
        "rechunk_preview_metadata": {"media_assets": [preview_asset]},
        "rechunk_preview_chunks": [{"content": "must not persist"}],
    }
    await document.save(update_fields=["metadata"])

    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="rechunk-task",
        chunk_size=100,
        chunk_overlap=0,
        chunks=[
            {
                "content": "user edited content",
                "chunk_index": 0,
                "token_count": 4,
                "metadata": {"origin": "edited-preview"},
            }
        ],
    )

    assert result["status"] == "success"
    assert result["chunk_count"] == 1
    refreshed = await Document.get(id=document.id)
    assert refreshed.status == DocumentStatus.COMPLETED.value
    assert "rechunk_preview_metadata" not in (refreshed.metadata or {})
    assert "rechunk_preview_chunks" not in (refreshed.metadata or {})
    assert refreshed.metadata["media_storage_document_id"] == str(document.id)
    assert refreshed.metadata["media_assets"] == [preview_asset]
    chunks = await DocumentChunk.filter(document_id=document.id).all()
    assert len(chunks) == 1
    assert chunks[0].id != old_chunk.id
    assert chunks[0].content == "user edited content"
    assert chunks[0].metadata == {"origin": "edited-preview"}
    refreshed_kb = await KnowledgeBase.get(id=kb.id)
    assert (refreshed_kb.total_chunks, refreshed_kb.total_tokens) == (1, 4)
    assert deleted_media_ids == [old_media_id]


@pytest.mark.asyncio
async def test_stale_task_does_not_create_a_staging_document(completed_document):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document

    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="superseded-task",
        chunk_size=100,
        chunk_overlap=0,
    )

    assert result == {"status": "stale", "document_id": str(document.id)}
    assert await Document.filter(status=staging.STAGING_STATUS).count() == 0
    assert await DocumentChunk.filter(document_id=document.id).count() == 1


@pytest.mark.asyncio
async def test_strict_vector_cleanup_uses_module_helpers(monkeypatch):
    client = SimpleNamespace(
        set_payload=AsyncMock(),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(staging, "_collection_name", lambda _dimension: "kb_dim_2")
    monkeypatch.setattr(staging, "_collection_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(staging, "_get_qdrant_client", AsyncMock(return_value=client))

    await staging._strict_vector_cleanup(
        dimension=2,
        set_payload={"kb_id": "kb", "document_id": "doc"},
        set_payload_ids=["new"],
        delete_ids=["old"],
    )

    client.set_payload.assert_awaited_once_with(
        collection_name="kb_dim_2",
        payload={"kb_id": "kb", "document_id": "doc"},
        points=["new"],
        wait=True,
    )
    points = client.delete.await_args.kwargs["points_selector"].points
    assert points == ["old"]
