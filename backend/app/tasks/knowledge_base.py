"""
Celery tasks for knowledge base document processing.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task

from app.models.knowledge_base import (
    Document,
    DocumentStatus,
)
from app.services.document_processor import document_processor
from app.services.vector_store import VectorStore, DimensionMismatchError

logger = logging.getLogger(__name__)


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

        # Get document
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}

        kb = document.knowledge_base

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
                raise ValueError("Document has no file_path or source_url")

            # Update document metadata
            document.metadata = document.metadata or {}
            document.metadata.update(metadata)

            # Get chunking settings from document metadata first, then fallback to KB settings
            doc_meta = document.metadata or {}
            kb_settings = kb.settings or {}
            chunk_size = doc_meta.get("chunk_size") or kb_settings.get(
                "chunk_size", 500
            )
            chunk_overlap = doc_meta.get("chunk_overlap") or kb_settings.get(
                "chunk_overlap", 50
            )
            separator = doc_meta.get("separator") or kb_settings.get("separator")

            # Create chunker with settings
            from app.services.document_processor import TextChunker

            chunker = TextChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=[separator] if separator else None,
            )

            # Chunk text
            chunks = chunker.chunk_text(text)

            if not chunks:
                raise ValueError("No chunks generated from document")

            # Initialize vector store with KB's embedding model and team ID for usage tracking
            embedding_model_id = (
                str(kb.embedding_model_id) if kb.embedding_model_id else None
            )
            team_id = str(kb.team_id) if kb.team_id else None
            vector_store = VectorStore(
                embedding_model_id=embedding_model_id,
                team_id=team_id,
            )

            # Store chunks with embeddings
            # Pass kb_id to enable dimension management:
            # - First document sets the KB's embedding dimension
            # - Subsequent documents must match the dimension
            created_chunks = await vector_store.store_chunks(document, chunks, kb_id=kb.id)

            # Calculate totals
            total_tokens = sum(c.token_count for c in created_chunks)

            # Update document
            document.status = DocumentStatus.COMPLETED.value
            document.chunk_count = len(created_chunks)
            document.token_count = total_tokens
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            await document.save()

            # Update KB statistics
            kb.total_chunks += len(created_chunks)
            kb.total_tokens += total_tokens
            await kb.save()

            logger.info(
                f"Document {document_id} processed: "
                f"{len(created_chunks)} chunks, {total_tokens} tokens"
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
            document.error_message = str(e)[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": str(e),
                "error_type": "dimension_mismatch",
            }

        except Exception as e:
            logger.exception(f"Error processing document {document_id}: {e}")

            # Update document status
            document.status = DocumentStatus.ERROR.value
            document.error_message = str(e)[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": str(e),
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
            return {"status": "error", "message": "Document not found"}

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

        # Get document
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}

        kb = document.knowledge_base

        try:
            # Update status to processing
            document.status = DocumentStatus.PROCESSING.value
            await document.save()

            # Get rechunk settings from metadata
            rechunk_settings = (document.metadata or {}).get("rechunk_settings", {})
            chunk_size = rechunk_settings.get("chunk_size", 500)
            chunk_overlap = rechunk_settings.get("chunk_overlap", 50)
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
                raise ValueError("Document has no file_path or source_url")

            # Create chunker with new settings
            from app.services.document_processor import TextChunker

            chunker = TextChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=[separator] if separator else None,
            )

            # Chunk text
            chunks = chunker.chunk_text(text)

            if not chunks:
                raise ValueError("No chunks generated from document")

            # Store chunks with embeddings (pass kb_id for dimension management)
            created_chunks = await vector_store.store_chunks(document, chunks, kb_id=kb.id)

            # Calculate totals
            total_tokens = sum(c.token_count for c in created_chunks)

            # Update document
            document.status = DocumentStatus.COMPLETED.value
            document.chunk_count = len(created_chunks)
            document.token_count = total_tokens
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            await document.save()

            # Update KB statistics
            kb.total_chunks += len(created_chunks)
            kb.total_tokens += total_tokens
            await kb.save()

            logger.info(
                f"Document {document_id} rechunked: "
                f"{len(created_chunks)} chunks, {total_tokens} tokens"
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
            document.error_message = str(e)[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": str(e),
                "error_type": "dimension_mismatch",
            }

        except Exception as e:
            logger.exception(f"Error rechunking document {document_id}: {e}")

            # Update document status
            document.status = DocumentStatus.ERROR.value
            document.error_message = str(e)[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": str(e),
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

        # Get document with KB
        document = (
            await Document.filter(id=doc_uuid)
            .prefetch_related("knowledge_base")
            .first()
        )

        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}

        kb = document.knowledge_base

        try:
            # Get all chunks for this document
            chunks = await DocumentChunk.filter(document_id=doc_uuid).order_by(
                "chunk_index"
            )

            if not chunks:
                logger.warning(f"No chunks found for document {document_id}")
                return {
                    "status": "success",
                    "message": "No chunks to embed",
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

            # Generate embeddings and store vectors for each chunk
            embedded_count = 0
            failed_count = 0
            last_error = None
            for chunk in chunks:
                try:
                    await vector_store.add_chunk_vector(kb.id, chunk)
                    embedded_count += 1
                except Exception as e:
                    failed_count += 1
                    last_error = str(e)
                    logger.error(f"Failed to embed chunk {chunk.id}: {e}")

            # Check if embedding was successful
            if embedded_count == 0 and len(chunks) > 0:
                # All chunks failed - mark as error
                document.status = DocumentStatus.ERROR.value
                document.error_message = f"All {len(chunks)} chunks failed to embed: {last_error}"[:500]
                await document.save()

                logger.error(
                    f"Document {document_id} embedding failed: "
                    f"0/{len(chunks)} chunks embedded"
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": f"All chunks failed to embed: {last_error}",
                    "embedded_count": 0,
                    "total_chunks": len(chunks),
                }

            # Check if there were any failures
            if failed_count > 0:
                # Partial failure - mark as error with details
                document.status = DocumentStatus.ERROR.value
                document.error_message = f"{failed_count}/{len(chunks)} chunks failed to embed: {last_error}"[:500]
                await document.save()

                # Still update KB statistics for successful chunks
                kb.total_chunks += embedded_count
                kb.total_tokens += int(document.token_count * embedded_count / len(chunks))
                await kb.save()

                logger.error(
                    f"Document {document_id} embedding partially failed: "
                    f"{embedded_count}/{len(chunks)} chunks embedded, {failed_count} failed"
                )

                return {
                    "status": "error",
                    "document_id": document_id,
                    "message": f"{failed_count}/{len(chunks)} chunks failed to embed: {last_error}",
                    "embedded_count": embedded_count,
                    "failed_count": failed_count,
                    "total_chunks": len(chunks),
                }

            # All chunks embedded successfully
            document.status = DocumentStatus.COMPLETED.value
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            await document.save()

            # Update KB statistics
            kb.total_chunks += len(chunks)
            kb.total_tokens += document.token_count
            await kb.save()

            logger.info(
                f"Document {document_id} embedding completed: "
                f"{embedded_count}/{len(chunks)} chunks embedded"
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
            document.error_message = str(e)[:500]
            await document.save()

            return {
                "status": "error",
                "document_id": document_id,
                "message": str(e),
            }

    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_embed())
