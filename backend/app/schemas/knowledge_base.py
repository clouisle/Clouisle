"""
Knowledge Base schemas for API request/response.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


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

    chunk_size: int = Field(default=500, ge=100, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=50, ge=0, description="Overlap between chunks")
    separator: Optional[str] = Field(default=None, description="Custom text separator")


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
    settings: Optional[KnowledgeBaseSettings] = Field(None, description="KB settings")


class KnowledgeBaseUpdate(BaseModel):
    """Update knowledge base request"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    embedding_model_id: Optional[UUID] = None
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


class KnowledgeBase(KnowledgeBaseBase):
    """Knowledge base response schema"""

    id: UUID
    team: TeamInfo
    created_by: Optional[CreatorInfo] = None
    status: str
    embedding_model_id: Optional[UUID] = None
    embedding_model: Optional[EmbeddingModelInfo] = None
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
    created_at: datetime

    class Config:
        from_attributes = True


class RechunkRequest(BaseModel):
    """Request to rechunk a document with new settings"""

    chunk_size: int = Field(default=500, ge=100, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=50, ge=0, description="Overlap between chunks")
    separator: Optional[str] = Field(default=None, description="Custom text separator")


class ProcessRequest(BaseModel):
    """Request to start processing a pending document"""

    chunk_size: Optional[int] = Field(None, ge=100, description="Chunk size in tokens")
    chunk_overlap: Optional[int] = Field(
        None, ge=0, description="Overlap between chunks"
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

    chunk_size: int = Field(default=500, ge=100, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=50, ge=0, description="Overlap between chunks")
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


class ChunkPreviewResponse(BaseModel):
    """Chunking preview response"""

    total_chunks: int
    total_tokens: int
    total_chars: int
    chunks: List[ChunkPreviewItem]


# ============ Search Schemas ============


class SearchMode:
    """Search mode constants"""

    VECTOR = "vector"  # Vector/semantic search
    FULLTEXT = "fulltext"  # Full-text search
    HYBRID = "hybrid"  # Hybrid (vector + fulltext)


class SearchRequest(BaseModel):
    """Search request for knowledge base"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    search_mode: str = Field(
        default="hybrid", description="Search mode: vector, fulltext, hybrid"
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    score_threshold: float = Field(
        default=0.0, ge=0, le=1, description="Minimum similarity score"
    )
    filter_doc_ids: Optional[List[UUID]] = Field(
        None, description="Filter by document IDs"
    )


class SearchResult(BaseModel):
    """Search result item"""

    chunk_id: UUID
    document_id: UUID
    document_name: str
    content: str
    score: float
    metadata: Optional[dict] = None


class SearchResponse(BaseModel):
    """Search response"""

    query: str
    results: List[SearchResult]
    total: int


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
