"""
Agent schemas for API request/response.
"""

from datetime import datetime
from typing import Any, Literal
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


class MemoryConfig(BaseModel):
    """Memory configuration schema with validation"""

    max_memories_per_retrieval: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of memories to retrieve per query (1-50)",
    )
    auto_extract: bool = Field(
        default=True,
        description="Automatically extract and save memories from conversations",
    )
    importance_threshold: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Minimum importance level for auto-extracted memories",
    )


class ContextCompressionConfig(BaseModel):
    """Context compression configuration schema with validation"""

    enabled: bool = Field(
        default=True,
        description="Enable request-time context compression before model calls",
    )
    micro_compaction_enabled: bool = Field(
        default=True,
        description="Enable lightweight reasoning/tool result compaction first",
    )
    macro_compaction_enabled: bool = Field(
        default=True,
        description="Enable synthetic summary compaction for older turn blocks",
    )
    preflight_guard_enabled: bool = Field(
        default=True,
        description="Enable preflight token budget guard before model calls",
    )
    reactive_retry_enabled: bool = Field(
        default=True,
        description="Enable one-shot aggressive retry on context length errors",
    )
    recent_raw_turns: int = Field(
        default=3,
        ge=1,
        le=12,
        description="Number of recent raw turn blocks to preserve during macro compaction",
    )
    recent_tool_turns: int = Field(
        default=2,
        ge=0,
        le=8,
        description="Number of recent tool turn blocks to preserve during macro compaction",
    )
    warning_ratio: float = Field(
        default=0.7,
        ge=0.1,
        le=1.0,
        description="Utilization ratio for warning-level context pressure",
    )
    auto_compact_trigger_ratio: float = Field(
        default=0.8,
        ge=0.1,
        le=1.0,
        description="Utilization ratio that proactively triggers selective compaction",
    )
    blocking_ratio: float = Field(
        default=0.92,
        ge=0.1,
        le=1.0,
        description="Utilization ratio that escalates to blocking-level macro compaction",
    )
    compaction_policy: Literal["staged", "hard_budget_only"] = Field(
        default="staged",
        description="How request-time compaction policy is selected",
    )
    macro_on_trigger: bool = Field(
        default=False,
        description="Allow macro compaction immediately when proactive trigger ratio is reached",
    )
    retention_strategy: Literal["recent_raw_and_tool_first"] = Field(
        default="recent_raw_and_tool_first",
        description="Retention strategy used during selective and macro compaction",
    )
    keep_recent_tool_results: int = Field(
        default=2,
        ge=0,
        le=8,
        description="Number of most recent tool results to keep raw during selective micro compaction",
    )
    keep_recent_tool_result_minutes: int = Field(
        default=20,
        ge=0,
        le=1440,
        description="Reserved window for keeping recent tool results raw; currently informational",
    )
    tool_result_compact_min_tokens: int = Field(
        default=256,
        ge=32,
        le=16000,
        description="Only compact older tool results at or above this estimated token size",
    )
    session_memory_enabled: bool = Field(
        default=True,
        description="Enable conversation-scoped session memory compaction when snapshots are available",
    )
    session_memory_async_extract: bool = Field(
        default=True,
        description="Enqueue async session memory extraction after final assistant replies",
    )
    session_memory_max_tokens: int = Field(
        default=400,
        ge=64,
        le=4000,
        description="Maximum token budget for injected session memory summary",
    )
    session_memory_min_turns: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Minimum conversation turn blocks before async session memory extraction runs",
    )
    session_memory_failure_threshold: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Failures before opening the session memory extractor breaker",
    )
    session_memory_cooldown_seconds: int = Field(
        default=600,
        ge=60,
        le=86400,
        description="Cooldown window for session memory extractor failures",
    )
    legacy_compact_enabled: bool = Field(
        default=True,
        description="Enable last-resort LLM legacy compaction when deterministic compaction still exceeds budget",
    )
    legacy_compact_failure_threshold: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Failures before opening the legacy compact breaker",
    )
    legacy_compact_cooldown_seconds: int = Field(
        default=600,
        ge=60,
        le=86400,
        description="Cooldown window for legacy compact failures",
    )
    output_token_reserve: int = Field(
        default=4000,
        ge=256,
        le=32000,
        description="Reserved output tokens when computing prompt budget",
    )
    safety_margin_tokens: int = Field(
        default=1000,
        ge=0,
        le=16000,
        description="Extra input safety margin kept below the model context window",
    )
    summary_max_tokens: int = Field(
        default=1000,
        ge=128,
        le=8000,
        description="Target token budget for synthetic summary content",
    )
    drop_historical_reasoning_first: bool = Field(
        default=True,
        description="Prefer dropping older reasoning content before heavier compaction",
    )
    emit_sse_events: bool = Field(
        default=True,
        description="Emit streaming compression SSE events when compaction is applied",
    )


