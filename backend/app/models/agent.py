"""
Agent and Conversation models for AI assistant functionality.
Supports configurable AI agents with tools, knowledge bases, and conversation history.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User
    from app.models.model import TeamModel
    from app.models.knowledge_base import KnowledgeBase


class AgentStatus(str, Enum):
    """Agent status"""

    DRAFT = "draft"  # Draft, not published
    PUBLISHED = "published"  # Published and available


class AgentVisibility(str, Enum):
    """Agent visibility"""

    PRIVATE = "private"  # Only creator can access
    TEAM = "team"  # Team members can access
    PUBLIC = "public"  # Public access (future)


class RAGMode(str, Enum):
    """RAG retrieval mode"""

    OFF = "off"  # No RAG, even if knowledge bases are configured
    AUTO = "auto"  # Traditional RAG: automatically retrieve on every message
    AGENTIC = "agentic"  # Agentic RAG: agent decides when to search


class Agent(models.Model):
    """
    AI Agent entity.

    An agent is a configurable AI assistant that can use tools,
    access knowledge bases, and maintain conversation context.
    """

    id = fields.UUIDField(pk=True)

    # Team association for data isolation
    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="agents",
        on_delete=fields.CASCADE,
        description="Team that owns this agent",
    )
    team_id: fields.Field[str]  # type: ignore[assignment]

    # Basic info
    name = fields.CharField(max_length=100, description="Agent name")
    description = fields.TextField(null=True, description="Agent description")
    avatar_url = fields.CharField(max_length=500, null=True, description="Avatar URL")
    icon = fields.CharField(max_length=500, null=True, description="Icon emoji or URL")

    # Model configuration
    model: fields.ForeignKeyRelation["TeamModel"] | None = fields.ForeignKeyField(
        "models.TeamModel",
        related_name="agents",
        on_delete=fields.SET_NULL,
        null=True,
        description="LLM model to use (null = team default)",
    )
    model_id: UUID | None  # type: ignore[assignment]

    # Prompt configuration
    system_prompt = fields.TextField(null=True, description="System prompt")
    max_iterations = fields.IntField(
        default=5, description="Max tool call iterations (1-200)"
    )

    # Tools configuration (JSON array)
    # [{"type": "builtin", "name": "web_search"}, {"type": "mcp", "server_id": "xxx"}]
    tools_config: list = fields.JSONField(
        default=list, description="Tools configuration"
    )  # type: ignore[assignment]

    # Tools credentials (JSON object)
    # {"TAVILY_API_KEY": "tvly-xxx", "OPENWEATHER_API_KEY": "xxx"}
    tools_credentials: dict = fields.JSONField(
        default=dict, description="Tools credentials (API keys, tokens, etc.)"
    )  # type: ignore[assignment]

    # Vision configuration
    enable_vision = fields.BooleanField(
        default=False, description="Enable vision/image understanding"
    )

    # File upload configuration
    enable_file_upload = fields.BooleanField(
        default=False, description="Enable file upload and parsing"
    )
    file_upload_config: dict = fields.JSONField(
        default=dict, description="File upload configuration"
    )  # type: ignore[assignment]

    # Streaming and tool timeout configuration
    streaming_config: dict = fields.JSONField(
        default=dict,
        description="Streaming configuration (global_timeout, heartbeat_interval, tool_timeouts)"
    )  # type: ignore[assignment]

    # RAG configuration
    rag_mode = fields.CharEnumField(
        RAGMode,
        default=RAGMode.AGENTIC,
        description="RAG retrieval mode: off, auto, or agentic",
    )

    # Variables definition (JSON array)
    # [{"name": "user_name", "type": "string", "required": true, "default": ""}]
    variables: list = fields.JSONField(
        default=list, description="Input variables definition"
    )  # type: ignore[assignment]

    # Opening message configuration
    opening_message = fields.TextField(
        null=True, description="Opening message when starting a new conversation"
    )
    suggested_questions: list = fields.JSONField(
        default=list, description="Suggested questions to show users"
    )  # type: ignore[assignment]

    # Status
    status = fields.CharEnumField(
        AgentStatus, default=AgentStatus.DRAFT, description="Agent status"
    )
    visibility = fields.CharEnumField(
        AgentVisibility, default=AgentVisibility.PRIVATE, description="Visibility"
    )

    # Statistics (累计统计，不会因删除而减少)
    conversation_count = fields.IntField(
        default=0, description="Total conversations created"
    )
    message_count = fields.IntField(default=0, description="Total messages created")
    total_tokens = fields.BigIntField(
        default=0, description="Total tokens consumed (累计)"
    )

    # Audit
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_agents",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Relations
    agent_knowledge_bases: fields.ReverseRelation["AgentKnowledgeBase"]
    conversations: fields.ReverseRelation["Conversation"]

    class Meta:
        table = "agents"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class AgentKnowledgeBase(models.Model):
    """
    Agent-KnowledgeBase association.

    Links an agent to a knowledge base with RAG retrieval settings.
    """

    id = fields.UUIDField(pk=True)

    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent",
        related_name="agent_knowledge_bases",
        on_delete=fields.CASCADE,
    )
    agent_id: UUID  # type: ignore[assignment]

    knowledge_base: fields.ForeignKeyRelation["KnowledgeBase"] = fields.ForeignKeyField(
        "models.KnowledgeBase",
        related_name="agent_knowledge_bases",
        on_delete=fields.CASCADE,
    )
    knowledge_base_id: UUID  # type: ignore[assignment]

    # RAG configuration
    retrieval_top_k = fields.IntField(
        default=5, description="Number of chunks to retrieve"
    )
    score_threshold = fields.FloatField(
        default=0.3, description="Minimum similarity score (0-1, lower = more results)"
    )

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "agent_knowledge_bases"
        unique_together = [("agent", "knowledge_base")]

    def __str__(self):
        return f"Agent {self.agent_id} -> KB {self.knowledge_base_id}"


class MessageRole(str, Enum):
    """Message role"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Conversation(models.Model):
    """
    Conversation session.

    A conversation is a chat session between a user and an agent,
    containing multiple messages.
    """

    id = fields.UUIDField(pk=True)

    agent: fields.ForeignKeyRelation[Agent] | None = fields.ForeignKeyField(
        "models.Agent",
        related_name="conversations",
        on_delete=fields.SET_NULL,
        null=True,
        description="Agent (null if agent deleted)",
    )
    agent_id: UUID | None  # type: ignore[assignment]

    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="conversations",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    # Conversation info
    title = fields.CharField(
        max_length=200, null=True, description="Auto-generated or user-defined title"
    )

    # Variables (filled at conversation start)
    variables: dict = fields.JSONField(default=dict, description="Variable values")  # type: ignore[assignment]

    # Statistics
    message_count = fields.IntField(default=0, description="Number of messages")
    token_usage = fields.IntField(default=0, description="Total tokens used")

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Relations
    messages: fields.ReverseRelation["Message"]

    class Meta:
        table = "conversations"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation {self.id}"


