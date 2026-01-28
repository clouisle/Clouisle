"""
Agent schemas for API request/response.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Enums ============


class AgentStatus:
    """Agent status constants"""

    DRAFT = "draft"
    PUBLISHED = "published"


class AgentVisibility:
    """Agent visibility constants"""

    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


class RAGMode:
    """RAG retrieval mode constants"""

    OFF = "off"  # No RAG
    AUTO = "auto"  # Traditional RAG: auto retrieve
    AGENTIC = "agentic"  # Agentic RAG: agent decides


class MessageRole:
    """Message role constants"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ============ Shared Schemas ============


class CreatorInfo(BaseModel):
    """Creator user info"""

    id: UUID
    username: str
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class TeamInfo(BaseModel):
    """Team info"""

    id: UUID
    name: str
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class ModelInfo(BaseModel):
    """Model info for agent"""

    id: UUID
    name: str
    provider: str
    model_id: str

    class Config:
        from_attributes = True


class KnowledgeBaseInfo(BaseModel):
    """Knowledge base info for agent"""

    id: UUID
    name: str
    description: str | None = None
    icon: str | None = None
    document_count: int = 0

    class Config:
        from_attributes = True


class ToolConfig(BaseModel):
    """Tool configuration"""

    type: str = Field(..., description="Tool type: builtin, custom, mcp")
    name: str | None = Field(None, description="Tool name (for builtin/custom)")
    tool_id: str | None = Field(None, description="Tool ID (for custom tools)")
    server_id: str | None = Field(None, description="MCP server ID")
    config: dict[str, Any] | None = Field(None, description="Tool-specific config")


class VariableDefinition(BaseModel):
    """Variable definition for agent"""

    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(
        default="text",
        description="Variable type: text, paragraph, select, number, checkbox",
    )
    label: str | None = Field(None, max_length=100, description="Display label")
    required: bool = Field(default=False)
    hidden: bool = Field(default=False, description="Hide from user input form")
    default: str | None = None
    description: str | None = None
    options: list[str] | None = Field(None, description="Options for select type")
    min: float | None = Field(None, description="Minimum value for number type")
    max: float | None = Field(None, description="Maximum value for number type")
    maxLength: int | None = Field(
        None, ge=1, description="Max length for text/paragraph type"
    )


class AgentKnowledgeBaseConfig(BaseModel):
    """Knowledge base configuration for agent"""

    knowledge_base_id: UUID
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.5, ge=0, le=1)


class FileUploadConfig(BaseModel):
    """File upload configuration for agent"""

    # Parser configuration - which tool to use for parsing files
    # Format: {"type": "builtin", "name": "markitdown"} or {"type": "custom", "tool_id": "xxx"}
    parser: dict | None = Field(
        default=None,
        description="File parser configuration. If None, file upload is disabled even if enable_file_upload is True.",
    )
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        ge=1024,
        le=50 * 1024 * 1024,  # 50MB max
        description="Maximum file size in bytes",
    )
    max_files: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of files per message",
    )
    max_content_length: int = Field(
        default=100000,  # ~100KB of text
        ge=1000,
        le=500000,  # 500KB max
        description="Maximum parsed content length in characters",
    )
    truncate_strategy: str = Field(
        default="end",
        description="Truncation strategy: 'end' (keep start), 'start' (keep end), 'middle' (keep start and end)",
    )
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            ".pdf",
            ".docx",
            ".doc",
            ".pptx",
            ".ppt",
            ".xlsx",
            ".xls",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".html",
        ],
        description="Allowed file extensions",
    )


# ============ Agent Schemas ============