class ImageGenerationConfig(BaseModel):
    """Agent image generation configuration"""

    default_model_ref: str | None = Field(
        default=None,
        description="Default image model reference (UUID or provider/model_id)",
    )
    default_width: int = Field(
        default=1024,
        ge=256,
        le=4096,
        description="Default generated image width",
    )
    default_height: int = Field(
        default=1024,
        ge=256,
        le=4096,
        description="Default generated image height",
    )
    max_images: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum number of images per tool call",
    )
    allow_reference_images: bool = Field(
        default=True,
        description="Allow reference images for edit/reference generation flows",
    )
    allowed_providers: list[str] = Field(
        default_factory=list,
        description="Optional allowlist of providers for image generation",
    )
    require_confirmation: bool = Field(
        default=False,
        description="Whether generation should require explicit confirmation before execution",
    )


class VideoGenerationConfig(BaseModel):
    """Agent video generation configuration"""

    default_model_ref: str | None = Field(
        default=None,
        description="Default video model reference (UUID or provider/model_id)",
    )
    default_duration: float = Field(
        default=5.0,
        ge=1.0,
        le=30.0,
        description="Default generated video duration in seconds",
    )
    max_duration: float = Field(
        default=10.0,
        ge=1.0,
        le=30.0,
        description="Maximum video duration per tool call",
    )
    default_aspect_ratio: str = Field(
        default="16:9",
        description="Default video aspect ratio",
    )
    poll_interval_ms: int = Field(
        default=3000,
        ge=500,
        le=30000,
        description="Polling interval for provider video task status",
    )
    poll_timeout_s: int = Field(
        default=120,
        ge=5,
        le=600,
        description="Maximum synchronous polling time before returning pending",
    )
    allowed_providers: list[str] = Field(
        default_factory=list,
        description="Optional allowlist of providers for video generation",
    )
    require_confirmation: bool = Field(
        default=False,
        description="Whether generation should require explicit confirmation before execution",
    )


class CreatorInfo(BaseModel):
    """Creator user info"""

    id: UUID | None = None  # Allow None for deleted users
    username: str
    avatar_url: str | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_user(cls, user):
        """Create CreatorInfo from user, handling deleted users"""
        if user is None:
            return cls(id=None, username="Deleted User", avatar_url=None)
        return cls(id=user.id, username=user.username, avatar_url=user.avatar_url)


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
    retrieval_top_k: int = Field(default=5, ge=1, le=100)
    score_threshold: float = Field(default=0.3, ge=0, le=1)
    search_mode: str = Field(default="hybrid", pattern="^(vector|fulltext|hybrid)$")


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
        default=5, ge=1, le=200, description="Max tool call iterations"
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
    enable_user_input_request: bool = Field(
        default=False, description="Enable user input request with predefined options"
    )
    enable_memory: bool = Field(
        default=False,
        description="Enable memory to remember user information across conversations",
    )
    memory_config: MemoryConfig | None = Field(
        default=None,
        description="Memory configuration (max_memories_per_retrieval, auto_extract)",
    )
    context_compression_config: ContextCompressionConfig | None = Field(
        default=None,
        description="Context compression configuration",
    )
    enable_image_generation: bool = Field(
        default=False,
        description="Enable agent image generation tool",
    )
    image_generation_config: ImageGenerationConfig | None = Field(
        default=None,
        description="Agent image generation configuration",
    )
    enable_video_generation: bool = Field(
        default=False,
        description="Enable agent video generation tool",
    )
    video_generation_config: VideoGenerationConfig | None = Field(
        default=None,
        description="Agent video generation configuration",
    )
    rag_mode: str = Field(
        default=RAGMode.AGENTIC, description="RAG mode: off, auto, or agentic"
    )
    knowledge_base_configs: list[AgentKnowledgeBaseConfig] = Field(default_factory=list)
    variables: list[VariableDefinition] = Field(default_factory=list)
    opening_message: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)
    visibility: str = Field(default=AgentVisibility.TEAM)