class Message(models.Model):
    """
    Chat message.

    A single message in a conversation, can be from user, assistant, or tool.
    Supports message versioning for regeneration and editing.
    """

    id = fields.UUIDField(pk=True)

    conversation: fields.ForeignKeyRelation[Conversation] = fields.ForeignKeyField(
        "models.Conversation",
        related_name="messages",
        on_delete=fields.CASCADE,
    )
    conversation_id: UUID  # type: ignore[assignment]

    # Message content
    role = fields.CharEnumField(MessageRole, description="Message role")
    content = fields.TextField(description="Message content")

    # Version support - parent_id points to the original message in a version group
    # If null, this is the original message
    # If set, this is an alternative version of the parent message
    parent_id = fields.UUIDField(
        null=True, description="Parent message ID (for versions)"
    )
    is_active = fields.BooleanField(
        default=True, description="Whether this version is currently active"
    )
    version_number = fields.IntField(
        default=1, description="Version number within the group"
    )

    # Attachments (for user messages with images/files)
    images: list | None = fields.JSONField(
        null=True, description="Image URLs (data: or https://)"
    )  # type: ignore[assignment]
    file_urls: list | None = fields.JSONField(
        null=True, description="File URLs for uploaded files"
    )  # type: ignore[assignment]

    # Tool call related (for assistant tool calls and tool responses)
    tool_calls: list | None = fields.JSONField(
        null=True, description="Tool calls made by assistant"
    )  # type: ignore[assignment]
    tool_call_id = fields.CharField(
        max_length=100, null=True, description="Tool call ID (for tool role messages)"
    )
    tool_name = fields.CharField(
        max_length=100, null=True, description="Tool name (for tool role messages)"
    )

    # Reasoning content (for assistant messages with chain-of-thought)
    reasoning_content = fields.TextField(
        null=True, description="Reasoning/thinking content from LLM"
    )

    # Metadata
    model_used = fields.CharField(max_length=100, null=True, description="Model used")
    token_usage: dict | None = fields.JSONField(  # type: ignore[assignment]
        null=True, description='Token usage {"prompt": 100, "completion": 50}'
    )
    duration_ms = fields.IntField(null=True, description="Response duration in ms")

    # RAG context (for user messages that triggered retrieval)
    rag_context: list | None = fields.JSONField(
        null=True, description="Retrieved context chunks"
    )  # type: ignore[assignment]

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
