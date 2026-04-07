"""
Celery tasks for knowledge base document processing.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task

from app.core.i18n import t, get_default_language
from app.models.knowledge_base import (
    Document,
    DocumentStatus,
)
from app.models.notification import AutoNotificationType
from app.services.auto_notification import AutoNotificationService
from app.services.document_processor import document_processor
from app.services.vector_store import VectorStore, DimensionMismatchError

logger = logging.getLogger(__name__)


def _get_document_error_lang(document: Document, user_locale: str = "en") -> str:
    if document.uploaded_by_id:
        return user_locale
    return "en"


def _get_dimension_mismatch_error(document: Document, user_locale: str = "en") -> str:
    return t(
        "kb_embedding_dimension_mismatch",
        lang=_get_document_error_lang(document, user_locale),
    )


def _get_generic_processing_error(document: Document, user_locale: str = "en") -> str:
    return t(
        "document_processing_failed_generic",
        lang=_get_document_error_lang(document, user_locale),
    )


async def _send_doc_indexed_notification(
    document: Document,
    kb_name: str,
    team_id: UUID,
    chunk_count: int,
    token_count: int,
    user_locale: str = "en",
) -> None:
    """Send notification when document is indexed successfully."""
    try:
        # Send to uploader if available, otherwise to team
        if document.uploaded_by_id:
            await AutoNotificationService.send_to_user(
                notification_type=AutoNotificationType.KB_DOC_INDEXED,
                user_id=document.uploaded_by_id,
                title=t("notify_kb_doc_indexed_title", lang=user_locale),
                content=t(
                    "notify_kb_doc_indexed_content",
                    lang=user_locale,
                    doc_name=document.name,
                    kb_name=kb_name,
                    chunk_count=chunk_count,
                    token_count=token_count,
                ),
                data={
                    "document_id": str(document.id),
                    "document_name": document.name,
                    "kb_name": kb_name,
                    "chunk_count": chunk_count,
                    "token_count": token_count,
                },
                link_url=f"/kb/{document.knowledge_base_id}",
            )
        else:
            default_lang = await get_default_language()
            await AutoNotificationService.send_to_team(
                notification_type=AutoNotificationType.KB_DOC_INDEXED,
                team_id=team_id,
                title=t("notify_kb_doc_indexed_title", lang=default_lang),
                content=t(
                    "notify_kb_doc_indexed_content",
                    lang=default_lang,
                    doc_name=document.name,
                    kb_name=kb_name,
                    chunk_count=chunk_count,
                    token_count=token_count,
                ),
                data={
                    "document_id": str(document.id),
                    "document_name": document.name,
                    "kb_name": kb_name,
                    "chunk_count": chunk_count,
                    "token_count": token_count,
                },
                link_url=f"/kb/{document.knowledge_base_id}",
            )
    except Exception as e:
        logger.error(f"Failed to send doc indexed notification: {e}")


async def _send_doc_failed_notification(
    document: Document,
    kb_name: str,
    team_id: UUID,
    error: str,
    user_locale: str = "en",
) -> None:
    """Send notification when document indexing fails."""
    try:
        # Send to uploader if available, otherwise to team
        if document.uploaded_by_id:
            await AutoNotificationService.send_to_user(
                notification_type=AutoNotificationType.KB_DOC_FAILED,
                user_id=document.uploaded_by_id,
                title=t("notify_kb_doc_failed_title", lang=user_locale),
                content=t(
                    "notify_kb_doc_failed_content",
                    lang=user_locale,
                    doc_name=document.name,
                    kb_name=kb_name,
                    error=error[:200],  # Truncate error message
                ),
                data={
                    "document_id": str(document.id),
                    "document_name": document.name,
                    "kb_name": kb_name,
                    "error": error[:500],
                },
                link_url=f"/kb/{document.knowledge_base_id}",
            )
        else:
            default_lang = await get_default_language()
            await AutoNotificationService.send_to_team(
                notification_type=AutoNotificationType.KB_DOC_FAILED,
                team_id=team_id,
                title=t("notify_kb_doc_failed_title", lang=default_lang),
                content=t(
                    "notify_kb_doc_failed_content",
                    lang=default_lang,
                    doc_name=document.name,
                    kb_name=kb_name,
                    error=error[:200],  # Truncate error message
                ),
                data={
                    "document_id": str(document.id),
                    "document_name": document.name,
                    "kb_name": kb_name,
                    "error": error[:500],
                },
                link_url=f"/kb/{document.knowledge_base_id}",
            )
    except Exception as e:
        logger.error(f"Failed to send doc failed notification: {e}")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: str) -> dict:
    """
    Celery task to process a document.

    Steps:
    1. Extract text from document
    2. Chunk text
    3. Generate embeddings
    4. Store in vector database
    5. Update document status

    Args:
        document_id: UUID string of document to process

    Returns:
        Result dict with status and stats
    """
    import asyncio

    async def _process():
        doc_uuid = UUID(document_id)

        # Get document with uploader for locale
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base", "uploaded_by")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t("document_not_found", lang=default_lang),
            }

        kb = document.knowledge_base
        # Get uploader's locale for notifications
        user_locale = (
            getattr(document.uploaded_by, "locale", "en")
            if document.uploaded_by
            else "en"
        )

        try:
            # Update status to processing
            document.status = DocumentStatus.PROCESSING.value
            await document.save()

            # Extract text
            # Get clean_text setting from document metadata (default to True)
            doc_meta = document.metadata or {}
            clean_text_setting = doc_meta.get("clean_text", True)

            if document.file_path:
                text, metadata = await document_processor.extract_text(
                    document.file_path,
                    document.doc_type,
                    clean_text=clean_text_setting,
                )
            elif document.source_url:
                text, metadata = await document_processor.fetch_url_content(
                    document.source_url,
                    clean_text=clean_text_setting,
                )
            else:
                raise ValueError(t("document_missing_source", lang=user_locale))

            # Update document metadata
            document.metadata = document.metadata or {}
            document.metadata.update(metadata)

            # Get chunking settings from document metadata first, then fallback to KB settings
            doc_meta = document.metadata or {}
            kb_settings = kb.settings or {}
            chunk_size = doc_meta.get("chunk_size") or kb_settings.get(
                "chunk_size", 1000
            )
            chunk_overlap = doc_meta.get("chunk_overlap") or kb_settings.get(
                "chunk_overlap", 100
            )
            separator = doc_meta.get("separator") or kb_settings.get("separator")

            # Chunk text
            from app.services.document_processor import chunk_text

            chunks = chunk_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=[separator] if separator else None,
            )

            if not chunks:
                raise ValueError(t("document_no_chunks_generated", lang=user_locale))

            # Initialize vector store with KB's embedding model and team ID for usage tracking
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None
            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                team_id=team_id,
            )

            # Store chunks with embeddings and progress tracking
            # Pass kb_id to enable dimension management:
            # - First document sets the KB's embedding dimension
            # - Subsequent documents must match the dimension
            async def _update_progress(embedded: int, failed: int, total: int) -> None:
                document.metadata = document.metadata or {}
                document.metadata["embed_progress"] = {
                    "embedded": embedded,
                    "failed": failed,
                    "total": total,
                }
                await document.save(update_fields=["metadata"])

            created_chunks = await vector_store.store_chunks_with_progress(
                document, chunks, kb_id=kb.id, progress_callback=_update_progress
            )
            logger.info(
                f"Document {document_id} embeddings stored, chunks={len(created_chunks)}"
            )

            # Check for failed chunks
            failed_chunks = [c for c in created_chunks if c.status == "failed"]
            embedded_chunks = [c for c in created_chunks if c.status == "embedded"]

            # Calculate totals from embedded chunks
            total_tokens = sum(c.token_count for c in created_chunks)

            # Clear progress from metadata
            document.metadata = document.metadata or {}
            document.metadata.pop("embed_progress", None)

            if failed_chunks and not embedded_chunks:
                # All failed
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "all_chunks_failed_to_embed",
                    lang=user_locale,
                    error=t("unknown_error_generic", lang=user_locale),
                )[:500]
                document.chunk_count = len(created_chunks)
                document.token_count = total_tokens
                await document.save()

                await _send_doc_failed_notification(
                    document=document,
                    kb_name=kb.name,
                    team_id=kb.team_id,
                    error=document.error_message,
                    user_locale=user_locale,
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": document.error_message,
                }

            if failed_chunks:
                # Partial failure
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "chunks_failed_to_embed",
                    lang=user_locale,
                    failed_count=len(failed_chunks),
                    total_chunks=len(created_chunks),
                    error=t("unknown_error_generic", lang=user_locale),
                )[:500]
            else:
                document.status = DocumentStatus.COMPLETED.value
                document.error_message = None

            document.chunk_count = len(created_chunks)
            document.token_count = total_tokens
            document.processed_at = datetime.now(timezone.utc)
            await document.save()
            logger.info(
                f"Document {document_id} status updated: {document.status}, chunks={document.chunk_count}, tokens={document.token_count}"
            )

            # Update KB statistics
            kb.total_chunks += len(created_chunks)
            kb.total_tokens += total_tokens
            await kb.save()
            logger.info(
                f"KB {kb.id} stats updated: chunks={kb.total_chunks}, tokens={kb.total_tokens}"
            )

            logger.info(
                f"Document {document_id} processed: "
                f"{len(created_chunks)} chunks, {total_tokens} tokens"
            )

            # Send success notification
            await _send_doc_indexed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                chunk_count=len(created_chunks),
                token_count=total_tokens,
                user_locale=user_locale,
            )

            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": len(created_chunks),
                "token_count": total_tokens,
            }

        except DimensionMismatchError as e:
            logger.error(f"Dimension mismatch for document {document_id}: {e}")

            # Update document status with specific error
            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_dimension_mismatch_error(
                document, user_locale
            )[:500]
            await document.save()

            # Send failure notification
            await _send_doc_failed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                error=document.error_message,
                user_locale=user_locale,
            )

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
                "error_type": "dimension_mismatch",
            }

        except Exception as e:
            logger.exception(f"Error processing document {document_id}: {e}")

            # Update document status
            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_generic_processing_error(
                document, user_locale
            )[:500]
            await document.save()

            # Send failure notification
            await _send_doc_failed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                error=document.error_message,
                user_locale=user_locale,
            )

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
            }

    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_process())


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def reprocess_document_task(self, document_id: str) -> dict:
    """
    Celery task to reprocess a document.

    Deletes existing chunks and re-processes the document.

    Args:
        document_id: UUID string of document to reprocess

    Returns:
        Result dict with status and stats
    """
    import asyncio

    async def _reprocess():
        doc_uuid = UUID(document_id)

        # Get document
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t("document_not_found", lang=default_lang),
            }

        kb = document.knowledge_base

        # Delete existing chunks (no team_id needed for deletion)
        vector_store = VectorStore()
        deleted_count = await vector_store.delete_document_vectors(doc_uuid)

        # Update KB stats
        kb.total_chunks -= document.chunk_count
        kb.total_tokens -= document.token_count
        await kb.save()

        # Reset document stats
        document.chunk_count = 0
        document.token_count = 0
        await document.save()

        logger.info(f"Deleted {deleted_count} chunks for document {document_id}")

        return {"status": "pending", "deleted_chunks": deleted_count}

    # Run delete, then process
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(_reprocess())

    if result.get("status") == "pending":
        # Chain to process task
        return process_document_task(document_id)

    return result


@shared_task
def process_url_document_task(document_id: str) -> dict:
    """
    Celery task to fetch and process a URL document.

    Args:
        document_id: UUID string of document to process

    Returns:
        Result dict with status and stats
    """
    # URL documents are processed the same way, just different extraction
    return process_document_task(document_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def rechunk_document_task(self, document_id: str) -> dict:
    """
    Celery task to rechunk a document with custom settings.

    Uses settings stored in document.metadata["rechunk_settings"].

    Args:
        document_id: UUID string of document to rechunk

    Returns:
        Result dict with status and stats
    """
    import asyncio

    async def _rechunk():
        doc_uuid = UUID(document_id)

        # Get document with uploader for locale
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base", "uploaded_by")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t("document_not_found", lang=default_lang),
            }

        kb = document.knowledge_base
        # Get uploader's locale for notifications
        user_locale = (
            getattr(document.uploaded_by, "locale", "en")
            if document.uploaded_by
            else "en"
        )

        try:
            # Update status to processing
            document.status = DocumentStatus.PROCESSING.value
            await document.save()

            # Get rechunk settings from metadata
            rechunk_settings = (document.metadata or {}).get("rechunk_settings", {})
            chunk_size = rechunk_settings.get("chunk_size", 1000)
            chunk_overlap = rechunk_settings.get("chunk_overlap", 100)
            separator = rechunk_settings.get("separator")
            clean_text_setting = rechunk_settings.get("clean_text", True)

            # Delete existing chunks and prepare for re-embedding with team_id for usage tracking
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None
            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                team_id=team_id,
            )
            deleted_count = await vector_store.delete_document_vectors(doc_uuid)

            # Update KB stats for deleted chunks
            kb.total_chunks = max(0, kb.total_chunks - document.chunk_count)
            kb.total_tokens = max(0, kb.total_tokens - document.token_count)
            await kb.save()

            logger.info(
                f"Deleted {deleted_count} chunks for rechunking document {document_id}"
            )

            # Extract text
            if document.file_path:
                text, _ = await document_processor.extract_text(
                    document.file_path,
                    document.doc_type,
                    clean_text=clean_text_setting,
                )
            elif document.source_url:
                text, _ = await document_processor.fetch_url_content(
                    document.source_url,
                    clean_text=clean_text_setting,
                )
            else:
                raise ValueError(t("document_missing_source", lang=user_locale))

            # Chunk text
            from app.services.document_processor import chunk_text

            chunks = chunk_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=[separator] if separator else None,
            )

            if not chunks:
                raise ValueError(t("document_no_chunks_generated", lang=user_locale))

            # Store chunks with embeddings and progress (pass kb_id for dimension management)
            async def _update_rechunk_progress(
                embedded: int, failed: int, total: int
            ) -> None:
                document.metadata = document.metadata or {}
                document.metadata["embed_progress"] = {
                    "embedded": embedded,
                    "failed": failed,
                    "total": total,
                }
                await document.save(update_fields=["metadata"])

            created_chunks = await vector_store.store_chunks_with_progress(
                document,
                chunks,
                kb_id=kb.id,
                progress_callback=_update_rechunk_progress,
            )

            # Check for failed chunks
            failed_chunks = [c for c in created_chunks if c.status == "failed"]
            total_tokens = sum(c.token_count for c in created_chunks)

            # Clear progress from metadata
            document.metadata = document.metadata or {}
            document.metadata.pop("embed_progress", None)

            if failed_chunks and len(failed_chunks) == len(created_chunks):
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "all_chunks_failed_to_embed",
                    lang=user_locale,
                    error=t("unknown_error_generic", lang=user_locale),
                )[:500]
            elif failed_chunks:
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "chunks_failed_to_embed",
                    lang=user_locale,
                    failed_count=len(failed_chunks),
                    total_chunks=len(created_chunks),
                    error=t("unknown_error_generic", lang=user_locale),
                )[:500]
            else:
                document.status = DocumentStatus.COMPLETED.value
                document.error_message = None

            document.chunk_count = len(created_chunks)
            document.token_count = total_tokens
            document.processed_at = datetime.now(timezone.utc)
            await document.save()

            # Update KB statistics
            kb.total_chunks += len(created_chunks)
            kb.total_tokens += total_tokens
            await kb.save()

            logger.info(
                f"Document {document_id} rechunked: "
                f"{len(created_chunks)} chunks, {total_tokens} tokens"
            )

            # Send success notification
            await _send_doc_indexed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                chunk_count=len(created_chunks),
                token_count=total_tokens,
                user_locale=user_locale,
            )

            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": len(created_chunks),
                "token_count": total_tokens,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }

        except DimensionMismatchError as e:
            logger.error(f"Dimension mismatch rechunking document {document_id}: {e}")

            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_dimension_mismatch_error(
                document, user_locale
            )[:500]
            await document.save()

            # Send failure notification
            await _send_doc_failed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                error=document.error_message,
                user_locale=user_locale,
            )

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
                "error_type": "dimension_mismatch",
            }

        except Exception as e:
            logger.exception(f"Error rechunking document {document_id}: {e}")

            # Update document status
            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_generic_processing_error(
                document, user_locale
            )[:500]
            await document.save()

            # Send failure notification
            await _send_doc_failed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                error=document.error_message,
                user_locale=user_locale,
            )

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
            }

    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_rechunk())


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def embed_document_chunks_task(self, document_id: str) -> dict:
    """
    Celery task to generate vector embeddings for existing document chunks.

    This is used when chunks are created directly from the frontend preview,
    and only need embedding generation (not text extraction/chunking).

    Args:
        document_id: UUID string of document whose chunks need embedding

    Returns:
        Result dict with status and stats
    """
    import asyncio

    async def _embed():
        from app.models.knowledge_base import DocumentChunk

        doc_uuid = UUID(document_id)

        # Get document with KB and uploader for locale
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base", "uploaded_by")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t("document_not_found", lang=default_lang),
            }

        kb = document.knowledge_base
        # Get uploader's locale for notifications
        user_locale = (
            getattr(document.uploaded_by, "locale", "en")
            if document.uploaded_by
            else "en"
        )

        async def _refresh_kb_stats() -> None:
            docs = await Document.filter(
                knowledge_base_id=kb.id,
                status=DocumentStatus.COMPLETED.value,
            ).all()
            kb.total_chunks = sum(doc.chunk_count for doc in docs)
            kb.total_tokens = sum(doc.token_count for doc in docs)
            await kb.save()
            logger.info(
                f"KB {kb.id} stats refreshed: chunks={kb.total_chunks}, tokens={kb.total_tokens}"
            )

        try:
            # Get all chunks for this document
            chunks = await DocumentChunk.filter(document_id=doc_uuid).order_by(
                "chunk_index"
            )

            if not chunks:
                logger.warning(f"No chunks found for document {document_id}")
                default_lang = await get_default_language()
                document.status = DocumentStatus.ERROR.value
                document.error_message = t("no_chunks_to_embed", lang=default_lang)
                await document.save()
                return {
                    "status": "success",
                    "message": t("no_chunks_to_embed", lang=default_lang),
                    "embedded_count": 0,
                }

            # Initialize vector store with KB's embedding model and team ID for usage tracking
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None
            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                team_id=team_id,
            )

            # Generate embeddings and store vectors for each chunk with progress
            embedded_count = 0
            failed_count = 0
            last_error = None
            total_chunks = len(chunks)
            for chunk in chunks:
                try:
                    await vector_store.add_chunk_vector(kb.id, chunk)
                    chunk.status = "embedded"
                    chunk.error_message = None
                    await chunk.save(update_fields=["status", "error_message"])
                    embedded_count += 1
                except Exception as e:
                    failed_count += 1
                    last_error = str(e)
                    chunk.status = "failed"
                    chunk.error_message = _get_generic_processing_error(
                        document, user_locale
                    )[:500]
                    await chunk.save(update_fields=["status", "error_message"])
                    logger.error(f"Failed to embed chunk {chunk.id}: {e}")

                # Update progress in document metadata
                document.metadata = document.metadata or {}
                document.metadata["embed_progress"] = {
                    "embedded": embedded_count,
                    "failed": failed_count,
                    "total": total_chunks,
                }
                await document.save(update_fields=["metadata"])

            # Clear progress from metadata
            document.metadata = document.metadata or {}
            document.metadata.pop("embed_progress", None)

            # Check if embedding was successful
            if embedded_count == 0 and len(chunks) > 0:
                # All chunks failed - mark as error
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "all_chunks_failed_to_embed",
                    lang=user_locale,
                    error=last_error
                    or t("unknown_error_generic", lang=user_locale),
                )[:500]
                await document.save()

                logger.error(
                    f"Document {document_id} embedding failed: "
                    f"0/{len(chunks)} chunks embedded"
                )

                # Send failure notification
                localized_error = t(
                    "all_chunks_failed_to_embed",
                    lang=user_locale,
                    error=last_error
                    or t("unknown_error_generic", lang=user_locale),
                )
                await _send_doc_failed_notification(
                    document=document,
                    kb_name=kb.name,
                    team_id=kb.team_id,
                    error=localized_error,
                    user_locale=user_locale,
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": localized_error,
                    "embedded_count": 0,
                    "total_chunks": len(chunks),
                }

            # Check if there were any failures
            if failed_count > 0:
                # Partial failure - mark as error with details
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "chunks_failed_to_embed",
                    lang=user_locale,
                    failed_count=failed_count,
                    total_chunks=len(chunks),
                    error=last_error,
                )[:500]
                await document.save()

                await _refresh_kb_stats()

                logger.error(
                    f"Document {document_id} embedding partially failed: "
                    f"{embedded_count}/{len(chunks)} chunks embedded, {failed_count} failed"
                )

                # Send failure notification
                await _send_doc_failed_notification(
                    document=document,
                    kb_name=kb.name,
                    team_id=kb.team_id,
                    error=document.error_message,
                    user_locale=user_locale,
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": document.error_message,
                    "embedded_count": embedded_count,
                    "failed_count": failed_count,
                    "total_chunks": len(chunks),
                }

            # All chunks embedded successfully
            document.status = DocumentStatus.COMPLETED.value
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            await document.save()
            logger.info(
                f"Document {document_id} status updated: {document.status}, chunks={document.chunk_count}, tokens={document.token_count}"
            )

            # Update KB statistics
            await _refresh_kb_stats()

            logger.info(
                f"Document {document_id} embedding completed: "
                f"{embedded_count}/{len(chunks)} chunks embedded"
            )

            # Send success notification
            await _send_doc_indexed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                chunk_count=document.chunk_count,
                token_count=document.token_count,
                user_locale=user_locale,
            )

            return {
                "status": "success",
                "document_id": document_id,
                "embedded_count": embedded_count,
                "total_chunks": len(chunks),
            }

        except Exception as e:
            logger.exception(f"Error embedding document {document_id}: {e}")

            # Update document status to ERROR
            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_generic_processing_error(
                document, user_locale
            )[:500]
            await document.save()

            # Send failure notification
            await _send_doc_failed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                error=document.error_message,
                user_locale=user_locale,
            )

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
            }

    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_embed())


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def retry_failed_chunks_task(self, document_id: str) -> dict:
    """
    Celery task to retry embedding for failed chunks only.

    Args:
        document_id: UUID string of document with failed chunks

    Returns:
        Result dict with status and stats
    """
    import asyncio

    async def _retry():
        from app.models.knowledge_base import DocumentChunk

        doc_uuid = UUID(document_id)

        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base", "uploaded_by")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t("document_not_found", lang=default_lang),
            }

        kb = document.knowledge_base
        user_locale = (
            getattr(document.uploaded_by, "locale", "en")
            if document.uploaded_by
            else "en"
        )

        try:
            # Update status to processing
            document.status = DocumentStatus.PROCESSING.value
            await document.save()

            # Get only failed chunks
            failed_chunks = await DocumentChunk.filter(
                document_id=doc_uuid, status="failed"
            ).order_by("chunk_index")

            if not failed_chunks:
                default_lang = await get_default_language()
                document.status = DocumentStatus.COMPLETED.value
                document.error_message = None
                await document.save()
                return {
                    "status": "success",
                    "document_id": document_id,
                    "message": t("no_failed_chunks", lang=default_lang),
                    "retried_count": 0,
                }

            # Get total chunk count for progress
            total_chunks = await DocumentChunk.filter(document_id=doc_uuid).count()

            # Initialize vector store
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None
            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                team_id=team_id,
            )

            # Count already-embedded chunks
            already_embedded = await DocumentChunk.filter(
                document_id=doc_uuid, status="embedded"
            ).count()

            embedded_count = already_embedded
            still_failed = 0
            last_error = None

            for chunk in failed_chunks:
                try:
                    await vector_store.add_chunk_vector(kb.id, chunk)
                    chunk.status = "embedded"
                    chunk.error_message = None
                    await chunk.save(update_fields=["status", "error_message"])
                    embedded_count += 1
                except Exception as e:
                    still_failed += 1
                    last_error = str(e)
                    chunk.error_message = _get_generic_processing_error(
                        document, user_locale
                    )[:500]
                    await chunk.save(update_fields=["error_message"])
                    logger.error(f"Retry failed for chunk {chunk.id}: {e}")

                # Update progress
                document.metadata = document.metadata or {}
                document.metadata["embed_progress"] = {
                    "embedded": embedded_count,
                    "failed": still_failed,
                    "total": total_chunks,
                }
                await document.save(update_fields=["metadata"])

            # Clear progress
            document.metadata = document.metadata or {}
            document.metadata.pop("embed_progress", None)

            if still_failed > 0:
                document.status = DocumentStatus.ERROR.value
                document.error_message = t(
                    "chunks_still_failed_after_retry",
                    lang=user_locale,
                    failed_count=still_failed,
                    total_chunks=total_chunks,
                    error=last_error
                    or t("unknown_error_generic", lang=user_locale),
                )[:500]
                await document.save()

                await _send_doc_failed_notification(
                    document=document,
                    kb_name=kb.name,
                    team_id=kb.team_id,
                    error=document.error_message,
                    user_locale=user_locale,
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": document.error_message,
                    "retried_count": len(failed_chunks),
                    "still_failed": still_failed,
                }

            # All retries succeeded
            document.status = DocumentStatus.COMPLETED.value
            document.error_message = None
            document.processed_at = datetime.now(timezone.utc)
            await document.save()

            # Refresh KB stats
            docs = await Document.filter(
                knowledge_base_id=kb.id,
                status=DocumentStatus.COMPLETED.value,
            ).all()
            kb.total_chunks = sum(doc.chunk_count for doc in docs)
            kb.total_tokens = sum(doc.token_count for doc in docs)
            await kb.save()

            await _send_doc_indexed_notification(
                document=document,
                kb_name=kb.name,
                team_id=kb.team_id,
                chunk_count=document.chunk_count,
                token_count=document.token_count,
                user_locale=user_locale,
            )

            return {
                "status": "success",
                "document_id": document_id,
                "retried_count": len(failed_chunks),
                "total_chunks": total_chunks,
            }

        except Exception as e:
            logger.exception(
                f"Error retrying failed chunks for document {document_id}: {e}"
            )
            document.status = DocumentStatus.ERROR.value
            document.error_message = _get_generic_processing_error(
                document, user_locale
            )[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": document.error_message,
            }

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_retry())