class AgentBase(BaseModel):
    """Base schema for agent"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent name")
    description: str | None = Field(None, max_length=500, description="Description")
    icon: str | None = Field(None, max_length=500, description="Icon emoji or URL")


class AgentCreate(AgentBase):
    """Create agent request"""

    team_id: UUID = Field(..., description="Team ID")
    avatar_url: str | None = Field(None, max_length=500)
    model_id: UUID | None = Field(None, description="TeamModel ID")
    system_prompt: str | None = None
    max_iterations: int = Field(
        default=5, ge=1, le=20, description="Max tool call iterations"
    )
    tools_config: list[ToolConfig] = Field(default_factory=list)
    tools_credentials: dict[str, str] = Field(
        default_factory=dict, description="Tools credentials (API keys, tokens, etc.)"
    )
    enable_vision: bool = Field(
        default=False, description="Enable vision/image understanding"
    )
    enable_file_upload: bool = Field(
        default=False, description="Enable file upload and parsing"
    )
    file_upload_config: FileUploadConfig | None = Field(
        default=None, description="File upload configuration"
    )
    rag_mode: str = Field(
        default=RAGMode.AGENTIC, description="RAG mode: off, auto, or agentic"
    )
    knowledge_base_configs: list[AgentKnowledgeBaseConfig] = Field(default_factory=list)
    variables: list[VariableDefinition] = Field(default_factory=list)
    opening_message: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)
    visibility: str = Field(default=AgentVisibility.PRIVATE)


class AgentUpdate(BaseModel):
    """Update agent request"""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, max_length=500)
    model_id: UUID | None = None
    system_prompt: str | None = None
    max_iterations: int | None = Field(
        None, ge=1, le=20, description="Max tool call iterations"
    )
    tools_config: list[ToolConfig] | None = None
    tools_credentials: dict[str, str] | None = None
    enable_vision: bool | None = None
    enable_file_upload: bool | None = None
    file_upload_config: FileUploadConfig | None = None
    rag_mode: str | None = Field(None, description="RAG mode: off, auto, or agentic")
    knowledge_base_configs: list[AgentKnowledgeBaseConfig] | None = None
    variables: list[VariableDefinition] | None = None
    opening_message: str | None = None
    suggested_questions: list[str] | None = None
    visibility: str | None = None


class AgentKnowledgeBaseOut(BaseModel):
    """Agent knowledge base association output"""

    id: UUID
    knowledge_base: KnowledgeBaseInfo
    retrieval_top_k: int
    score_threshold: float

    class Config:
        from_attributes = True


class AgentOut(AgentBase):
    """Agent response schema"""

    id: UUID
    team: TeamInfo
    avatar_url: str | None = None
    model_id: UUID | None = None
    model: ModelInfo | None = None
    system_prompt: str | None = None
    max_iterations: int = 5
    tools_config: list[dict[str, Any]] = []
    tools_credentials: dict[str, str] = {}
    enable_vision: bool = False
    enable_file_upload: bool = False
    file_upload_config: dict[str, Any] | None = None
    rag_mode: str = RAGMode.AGENTIC
    variables: list[dict[str, Any]] = []
    opening_message: str | None = None
    suggested_questions: list[str] = []
    knowledge_bases: list[AgentKnowledgeBaseOut] = []
    status: str
    visibility: str
    conversation_count: int = 0
    message_count: int = 0
    created_by: CreatorInfo | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentPublicOut(BaseModel):
    """Public agent info for chat page (minimal info exposed)"""

    id: UUID
    name: str
    description: str | None = None
    icon: str | None = None
    avatar_url: str | None = None
    opening_message: str | None = None
    suggested_questions: list[str] = []
    variables: list[dict[str, Any]] = []
    enable_vision: bool = False
    enable_file_upload: bool = False
    file_upload_config: dict[str, Any] | None = None
    created_by: CreatorInfo | None = None

    class Config:
        from_attributes = True


class AgentListOut(BaseModel):
    """Simplified agent for list view"""

    id: UUID
    name: str
    description: str | None = None
    icon: str | None = None
    avatar_url: str | None = None
    team: TeamInfo
    model: ModelInfo | None = None
    status: str
    visibility: str
    conversation_count: int = 0
    message_count: int = 0
    created_by: CreatorInfo | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Conversation Schemas ============


class ConversationCreate(BaseModel):
    """Create conversation request (implicit, created on first message)"""

    variables: dict[str, Any] = Field(
        default_factory=dict, description="Variable values"
    )


class ConversationUpdate(BaseModel):
    """Update conversation request"""

    title: str | None = Field(None, min_length=1, max_length=200)


class ConversationOut(BaseModel):
    """Conversation response schema"""

    id: UUID
    agent_id: UUID
    agent_name: str | None = None
    agent_icon: str | None = None
    title: str | None = None
    variables: dict[str, Any] = {}
    message_count: int = 0
    token_usage: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationListOut(BaseModel):
    """Simplified conversation for list view"""

    id: UUID
    agent_id: UUID
    agent_name: str | None = None
    agent_icon: str | None = None
    title: str | None = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
    # User info for admin view
    user_id: UUID | None = None
    user_name: str | None = None

    class Config:
        from_attributes = True


# ============ Message Schemas ============


class MessageVersion(BaseModel):
    """Message version info"""

    id: UUID
    version_number: int
    is_active: bool
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    """Message response schema"""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    # Attachments
    images: list[dict[str, Any]] | None = None
    file_urls: list[dict[str, Any]] | None = None
    # Tool calls
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    # Reasoning (chain-of-thought)
    reasoning_content: str | None = None
    # Metadata
    model_used: str | None = None
    token_usage: dict[str, int] | None = None
    duration_ms: int | None = None
    rag_context: list[dict[str, Any]] | None = None
    created_at: datetime
    # Version info
    parent_id: UUID | None = None
    is_active: bool = True
    version_number: int = 1
    version_count: int = 1  # Total versions in this group
    versions: list[MessageVersion] | None = (
        None  # All versions (optional, for detail view)
    )

    class Config:
        from_attributes = True


class SwitchVersionRequest(BaseModel):
    """Request to switch message version"""

    version_id: UUID = Field(..., description="Target version message ID")


class RegenerateRequest(BaseModel):
    """Request to regenerate a message"""

    # Optional: override variables for this regeneration
    variables: dict[str, Any] = Field(default_factory=dict)


class ConversationWithMessages(ConversationOut):
    """Conversation with messages"""

    messages: list[MessageOut] = []


# ============ Chat Schemas ============


class ImageContent(BaseModel):
    """Image content for vision"""

    type: str = Field(default="image_url", description="Content type")
    url: str = Field(..., description="Image URL (data:image/... or https://...)")


class FileContent(BaseModel):
    """Parsed file content for chat (deprecated, use FileUrl instead)"""

    filename: str = Field(..., description="Original filename")
    content: str = Field(..., description="Parsed content (markdown format)")
    mime_type: str = Field(..., description="MIME type of the file")
    size: int = Field(..., ge=0, description="Original file size in bytes")
    truncated: bool = Field(default=False, description="Whether content was truncated")
    original_length: int | None = Field(
        default=None, description="Original content length before truncation"
    )


class FileUrl(BaseModel):
    """File URL for tool-based file processing"""

    filename: str = Field(..., description="Original filename")
    url: str = Field(..., description="File URL for the markitdown tool to process")
    size: int = Field(..., ge=0, description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")


class HistoryMessage(BaseModel):
    """Message for history override"""

    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request"""

    message: str = Field(
        ..., min_length=1, max_length=32000, description="User message"
    )
    images: list[ImageContent] = Field(
        default_factory=list, description="Images for vision"
    )
    files: list[FileContent] = Field(
        default_factory=list, description="Parsed files for file upload (deprecated, use file_urls instead)"
    )
    file_urls: list[FileUrl] = Field(
        default_factory=list,
        description="File URLs for backend to download, parse and inject into {{fileContent}} variable.",
    )
    conversation_id: UUID | None = Field(
        None, description="Continue existing conversation"
    )
    variables: dict[str, Any] = Field(
        default_factory=dict, description="Variable values"
    )
    history_override: list[HistoryMessage] | None = Field(
        None,
        description="Override conversation history. If provided, use these messages instead of loading from database. Used for version switching and regeneration.",
    )


class ChatResponse(BaseModel):
    """Chat response (non-streaming)"""

    conversation_id: UUID
    message: MessageOut
    usage: dict[str, int] | None = None


# SSE Event Types for streaming
class SSEEventType:
    """SSE event types for streaming chat"""

    MESSAGE_START = "message_start"
    CONTENT_DELTA = "content_delta"
    REASONING_START = "reasoning_start"  # 思维链开始
    REASONING_DELTA = "reasoning_delta"  # 思维链内容增量
    REASONING_END = "reasoning_end"  # 思维链结束
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RAG_START = "rag_start"  # RAG检索开始
    RAG_CONTEXT = "rag_context"
    MESSAGE_END = "message_end"
    ERROR = "error"
