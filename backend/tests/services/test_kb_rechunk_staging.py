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
from app.services.kb_rechunk_staging import (
    CLEANUP_MARKER,
    COMPLETED_TASK_MARKER,
    _build_stage_chunks,
    _cleanup_stage,
    _create_stage,
    _finish_cleanup,
    _promote_stage,
    _rewrite_media_reference,
    _strict_vector_cleanup,
)


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


def test_rewrite_media_reference_handles_nested_values():
    old, new = "/a/", "/b/"
    assert _rewrite_media_reference(f"{old}x", old, new) == f"{new}x"
    assert _rewrite_media_reference([f"{old}x", 1], old, new) == [f"{new}x", 1]
    assert _rewrite_media_reference({"p": f"{old}x"}, old, new) == {"p": f"{new}x"}
    assert _rewrite_media_reference(1, old, new) == 1


@pytest.mark.asyncio
async def test_strict_vector_cleanup_skips_missing_collection_and_empty_payload(
    monkeypatch,
):
    client = SimpleNamespace(set_payload=AsyncMock(), delete=AsyncMock())
    monkeypatch.setattr(staging, "_collection_name", lambda _d: "kb")
    monkeypatch.setattr(staging, "_collection_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(staging, "_get_qdrant_client", AsyncMock(return_value=client))

    await _strict_vector_cleanup(dimension=2, delete_ids=["old"])
    client.delete.assert_not_awaited()

    monkeypatch.setattr(staging, "_collection_exists", AsyncMock(return_value=True))
    await _strict_vector_cleanup(
        dimension=2, set_payload={"kb_id": "kb"}, delete_ids=None
    )
    client.set_payload.assert_not_awaited()
    client.delete.assert_not_awaited()

    await _strict_vector_cleanup(dimension=None, delete_ids=["old"])
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_stage_returns_none_for_missing_source(database):
    assert await _create_stage(SimpleNamespace(id=uuid4()), "task") is None


@pytest.mark.asyncio
async def test_build_stage_chunks_rejects_empty_output(completed_document):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    with pytest.raises(ValueError, match="document_no_chunks_generated"):
        await _build_stage_chunks(
            document,
            document,
            "",
            {},
            chunk_size=100,
            chunk_overlap=0,
            separator=None,
            chunks=[],
            batch_size=1,
        )


@pytest.mark.asyncio
async def test_promote_stage_early_results(completed_document):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    kwargs = {
        "chunks": [],
        "stage_metadata": {},
        "dimension": None,
        "chunk_size": 100,
        "chunk_overlap": 0,
    }
    assert await _promote_stage(document.id, uuid4(), "wrong-task", **kwargs) == {
        "status": "stale",
        "document_id": str(document.id),
    }

    document.metadata = {
        **(document.metadata or {}),
        "task_id": "task",
        COMPLETED_TASK_MARKER: "task",
    }
    await document.save(update_fields=["metadata"])
    assert await _promote_stage(document.id, uuid4(), "task", **kwargs) == {
        "status": "already_completed",
        "document_id": str(document.id),
    }

    document.metadata = {
        "task_id": "task",
        CLEANUP_MARKER: {"x": 1},
    }
    await document.save(update_fields=["metadata"])
    assert await _promote_stage(document.id, uuid4(), "task", **kwargs) == {
        "status": "cleanup_pending",
        "document_id": str(document.id),
    }


@pytest.mark.asyncio
async def test_finish_cleanup_covers_missing_doc_and_non_journal(completed_document):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    assert await _finish_cleanup(uuid4()) is False

    document.metadata = {**(document.metadata or {}), CLEANUP_MARKER: "not-a-dict"}
    await document.save(update_fields=["metadata"])
    assert await _finish_cleanup(document.id) is True


@pytest.mark.asyncio
async def test_finish_cleanup_handles_dimension_media_and_journal(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    deleted_media: list[tuple] = []
    deleted_files: list[str] = []

    async def delete_media(kb_id, media_id):
        deleted_media.append((kb_id, media_id))

    async def delete_file(path):
        deleted_files.append(path)
        raise OSError("gone")

    monkeypatch.setattr(staging, "_strict_vector_cleanup", AsyncMock())
    monkeypatch.setattr(
        staging, "get_kb_embedding_dimension", AsyncMock(side_effect=RuntimeError())
    )
    monkeypatch.setattr(staging.document_processor, "delete_media_assets", delete_media)
    monkeypatch.setattr(staging.document_processor, "delete_file", delete_file)

    old_media, new_media = uuid4(), uuid4()
    journal = {
        "dimension": "invalid",
        "promotion_id": "p1",
        "old_media_document_id": str(old_media),
        "new_media_document_id": str(new_media),
        "old_asset_paths": ["keep.png", "remove.png"],
        "new_asset_paths": ["keep.png"],
    }
    document.metadata = {**(document.metadata or {}), CLEANUP_MARKER: journal}
    await document.save(update_fields=["metadata"])

    document.metadata = {**(document.metadata or {}), "other": True}
    await document.save(update_fields=["metadata"])
    assert await _finish_cleanup(document.id) is True
    assert deleted_media == [(document.knowledge_base_id, old_media)]

    same_media = str(uuid4())
    journal["old_media_document_id"] = same_media
    journal["new_media_document_id"] = same_media
    document.metadata = {
        **(document.metadata or {}),
        CLEANUP_MARKER: journal,
    }
    await document.save(update_fields=["metadata"])
    assert await _finish_cleanup(document.id) is True
    assert deleted_files == ["remove.png"]
    refreshed = await Document.get(id=document.id)
    assert CLEANUP_MARKER not in (refreshed.metadata or {})


@pytest.mark.asyncio
async def test_cleanup_stage_falls_back_to_dimension_after_error(
    completed_document, monkeypatch
):
    _team, kb, document, _old_chunk, _old_media_id = completed_document
    monkeypatch.setattr(
        staging, "get_kb_embedding_dimension", AsyncMock(side_effect=RuntimeError())
    )
    monkeypatch.setattr(staging, "_strict_vector_cleanup", AsyncMock())
    monkeypatch.setattr(staging.document_processor, "delete_media_assets", AsyncMock())
    await _cleanup_stage(document, kb.id)
    assert not await Document.filter(id=document.id).exists()


@pytest.mark.asyncio
async def test_rechunk_early_validation_and_not_found(database):
    with pytest.raises(ValueError, match="expected_task_id"):
        await staging.rechunk_document_staged(
            uuid4(), expected_task_id="", chunk_size=1, chunk_overlap=0
        )
    with pytest.raises(ValueError, match="batch_size"):
        await staging.rechunk_document_staged(
            uuid4(), expected_task_id="t", chunk_size=1, chunk_overlap=0, batch_size=0
        )
    document_id = uuid4()
    assert await staging.rechunk_document_staged(
        document_id, expected_task_id="t", chunk_size=1, chunk_overlap=0
    ) == {
        "status": "error",
        "document_id": str(document_id),
        "error_type": "not_found",
    }


@pytest.mark.asyncio
async def test_rechunk_read_only_and_completed_and_stage_missing(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    original_metadata = dict(document.metadata or {})

    document.metadata = {**original_metadata, "feishu_read_only": True}
    await document.save(update_fields=["metadata"])
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["error_type"] == "read_only_document"

    document.metadata = {**original_metadata, COMPLETED_TASK_MARKER: "rechunk-task"}
    await document.save(update_fields=["metadata"])
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["status"] == "already_completed"

    document.metadata = original_metadata
    await document.save(update_fields=["metadata"])
    monkeypatch.setattr(staging, "_create_stage", AsyncMock(return_value=None))
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["status"] == "stale"


@pytest.mark.asyncio
async def test_rechunk_cleanup_marker_failure_returns_pending(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {**(document.metadata or {}), CLEANUP_MARKER: {"x": 1}}
    await document.save(update_fields=["metadata"])
    monkeypatch.setattr(
        staging, "_finish_cleanup", AsyncMock(side_effect=RuntimeError("cleanup"))
    )
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["status"] == "cleanup_pending"
    assert result["committed"] is True


class _FakeLexical:
    indexed: int | None = None

    def __init__(self, **_kwargs):
        pass

    async def delete_document(self, *_args, **_kwargs):
        return 1

    async def index_chunks(self, chunks):
        return len(chunks) if type(self).indexed is None else type(self).indexed


async def _stage_with_chunk(document, content="replacement"):
    stage = await Document.create(
        id=uuid4(),
        knowledge_base_id=document.knowledge_base_id,
        name="stage",
        doc_type="markdown",
        status=staging.STAGING_STATUS,
        metadata={"rechunk_task_id": "rechunk-task"},
    )
    chunk = await DocumentChunk.create(
        id=uuid4(),
        document_id=stage.id,
        content=content,
        chunk_index=0,
        token_count=2,
        status="embedded",
    )
    return stage, chunk


@pytest.mark.asyncio
async def test_promote_stage_keeps_staged_media_and_updates_metadata(
    completed_document, monkeypatch
):
    _team, kb, document, _old_chunk, _old_media_id = completed_document
    kb.embedding_dimension = None
    await kb.save(update_fields=["embedding_dimension"])
    stage, chunk = await _stage_with_chunk(document)
    monkeypatch.setattr(staging, "LexicalStore", _FakeLexical)

    result = await _promote_stage(
        document.id,
        stage.id,
        "rechunk-task",
        chunks=[chunk],
        stage_metadata={
            "media_assets": [
                {"path": f"documents/kb/media/{stage.id}/a.png", "url": "/a.png"}
            ],
            "image_understanding": {"images": []},
        },
        dimension=2,
        chunk_size=100,
        chunk_overlap=0,
    )
    assert result["status"] == "success"
    refreshed = await Document.get(id=document.id)
    assert refreshed.metadata["media_storage_document_id"] == str(stage.id)
    assert refreshed.metadata["media_assets"][0]["path"] == (
        f"documents/kb/media/{stage.id}/a.png"
    )
    assert refreshed.metadata["image_understanding"] == {"images": []}
    refreshed_kb = await KnowledgeBase.get(id=kb.id)
    assert refreshed_kb.embedding_dimension == 2


@pytest.mark.asyncio
async def test_promote_stage_handles_preview_media_and_missing_storage_id(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    stage, chunk = await _stage_with_chunk(document)
    monkeypatch.setattr(staging, "LexicalStore", _FakeLexical)
    document.metadata = {"task_id": "rechunk-task"}
    await document.save(update_fields=["metadata"])

    result = await _promote_stage(
        document.id,
        stage.id,
        "rechunk-task",
        chunks=[chunk],
        stage_metadata={
            "media_assets": [
                {
                    "path": f"documents/x/media/{document.id}/preview.png",
                    "url": "/p.png",
                }
            ]
        },
        dimension=None,
        chunk_size=100,
        chunk_overlap=0,
    )
    assert result["status"] == "success"
    refreshed = await Document.get(id=document.id)
    assert refreshed.metadata["media_storage_document_id"] == str(document.id)


@pytest.mark.asyncio
async def test_promote_stage_drops_absent_storage_id_for_legacy_assets(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    stage, chunk = await _stage_with_chunk(document)
    monkeypatch.setattr(staging, "LexicalStore", _FakeLexical)
    document.metadata = {
        "task_id": "rechunk-task",
        "media_assets": [{"path": "legacy/path.png", "url": "/legacy.png"}],
    }
    await document.save(update_fields=["metadata"])

    await _promote_stage(
        document.id,
        stage.id,
        "rechunk-task",
        chunks=[chunk],
        stage_metadata={},
        dimension=None,
        chunk_size=100,
        chunk_overlap=0,
    )
    refreshed = await Document.get(id=document.id)
    assert "media_storage_document_id" not in refreshed.metadata
    assert refreshed.metadata["media_assets"] == [
        {"path": "legacy/path.png", "url": "/legacy.png"}
    ]


@pytest.mark.asyncio
async def test_promote_stage_preserves_explicit_storage_id(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, old_media_id = completed_document
    stage, chunk = await _stage_with_chunk(document)
    monkeypatch.setattr(staging, "LexicalStore", _FakeLexical)
    document.metadata = {
        "task_id": "rechunk-task",
        "media_storage_document_id": str(old_media_id),
    }
    await document.save(update_fields=["metadata"])

    await _promote_stage(
        document.id,
        stage.id,
        "rechunk-task",
        chunks=[chunk],
        stage_metadata={},
        dimension=None,
        chunk_size=100,
        chunk_overlap=0,
    )
    refreshed = await Document.get(id=document.id)
    assert refreshed.metadata["media_storage_document_id"] == str(old_media_id)


@pytest.mark.asyncio
async def test_promote_stage_rejects_incomplete_lexical_index(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    stage, chunk = await _stage_with_chunk(document)
    monkeypatch.setattr(staging, "LexicalStore", _FakeLexical)
    monkeypatch.setattr(_FakeLexical, "indexed", 0)

    with pytest.raises(staging.StagedRechunkError, match="Lexical promotion"):
        await _promote_stage(
            document.id,
            stage.id,
            "rechunk-task",
            chunks=[chunk],
            stage_metadata={},
            dimension=None,
            chunk_size=100,
            chunk_overlap=0,
        )


@pytest.mark.asyncio
async def test_cleanup_stage_uses_existing_dimension(completed_document, monkeypatch):
    _team, kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {**(document.metadata or {}), "rechunk_embedding_dimension": 2}
    await document.save(update_fields=["metadata"])
    monkeypatch.setattr(staging, "_strict_vector_cleanup", AsyncMock())
    monkeypatch.setattr(staging, "get_kb_embedding_dimension", AsyncMock())
    monkeypatch.setattr(staging.document_processor, "delete_media_assets", AsyncMock())
    await _cleanup_stage(document, kb.id)
    staging.get_kb_embedding_dimension.assert_not_awaited()


@pytest.mark.asyncio
async def test_finish_cleanup_returns_false_when_document_vanishes(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    same = str(uuid4())
    document.metadata = {
        **(document.metadata or {}),
        CLEANUP_MARKER: {
            "promotion_id": "p",
            "old_media_document_id": same,
            "new_media_document_id": same,
            "old_asset_paths": ["remove.png"],
            "new_asset_paths": [],
        },
    }
    await document.save(update_fields=["metadata"])
    monkeypatch.setattr(staging, "_strict_vector_cleanup", AsyncMock())

    async def vanish(_path):
        await Document.filter(id=document.id).delete()

    monkeypatch.setattr(staging.document_processor, "delete_file", vanish)
    assert await _finish_cleanup(document.id) is False


@pytest.mark.asyncio
async def test_finish_cleanup_keeps_newer_journal(completed_document, monkeypatch):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {
        **(document.metadata or {}),
        CLEANUP_MARKER: {"promotion_id": "old", "dimension": 2},
    }
    await document.save(update_fields=["metadata"])

    async def replace_journal(**_kwargs):
        fresh = await Document.get(id=document.id)
        fresh.metadata = {
            **(fresh.metadata or {}),
            CLEANUP_MARKER: {"promotion_id": "new"},
        }
        await fresh.save(update_fields=["metadata"])

    monkeypatch.setattr(staging, "_strict_vector_cleanup", replace_journal)
    assert await _finish_cleanup(document.id) is True
    refreshed = await Document.get(id=document.id)
    assert refreshed.metadata[CLEANUP_MARKER] == {"promotion_id": "new"}


@pytest.mark.asyncio
async def test_rechunk_cleanup_then_reload_is_stale(completed_document, monkeypatch):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {**(document.metadata or {}), CLEANUP_MARKER: {"x": 1}}
    await document.save(update_fields=["metadata"])

    async def finish(_doc_id):
        fresh = await Document.get(id=document.id)
        fresh.metadata = {**(fresh.metadata or {}), "task_id": "other"}
        await fresh.save(update_fields=["metadata"])
        return True

    monkeypatch.setattr(staging, "_finish_cleanup", finish)
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["status"] == "stale"


@pytest.mark.asyncio
async def test_rechunk_cleanup_then_continue(completed_document, monkeypatch):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {**(document.metadata or {}), CLEANUP_MARKER: {"x": 1}}
    await document.save(update_fields=["metadata"])
    monkeypatch.setattr(staging, "_finish_cleanup", AsyncMock(return_value=True))
    monkeypatch.setattr(staging, "_create_stage", AsyncMock(return_value=None))
    result = await staging.rechunk_document_staged(
        document.id, expected_task_id="rechunk-task", chunk_size=100, chunk_overlap=0
    )
    assert result["status"] == "stale"


@pytest.mark.asyncio
async def test_rechunk_ignores_non_dict_preview_metadata(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    document.metadata = {
        **(document.metadata or {}),
        staging.PREVIEW_METADATA_KEY: "not-a-dict",
    }
    await document.save(update_fields=["metadata"])
    stage = SimpleNamespace(id=uuid4(), metadata={})
    monkeypatch.setattr(staging, "_create_stage", AsyncMock(return_value=stage))
    monkeypatch.setattr(staging, "_save_stage_metadata", AsyncMock())
    monkeypatch.setattr(
        staging, "_build_stage_chunks", AsyncMock(return_value=([], None))
    )
    monkeypatch.setattr(
        staging, "_promote_stage", AsyncMock(return_value={"status": "success"})
    )
    monkeypatch.setattr(staging, "_finish_cleanup", AsyncMock(return_value=True))
    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="rechunk-task",
        chunk_size=100,
        chunk_overlap=0,
        chunks=[{"content": "x", "chunk_index": 0}],
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_rechunk_cleans_stage_when_promotion_is_stale(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    stage = SimpleNamespace(id=uuid4(), metadata={})
    monkeypatch.setattr(staging, "_create_stage", AsyncMock(return_value=stage))
    monkeypatch.setattr(staging, "_save_stage_metadata", AsyncMock())
    monkeypatch.setattr(
        staging, "_build_stage_chunks", AsyncMock(return_value=([], None))
    )
    monkeypatch.setattr(
        staging, "_promote_stage", AsyncMock(return_value={"status": "stale"})
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(staging, "_cleanup_stage", cleanup)
    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="rechunk-task",
        chunk_size=100,
        chunk_overlap=0,
        chunks=[{"content": "x", "chunk_index": 0}],
    )
    assert result["status"] == "stale"
    cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_rechunk_reports_cleanup_pending_when_finish_returns_false(
    completed_document, monkeypatch
):
    _team, _kb, document, _old_chunk, _old_media_id = completed_document
    stage = SimpleNamespace(id=uuid4(), metadata={})
    monkeypatch.setattr(staging, "_create_stage", AsyncMock(return_value=stage))
    monkeypatch.setattr(staging, "_save_stage_metadata", AsyncMock())
    monkeypatch.setattr(
        staging, "_build_stage_chunks", AsyncMock(return_value=([], None))
    )
    monkeypatch.setattr(
        staging, "_promote_stage", AsyncMock(return_value={"status": "success"})
    )
    monkeypatch.setattr(staging, "_finish_cleanup", AsyncMock(return_value=False))
    result = await staging.rechunk_document_staged(
        document.id,
        expected_task_id="rechunk-task",
        chunk_size=100,
        chunk_overlap=0,
        chunks=[{"content": "x", "chunk_index": 0}],
    )
    assert result["status"] == "cleanup_pending"
    assert result["committed"] is True
