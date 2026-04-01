"""
LLM 类型定义
"""

# Base types
from .base import (
    MediaContent,
    ImageContent,
    VideoContent,
    AudioContent,
    ContentType,
    ContentPart,
    Usage,
    TaskStatus,
)

# Chat types
from .chat import (
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
)

# Image types
from .image import (
    ImageSize,
    ImageStyle,
    ImageQuality,
    ImageGenerationRequest,
    GeneratedImage,
    ImageGenerationResponse,
)

# Video types
from .video import (
    AspectRatio,
    VideoGenerationRequest,
    VideoGenerationResponse,
)

# Audio types
from .audio import (
    TTSVoice,
    AudioFormat,
    TTSRequest,
    TTSResponse,
    STTRequest,
    STTResponse,
    TranscriptionSegment,
    TranscriptionWord,
)

# Rerank types
from .rerank import (
    RerankResult,
    RerankResponse,
)

__all__ = [
    # Base
    "MediaContent",
    "ImageContent",
    "VideoContent",
    "AudioContent",
    "ContentType",
    "ContentPart",
    "Usage",
    "TaskStatus",
    # Chat
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
    # Image
    "ImageSize",
    "ImageStyle",
    "ImageQuality",
    "ImageGenerationRequest",
    "GeneratedImage",
    "ImageGenerationResponse",
    # Video
    "AspectRatio",
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    # Audio
    "TTSVoice",
    "AudioFormat",
    "TTSRequest",
    "TTSResponse",
    "STTRequest",
    "STTResponse",
    "TranscriptionSegment",
    "TranscriptionWord",
    # Rerank
    "RerankResult",
    "RerankResponse",
]
