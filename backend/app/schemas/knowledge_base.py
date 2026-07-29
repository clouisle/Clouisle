"""
Knowledge Base schemas for API request/response.
"""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ============ Enums (mirroring model enums for API) ============


class KnowledgeBaseStatus:
    """Knowledge base status constants"""

    ACTIVE = "active"
    PROCESSING = "processing"
    ERROR = "error"
    ARCHIVED = "archived"


class DocumentStatus:
    """Document status constants"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class DocumentType:
    """Document type constants"""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"
    MD = "markdown"
    HTML = "html"
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    JSON = "json"
    URL = "url"


# ============ Knowledge Base Schemas ============


class KnowledgeBaseSettings(BaseModel):
    """Knowledge base settings"""

    chunk_size: int = Field(
        default=1000, ge=100, description="Chunk size in characters"
    )
    chunk_overlap: int = Field(
        default=100, ge=0, description="Overlap between chunks in characters"
    )
    separator: Optional[str] = Field(default=None, description="Custom text separator")
    rerank_enabled: bool = Field(
        default=True, description="Whether reranking is enabled for retrieval"
    )
    rerank_candidate_k: int = Field(
        default=10, ge=1, le=100, description="Candidate pool size before reranking"
    )
    rerank_score_threshold: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Optional minimum rerank score threshold",
    )
    search_mode: Literal["vector", "fulltext", "hybrid"] | None = Field(
        default=None, description="Default retrieval mode"
    )
    top_k: int | None = Field(default=None, ge=1, le=100)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
    dense_weight: float | None = Field(default=None, ge=0)
    lexical_weight: float | None = Field(default=None, ge=0)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_hybrid_weights(self):
        if (
            self.search_mode == "hybrid"
            and self.dense_weight == 0
            and self.lexical_weight == 0
        ):
            raise ValueError("at least one retrieval weight must be positive")
        return self


class KnowledgeBaseBase(BaseModel):
    """Base schema for knowledge base"""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Knowledge base name"
    )
    description: Optional[str] = Field(None, max_length=500, description="Description")
    icon: Optional[str] = Field(None, max_length=50, description="Icon name or emoji")


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """Create knowledge base request"""

    team_id: UUID = Field(..., description="Team ID for ownership")
    embedding_model_id: Optional[UUID] = Field(None, description="Embedding model ID")
    rerank_model_id: Optional[UUID] = Field(None, description="Rerank model ID")
    settings: Optional[KnowledgeBaseSettings] = Field(None, description="KB settings")


class KnowledgeBaseUpdate(BaseModel):
    """Update knowledge base request"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    embedding_model_id: Optional[UUID] = None
    rerank_model_id: Optional[UUID] = None
    settings: Optional[KnowledgeBaseSettings] = None
    status: Optional[str] = Field(None, description="Status (active, archived)")


class CreatorInfo(BaseModel):
    """Creator user info"""

    id: UUID
    username: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class TeamInfo(BaseModel):
    """Team info for knowledge base"""

    id: UUID
    name: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class EmbeddingModelInfo(BaseModel):
    """嵌入模型简要信息"""

    id: UUID
    name: str
    provider: str
    model_id: str

    class Config:
        from_attributes = True


class RerankModelInfo(BaseModel):
    """重排序模型简要信息"""

    id: UUID
    name: str
    provider: str
    model_id: str

    class Config:
        from_attributes = True


class KnowledgeBase(KnowledgeBaseBase):
    """Knowledge base response schema"""

    id: UUID
    team: TeamInfo
    created_by: Optional[CreatorInfo] = None
    status: str
    embedding_model_id: Optional[UUID] = None
    embedding_model: Optional[EmbeddingModelInfo] = None
    rerank_model_id: Optional[UUID] = None
    rerank_model: Optional[RerankModelInfo] = None
    embedding_dimension: Optional[int] = Field(
        None,
        description="Embedding vector dimension (set after first document processing)",
    )
    settings: Optional[dict] = None
    document_count: int
    total_chunks: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseList(BaseModel):
    """Simplified knowledge base for list view"""

    id: UUID
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    team: TeamInfo
    created_by: Optional[CreatorInfo] = None
    status: str
    embedding_model_id: Optional[UUID] = None
    embedding_model: Optional[EmbeddingModelInfo] = None
    rerank_model_id: Optional[UUID] = None
    rerank_model: Optional[RerankModelInfo] = None
    embedding_dimension: Optional[int] = Field(
        None, description="Embedding vector dimension"
    )
    document_count: int
    total_chunks: int
    total_tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Document Schemas ============


