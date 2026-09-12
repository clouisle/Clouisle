"""
Embedding 适配器
"""

from .adapter import (
    BaseEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
    create_embedding_adapter,
)
from .factory import create_embedding_model

__all__ = [
    "create_embedding_model",
    "create_embedding_adapter",
    "BaseEmbeddingAdapter",
    "OpenAICompatibleEmbeddingAdapter",
]
