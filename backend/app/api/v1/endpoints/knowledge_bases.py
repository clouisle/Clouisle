"""
Knowledge Base API endpoints.
Provides CRUD operations for knowledge bases and documents.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Body
from fastapi.responses import FileResponse
from tortoise.expressions import F

from app.api import deps
from app.models.user import User, Team, TeamMember
from app.models.model import TeamModel, Model
from app.models.knowledge_base import (
    KnowledgeBase,
    Document,
    DocumentChunk,
    KnowledgeBaseStatus,
    DocumentStatus,
    DocumentType,
)
from app.schemas.knowledge_base import (
    KnowledgeBase as KnowledgeBaseSchema,
    KnowledgeBaseList,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseStats,
    EmbeddingModelInfo,
    RerankModelInfo,
    Document as DocumentSchema,
    DocumentList,
    DocumentCreate,
    DocumentUpdate,
    DocumentChunk as ChunkSchema,
    DocumentChunkUpdate,
    ProcessRequest,
    ProcessWithChunksRequest,
    RechunkRequest,
    SearchRequest,
    SearchResponse,
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    ChunkPreviewItem,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.document_processor import document_processor
from app.services.vector_store import VectorStore, DimensionMismatchError

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


async def check_team_access(
    team_id: UUID, user: User, require_admin: bool = False
) -> Team:
    """
    Check if user has access to the team.
    Returns the team if access is granted.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return team

    membership = await TeamMember.filter(team=team, user=user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=403,
        )

    if require_admin and membership.role not in ["owner", "admin"]:
        raise BusinessError(
            code=ResponseCode.TEAM_ADMIN_REQUIRED,
            msg_key="team_admin_required",
            status_code=403,
        )

    return team


async def get_embedding_model_info(model_id: UUID | None) -> EmbeddingModelInfo | None:
    """获取嵌入模型简要信息"""
    if not model_id:
        return None
    model = await Model.filter(id=model_id).first()
    if not model:
        return None
    return EmbeddingModelInfo(
        id=model.id,
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
    )


async def get_rerank_model_info(model_id: UUID | None) -> RerankModelInfo | None:
    """获取重排序模型简要信息"""
    if not model_id:
        return None
    model = await Model.filter(id=model_id).first()
    if not model:
        return None
    return RerankModelInfo(
        id=model.id,
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
    )


def _build_model_info(model: Model | None) -> dict | None:
    """构建模型简要信息"""
    if not model:
        return None
    return {
        "id": model.id,
        "name": model.name,
        "provider": model.provider,
        "model_id": model.model_id,
    }


async def kb_with_model_info(kb: KnowledgeBase) -> dict:
    """构建包含嵌入模型和重排序模型信息的知识库响应"""
    embedding_model = await get_embedding_model_info(kb.embedding_model_id)
    rerank_model = await get_rerank_model_info(kb.rerank_model_id)
    kb_data = KnowledgeBaseSchema.model_validate(kb).model_dump()
    kb_data["embedding_model"] = embedding_model
    kb_data["rerank_model"] = rerank_model
    return kb_data


async def ensure_team_authorized_model(
    team_id: UUID, model_id: UUID | None, model_type: str
) -> Model | None:
    """检查团队是否已授权指定类型的模型。"""
    if not model_id:
        return None

    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.MODEL_NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    if model.model_type != model_type:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg=f"Model {model.name} is not a {model_type} model",
        )

    team_model = await TeamModel.filter(
        team_id=team_id,
        model_id=model_id,
        is_enabled=True,
    ).first()
    if not team_model:
        raise BusinessError(
            code=ResponseCode.MODEL_NOT_AUTHORIZED,
            msg_key="model_not_authorized",
        )

    return model


async def check_kb_access(
    kb_id: UUID, user: User, require_write: bool = False
) -> KnowledgeBase:
    """
    Check if user has access to the knowledge base.
    Returns the knowledge base if access is granted.
    """
    kb = (
        await KnowledgeBase.filter(id=kb_id)
        .prefetch_related("team", "created_by")
        .first()
    )
    if not kb:
        raise BusinessError(
            code=ResponseCode.KB_NOT_FOUND,
            msg_key="kb_not_found",
            status_code=404,
        )

    # Check team access
    await check_team_access(kb.team.id, user, require_admin=require_write)
    return kb


# ============ Knowledge Base CRUD ============


