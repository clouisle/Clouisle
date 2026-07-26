from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.knowledge_base import (
    ChunkInput,
    ChunkPreviewItem,
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    CreatorInfo,
    Document,
    DocumentChunk,
    DocumentChunkUpdate,
    DocumentCreate,
    DocumentList,
    DocumentStatus,
    DocumentType,
    DocumentUpdate,
    EmbeddingModelInfo,
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseList,
    KnowledgeBaseSettings,
    KnowledgeBaseStats,
    KnowledgeBaseStatus,
    KnowledgeBaseUpdate,
    ProcessRequest,
    ProcessWithChunksRequest,
    RechunkRequest,
    RerankModelInfo,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SearchResult,
    TeamInfo,
)


def test_constants_and_request_defaults():
    assert {
        KnowledgeBaseStatus.ACTIVE,
        KnowledgeBaseStatus.PROCESSING,
        KnowledgeBaseStatus.ERROR,
        KnowledgeBaseStatus.ARCHIVED,
    } == {"active", "processing", "error", "archived"}
    assert {
        DocumentStatus.PENDING,
        DocumentStatus.PROCESSING,
        DocumentStatus.COMPLETED,
        DocumentStatus.ERROR,
    } == {"pending", "processing", "completed", "error"}
    assert DocumentType.URL == "url"
    assert {
        DocumentType.PDF,
        DocumentType.DOCX,
        DocumentType.DOC,
        DocumentType.TXT,
        DocumentType.MD,
        DocumentType.HTML,
        DocumentType.CSV,
        DocumentType.XLSX,
        DocumentType.XLS,
        DocumentType.JSON,
    } == {"pdf", "docx", "doc", "txt", "markdown", "html", "csv", "xlsx", "xls", "json"}
    assert {SearchMode.VECTOR, SearchMode.FULLTEXT, SearchMode.HYBRID} == {
        "vector",
        "fulltext",
        "hybrid",
    }

    assert KnowledgeBaseSettings().model_dump() == {
        "chunk_size": 1000,
        "chunk_overlap": 100,
        "separator": None,
        "rerank_enabled": True,
        "rerank_candidate_k": 10,
        "rerank_score_threshold": None,
    }
    assert RechunkRequest().model_dump() == {
        "chunk_size": 1000,
        "chunk_overlap": 100,
        "separator": None,
    }
    assert ProcessRequest().model_dump() == {
        "chunk_size": None,
        "chunk_overlap": None,
        "separator": None,
        "clean_text": None,
    }
    assert ChunkPreviewRequest().model_dump() == {
        "chunk_size": 1000,
        "chunk_overlap": 100,
        "separator": None,
        "clean_text": True,
    }
    assert DocumentCreate(name="site").doc_type == "url"
    assert (
        DocumentChunk(
            id=uuid4(),
            document_id=uuid4(),
            content="text",
            chunk_index=0,
            token_count=1,
            created_at=datetime.now(UTC),
        ).status
        == "embedded"
    )


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (KnowledgeBaseSettings, {"chunk_size": 99}),
        (KnowledgeBaseSettings, {"chunk_overlap": -1}),
        (KnowledgeBaseSettings, {"rerank_candidate_k": 101}),
        (KnowledgeBaseSettings, {"rerank_score_threshold": 1.1}),
        (KnowledgeBaseCreate, {"name": "", "team_id": uuid4()}),
        (KnowledgeBaseCreate, {"name": "x" * 101, "team_id": uuid4()}),
        (KnowledgeBaseUpdate, {"description": "x" * 501}),
        (KnowledgeBaseUpdate, {"icon": "x" * 51}),
        (DocumentCreate, {"name": ""}),
        (DocumentCreate, {"name": "ok", "source_url": "x" * 1025}),
        (DocumentUpdate, {"name": ""}),
        (DocumentChunkUpdate, {"content": ""}),
        (RechunkRequest, {"chunk_size": 50}),
        (ProcessRequest, {"chunk_overlap": -1}),
        (ChunkInput, {"content": "x", "chunk_index": -1}),
        (ProcessWithChunksRequest, {"chunks": []}),
        (ChunkPreviewRequest, {"chunk_size": 99}),
        (SearchRequest, {"query": ""}),
        (SearchRequest, {"query": "x", "top_k": 21}),
        (SearchRequest, {"query": "x", "score_threshold": -0.1}),
        (SearchRequest, {"query": "x", "dense_weight": -0.1}),
        (SearchRequest, {"query": "x", "lexical_weight": -0.1}),
        (SearchRequest, {"query": "x", "rrf_k": 0}),
        (SearchRequest, {"query": "x", "dense_weight": 0, "lexical_weight": 0}),
        (SearchRequest, {"query": "x", "rerank_candidate_k": 0}),
        (SearchRequest, {"query": "x", "rerank_score_threshold": 1.1}),
    ],
)
def test_field_constraints_reject_invalid_values(model, values):
    with pytest.raises(ValidationError):
        model(**values)