class DocumentBase(BaseModel):
    """Base schema for document"""

    name: str = Field(..., min_length=1, max_length=255, description="Document name")


class DocumentCreate(DocumentBase):
    """Create document request (for URL-based documents)"""

    source_url: Optional[str] = Field(None, max_length=1024, description="Source URL")
    doc_type: str = Field(default=DocumentType.URL, description="Document type")


class DocumentUpdate(BaseModel):
    """Update document request"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)


class Document(DocumentBase):
    """Document response schema"""

    id: UUID
    knowledge_base_id: UUID
    doc_type: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    source_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    chunk_count: int
    token_count: int
    metadata: Optional[dict] = None
    uploaded_by: Optional[CreatorInfo] = None
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Simplified document for list view"""

    id: UUID
    name: str
    doc_type: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    source_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    chunk_count: int
    token_count: int
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Document Chunk Schemas ============


class DocumentChunkUpdate(BaseModel):
    """Update document chunk request"""

    content: str = Field(..., min_length=1, description="Updated chunk content")


class DocumentChunk(BaseModel):
    """Document chunk response schema"""

    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    token_count: int
    metadata: Optional[dict] = None
    status: str = "embedded"
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RechunkRequest(BaseModel):
    """Request to rechunk a document with new settings"""

    chunk_size: int = Field(
        default=1000, ge=100, description="Chunk size in characters"
    )
    chunk_overlap: int = Field(
        default=100, ge=0, description="Overlap between chunks in characters"
    )
    separator: Optional[str] = Field(default=None, description="Custom text separator")


class ProcessRequest(BaseModel):
    """Request to start processing a pending document"""

    chunk_size: Optional[int] = Field(
        None, ge=100, description="Chunk size in characters"
    )
    chunk_overlap: Optional[int] = Field(
        None, ge=0, description="Overlap between chunks in characters"
    )
    separator: Optional[str] = Field(None, description="Custom text separator")
    clean_text: Optional[bool] = Field(
        None, description="Whether to clean and normalize text"
    )


class ChunkInput(BaseModel):
    """Input for a single chunk when submitting pre-chunked content"""

    content: str = Field(..., min_length=1, description="Chunk content")
    chunk_index: int = Field(..., ge=0, description="Chunk index (0-based)")


class ProcessWithChunksRequest(BaseModel):
    """Request to process a document with pre-defined chunks from frontend"""

    chunks: List[ChunkInput] = Field(
        ..., min_length=1, description="Pre-chunked content"
    )


class ChunkPreviewRequest(BaseModel):
    """Request to preview chunking results"""

    chunk_size: int = Field(
        default=1000, ge=100, description="Chunk size in characters"
    )
    chunk_overlap: int = Field(
        default=100, ge=0, description="Overlap between chunks in characters"
    )
    separator: Optional[str] = Field(default=None, description="Custom text separator")
    clean_text: bool = Field(
        default=True, description="Whether to clean and normalize text"
    )


class ChunkPreviewItem(BaseModel):
    """Preview chunk item"""

    chunk_index: int
    content: str
    token_count: int
    char_count: int
    overlap_length: int = Field(
        default=0, description="Overlap character count at the start of this chunk"
    )


class ChunkPreviewResponse(BaseModel):
    """Chunking preview response"""

    total_chunks: int
    total_tokens: int
    total_chars: int
    chunks: List[ChunkPreviewItem]


# ============ Search Schemas ============


class SearchMode(str, Enum):
    """Supported search modes."""

    VECTOR = "vector"
    FULLTEXT = "fulltext"
    HYBRID = "hybrid"


