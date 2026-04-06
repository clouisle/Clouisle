"""
Chat 适配器基类

定义统一的 Chat 适配器接口，所有服务商适配器都需要实现这个接口。
"""

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.llm.types import (
    Message,
    ChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    ToolCall,
    FunctionCall,
    ToolDefinition,
    FinishReason,
    Usage,
)


logger = logging.getLogger(__name__)


class BaseChatAdapter(ABC):
    """
    Chat 适配器基类

    所有服务商适配器都需要继承此类并实现抽象方法。
    适配器负责：
    1. 消息格式转换（输入）
    2. 响应解析（输出）
    3. 思考内容提取
    4. 工具调用处理
    """

    def __init__(self, model_config: Any):
        """
        初始化适配器

        Args:
            model_config: 模型配置对象，包含 provider, model_id, api_key, base_url 等
        """
        self.model_config = model_config

    @property
    def model_id(self) -> str:
        """模型 ID"""
        return self.model_config.model_id

    @property
    def api_key(self) -> str | None:
        """API Key"""
        return self.model_config.api_key

    @property
    def base_url(self) -> str | None:
        """Base URL"""
        return self.model_config.base_url

    @property
    def default_params(self) -> dict[str, Any]:
        """默认参数"""
        return self.model_config.default_params or {}

    @property
    def config(self) -> dict[str, Any]:
        """额外配置"""
        return self.model_config.config or {}

    @property
    def temperature(self) -> float | None:
        """温度参数"""
        return self.default_params.get("temperature")

    @property
    def top_p(self) -> float | None:
        """Top P 参数"""
        return self.default_params.get("top_p")

    @property
    def max_tokens(self) -> int | None:
        """最大输出 token"""
        # 优先使用 ORM 独立字段 max_output_tokens
        max_output = getattr(self.model_config, "max_output_tokens", None)
        if max_output is not None:
            return max_output
        # 其次从 default_params 读取
        max_from_params = self.default_params.get("max_tokens")
        if max_from_params is not None:
            return int(max_from_params)
        # 最后从 config 读取
        max_from_config = self.config.get("max_tokens")
        if max_from_config is not None:
            return int(max_from_config)
        return None

    @property
    def timeout(self) -> int:
        """超时时间"""
        return self.config.get("timeout", 60)

    @property
    def thinking_enabled(self) -> bool:
        """是否启用 thinking/reasoning"""
        thinking = self.config.get("thinking") or self.default_params.get("thinking")
        if thinking is None:
            return False
        if isinstance(thinking, bool):
            return thinking
        if isinstance(thinking, dict):
            return thinking.get("enabled", True)
        return bool(thinking)

    @property
    def thinking_budget(self) -> int | None:
        """thinking token 预算"""
        thinking = self.config.get("thinking") or self.default_params.get("thinking")
        if isinstance(thinking, dict):
            return thinking.get("budget_tokens") or thinking.get("budget")
        return None

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """
        非流式调用

        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 额外参数

        Returns:
            ChatResponse: 响应对象
        """
        pass

    @abstractmethod
    def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        流式调用

        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        pass

    def convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """
        转换工具定义为服务商格式

        默认实现为 OpenAI 格式，子类可覆盖

        Args:
            tools: 工具定义列表

        Returns:
            转换后的工具列表
        """
        if not tools:
            return None

        return [
            {
                "type": tool.type,
                "function": {
                    "name": tool.function.name,
                    "description": tool.function.description or "",
                    "parameters": tool.function.parameters,
                },
            }
            for tool in tools
        ]

    def create_tool_call(
        self,
        tool_id: str | None,
        name: str,
        arguments: str | dict,
    ) -> ToolCall:
        """
        创建工具调用对象

        Args:
            tool_id: 工具调用 ID
            name: 函数名
            arguments: 函数参数

        Returns:
            ToolCall 对象
        """
        import json

        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)

        return ToolCall(
            id=tool_id or str(uuid.uuid4()),
            type="function",
            function=FunctionCall(
                name=name,
                arguments=arguments,
            ),
        )

    def create_response(
        self,
        content: str | None = None,
        reasoning_content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: FinishReason = FinishReason.STOP,
        usage: Usage | None = None,
        response_id: str | None = None,
    ) -> ChatResponse:
        """
        创建响应对象

        Args:
            content: 响应内容
            reasoning_content: 思考内容
            tool_calls: 工具调用列表
            finish_reason: 完成原因
            usage: 使用统计
            response_id: 响应 ID

        Returns:
            ChatResponse 对象
        """
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS

        return ChatResponse(
            id=response_id or str(uuid.uuid4()),
            model=self.model_id,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage or Usage(),
        )

    def create_stream_chunk(
        self,
        content: str | None = None,
        reasoning_content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: FinishReason | None = None,
        usage: Usage | None = None,
        response_id: str | None = None,
    ) -> ChatStreamChunk:
        """
        创建流式响应块

        Args:
            content: 增量内容
            reasoning_content: 思考内容增量
            tool_calls: 工具调用
            finish_reason: 完成原因
            usage: 使用统计
            response_id: 响应 ID

        Returns:
            ChatStreamChunk 对象
        """
        return ChatStreamChunk(
            id=response_id or str(uuid.uuid4()),
            model=self.model_id,
            delta=ChatStreamDelta(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,
            usage=usage,
        )
