"""
Rerank 相关类型定义
"""

from pydantic import BaseModel, Field

from .base import Usage


class RerankResult(BaseModel):
    """单条重排序结果"""

    index: int = Field(..., ge=0, description="原始文档索引")
    score: float = Field(..., ge=0, le=1, description="相关性分数")
    reason: str | None = Field(default=None, description="可选排序原因")


class RerankResponse(BaseModel):
    """重排序响应"""

    model: str = Field(..., description="模型名称")
    results: list[RerankResult] = Field(default_factory=list, description="排序结果")
    usage: Usage = Field(default_factory=Usage, description="使用统计")
