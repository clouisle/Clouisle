"""
Embedding 相关类型定义
"""

from pydantic import BaseModel, Field

from .base import Usage


class EmbeddingResponse(BaseModel):
    """嵌入响应"""

    model: str = Field(..., description="模型名称")
    embeddings: list[list[float]] = Field(
        default_factory=list, description="嵌入向量列表"
    )
    usage: Usage = Field(default_factory=Usage, description="使用统计")
