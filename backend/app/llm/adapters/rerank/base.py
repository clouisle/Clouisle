"""
Rerank 适配器基类
"""

from abc import ABC, abstractmethod
from typing import Any

from app.llm.types import RerankResponse


class BaseRerankAdapter(ABC):
    """重排序适配器基类"""

    def __init__(self, model_config: Any):
        self.model_config = model_config

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        """执行重排序。"""
        raise NotImplementedError