class SearchConfiguration(BaseModel):
    """Validated retrieval configuration shared by single and batch search."""

    search_mode: SearchMode = Field(
        default=SearchMode.HYBRID, description="Search mode: vector, fulltext, hybrid"
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    score_threshold: float = Field(
        default=0.0, ge=0, le=1, description="Minimum dense similarity score"
    )
    dense_weight: float = Field(default=1.0, ge=0, description="Dense RRF weight")
    lexical_weight: float = Field(default=1.0, ge=0, description="Lexical RRF weight")
    rrf_k: int = Field(default=60, ge=1, le=1000, description="RRF rank constant")
    filter_doc_ids: Optional[List[UUID]] = Field(
        None, description="Filter by document IDs"
    )
    rerank_enabled: Optional[bool] = Field(
        default=None, description="Override rerank enabled setting"
    )
    rerank_candidate_k: Optional[int] = Field(
        default=None, ge=1, le=100, description="Override rerank candidate pool size"
    )
    rerank_score_threshold: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Override rerank score threshold, null disables threshold",
    )

    @model_validator(mode="after")
    def validate_hybrid_weights(self):
        if (
            self.search_mode == SearchMode.HYBRID
            and self.dense_weight == 0
            and self.lexical_weight == 0
        ):
            raise ValueError("at least one retrieval weight must be positive")
        return self


class SearchRequest(SearchConfiguration):
    """Search request for one knowledge base configuration."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")


class SearchBatchConfiguration(SearchConfiguration):
    """Identified search configuration in a batch request."""

    id: str = Field(..., min_length=1, max_length=64)


class SearchBatchRequest(BaseModel):
    """Search one query with independently evaluated configurations."""

    query: str = Field(..., min_length=1, max_length=1000)
    configurations: List[SearchBatchConfiguration] = Field(
        ..., min_length=1, max_length=10
    )

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [configuration.id for configuration in self.configurations]
        if len(ids) != len(set(ids)):
            raise ValueError("configuration ids must be unique")
        return self


class SearchResult(BaseModel):
    """Search result item"""

    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    score: float
    metadata: Optional[dict] = None
    search_type: Optional[str] = None
    dense_score: Optional[float] = None
    dense_rank: Optional[int] = None
    lexical_score: Optional[float] = None
    lexical_rank: Optional[int] = None
    fusion_score: Optional[float] = None
    fusion_rank: Optional[int] = None
    original_score: Optional[float] = None
    rerank_score: Optional[float] = None
    rerank_rank: Optional[int] = None
    rerank_reason: Optional[str] = None
    final_score_stage: Optional[str] = None
    degradation_reasons: Optional[List[dict[str, str]]] = None


class RetrievalDiagnostic(BaseModel):
    """Retrieval target diagnostic."""

    kb_id: UUID
    code: Literal["inactive", "missing_embedding_model", "timeout", "failed"]
    detail: Optional[str] = None
    stage: Optional[str] = None


class RetrievalTiming(BaseModel):
    """Observed retrieval stage latency."""

    stage: Literal["recall", "rerank", "context", "total"]
    latency_ms: float


class SearchResponse(BaseModel):
    """Search response"""

    query: str
    results: List[SearchResult]
    total: int
    diagnostics: List[RetrievalDiagnostic] = Field(default_factory=list)
    timings: List[RetrievalTiming] = Field(default_factory=list)


class SearchBatchError(BaseModel):
    """Sanitized failure for one batch configuration."""

    code: int
    retrieval_error_category: str
    stage: Optional[str] = None


class SearchBatchOutcome(BaseModel):
    """Independent outcome for one search configuration."""

    id: str
    status: Literal["fulfilled", "rejected"]
    response: Optional[SearchResponse] = None
    error: Optional[SearchBatchError] = None


class SearchBatchResponse(BaseModel):
    """Ordered outcomes for a batch search."""

    query: str
    outcomes: List[SearchBatchOutcome]


# ============ Statistics Schemas ============


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics"""

    id: UUID
    name: str
    document_count: int
    total_chunks: int
    total_tokens: int
    documents_by_status: dict
    documents_by_type: dict
    # Embedding configuration
    embedding_dimension: Optional[int] = Field(
        None, description="Embedding vector dimension"
    )
    # Embedding statistics
    embedding_stats: Optional[dict] = None