def test_nested_create_update_and_chunk_models_round_trip():
    team_id = uuid4()
    embedding_id = uuid4()
    created = KnowledgeBaseCreate(
        name="Engineering",
        description="Internal docs",
        icon="book",
        team_id=str(team_id),
        embedding_model_id=embedding_id,
        rerank_model_id=None,
        settings={
            "chunk_size": 200,
            "chunk_overlap": 20,
            "separator": "\n",
            "rerank_enabled": False,
            "rerank_candidate_k": 25,
            "rerank_fail_open": False,
            "rerank_score_threshold": 0.4,
        },
    )
    assert created.team_id == team_id
    assert isinstance(created.settings, KnowledgeBaseSettings)
    assert KnowledgeBaseCreate.model_validate(created.model_dump()) == created

    update = KnowledgeBaseUpdate(
        name="Renamed",
        embedding_model_id=embedding_id,
        settings={"chunk_size": 300},
        status=KnowledgeBaseStatus.ARCHIVED,
    )
    assert update.model_dump(exclude_unset=True) == {
        "name": "Renamed",
        "embedding_model_id": embedding_id,
        "settings": {"chunk_size": 300},
        "status": "archived",
    }

    request = ProcessWithChunksRequest(
        chunks=[
            {"content": "first", "chunk_index": 0},
            ChunkInput(content="second", chunk_index=1),
        ]
    )
    preview = ChunkPreviewResponse(
        total_chunks=1,
        total_tokens=2,
        total_chars=5,
        chunks=[
            ChunkPreviewItem(
                chunk_index=0, content="hello", token_count=2, char_count=5
            )
        ],
    )
    assert [chunk.chunk_index for chunk in request.chunks] == [0, 1]
    assert preview.chunks[0].overlap_length == 0


def test_orm_conversion_for_nested_knowledge_base_models():
    now = datetime.now(UTC)
    team_id, creator_id, embedding_id, rerank_id, kb_id = (uuid4() for _ in range(5))
    source = SimpleNamespace(
        id=kb_id,
        name="Product",
        description=None,
        icon=None,
        team=SimpleNamespace(id=team_id, name="Core", avatar_url=None),
        created_by=SimpleNamespace(
            id=creator_id, username="owner", avatar_url="avatar.png"
        ),
        status="active",
        embedding_model_id=embedding_id,
        embedding_model=SimpleNamespace(
            id=embedding_id, name="Embed", provider="local", model_id="embed-v1"
        ),
        rerank_model_id=rerank_id,
        rerank_model=SimpleNamespace(
            id=rerank_id, name="Rerank", provider="local", model_id="rerank-v1"
        ),
        embedding_dimension=768,
        settings={"chunk_size": 500},
        document_count=2,
        total_chunks=4,
        total_tokens=100,
        created_at=now,
        updated_at=now,
    )

    full = KnowledgeBase.model_validate(source)
    listed = KnowledgeBaseList.model_validate(source)
    assert full.team == TeamInfo(id=team_id, name="Core")
    assert full.created_by == CreatorInfo(
        id=creator_id, username="owner", avatar_url="avatar.png"
    )
    assert full.embedding_model == EmbeddingModelInfo(
        id=embedding_id, name="Embed", provider="local", model_id="embed-v1"
    )
    assert full.rerank_model == RerankModelInfo(
        id=rerank_id, name="Rerank", provider="local", model_id="rerank-v1"
    )
    assert listed.model_dump(mode="json")["id"] == str(kb_id)


def test_document_models_accept_mappings_and_orm_objects_and_serialize():
    now = datetime.now(UTC)
    document_id, kb_id, user_id = uuid4(), uuid4(), uuid4()
    values = {
        "id": document_id,
        "knowledge_base_id": kb_id,
        "name": "guide.pdf",
        "doc_type": "pdf",
        "file_path": "/guide.pdf",
        "file_size": 123,
        "source_url": None,
        "status": "completed",
        "error_message": None,
        "chunk_count": 2,
        "token_count": 20,
        "metadata": {"language": "en"},
        "uploaded_by": SimpleNamespace(id=user_id, username="writer", avatar_url=None),
        "created_at": now,
        "updated_at": now,
        "processed_at": now,
    }
    document = Document.model_validate(SimpleNamespace(**values))
    listed = DocumentList.model_validate(values)
    chunk = DocumentChunk.model_validate(
        SimpleNamespace(
            id=uuid4(),
            document_id=document_id,
            content="body",
            chunk_index=0,
            token_count=1,
            metadata={"page": 1},
            status="failed",
            error_message="embedding unavailable",
            created_at=now,
        )
    )

    assert document.uploaded_by.username == "writer"
    assert listed.metadata == {"language": "en"}
    assert chunk.model_dump(mode="json")["document_id"] == str(document_id)


def test_search_and_statistics_models_serialize_nested_values():
    chunk_id, document_id, kb_id = uuid4(), uuid4(), uuid4()
    request = SearchRequest(
        query="deployment",
        search_mode=SearchMode.VECTOR,
        top_k=20,
        score_threshold=1,
        filter_doc_ids=[str(document_id)],
        rerank_enabled=True,
        rerank_candidate_k=100,
        rerank_fail_open=False,
        rerank_score_threshold=0,
    )
    response = SearchResponse(
        query=request.query,
        results=[
            SearchResult(
                chunk_id=chunk_id,
                document_id=document_id,
                document_name="runbook",
                content="deploy safely",
                score=0.9,
                metadata={"page": 2},
                search_type="hybrid",
                original_score=0.7,
                rerank_score=0.9,
                rerank_reason="relevant",
            )
        ],
        total=1,
    )
    stats = KnowledgeBaseStats(
        id=kb_id,
        name="Operations",
        document_count=1,
        total_chunks=2,
        total_tokens=10,
        documents_by_status={"completed": 1},
        documents_by_type={"pdf": 1},
        embedding_dimension=768,
        embedding_stats={"embedded": 2},
    )

    assert request.filter_doc_ids == [document_id]
    assert response.model_dump(mode="json")["results"][0]["chunk_id"] == str(chunk_id)
    assert stats.model_dump(mode="json")["embedding_stats"] == {"embedded": 2}
