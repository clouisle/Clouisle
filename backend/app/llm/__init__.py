"""
Clouisle LLM 调用模块

提供统一的 LLM 调用接口。

模型标识符格式:
    所有方法的 model_id 参数支持以下格式：
    - UUID: 数据库主键 (e.g., "550e8400-e29b-41d4-a716-446655440000")
    - 句柄: "provider/model_id" (e.g., "openai/gpt-4o", "anthropic/claude-3-opus")
    - None: 使用该类型的默认模型

使用示例:
    from app.llm import model_manager

    # Chat 调用 (使用默认模型)
    response = await model_manager.chat(
        messages=[{"role": "user", "content": "Hello!"}]
    )

    # Chat 调用 (指定模型句柄)
    response = await model_manager.chat(
        messages=[{"role": "user", "content": "Hello!"}],
        model_id="openai/gpt-4o"
    )

    # 流式调用
    async for chunk in model_manager.chat_stream(messages):
        print(chunk.delta.content, end="")

    # Embedding
    vectors = await model_manager.embed(["text1", "text2"])

    # 图像生成
    result = await model_manager.generate_image({"prompt": "A cat"})

    # TTS
    audio = await model_manager.text_to_speech({"text": "Hello!"})

    # STT
    text = await model_manager.speech_to_text({"audio": {...}})

    # 获取 LangChain 原生模型 (用于 LangGraph 等高级场景)
    chat_model = await model_manager.get_chat_model("anthropic/claude-3-opus")
"""

from .manager import model_manager, ModelManager
from .errors import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    ContextLengthError,
    ContentFilterError,
    ModelNotFoundError,
    ModelDisabledError,
    ProviderError,
    TimeoutError,
    InvalidRequestError,
    InsufficientQuotaError,
    QuotaExceededError,
    TaskNotFoundError,
    UnsupportedOperationError,
)
from .types import (
    # Base
    MediaContent,
    ImageContent,
    VideoContent,
    AudioContent,
    ContentType,
    ContentPart,
    Usage,
    TaskStatus,
    # Chat
    MessageRole,
    Message,
    ToolCall,
    FunctionCall,
    ToolDefinition,
    FunctionDefinition,
    FinishReason,
    ChatRequest,
    ChatResponse,
    ChatStreamDelta,
    ChatStreamChunk,
    # Image
    ImageGenerationRequest,
    ImageGenerationResponse,
    GeneratedImage,
    # Video
    VideoGenerationRequest,
    VideoGenerationResponse,
    # Audio
    TTSRequest,
    TTSResponse,
    STTRequest,
    STTResponse,
    RerankResult,
    RerankResponse,
)
from .tools import tool_registry, ToolRegistry, ToolInfo, ToolParameter

__all__ = [
    # Manager
    "model_manager",
    "ModelManager",
    # Errors
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "ContextLengthError",
    "ContentFilterError",
    "ModelNotFoundError",
    "ModelDisabledError",
    "ProviderError",
    "TimeoutError",
    "InvalidRequestError",
    "InsufficientQuotaError",
    "QuotaExceededError",
    "TaskNotFoundError",
    "UnsupportedOperationError",
    # Base Types
    "MediaContent",
    "ImageContent",
    "VideoContent",
    "AudioContent",
    "ContentType",
    "ContentPart",
    "Usage",
    "TaskStatus",
    # Chat Types
    "MessageRole",
    "Message",
    "ToolCall",
    "FunctionCall",
    "ToolDefinition",
    "FunctionDefinition",
    "FinishReason",
    "ChatRequest",
    "ChatResponse",
    "ChatStreamDelta",
    "ChatStreamChunk",
    # Image Types
    "ImageGenerationRequest",
    "ImageGenerationResponse",
    "GeneratedImage",
    # Video Types
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    # Audio Types
    "TTSRequest",
    "TTSResponse",
    "STTRequest",
    "STTResponse",
    # Rerank Types
    "RerankResult",
    "RerankResponse",
    # Tools
    "tool_registry",
    "ToolRegistry",
    "ToolInfo",
    "ToolParameter",
]
