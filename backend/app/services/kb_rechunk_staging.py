"""Stage and atomically publish a replacement for an existing KB document.

The relational document/chunk rows and the pg_search projection are switched in
one PostgreSQL transaction. Qdrant and upload storage are external systems;
their post-commit work is recorded on the document and is safe to retry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from tortoise.transactions import in_transaction

from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    DocumentType,
    KnowledgeBase,
)
from app.services.document_processor import chunk_text, document_processor
from app.services.lexical_store import LexicalStore, chunk_document
from app.services.vector_store import (
    DimensionMismatchError,
    VectorStore,
    _collection_exists_strict,
    _collection_name,
    _get_qdrant_client,
    _validate_embeddings,
    get_kb_embedding_dimension,
    qmodels,
)

logger = logging.getLogger(__name__)

STAGING_STATUS = "rechunk_staging"
STAGING_MARKER = "rechunk_stage_for"
CLEANUP_MARKER = "rechunk_cleanup"
COMPLETED_TASK_MARKER = "rechunk_completed_task_id"
PREVIEW_CHUNKS_KEY = "rechunk_preview_chunks"
PREVIEW_METADATA_KEY = "rechunk_preview_metadata"
PREVIEW_METADATA_FIELDS = frozenset(
    {"media_assets", "image_understanding", "format", "doc_type"}
)
MEDIA_EXTRACTED_MARKER = "rechunk_media_extracted"


class StagedRechunkError(RuntimeError):
    """A replacement could not be built; the published document is unchanged."""


def _rewrite_media_reference(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_rewrite_media_reference(item, old, new) for item in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_media_reference(item, old, new) for key, item in value.items()
        }
    return value


def _current_task(document: Document, expected_task_id: str) -> bool:
    return (document.metadata or {}).get("task_id") == expected_task_id


def _result_error(document_id: UUID, error: Exception) -> dict[str, Any]:
    error_type = (
        "dimension_mismatch"
        if isinstance(error, DimensionMismatchError)
        else "processing_failed"
    )
    return {
        "status": "error",
        "document_id": str(document_id),
        "error_type": error_type,
        "message": str(error)[:500],
        "preserved_previous_version": True,
    }


async def _extract_and_enrich(
    source: Document,
    stage: Document,
    *,
    clean_text: bool,
) -> tuple[str, dict[str, Any]]:
    from app.services.kb_image_ingestion import image_settings, prepare_document

    stage.knowledge_base = source.knowledge_base
    return await prepare_document(
        stage, clean_text=clean_text, settings=await image_settings()
    )


async def _create_stage(source: Document, expected_task_id: str) -> Document | None:
    """Create a hidden stage row only while the caller still owns the task."""
    stage_id = uuid4()
    metadata = {
        STAGING_MARKER: str(source.id),
        "rechunk_task_id": expected_task_id,
    }
    async with in_transaction() as connection:
        locked_source = await (
            Document.filter(id=source.id)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if not locked_source or not _current_task(locked_source, expected_task_id):
            return None
        stage = await Document.create(
            id=stage_id,
            knowledge_base_id=locked_source.knowledge_base_id,
            name=locked_source.name,
            doc_type=locked_source.doc_type,
            file_path=locked_source.file_path,
            file_size=locked_source.file_size,
            source_url=locked_source.source_url,
            uploaded_by_id=locked_source.uploaded_by_id,
            status=STAGING_STATUS,
            error_message=None,
            chunk_count=0,
            token_count=0,
            metadata=metadata,
            using_db=connection,
        )
    stage.knowledge_base = source.knowledge_base
    return stage


async def _save_stage_metadata(stage: Document, updates: dict[str, Any]) -> None:
    metadata = dict(stage.metadata or {})
    metadata.update(updates)
    stage.metadata = metadata
    await stage.save(update_fields=["metadata"])


async def _build_stage_chunks(
    source: Document,
    stage: Document,
    text: str,
    extracted_metadata: dict[str, Any],
    *,
    chunk_size: int,
    chunk_overlap: int,
    separator: str | None,
    chunks: list[dict[str, Any]] | None,
    batch_size: int,
) -> tuple[list[DocumentChunk], int | None]:
    excluded = {
        PREVIEW_CHUNKS_KEY,
        PREVIEW_METADATA_KEY,
        CLEANUP_MARKER,
        COMPLETED_TASK_MARKER,
    }
    if chunks is None:
        excluded.update({"media_assets", "image_understanding"})
    base_metadata = {
        key: value
        for key, value in (source.metadata or {}).items()
        if key not in excluded
    }
    base_metadata.update(stage.metadata or {})
    base_metadata.update(extracted_metadata)
    base_metadata.update(
        {
            STAGING_MARKER: str(source.id),
            "rechunk_task_id": (stage.metadata or {}).get("rechunk_task_id"),
        }
    )
    if chunks is None:
        base_metadata[MEDIA_EXTRACTED_MARKER] = True
    stage.metadata = base_metadata
    await stage.save(update_fields=["metadata"])

    if chunks is None:
        is_markdown = source.doc_type == DocumentType.MD.value or (
            base_metadata.get("format") == "markdown"
        )
        chunks_data = chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[separator] if separator else None,
            is_markdown=is_markdown,
        )
    else:
        chunks_data = chunks
    if not chunks_data:
        raise ValueError("document_no_chunks_generated")

    chunk_objs = [
        DocumentChunk(
            id=uuid4(),
            document_id=stage.id,
            content=str(item["content"]),
            chunk_index=int(item["chunk_index"]),
            token_count=int(
                item.get("token_count")
                if item.get("token_count") is not None
                else len(str(item["content"])) // 4
            ),
            metadata=item.get("metadata"),
            embedding_id=None,
            status="pending",
        )
        for item in chunks_data
    ]
    await DocumentChunk.bulk_create(chunk_objs)

    kb = source.knowledge_base
    try:
        expected_dimension = await get_kb_embedding_dimension(kb.id)
    except Exception:
        logger.warning("Could not read KB embedding dimension for %s", kb.id)
        expected_dimension = kb.embedding_dimension
    vectors = VectorStore(
        embedding_model_id=str(kb.embedding_model_id)
        if kb.embedding_model_id
        else None,
        team_id=str(kb.team_id) if kb.team_id else None,
        embedding_dimension=expected_dimension,
    )
    dimension: int | None = expected_dimension
    embedded = 0
    for start in range(0, len(chunk_objs), batch_size):
        batch = chunk_objs[start : start + batch_size]
        embeddings = await vectors.embed_texts([chunk.content for chunk in batch])
        batch_dimension = _validate_embeddings(embeddings, len(batch), dimension)
        if dimension is not None and batch_dimension != dimension:
            raise DimensionMismatchError(
                f"Embedding dimension mismatch: expected {dimension}, "
                f"but model produces {batch_dimension}."
            )
        dimension = batch_dimension
        await vectors._batch_store_embeddings(
            [chunk.id for chunk in batch],
            embeddings,
            dimension=dimension,
            payloads=[
                {
                    # Keep staged vectors out of ordinary KB result sets.
                    "kb_id": f"rechunk-staging:{stage.id}",
                    "document_id": str(stage.id),
                }
                for _ in batch
            ],
        )
        for chunk in batch:
            chunk.embedding_id = f"kb_{kb.id}_chunk_{chunk.id}"
            chunk.status = "embedded"
            chunk.error_message = None
        await DocumentChunk.bulk_update(
            batch, fields=["embedding_id", "status", "error_message"]
        )
        embedded += len(batch)
        await _save_stage_metadata(
            stage,
            {
                "embed_progress": embedded,
                "rechunk_embedding_dimension": dimension,
            },
        )

    if embedded != len(chunk_objs):
        raise StagedRechunkError("Not all staged chunks were embedded")
    stage.chunk_count = len(chunk_objs)
    stage.token_count = sum(chunk.token_count for chunk in chunk_objs)
    await stage.save(update_fields=["chunk_count", "token_count"])
    return chunk_objs, dimension


async def _strict_vector_cleanup(
    *,
    dimension: int | None,
    set_payload: dict[str, str] | None = None,
    set_payload_ids: list[str] | None = None,
    delete_ids: list[str] | None = None,
) -> None:
    if not dimension:
        return
    collection = _collection_name(dimension)
    if not await _collection_exists_strict(collection):
        return
    client = await _get_qdrant_client()
    if set_payload and set_payload_ids:
        await client.set_payload(
            collection_name=collection,
            payload=set_payload,
            points=set_payload_ids,
            wait=True,
        )
    if delete_ids:
        await client.delete(
            collection_name=collection,
            points_selector=qmodels.PointIdsList(points=delete_ids),
            wait=True,
        )


async def _cleanup_stage(stage: Document, kb_id: UUID) -> None:
    """Best-effort removal of a failed stage; never mask the original error."""
    metadata = dict(stage.metadata or {})
    chunk_ids = [
        str(value)
        for value in await DocumentChunk.filter(document_id=stage.id).values_list(
            "id", flat=True
        )
    ]
    dimension = metadata.get("rechunk_embedding_dimension")
    if not isinstance(dimension, int):
        try:
            dimension = await get_kb_embedding_dimension(kb_id)
        except Exception:
            dimension = None
    try:
        await _strict_vector_cleanup(dimension=dimension, delete_ids=chunk_ids)
    except Exception:
        logger.exception("Could not remove staged vectors for %s", stage.id)
    try:
        await document_processor.delete_media_assets(kb_id, stage.id)
    except Exception:
        logger.exception("Could not remove staged media for %s", stage.id)
    async with in_transaction() as connection:
        await DocumentChunk.filter(document_id=stage.id).using_db(connection).delete()
        await Document.filter(id=stage.id).using_db(connection).delete()


async def _promote_stage(
    document_id: UUID,
    stage_id: UUID,
    expected_task_id: str,
    *,
    chunks: list[DocumentChunk],
    stage_metadata: dict[str, Any],
    dimension: int | None,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, Any]:
    async with in_transaction() as connection:
        document = await (
            Document.filter(id=document_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if not document or not _current_task(document, expected_task_id):
            return {"status": "stale", "document_id": str(document_id)}
        metadata = dict(document.metadata or {})
        if metadata.get(COMPLETED_TASK_MARKER) == expected_task_id:
            return {"status": "already_completed", "document_id": str(document_id)}
        if metadata.get(CLEANUP_MARKER):
            return {"status": "cleanup_pending", "document_id": str(document_id)}

        kb = await (
            KnowledgeBase.filter(id=document.knowledge_base_id)
            .using_db(connection)
            .select_for_update()
            .get()
        )
        old_chunks = (
            await DocumentChunk.filter(document_id=document.id)
            .using_db(connection)
            .all()
        )
        old_chunk_ids = [str(chunk.id) for chunk in old_chunks]
        old_media_id = metadata.get("media_storage_document_id") or str(document.id)
        old_asset_paths = [
            str(asset["path"])
            for asset in (metadata.get("media_assets") or [])
            if isinstance(asset, dict) and asset.get("path")
        ]

        new_metadata = dict(metadata)
        for key in (
            "media_assets",
            "image_understanding",
            "embed_progress",
            "rechunk_embedding_dimension",
            STAGING_MARKER,
            "rechunk_task_id",
            PREVIEW_CHUNKS_KEY,
            PREVIEW_METADATA_KEY,
            MEDIA_EXTRACTED_MARKER,
        ):
            new_metadata.pop(key, None)
        rechunk_settings = metadata.get("rechunk_settings") or {}
        new_metadata.update(
            {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "rechunk_settings": {
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "separator": rechunk_settings.get("separator"),
                    "clean_text": rechunk_settings.get("clean_text", True),
                },
                COMPLETED_TASK_MARKER: expected_task_id,
            }
        )

        assets = stage_metadata.get("media_assets") or []
        fresh_media = bool(stage_metadata.get(MEDIA_EXTRACTED_MARKER))
        staged_media = any(
            f"/media/{stage_id}/" in str(asset.get("path") or "") for asset in assets
        )
        preview_media = any(
            f"/media/{document.id}/" in str(asset.get("path") or "") for asset in assets
        )
        old_prefix = f"/documents/{stage_id}/media/"
        new_prefix = f"/documents/{document.id}/media/"
        if staged_media:
            # Immutable stage media stays where it is; URLs point at the document.
            new_metadata["media_assets"] = _rewrite_media_reference(
                assets, old_prefix, new_prefix
            )
            new_metadata["media_storage_document_id"] = str(stage_id)
            new_media_id: str | None = str(stage_id)
        else:
            chosen_assets = (
                assets if fresh_media else assets or metadata.get("media_assets") or []
            )
            if chosen_assets:
                new_metadata["media_assets"] = chosen_assets
            else:
                new_metadata.pop("media_assets", None)
            if preview_media:
                new_metadata["media_storage_document_id"] = str(document.id)
                new_media_id = str(document.id)
            else:
                new_media_id = old_media_id
                if metadata.get("media_storage_document_id") and not fresh_media:
                    new_metadata["media_storage_document_id"] = metadata[
                        "media_storage_document_id"
                    ]
                else:
                    new_metadata.pop("media_storage_document_id", None)
        if fresh_media:
            new_metadata.pop("image_understanding", None)
        if stage_metadata.get("image_understanding"):
            new_metadata["image_understanding"] = stage_metadata["image_understanding"]

        for chunk in chunks:
            chunk.content = chunk.content.replace(old_prefix, new_prefix)
            chunk.metadata = _rewrite_media_reference(
                chunk.metadata, old_prefix, new_prefix
            )
            chunk.document_id = document.id
            await chunk.save(
                using_db=connection,
                update_fields=["document_id", "content", "metadata"],
            )
        await (
            DocumentChunk.filter(document_id=document.id)
            .using_db(connection)
            .exclude(id__in=[chunk.id for chunk in chunks])
            .delete()
        )

        document.metadata = new_metadata
        document.status = DocumentStatus.COMPLETED.value
        document.error_message = None
        document.chunk_count = len(chunks)
        document.token_count = sum(chunk.token_count for chunk in chunks)
        document.processed_at = datetime.now(timezone.utc)
        await document.save(
            using_db=connection,
            update_fields=[
                "metadata",
                "status",
                "error_message",
                "chunk_count",
                "token_count",
                "processed_at",
            ],
        )

        kb.total_chunks = max(0, kb.total_chunks - len(old_chunks)) + len(chunks)
        kb.total_tokens = (
            max(0, kb.total_tokens - sum(c.token_count for c in old_chunks))
            + document.token_count
        )
        if dimension and not kb.embedding_dimension:
            kb.embedding_dimension = dimension
        await kb.save(
            using_db=connection,
            update_fields=["total_chunks", "total_tokens", "embedding_dimension"],
        )

        lexical = LexicalStore(connection=connection)
        await lexical.delete_document(str(document.id), team_id=str(kb.team_id))
        document.knowledge_base = kb
        for chunk in chunks:
            chunk.document = document
        indexed = await lexical.index_chunks(
            [chunk_document(chunk, document) for chunk in chunks]
        )
        if indexed != len(chunks):
            raise StagedRechunkError(
                f"Lexical promotion indexed {indexed} of {len(chunks)} chunks"
            )

        journal = {
            "promotion_id": str(uuid4()),
            "task_id": expected_task_id,
            "dimension": dimension,
            "new_chunk_ids": [str(chunk.id) for chunk in chunks],
            "old_chunk_ids": old_chunk_ids,
            "old_media_document_id": str(old_media_id),
            "new_media_document_id": new_media_id,
            "old_asset_paths": old_asset_paths,
            "new_asset_paths": [
                str(asset["path"])
                for asset in (new_metadata.get("media_assets") or [])
                if isinstance(asset, dict) and asset.get("path")
            ],
        }
        document.metadata = {**new_metadata, CLEANUP_MARKER: journal}
        await document.save(using_db=connection, update_fields=["metadata"])
        await Document.filter(id=stage_id).using_db(connection).delete()

        return {
            "status": "success",
            "document_id": str(document.id),
            "chunk_count": len(chunks),
            "token_count": document.token_count,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }


async def _finish_cleanup(document_id: UUID) -> bool:
    document = await Document.filter(id=document_id).first()
    if not document:
        return False
    metadata = dict(document.metadata or {})
    journal = metadata.get(CLEANUP_MARKER)
    if not isinstance(journal, dict):
        return True

    dimension = journal.get("dimension")
    if not isinstance(dimension, int):
        try:
            dimension = await get_kb_embedding_dimension(document.knowledge_base_id)
        except Exception:
            dimension = None
    new_ids = [str(value) for value in journal.get("new_chunk_ids") or []]
    old_ids = [str(value) for value in journal.get("old_chunk_ids") or []]
    await _strict_vector_cleanup(
        dimension=dimension,
        set_payload={
            "kb_id": str(document.knowledge_base_id),
            "document_id": str(document.id),
        },
        set_payload_ids=new_ids,
        delete_ids=old_ids,
    )

    old_media_id = journal.get("old_media_document_id")
    new_media_id = journal.get("new_media_document_id")
    if old_media_id and old_media_id != new_media_id:
        await document_processor.delete_media_assets(
            document.knowledge_base_id, UUID(str(old_media_id))
        )
    else:
        # Same media directory: remove only files the new version replaced.
        new_paths = {str(value) for value in journal.get("new_asset_paths") or []}
        for path in journal.get("old_asset_paths") or []:
            if str(path) in new_paths:
                continue
            try:
                await document_processor.delete_file(str(path))
            except Exception:
                logger.exception("Could not delete replaced media file %s", path)

    async with in_transaction() as connection:
        locked = await (
            Document.filter(id=document_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )
        if not locked:
            return False
        latest_metadata = dict(locked.metadata or {})
        latest_journal = latest_metadata.get(CLEANUP_MARKER)
        if isinstance(latest_journal, dict) and latest_journal.get(
            "promotion_id"
        ) == journal.get("promotion_id"):
            latest_metadata.pop(CLEANUP_MARKER, None)
            locked.metadata = latest_metadata
            await locked.save(using_db=connection, update_fields=["metadata"])
    return True


async def rechunk_document_staged(
    document_id: UUID | str,
    *,
    expected_task_id: str,
    chunk_size: int,
    chunk_overlap: int,
    separator: str | None = None,
    clean_text: bool = True,
    chunks: list[dict[str, Any]] | None = None,
    batch_size: int = 25,
) -> dict[str, Any]:
    """Build a hidden replacement, then atomically publish its DB/lexical state.

    The caller MUST pass the task id installed transactionally by the API. A
    stale task never commits. Errors leave the old document, chunks, lexical
    projection, counters and media pointer unchanged. Post-commit Qdrant/media
    cleanup is idempotent and stored in ``metadata.rechunk_cleanup`` until done.
    """
    doc_uuid = UUID(str(document_id))
    if not expected_task_id:
        raise ValueError("expected_task_id is required for staged rechunk")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    source = (
        await Document.filter(id=doc_uuid).prefetch_related("knowledge_base").first()
    )
    if not source:
        return {
            "status": "error",
            "document_id": str(doc_uuid),
            "error_type": "not_found",
        }
    if not _current_task(source, expected_task_id):
        return {"status": "stale", "document_id": str(doc_uuid)}

    metadata = dict(source.metadata or {})
    if metadata.get("feishu_source_id") or metadata.get("feishu_read_only"):
        return {
            "status": "error",
            "document_id": str(doc_uuid),
            "error_type": "read_only_document",
            "preserved_previous_version": True,
        }

    # Finish prior post-commit projection cleanup first; otherwise its journal
    # could be overwritten by a later commit.
    if metadata.get(CLEANUP_MARKER):
        try:
            await _finish_cleanup(doc_uuid)
        except Exception:
            logger.exception(
                "Could not finish previous rechunk cleanup for %s", doc_uuid
            )
            return {
                "status": "cleanup_pending",
                "document_id": str(doc_uuid),
                "committed": True,
            }
        source = await Document.get(id=doc_uuid).prefetch_related("knowledge_base")
        if not _current_task(source, expected_task_id):
            return {"status": "stale", "document_id": str(doc_uuid)}
        metadata = dict(source.metadata or {})
    if metadata.get(COMPLETED_TASK_MARKER) == expected_task_id:
        return {
            "status": "already_completed",
            "document_id": str(doc_uuid),
            "chunk_count": source.chunk_count,
            "token_count": source.token_count,
        }

    stage = await _create_stage(source, expected_task_id)
    if not stage:
        return {"status": "stale", "document_id": str(doc_uuid)}

    stage_metadata: dict[str, Any] = {}
    try:
        if chunks is None:
            text, extracted_metadata = await _extract_and_enrich(
                source, stage, clean_text=clean_text
            )
            stage_metadata.update(extracted_metadata)
        else:
            preview_metadata = metadata.get(PREVIEW_METADATA_KEY)
            if isinstance(preview_metadata, dict):
                stage_metadata.update(
                    {
                        key: value
                        for key, value in preview_metadata.items()
                        if key in PREVIEW_METADATA_FIELDS
                    }
                )
            text = ""
        await _save_stage_metadata(stage, stage_metadata)
        staged_chunks, dimension = await _build_stage_chunks(
            source,
            stage,
            text,
            stage_metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=separator,
            chunks=chunks,
            batch_size=batch_size,
        )
        result = await _promote_stage(
            doc_uuid,
            stage.id,
            expected_task_id,
            chunks=staged_chunks,
            stage_metadata=dict(stage.metadata or {}),
            dimension=dimension,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if result["status"] in {"stale", "already_completed", "cleanup_pending"}:
            await _cleanup_stage(stage, source.knowledge_base_id)
            return result
        try:
            if not await _finish_cleanup(doc_uuid):
                return {
                    "status": "cleanup_pending",
                    "document_id": str(doc_uuid),
                    "committed": True,
                }
        except Exception:
            logger.exception(
                "Rechunk committed but external cleanup is pending for %s", doc_uuid
            )
            result["status"] = "cleanup_pending"
            result["committed"] = True
        return result
    except Exception as exc:
        try:
            await _cleanup_stage(stage, source.knowledge_base_id)
        except Exception:
            logger.exception("Could not clean failed rechunk stage %s", stage.id)
        return _result_error(doc_uuid, exc)