class AgentUpdate(BaseModel):
    """Update agent request"""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, max_length=500)
    model_id: UUID | None = None
    system_prompt: str | None = None
    max_iterations: int | None = Field(
        None, ge=1, le=200, description="Max tool call iterations"
    )
    tools_config: list[ToolConfig] | None = None
    tools_credentials: dict[str, str] | None = None
    enable_vision: bool | None = None
    enable_file_upload: bool | None = None
    file_upload_config: FileUploadConfig | None = None
    enable_user_input_request: bool | None = None
    enable_memory: bool | None = None
    memory_config: MemoryConfig | None = None
    context_compression_config: ContextCompressionConfig | None = None
    enable_image_generation: bool | None = None
    image_generation_config: ImageGenerationConfig | None = None
    enable_video_generation: bool | None = None
    video_generation_config: VideoGenerationConfig | None = None
    rag_mode: str | None = Field(None, description="RAG mode: off, auto, or agentic")
    knowledge_base_configs: list[AgentKnowledgeBaseConfig] | None = None
    variables: list[VariableDefinition] | None = None
    opening_message: str | None = None
    suggested_questions: list[str] | None = None
    visibility: str | None = None
    embed_config: dict[str, Any] | None = None


class AgentKnowledgeBaseOut(BaseModel):
    """Agent knowledge base association output"""

    id: UUID
    knowledge_base: KnowledgeBaseInfo
    retrieval_top_k: int
    score_threshold: float
    search_mode: str

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
    tools_config: list[ToolConfig] = []
    tools_credentials: dict[str, str] = {}
    enable_vision: bool = False
    enable_file_upload: bool = False
    file_upload_config: FileUploadConfig | None = None
    enable_user_input_request: bool = False
    enable_memory: bool = False
    memory_config: MemoryConfig | None = None
    context_compression_config: ContextCompressionConfig | None = None
    enable_image_generation: bool = False
    image_generation_config: ImageGenerationConfig | None = None
    enable_video_generation: bool = False
    video_generation_config: VideoGenerationConfig | None = None
    rag_mode: str = RAGMode.AGENTIC
    variables: list[VariableDefinition] = []
    opening_message: str | None = None
    suggested_questions: list[str] = []
    knowledge_bases: list[AgentKnowledgeBaseOut] = []
    embed_config: dict[str, Any] = {}
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


class EmbedAgentInfo(BaseModel):
    """Agent info for embed page (minimal, no auth-sensitive data)"""

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
    embed_config: dict[str, Any] = {}

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


class HistoryToolCall(BaseModel):
    """Tool call for history override assistant messages"""

    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool/function name")
    arguments: dict[str, Any] | str = Field(
        default_factory=dict,
        description="Tool arguments payload",
    )


class HistoryMessage(BaseModel):
    """Message for history override"""

    role: str = Field(..., description="Message role: user, assistant or tool")
    content: str = Field(..., description="Message content")
    reasoning_content: str | None = Field(
        default=None,
        description="Assistant reasoning replay content",
    )
    tool_calls: list[HistoryToolCall] | None = Field(
        default=None,
        description="Assistant tool calls for replay",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="Tool result tool_call_id",
    )
    tool_name: str | None = Field(
        default=None,
        description="Tool result tool name",
    )


class ChatRequest(BaseModel):
    """Chat request"""

    message: str = Field(
        ..., min_length=1, max_length=32000, description="User message"
    )
    images: list[ImageContent] = Field(
        default_factory=list, description="Images for vision"
    )
    files: list[FileContent] = Field(
        default_factory=list,
        description="Parsed files for file upload (deprecated, use file_urls instead)",
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
    MEDIA_RESULT = "media_result"
    RAG_START = "rag_start"  # RAG检索开始
    RAG_CONTEXT = "rag_context"
    USER_INPUT_REQUEST = "user_input_request"  # 用户输入请求
    COMPRESSION_START = "compression_start"  # 上下文压缩开始
    COMPRESSION_END = "compression_end"  # 上下文压缩结束
    OUTPUT_TRUNCATED = "output_truncated"  # 输出被截断（达到max_tokens限制）
    MESSAGE_END = "message_end"
    ERROR = "error"
