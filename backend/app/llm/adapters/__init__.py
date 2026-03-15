"""
LLM 适配器
"""

from .chat import create_chat_model
from .embedding import create_embedding_model
from .image import create_image_adapter
from .audio import create_tts_adapter, create_stt_adapter
from .rerank import create_rerank_adapter

__all__ = [
    "create_chat_model",
    "create_embedding_model",
    "create_rerank_adapter",
    "create_image_adapter",
    "create_tts_adapter",
    "create_stt_adapter",
]