@router.get("", response_model=Response[PageData[KnowledgeBaseList]])
async def list_knowledge_bases(
    team_id: UUID | None = None,
    search: str | None = None,
    status: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    List knowledge bases.
    If team_id is provided, list KBs for that team (requires team membership).
    Otherwise, list all KBs the user has access to.
    """
    query = KnowledgeBase.all()

    if team_id:
        # Check team access
        await check_team_access(team_id, current_user)
        query = query.filter(team_id=team_id)
    elif not current_user.is_superuser:
        # Get all teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        query = query.filter(team_id__in=memberships)

    if search:
        query = query.filter(name__icontains=search)

    if status:
        query = query.filter(status__in=status)

    total = await query.count()
    skip = (page - 1) * page_size
    kbs = (
        await query.prefetch_related("team", "created_by").offset(skip).limit(page_size)
    )

    # 为每个知识库添加模型信息
    model_ids: list[UUID] = []
    for kb in kbs:
        if kb.embedding_model_id:
            model_ids.append(kb.embedding_model_id)
        if kb.rerank_model_id:
            model_ids.append(kb.rerank_model_id)
    models = await Model.filter(id__in=model_ids).all()
    model_map = {model.id: model for model in models}

    kb_list = []
    for kb in kbs:
        kb_data = KnowledgeBaseList.model_validate(kb).model_dump()
        kb_data["embedding_model"] = _build_model_info(
            model_map.get(kb.embedding_model_id) if kb.embedding_model_id else None
        )
        kb_data["rerank_model"] = _build_model_info(
            model_map.get(kb.rerank_model_id) if kb.rerank_model_id else None
        )
        kb_list.append(kb_data)

    return success(
        data={
            "items": kb_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[KnowledgeBaseSchema])
async def create_knowledge_base(
    *,
    kb_in: KnowledgeBaseCreate,
    current_user: User = Depends(deps.PermissionChecker("kb:create")),
) -> Any:
    """
    Create a new knowledge base.
    Requires membership in the target team.
    """
    # Check team access
    team = await check_team_access(kb_in.team_id, current_user)

    # Check if name already exists in team
    existing = await KnowledgeBase.filter(
        team_id=kb_in.team_id, name=kb_in.name
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.KB_NAME_EXISTS,
            msg_key="kb_name_exists",
        )

    await ensure_team_authorized_model(
        kb_in.team_id, kb_in.embedding_model_id, "embedding"
    )
    await ensure_team_authorized_model(kb_in.team_id, kb_in.rerank_model_id, "rerank")

    # Create knowledge base
    kb = await KnowledgeBase.create(
        name=kb_in.name,
        description=kb_in.description,
        icon=kb_in.icon,
        team=team,
        created_by=current_user,
        embedding_model_id=kb_in.embedding_model_id,
        rerank_model_id=kb_in.rerank_model_id,
        settings=kb_in.settings.model_dump() if kb_in.settings else None,
    )

    # Reload with relations
    kb = await KnowledgeBase.get(id=kb.id).prefetch_related("team", "created_by")
    kb_data = await kb_with_model_info(kb)
    return success(data=kb_data, msg_key="kb_created")


@router.get("/{kb_id}", response_model=Response[KnowledgeBaseSchema])
async def get_knowledge_base(
    kb_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    Get knowledge base by ID.
    """
    kb = await check_kb_access(kb_id, current_user)
    kb_data = await kb_with_model_info(kb)
    return success(data=kb_data)


@router.put("/{kb_id}", response_model=Response[KnowledgeBaseSchema])
async def update_knowledge_base(
    *,
    kb_id: UUID,
    kb_in: KnowledgeBaseUpdate,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Update knowledge base.
    Requires admin permission in the team.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    # Update fields
    if kb_in.name is not None:
        # Check name uniqueness
        existing = (
            await KnowledgeBase.filter(team_id=kb.team.id, name=kb_in.name)
            .exclude(id=kb_id)
            .first()
        )
        if existing:
            raise BusinessError(
                code=ResponseCode.KB_NAME_EXISTS,
                msg_key="kb_name_exists",
            )
        kb.name = kb_in.name

    if kb_in.description is not None:
        kb.description = kb_in.description
    if kb_in.icon is not None:
        kb.icon = kb_in.icon
    fields_set = kb_in.model_fields_set

    # embedding_model_id 创建后不允许修改，已有文档的向量与模型绑定
    if (
        "embedding_model_id" in fields_set
        and kb_in.embedding_model_id != kb.embedding_model_id
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg="Embedding model cannot be changed after knowledge base creation",
        )
    if "rerank_model_id" in fields_set:
        if kb_in.rerank_model_id is not None:
            await ensure_team_authorized_model(
                kb.team.id, kb_in.rerank_model_id, "rerank"
            )
        kb.rerank_model_id = kb_in.rerank_model_id
    if kb_in.settings is not None:
        kb.settings = kb_in.settings.model_dump()
    if kb_in.status is not None and kb_in.status in [
        KnowledgeBaseStatus.ACTIVE.value,
        KnowledgeBaseStatus.ARCHIVED.value,
    ]:
        kb.status = kb_in.status

    await kb.save()

    # Reload with relations
    kb = await KnowledgeBase.get(id=kb_id).prefetch_related("team", "created_by")
    kb_data = await kb_with_model_info(kb)
    return success(data=kb_data, msg_key="kb_updated")


@router.delete("/{kb_id}", response_model=Response[dict])
async def delete_knowledge_base(
    kb_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:delete")),
) -> Any:
    """
    Delete knowledge base and all its documents.
    Requires admin permission in the team.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    # Delete all documents and chunks (cascades)
    await kb.delete()

    return success(data={"id": str(kb_id)}, msg_key="kb_deleted")


@router.get("/{kb_id}/stats", response_model=Response[KnowledgeBaseStats])
async def get_knowledge_base_stats(
    kb_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    Get knowledge base statistics.
    Returns actual counts from database, not cached values.
    """
    kb = await check_kb_access(kb_id, current_user)

    # Get document counts by status
    docs = await Document.filter(knowledge_base_id=kb_id).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for doc in docs:
        by_status[doc.status] = by_status.get(doc.status, 0) + 1
        by_type[doc.doc_type] = by_type.get(doc.doc_type, 0) + 1

    # Use actual document count instead of cached value
    actual_doc_count = len(docs)

    # Calculate actual chunks and tokens from completed documents
    total_chunks = sum(doc.chunk_count for doc in docs)
    total_tokens = sum(doc.token_count for doc in docs)

    # Sync cached values if they differ
    if (
        kb.document_count != actual_doc_count
        or kb.total_chunks != total_chunks
        or kb.total_tokens != total_tokens
    ):
        kb.document_count = actual_doc_count
        kb.total_chunks = total_chunks
        kb.total_tokens = total_tokens
        await kb.save()

    # Get embedding statistics
    vector_store = VectorStore()
    embedding_stats = await vector_store.get_embedding_stats(kb_id)

    return success(
        data={
            "id": kb.id,
            "name": kb.name,
            "document_count": actual_doc_count,
            "total_chunks": total_chunks,
            "total_tokens": total_tokens,
            "documents_by_status": by_status,
            "documents_by_type": by_type,
            "embedding_dimension": kb.embedding_dimension,
            "embedding_stats": embedding_stats,
        }
    )


# ============ Document CRUD ============


@router.get("/{kb_id}/documents", response_model=Response[PageData[DocumentList]])
async def list_documents(
    kb_id: UUID,
    search: str | None = None,
    status: list[str] | None = None,
    doc_type: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    List documents in a knowledge base.
    """
    await check_kb_access(kb_id, current_user)

    query = Document.filter(knowledge_base_id=kb_id)
    if search:
        query = query.filter(name__icontains=search)
    if status:
        query = query.filter(status__in=status)
    if doc_type:
        query = query.filter(doc_type__in=doc_type)

    total = await query.count()
    skip = (page - 1) * page_size
    docs = await query.offset(skip).limit(page_size)

    return success(
        data={
            "items": docs,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/{kb_id}/documents/upload", response_model=Response[DocumentSchema])
async def upload_document(
    kb_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Upload a document to the knowledge base.
    Supported formats: PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON.

    The document will be created with 'pending' status.
    Use the /process endpoint to start processing after configuring chunk settings.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    # Validate file type
    if not file.filename:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_name_required",
        )

    # Determine document type
    doc_type = document_processor.get_document_type(file.filename, file.content_type)
    if not doc_type:
        raise BusinessError(
            code=ResponseCode.INVALID_DOCUMENT_TYPE,
            msg_key="invalid_document_type",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Save file to storage
    file_path = document_processor.get_storage_path(kb_id, file.filename)
    await document_processor.save_file(content, file_path)

    # Create document record (status: pending, not auto-processing)
    doc = await Document.create(
        knowledge_base=kb,
        name=file.filename,
        doc_type=doc_type,
        file_path=file_path,
        file_size=file_size,
        status=DocumentStatus.PENDING.value,
        uploaded_by=current_user,
    )

    # Update KB document count
    kb.document_count += 1
    await kb.save()

    # Reload with relations
    doc = await Document.get(id=doc.id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_uploaded")


@router.post("/{kb_id}/documents/url", response_model=Response[DocumentSchema])
async def add_url_document(
    kb_id: UUID,
    doc_in: DocumentCreate,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Add a URL-based document to the knowledge base.
    The content will be fetched and processed asynchronously.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    if not doc_in.source_url:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="source_url_required",
        )

    # Create document record
    doc = await Document.create(
        knowledge_base=kb,
        name=doc_in.name,
        doc_type=DocumentType.URL.value,
        source_url=doc_in.source_url,
        status=DocumentStatus.PENDING.value,
        uploaded_by=current_user,
    )

    # Update KB document count
    kb.document_count += 1
    await kb.save()

    # NOTE: Do NOT auto-trigger processing task for URL documents.
    # The user will be redirected to the preview editor to configure
    # chunking settings before manually triggering processing.

    # Reload with relations
    doc = await Document.get(id=doc.id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_created")


@router.get("/{kb_id}/documents/{doc_id}", response_model=Response[DocumentSchema])
async def get_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    Get document details.
    """
    await check_kb_access(kb_id, current_user)

    doc = (
        await Document.filter(id=doc_id, knowledge_base_id=kb_id)
        .prefetch_related("uploaded_by")
        .first()
    )
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    return success(data=doc)


@router.put("/{kb_id}/documents/{doc_id}", response_model=Response[DocumentSchema])
async def update_document(
    *,
    kb_id: UUID,
    doc_id: UUID,
    doc_in: DocumentUpdate,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Update document name.
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    if doc_in.name is not None:
        doc.name = doc_in.name
        await doc.save()

    doc = await Document.get(id=doc_id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_updated")


@router.delete("/{kb_id}/documents/{doc_id}", response_model=Response[dict])
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:delete")),
) -> Any:
    """
    Delete a document and all its chunks.
    Also cancels any pending/running Celery tasks.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    # Cancel Celery task if document is pending or processing
    if doc.status in [DocumentStatus.PENDING.value, DocumentStatus.PROCESSING.value]:
        task_id = (doc.metadata or {}).get("task_id")
        if task_id:
            try:
                from app.core.celery import celery_app

                celery_app.control.revoke(task_id, terminate=True)
                logger.info(f"Revoked Celery task {task_id} for document {doc_id}")
            except Exception as e:
                logger.warning(f"Failed to revoke Celery task {task_id}: {e}")

    # Delete vectors
    vector_store = VectorStore()
    await vector_store.delete_document_vectors(doc_id)

    # Delete file if exists
    if doc.file_path:
        document_processor.delete_file(doc.file_path)

    # Update KB statistics
    kb.document_count = max(0, kb.document_count - 1)
    kb.total_chunks = max(0, kb.total_chunks - doc.chunk_count)
    kb.total_tokens = max(0, kb.total_tokens - doc.token_count)
    await kb.save()

    # Delete document (chunks cascade)
    await doc.delete()

    return success(data={"id": str(doc_id)}, msg_key="document_deleted")


@router.get("/{kb_id}/documents/{doc_id}/download")
async def download_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> FileResponse:
    """
    Download the original document file.
    """
    await check_kb_access(kb_id, current_user, require_write=False)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    if not doc.file_path:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_not_found",
            status_code=404,
        )

    import os

    if not os.path.exists(doc.file_path):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_not_found",
            status_code=404,
        )

    # Determine media type based on document type
    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain",
        "md": "text/markdown",
        "html": "text/html",
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "json": "application/json",
    }
    media_type = media_types.get(doc.doc_type, "application/octet-stream")

    return FileResponse(
        path=doc.file_path,
        filename=doc.name,
        media_type=media_type,
    )


@router.post(
    "/{kb_id}/documents/{doc_id}/process", response_model=Response[DocumentSchema]
)
async def process_document(
    kb_id: UUID,
    doc_id: UUID,
    process_in: Optional[ProcessRequest] = Body(default=None),
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Start processing a pending document.
    Allows configuring chunk settings before processing.
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    if doc.status != DocumentStatus.PENDING.value:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="document_not_pending",
        )

    # Store chunk settings in document metadata for processing
    doc.metadata = doc.metadata or {}
    if process_in is not None:
        if process_in.chunk_size is not None:
            doc.metadata["chunk_size"] = process_in.chunk_size
        if process_in.chunk_overlap is not None:
            doc.metadata["chunk_overlap"] = process_in.chunk_overlap
        if process_in.separator is not None:
            doc.metadata["separator"] = process_in.separator
        if process_in.clean_text is not None:
            doc.metadata["clean_text"] = process_in.clean_text
    await doc.save()

    # Trigger async document processing task
    try:
        from app.tasks.knowledge_base import process_document_task

        task = process_document_task.delay(str(doc.id))
        # Save task ID for potential cancellation
        doc.metadata["task_id"] = task.id
        await doc.save()
    except Exception:
        logger.warning("Celery task not dispatched - worker may not be running")

    # Reload with relations
    doc = await Document.get(id=doc.id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_processing_started")


@router.post(
    "/{kb_id}/documents/{doc_id}/process-with-chunks",
    response_model=Response[DocumentSchema],
)
async def process_document_with_chunks(
    *,
    kb_id: UUID,
    doc_id: UUID,
    request: ProcessWithChunksRequest,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Process a document with pre-defined chunks from the frontend.

    This endpoint accepts chunks that have been edited/created in the frontend preview,
    saves them directly to the database, and triggers vector embedding generation.

    This bypasses the server-side chunking process, allowing users to have full
    control over how their documents are segmented.
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    # Allow reprocessing for pending, completed, and error status documents
    # Only block if currently processing
    if doc.status == DocumentStatus.PROCESSING.value:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="document_is_processing",
        )

    # Cancel existing task if any (for reprocessing completed/error documents)
    old_task_id = (doc.metadata or {}).get("embed_task_id")
    if old_task_id:
        try:
            from app.core.celery import celery_app

            celery_app.control.revoke(old_task_id, terminate=True)
        except Exception:
            pass

    # Delete existing vectors for reprocessing (if document was completed)
    if doc.status == DocumentStatus.COMPLETED.value:
        try:
            from app.services.vector_store import vector_store

            # Delete old vectors (chunks) by document ID
            await vector_store.delete_document_vectors(doc.id)
            logger.info(f"Deleted existing vectors for document {doc.id}")
        except Exception as e:
            logger.warning(f"Failed to delete existing vectors: {e}")

    # Update document status to processing
    doc.status = DocumentStatus.PROCESSING.value
    doc.error_message = None  # Clear previous error
    await doc.save()

    try:
        # Delete any existing chunks (in case of reprocessing)
        await DocumentChunk.filter(document_id=doc.id).delete()

        # Create chunks from frontend data
        total_tokens = 0
        total_chars = 0
        chunks_created = []

        for chunk_input in request.chunks:
            content = chunk_input.content.strip()
            if not content:
                continue

            char_count = len(content)
            token_count = char_count // 4  # Approximate token count

            chunk = await DocumentChunk.create(
                document=doc,
                content=content,
                chunk_index=chunk_input.chunk_index,
                token_count=token_count,
                metadata={"source": "frontend_preview"},
            )
            chunks_created.append(chunk)
            total_tokens += token_count
            total_chars += char_count

        # Update document statistics (keep status as PROCESSING, Celery task will set COMPLETED)
        doc.chunk_count = len(chunks_created)
        doc.token_count = total_tokens
        # Don't set status to COMPLETED here, let Celery task do it after embedding
        await doc.save()

        # Note: KB statistics will be updated by Celery task after successful embedding

        # Trigger async vector embedding task
        try:
            # Import celery_app first to ensure tasks are bound to the correct app
            from app.core.celery import celery_app  # noqa: F401
            from app.tasks.knowledge_base import embed_document_chunks_task

            logger.info(f"Dispatching embed_document_chunks_task for document {doc.id}")
            logger.info(
                f"Task app broker: {embed_document_chunks_task.app.conf.broker_url}"
            )
            task = embed_document_chunks_task.delay(str(doc.id))
            logger.info(f"Task dispatched successfully, task_id: {task.id}")
            doc.metadata = doc.metadata or {}
            doc.metadata["embed_task_id"] = task.id
            await doc.save()
        except Exception as e:
            logger.error(f"Vector embedding task not dispatched: {e}", exc_info=True)
            # If task dispatch fails, mark as error and raise exception
            doc.status = DocumentStatus.ERROR.value
            doc.error_message = f"Failed to start embedding task: {e}"
            await doc.save()
            raise BusinessError(
                code=ResponseCode.UNKNOWN_ERROR,
                msg_key="task_dispatch_failed",
            )

        # Reload with relations
        doc = await Document.get(id=doc.id).prefetch_related("uploaded_by")
        return success(data=doc, msg_key="document_processing_started")

    except Exception as e:
        # On error, reset document status
        doc.status = DocumentStatus.ERROR.value
        doc.error_message = str(e)
        await doc.save()
        logger.exception(f"Error processing document with chunks: {e}")
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="document_process_failed",
        )


@router.post(
    "/{kb_id}/documents/{doc_id}/preview-chunks",
    response_model=Response[ChunkPreviewResponse],
)
async def preview_document_chunks(
    *,
    kb_id: UUID,
    doc_id: UUID,
    preview_in: ChunkPreviewRequest,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    Preview how a document will be chunked with given settings.
    This extracts the text and generates chunks without saving them.

    Returns a preview of the chunking results with statistics.
    """
    await check_kb_access(kb_id, current_user)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    # Document must have a file path or source URL
    if not doc.file_path and not doc.source_url:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="document_no_source",
        )

    try:
        # Extract text from document
        if doc.file_path:
            text, _ = await document_processor.extract_text(
                doc.file_path,
                doc.doc_type,
                clean_text=preview_in.clean_text,
            )
        else:
            text, _ = await document_processor.fetch_url_content(
                doc.source_url,  # type: ignore[arg-type]
                clean_text=preview_in.clean_text,
            )

        # Create chunks with preview settings
        from app.services.document_processor import chunk_text

        separators = [preview_in.separator] if preview_in.separator else None
        chunks = chunk_text(
            text,
            chunk_size=preview_in.chunk_size,
            chunk_overlap=preview_in.chunk_overlap,
            separators=separators,
        )

        # Build preview response
        preview_items = [
            ChunkPreviewItem(
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                token_count=chunk["token_count"],
                char_count=chunk["char_count"],
                overlap_length=chunk.get("overlap_length", 0),
            )
            for chunk in chunks
        ]

        total_tokens = sum(c["token_count"] for c in chunks)
        total_chars = sum(c["char_count"] for c in chunks)

        return success(
            data=ChunkPreviewResponse(
                total_chunks=len(chunks),
                total_tokens=total_tokens,
                total_chars=total_chars,
                chunks=preview_items,
            ),
            msg_key="chunk_preview_generated",
        )

    except Exception as e:
        logger.exception(f"Error previewing chunks for document {doc_id}: {e}")
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="chunk_preview_failed",
        )


@router.post(
    "/{kb_id}/documents/{doc_id}/reprocess", response_model=Response[DocumentSchema]
)
async def reprocess_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Reprocess a document (re-chunk and re-embed).
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    # Cancel existing task if any
    old_task_id = (doc.metadata or {}).get("task_id")
    if old_task_id and doc.status in [
        DocumentStatus.PENDING.value,
        DocumentStatus.PROCESSING.value,
    ]:
        try:
            from app.core.celery import celery_app

            celery_app.control.revoke(old_task_id, terminate=True)
        except Exception as e:
            logger.warning(f"Failed to revoke old task {old_task_id}: {e}")

    # Reset status
    doc.status = DocumentStatus.PENDING.value
    doc.error_message = None  # type: ignore[assignment]
    await doc.save()

    # Trigger reprocessing task
    try:
        from app.tasks.knowledge_base import reprocess_document_task

        task = reprocess_document_task.delay(str(doc.id))
        # Save new task ID
        doc.metadata = doc.metadata or {}
        doc.metadata["task_id"] = task.id
        await doc.save()
    except Exception:
        import logging

        logging.warning("Celery task not dispatched - worker may not be running")

    doc = await Document.get(id=doc_id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_reprocess_started")


@router.post(
    "/{kb_id}/documents/{doc_id}/retry-failed-chunks",
    response_model=Response[DocumentSchema],
)
async def retry_failed_chunks(
    kb_id: UUID,
    doc_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Retry embedding for failed chunks only.
    Only works when document has status 'error' and has chunks with status 'failed'.
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    if doc.status != DocumentStatus.ERROR.value:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="document_not_in_error_state",
        )

    # Check if there are actually failed chunks
    from app.models.knowledge_base import DocumentChunk as DocumentChunkModel

    failed_count = await DocumentChunkModel.filter(
        document_id=doc_id, status="failed"
    ).count()

    if failed_count == 0:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="no_failed_chunks",
        )

    # Update status to processing
    doc.status = DocumentStatus.PROCESSING.value
    doc.error_message = None  # type: ignore[assignment]
    await doc.save()

    # Trigger retry task
    try:
        from app.tasks.knowledge_base import retry_failed_chunks_task

        task = retry_failed_chunks_task.delay(str(doc.id))
        doc.metadata = doc.metadata or {}
        doc.metadata["task_id"] = task.id
        await doc.save()
    except Exception:
        import logging

        logging.warning("Celery task not dispatched - worker may not be running")

    doc = await Document.get(id=doc_id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="retry_failed_chunks_started")


# ============ Document Chunks ============


@router.get(
    "/{kb_id}/documents/{doc_id}/chunks",
    response_model=Response[PageData[ChunkSchema]],
)
async def list_document_chunks(
    kb_id: UUID,
    doc_id: UUID,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    List chunks of a document.
    """
    await check_kb_access(kb_id, current_user)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    query = DocumentChunk.filter(document_id=doc_id).order_by("chunk_index")
    total = await query.count()
    skip = (page - 1) * page_size
    chunks = await query.offset(skip).limit(page_size)

    return success(
        data={
            "items": chunks,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.put(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}",
    response_model=Response[ChunkSchema],
)
async def update_document_chunk(
    *,
    kb_id: UUID,
    doc_id: UUID,
    chunk_id: UUID,
    chunk_in: DocumentChunkUpdate,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Update a document chunk's content.
    This will also update the vector embedding.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    chunk = await DocumentChunk.filter(id=chunk_id, document_id=doc_id).first()
    if not chunk:
        raise BusinessError(
            code=ResponseCode.CHUNK_NOT_FOUND,
            msg_key="chunk_not_found",
            status_code=404,
        )

    old_token_count = chunk.token_count
    chunk.content = chunk_in.content

    # Recalculate token count
    new_token_count = len(chunk_in.content) // 4  # Simple estimate
    chunk.token_count = new_token_count
    await chunk.save()

    # Update document and KB token counts
    token_diff = new_token_count - old_token_count
    doc.token_count += token_diff
    await doc.save()

    kb.total_tokens += token_diff
    await kb.save()

    # Update vector embedding
    try:
        embedding_model_id = (
            str(kb.embedding_model_id) if kb.embedding_model_id else None
        )
        team_id = str(kb.team_id) if kb.team_id else None
        vector_store = VectorStore(
            embedding_model_id=embedding_model_id,
            team_id=team_id,
        )
        await vector_store.update_chunk_vector(chunk, kb_id=kb.id)
    except DimensionMismatchError as e:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg=str(e),
        )
    except Exception as e:
        logger.error(
            f"Failed to update vector embedding for chunk {chunk_id}: {e}",
            exc_info=True,
        )
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="vector_update_failed",
        )

    return success(data=chunk, msg_key="chunk_updated")


@router.delete(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}",
    response_model=Response[dict],
)
async def delete_document_chunk(
    kb_id: UUID,
    doc_id: UUID,
    chunk_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("kb:delete")),
) -> Any:
    """
    Delete a document chunk.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    chunk = await DocumentChunk.filter(id=chunk_id, document_id=doc_id).first()
    if not chunk:
        raise BusinessError(
            code=ResponseCode.CHUNK_NOT_FOUND,
            msg_key="chunk_not_found",
            status_code=404,
        )

    # Delete vector
    try:
        embedding_model_id = (
            str(kb.embedding_model_id) if kb.embedding_model_id else None
        )
        vector_store = VectorStore(embedding_model_id=embedding_model_id)
        await vector_store.delete_chunk_vector(chunk_id)
    except Exception as e:
        import logging

        logging.warning(f"Failed to delete vector: {e}")

    # Update statistics
    kb.total_chunks = max(0, kb.total_chunks - 1)
    kb.total_tokens = max(0, kb.total_tokens - chunk.token_count)
    await kb.save()

    doc.chunk_count = max(0, doc.chunk_count - 1)
    doc.token_count = max(0, doc.token_count - chunk.token_count)
    await doc.save()

    # Delete chunk
    deleted_index = chunk.chunk_index
    await chunk.delete()

    # Reindex remaining chunks with a single bulk update
    await DocumentChunk.filter(
        document_id=doc_id, chunk_index__gt=deleted_index
    ).update(chunk_index=F("chunk_index") - 1)

    return success(data={"id": str(chunk_id)}, msg_key="chunk_deleted")


@router.post(
    "/{kb_id}/documents/{doc_id}/chunks",
    response_model=Response[ChunkSchema],
)
async def create_document_chunk(
    *,
    kb_id: UUID,
    doc_id: UUID,
    chunk_in: DocumentChunkUpdate,
    after_index: int | None = None,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Create a new chunk in a document.
    If after_index is provided, insert after that index, otherwise append at the end.
    """
    kb = await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    # Determine chunk index
    existing_chunks = await DocumentChunk.filter(document_id=doc_id).order_by(
        "chunk_index"
    )

    if after_index is not None:
        new_index = after_index + 1
        # Shift subsequent chunks
        for chunk in existing_chunks:
            if chunk.chunk_index >= new_index:
                chunk.chunk_index += 1
                await chunk.save()
    else:
        new_index = len(existing_chunks)

    # Calculate token count
    token_count = len(chunk_in.content) // 4

    # Create chunk
    chunk = await DocumentChunk.create(
        document=doc,
        content=chunk_in.content,
        chunk_index=new_index,
        token_count=token_count,
    )

    # Update statistics
    doc.chunk_count += 1
    doc.token_count += token_count
    await doc.save()

    kb.total_chunks += 1
    kb.total_tokens += token_count
    await kb.save()

    # Create vector embedding
    try:
        embedding_model_id = (
            str(kb.embedding_model_id) if kb.embedding_model_id else None
        )
        team_id = str(kb.team_id) if kb.team_id else None
        vector_store = VectorStore(
            embedding_model_id=embedding_model_id,
            team_id=team_id,
        )
        await vector_store.add_chunk_vector(kb_id, chunk)
    except Exception as e:
        import logging

        logging.warning(f"Failed to create vector embedding: {e}")

    return success(data=chunk, msg_key="chunk_created")


@router.post(
    "/{kb_id}/documents/{doc_id}/rechunk",
    response_model=Response[DocumentSchema],
)
async def rechunk_document(
    *,
    kb_id: UUID,
    doc_id: UUID,
    rechunk_in: RechunkRequest,
    current_user: User = Depends(deps.PermissionChecker("kb:update")),
) -> Any:
    """
    Re-chunk a document with new chunking settings.
    This will delete all existing chunks and create new ones.
    """
    await check_kb_access(kb_id, current_user, require_write=True)

    doc = await Document.filter(id=doc_id, knowledge_base_id=kb_id).first()
    if not doc:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_NOT_FOUND,
            msg_key="document_not_found",
            status_code=404,
        )

    if doc.status == DocumentStatus.PROCESSING.value:
        raise BusinessError(
            code=ResponseCode.DOCUMENT_PROCESSING,
            msg_key="document_processing",
        )

    # Cancel existing task if any
    old_task_id = (doc.metadata or {}).get("task_id")
    if old_task_id and doc.status == DocumentStatus.PENDING.value:
        try:
            from app.core.celery import celery_app

            celery_app.control.revoke(old_task_id, terminate=True)
        except Exception:
            pass

    # Store the rechunk settings in document metadata
    if not doc.metadata:
        doc.metadata = {}
    doc.metadata["rechunk_settings"] = {
        "chunk_size": rechunk_in.chunk_size,
        "chunk_overlap": rechunk_in.chunk_overlap,
        "separator": rechunk_in.separator,
    }
    doc.status = DocumentStatus.PENDING.value
    doc.error_message = None  # type: ignore[assignment]
    await doc.save()

    # Trigger rechunk task
    try:
        from app.tasks.knowledge_base import rechunk_document_task

        task = rechunk_document_task.delay(str(doc.id))
        # Save new task ID
        doc.metadata["task_id"] = task.id
        await doc.save()
    except Exception:
        import logging

        logging.warning("Celery task not dispatched - worker may not be running")

    doc = await Document.get(id=doc_id).prefetch_related("uploaded_by")
    return success(data=doc, msg_key="document_rechunk_started")


# ============ Search ============


@router.post("/{kb_id}/search", response_model=Response[SearchResponse])
async def search_knowledge_base(
    kb_id: UUID,
    search_in: SearchRequest,
    current_user: User = Depends(deps.PermissionChecker("kb:read")),
) -> Any:
    """
    Search the knowledge base.

    Supports three search modes:
    - vector: Semantic/vector similarity search
    - fulltext: Keyword/full-text search
    - hybrid: Combined vector + fulltext with RRF fusion

    Returns relevant document chunks with similarity scores.
    """
    kb = await check_kb_access(kb_id, current_user)

    # Get embedding model and team ID from KB for usage tracking
    embedding_model_id = str(kb.embedding_model_id) if kb.embedding_model_id else None
    team_id = str(kb.team_id) if kb.team_id else None
    vector_store = VectorStore(
        embedding_model_id=embedding_model_id,
        rerank_model_id=str(kb.rerank_model_id) if kb.rerank_model_id else None,
        team_id=team_id,
    )

    rerank_override_fields = {
        "rerank_enabled",
        "rerank_candidate_k",
        "rerank_fail_open",
        "rerank_score_threshold",
    }
    rerank_overrides = {
        field_name: getattr(search_in, field_name)
        for field_name in rerank_override_fields
        if field_name in search_in.model_fields_set
    }

    # Perform search
    try:
        results = await vector_store.search(
            kb_id=kb_id,
            query=search_in.query,
            search_mode=search_in.search_mode,
            top_k=search_in.top_k,
            score_threshold=search_in.score_threshold,
            filter_doc_ids=search_in.filter_doc_ids,
            rerank_overrides=rerank_overrides or None,
        )
    except DimensionMismatchError as e:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg=str(e),
        )
    except Exception as e:
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="vector_search_failed",
            error=str(e),
        )

    return success(
        data={
            "query": search_in.query,
            "results": results,
            "total": len(results),
        },
        msg_key="search_completed",
    )
