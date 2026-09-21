"""
Decision adapter base class.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.llm.types import DecisionRequest, DecisionResponse


class BaseDecisionAdapter(ABC):
    """决策模型适配器基类"""

    def __init__(self, model_config: Any):
        self.model_config = model_config

    @abstractmethod
    async def decide(self, request: DecisionRequest, **kwargs: Any) -> DecisionResponse:
        """对 state 上的若干问题求值，返回类型化答案。"""
        raise NotImplementedError
