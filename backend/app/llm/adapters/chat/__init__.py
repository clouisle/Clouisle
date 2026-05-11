"""
Chat 适配器
"""

from .factory import create_chat_model
from .base import BaseChatAdapter
from .openai_adapter import OpenAIAdapter
from .deepseek_adapter import DeepSeekAdapter
from .moonshot_adapter import MoonshotAdapter
from .ollama_adapter import OllamaAdapter
from .anthropic_adapter import AnthropicAdapter
from .gemini_adapter import GeminiAdapter
from .xai_adapter import XAIAdapter
from .openai_compatible_adapter import OpenAICompatibleAdapter
from .thinking import ThinkingExtractor, ContentExtractor
from .tool_call_accumulator import ToolCallAccumulator, extract_tool_calls_from_content

__all__ = [
    "create_chat_model",
    "BaseChatAdapter",
    "OpenAIAdapter",
    "DeepSeekAdapter",
    "MoonshotAdapter",
    "OllamaAdapter",
    "AnthropicAdapter",
    "GeminiAdapter",
    "XAIAdapter",
    "OpenAICompatibleAdapter",
    "ThinkingExtractor",
    "ContentExtractor",
    "ToolCallAccumulator",
    "extract_tool_calls_from_content",
]
