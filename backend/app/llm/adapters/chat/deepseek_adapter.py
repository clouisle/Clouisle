"""
DeepSeek Chat 适配器

支持 DeepSeek API，包括 R1 系列的 reasoning_content 功能。
"""

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.llm.types import (
    Message,
    MessageRole,
    ChatResponse,
    ChatStreamChunk,
    ToolDefinition,
    FinishReason,
    Usage,
)

from .base import BaseChatAdapter
from .thinking import ThinkingExtractor
from .tool_call_accumulator import ToolCallAccumulator

logger = logging.getLogger(__name__)


class DeepSeekAdapter(BaseChatAdapter):
    """
    DeepSeek Chat 适配器

    特点：
    - OpenAI 兼容接口
    - R1 模型的 reasoning_content 在 delta.reasoning_content
    - 历史消息中的 assistant 消息需要携带 reasoning_content 字段
    """

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """
        转换消息格式为 DeepSeek 格式

        DeepSeek R1 要求：
        - assistant 消息必须携带 reasoning_content 字段（即使为空）
        - 特别是当 assistant 消息包含 tool_calls 时
        """
        deepseek_messages: list[dict[str, Any]] = []

        for msg in messages:
            content: Any = msg.content

            # 处理多模态内容
            if isinstance(content, list):
                processed_content: list[dict[str, Any]] = []
                for part in content:
                    if hasattr(part, "type"):
                        part_type = (
                            part.type.value
                            if hasattr(part.type, "value")
                            else part.type
                        )
                        if part_type == "text" and hasattr(part, "text"):
                            processed_content.append(
                                {"type": "text", "text": part.text}
                            )
                        elif part_type == "image" and hasattr(part, "image"):
                            img = part.image
                            if img is not None and img.base64:
                                img_format = (
                                    img.format
                                    if hasattr(img, "format") and img.format
                                    else "png"
                                )
                                data_url = (
                                    f"data:image/{img_format};base64,{img.base64}"
                                )
                                processed_content.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": data_url},
                                    }
                                )
                            elif img is not None and img.url:
                                processed_content.append(
                                    {"type": "image_url", "image_url": {"url": img.url}}
                                )
                    elif isinstance(part, dict):
                        processed_content.append(part)
                content = processed_content if processed_content else ""

            role_value = msg.role.value if hasattr(msg.role, "value") else msg.role
            msg_dict: dict[str, Any] = {
                "role": role_value,
                "content": content if content else "",
            }

            # DeepSeek R1 特殊处理：assistant 消息需要 reasoning_content
            if role_value == MessageRole.ASSISTANT.value:
                # 如果有 tool_calls 或有 reasoning_content，必须携带该字段
                if msg.tool_calls or msg.reasoning_content is not None:
                    msg_dict["reasoning_content"] = msg.reasoning_content or ""

            # 处理工具调用
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]

            # 处理 tool_call_id
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id

            deepseek_messages.append(msg_dict)

        return deepseek_messages

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式调用"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or self.DEFAULT_BASE_URL,
            timeout=self.timeout,
        )

        try:
            deepseek_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": deepseek_messages,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.max_tokens is not None:
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools

            response = await client.chat.completions.create(**request_params)

            choice = response.choices[0]
            message = choice.message

            # 提取内容
            content = message.content

            # 提取 reasoning_content (DeepSeek R1)
            reasoning_content = ThinkingExtractor.extract(
                message,
                getattr(message, "model_extra", None),
            )

            # 提取工具调用
            tool_calls = None
            if message.tool_calls:
                tool_calls = [
                    self.create_tool_call(
                        tc.id,
                        tc.function.name,
                        tc.function.arguments,
                    )
                    for tc in message.tool_calls
                ]

            # 解析 finish_reason
            finish_reason = FinishReason.STOP
            if choice.finish_reason == "tool_calls":
                finish_reason = FinishReason.TOOL_CALLS
            elif choice.finish_reason == "length":
                finish_reason = FinishReason.LENGTH
            elif choice.finish_reason == "content_filter":
                finish_reason = FinishReason.CONTENT_FILTER

            # 解析 usage
            usage = Usage()
            if response.usage:
                usage = Usage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                )

            return self.create_response(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                response_id=response.id,
            )
        finally:
            await client.close()

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """流式调用"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or self.DEFAULT_BASE_URL,
            timeout=self.timeout,
        )

        try:
            deepseek_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": deepseek_messages,
                "stream": True,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.max_tokens is not None:
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools

            stream = await client.chat.completions.create(**request_params)

            response_id = str(uuid.uuid4())
            tool_accumulator = ToolCallAccumulator()

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason_str = chunk.choices[0].finish_reason

                # 提取内容
                content = delta.content if delta.content else None

                # 提取 reasoning_content (DeepSeek R1)
                # DeepSeek 在流式响应中通过 delta.reasoning_content 返回
                reasoning_content = ThinkingExtractor.extract(
                    delta,
                    getattr(delta, "model_extra", None),
                )

                # 累加工具调用
                tool_accumulator.accumulate(delta)

                # 处理完成
                tool_calls_delta = None
                finish_reason = None

                if finish_reason_str:
                    if (
                        finish_reason_str == "tool_calls"
                        and tool_accumulator.has_tool_calls()
                    ):
                        tool_calls_delta = tool_accumulator.finalize()
                        finish_reason = FinishReason.TOOL_CALLS
                    elif finish_reason_str == "stop":
                        finish_reason = FinishReason.STOP
                    elif finish_reason_str == "length":
                        finish_reason = FinishReason.LENGTH
                    elif finish_reason_str == "content_filter":
                        finish_reason = FinishReason.CONTENT_FILTER

                # 只有有内容时才 yield
                if content or reasoning_content or tool_calls_delta or finish_reason:
                    yield self.create_stream_chunk(
                        content=content,
                        reasoning_content=reasoning_content,
                        tool_calls=tool_calls_delta,
                        finish_reason=finish_reason,
                        response_id=response_id,
                    )
        finally:
            await client.close()
