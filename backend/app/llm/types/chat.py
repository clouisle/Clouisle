"""
Chat 相关类型定义
"""

from enum import Enum
from pydantic import BaseModel, Field

from .base import ContentPart, Usage


class MessageRole(str, Enum):
    """消息角色"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """工具调用"""

    id: str = Field(..., description="工具调用 ID")
    type: str = Field(default="function", description="工具类型")
    function: "FunctionCall" = Field(..., description="函数调用信息")


class FunctionCall(BaseModel):
    """函数调用详情"""

    name: str = Field(..., description="函数名")
    arguments: str = Field(..., description="函数参数 JSON 字符串")


class Message(BaseModel):
    """聊天消息"""

    role: MessageRole = Field(..., description="消息角色")
    content: str | list[ContentPart] | None = Field(
        default=None, description="消息内容"
    )
    reasoning_content: str | None = Field(
        default=None, description="思维链内容（仅用于部分模型/历史）"
    )
    name: str | None = Field(default=None, description="发送者名称")
    tool_call_id: str | None = Field(
        default=None, description="工具调用 ID (role=tool 时)"
    )
    tool_calls: list[ToolCall] | None = Field(default=None, description="工具调用列表")


class ToolDefinition(BaseModel):
    """工具定义"""

    type: str = Field(default="function")
    function: "FunctionDefinition" = Field(...)


class FunctionDefinition(BaseModel):
    """函数定义"""

    name: str = Field(..., description="函数名")
    description: str | None = Field(default=None, description="函数描述")
    parameters: dict = Field(default_factory=dict, description="参数 JSON Schema")
    strict: bool | None = Field(default=None, description="是否严格模式")


class FinishReason(str, Enum):
    """完成原因"""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


# ==================== Request / Response ====================


class ChatRequest(BaseModel):
    """Chat 请求"""

    messages: list[Message] = Field(..., description="消息列表")
    temperature: float | None = Field(default=None, ge=0, le=2, description="温度")
    top_p: float | None = Field(default=None, ge=0, le=1, description="Top P")
    max_tokens: int | None = Field(default=None, gt=0, description="最大输出 token")
    stream: bool = Field(default=False, description="是否流式输出")
    tools: list[ToolDefinition] | None = Field(default=None, description="工具定义列表")
    tool_choice: str | dict | None = Field(default=None, description="工具选择策略")


class ChatResponse(BaseModel):
    """Chat 响应"""

    id: str = Field(..., description="响应 ID")
    model: str = Field(..., description="模型名称")
    content: str | None = Field(default=None, description="响应内容")
    tool_calls: list[ToolCall] | None = Field(default=None, description="工具调用列表")
    finish_reason: FinishReason = Field(..., description="完成原因")
    usage: Usage = Field(..., description="使用统计")


class ChatStreamDelta(BaseModel):
    """流式响应增量"""

    role: MessageRole | None = Field(default=None, description="角色")
    content: str | None = Field(default=None, description="增量内容")
    reasoning_content: str | None = Field(default=None, description="思维链内容增量")
    tool_calls: list[ToolCall] | None = Field(default=None, description="工具调用")


class ChatStreamChunk(BaseModel):
    """流式响应块"""

    id: str = Field(..., description="响应 ID")
    model: str = Field(..., description="模型名称")
    delta: ChatStreamDelta = Field(..., description="增量数据")
    finish_reason: FinishReason | None = Field(default=None, description="完成原因")
    usage: Usage | None = Field(default=None, description="使用统计 (最后一个块)")


# Forward references
ToolCall.model_rebuild()
Message.model_rebuild()
ToolDefinition.model_rebuild()
