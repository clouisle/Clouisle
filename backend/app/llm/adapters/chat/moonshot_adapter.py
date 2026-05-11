"""
Moonshot Chat 适配器

支持 Moonshot (Kimi) API，包括 thinking 功能和 preserved thinking。
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


class MoonshotAdapter(BaseChatAdapter):
    """
    Moonshot (Kimi) Chat 适配器

    特点：
    - OpenAI 兼容接口
    - 支持 thinking 参数：{"type": "enabled"|"disabled", "keep": "all"|null}
    - 推理模型：kimi-k2.6, kimi-k2.5
    - reasoning_content 在 delta.reasoning_content 和 message.reasoning_content
    """

    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """转换消息格式为 Moonshot 格式"""
        moonshot_messages: list[dict[str, Any]] = []

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

            # Moonshot 支持 reasoning_content
            if role_value == MessageRole.ASSISTANT.value:
                if msg.reasoning_content is not None:
                    msg_dict["reasoning_content"] = msg.reasoning_content

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

            moonshot_messages.append(msg_dict)

        return moonshot_messages

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
            moonshot_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": moonshot_messages,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if self.max_tokens is not None:
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools

            # Moonshot 明确传递 thinking 参数
            thinking = self.get_effective_thinking()
            if self.thinking_enabled:
                request_params["thinking"] = (
                    thinking if isinstance(thinking, dict) else {"type": "enabled"}
                )
            else:
                request_params["thinking"] = {"type": "disabled"}

            response = await client.chat.completions.create(
                **request_params,
                extra_body=self.get_passthrough_body() or None,
            )

            choice = response.choices[0]
            message = choice.message

            # 提取内容
            content = message.content

            # 提取 reasoning_content
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
            moonshot_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": moonshot_messages,
                "stream": True,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if self.max_tokens is not None:
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools

            # Moonshot 明确传递 thinking 参数
            thinking = self.get_effective_thinking()
            if self.thinking_enabled:
                request_params["thinking"] = (
                    thinking if isinstance(thinking, dict) else {"type": "enabled"}
                )
            else:
                request_params["thinking"] = {"type": "disabled"}

            stream = await client.chat.completions.create(
                **request_params,
                extra_body=self.get_passthrough_body() or None,
            )

            response_id = str(uuid.uuid4())
            tool_accumulator = ToolCallAccumulator()

            async for chunk in stream:
                if not chunk.choices:
                    yield self.create_stream_chunk(
                        response_id=response_id,
                        stream_activity=True,
                    )
                    continue

                delta = chunk.choices[0].delta
                finish_reason_str = chunk.choices[0].finish_reason

                # 提取内容
                content = delta.content if delta.content else None

                # 提取 reasoning_content
                reasoning_content = ThinkingExtractor.extract(
                    delta,
                    getattr(delta, "model_extra", None),
                )

                raw_tool_calls = getattr(delta, "tool_calls", None)

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
                elif raw_tool_calls:
                    yield self.create_stream_chunk(
                        response_id=response_id,
                        stream_activity=True,
                    )
        finally:
            await client.close()
