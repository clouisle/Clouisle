"""
OpenAI Chat 适配器

支持 OpenAI 官方 API，包括 o1/o3 系列的 reasoning 功能。
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.llm.errors import InvalidRequestError
from app.llm.types import (
    Message,
    ChatResponse,
    ChatStreamChunk,
    ToolDefinition,
    FinishReason,
    Usage,
)

from .base import BaseChatAdapter, extract_cached_tokens
from .thinking import ThinkingExtractor
from .tool_call_accumulator import ToolCallAccumulator


class OpenAIAdapter(BaseChatAdapter):
    """
    OpenAI Chat 适配器

    特点：
    - 使用 OpenAI SDK 直接调用
    - 支持 o1/o3 模型的 reasoning_content
    - 标准工具调用格式
    """

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """转换消息格式为 OpenAI 格式"""
        openai_messages: list[dict[str, Any]] = []

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
                            if (
                                img is None
                                or getattr(img, "asset_ref", None)
                                or not (
                                    getattr(img, "base64", None)
                                    or getattr(img, "url", None)
                                )
                            ):
                                raise InvalidRequestError(
                                    message="Image payload is missing or unresolved"
                                )
                            mime = (
                                getattr(img, "mime_type", None)
                                or f"image/{getattr(img, 'format', 'png')}"
                            )
                            if mime not in {
                                "image/png",
                                "image/jpeg",
                                "image/gif",
                                "image/webp",
                            }:
                                raise InvalidRequestError(
                                    message=f"Unsupported image MIME type: {mime}"
                                )
                            image_url = getattr(img, "url", None)
                            image_base64 = getattr(img, "base64", None)
                            if image_base64:
                                url = f"data:{mime};base64,{image_base64}"
                            elif image_url:
                                from urllib.parse import urlsplit

                                if image_url.startswith("data:"):
                                    header, separator, _encoded = image_url.partition(
                                        ","
                                    )
                                    if not separator or ";base64" not in header.lower():
                                        raise InvalidRequestError(
                                            message="Image data URL must use base64 encoding"
                                        )
                                    data_mime = header[5:].split(";", 1)[0].lower()
                                    if data_mime != mime:
                                        raise InvalidRequestError(
                                            message="Image data URL MIME does not match declared image MIME"
                                        )
                                    url = image_url
                                else:
                                    parsed_url = urlsplit(image_url)
                                    if (
                                        parsed_url.scheme not in {"http", "https"}
                                        or not parsed_url.hostname
                                    ):
                                        raise InvalidRequestError(
                                            message="Image URL must be absolute HTTP(S) or a base64 data URL"
                                        )
                                    url = image_url
                            else:
                                raise InvalidRequestError(
                                    message="Image payload is missing or unresolved"
                                )
                            processed_content.append(
                                {"type": "image_url", "image_url": {"url": url}}
                            )
                        elif part_type == "image_url" and hasattr(part, "image_url"):
                            processed_content.append(
                                {"type": "image_url", "image_url": part.image_url}
                            )
                        elif part_type == "file" and hasattr(part, "file"):
                            raise InvalidRequestError(
                                message="File input is unsupported by OpenAI chat adapter"
                            )
                        elif part_type in {"audio", "video"}:
                            raise InvalidRequestError(
                                message=f"{part_type.title()} input is unsupported by OpenAI chat adapter"
                            )
                        else:
                            raise InvalidRequestError(
                                message=f"Unsupported content part: {part_type}"
                            )
                    elif isinstance(part, dict):
                        processed_content.append(part)
                    else:
                        raise InvalidRequestError(
                            message="Invalid multimodal content part"
                        )
                content = processed_content if processed_content else ""

            role_value = msg.role.value if hasattr(msg.role, "value") else msg.role
            msg_dict: dict[str, Any] = {
                "role": role_value,
                "content": content if content else "",
            }

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

            openai_messages.append(msg_dict)

        return openai_messages

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
            base_url=self.base_url,
            timeout=self.http_timeout,
        )

        try:
            openai_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": openai_messages,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if self.max_tokens is not None:
                request_params["max_completion_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools
            # OpenAI o1/o3 reasoning effort (only when thinking is enabled)
            if self.thinking_enabled and self.reasoning_effort:
                request_params["reasoning_effort"] = self.reasoning_effort

            # Add response_format if provided in kwargs
            if "response_format" in kwargs and kwargs["response_format"] is not None:
                request_params["response_format"] = kwargs["response_format"]

            response = await client.chat.completions.create(
                **request_params,
                extra_body=self.get_passthrough_body() or None,
            )

            choice = response.choices[0]
            message = choice.message

            # 提取内容
            content = message.content

            # 提取 reasoning (o1/o3 模型)
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
                    cache_read_tokens=extract_cached_tokens(response.usage),
                    total_input_tokens=response.usage.prompt_tokens,
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
            base_url=self.base_url,
            timeout=self.http_timeout,
        )

        try:
            openai_messages = self._convert_messages(messages)
            openai_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": openai_messages,
                "stream": True,
            }

            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if self.max_tokens is not None:
                request_params["max_completion_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools
            # OpenAI o1/o3 reasoning effort (only when thinking is enabled)
            if self.thinking_enabled and self.reasoning_effort:
                request_params["reasoning_effort"] = self.reasoning_effort

            # Add response_format if provided in kwargs
            if "response_format" in kwargs and kwargs["response_format"] is not None:
                request_params["response_format"] = kwargs["response_format"]

            # Streaming responses omit usage unless explicitly requested;
            # it arrives on the terminal chunk as an accumulated snapshot.
            request_params["stream_options"] = {"include_usage": True}

            stream = await client.chat.completions.create(
                **request_params,
                extra_body=self.get_passthrough_body() or None,
            )

            response_id = str(uuid.uuid4())
            tool_accumulator = ToolCallAccumulator()

            async for chunk in stream:
                if not chunk.choices:
                    # OpenAI 流式的 usage 在最后一个 chunk 返回（choices 为空）
                    if getattr(chunk, "usage", None):
                        yield self.create_stream_chunk(
                            response_id=response_id,
                            usage=Usage(
                                prompt_tokens=chunk.usage.prompt_tokens,
                                completion_tokens=chunk.usage.completion_tokens,
                                total_tokens=chunk.usage.total_tokens,
                                cache_read_tokens=extract_cached_tokens(chunk.usage),
                                total_input_tokens=chunk.usage.prompt_tokens,
                            ),
                        )
                    else:
                        yield self.create_stream_chunk(
                            response_id=response_id,
                            stream_activity=True,
                        )
                    continue

                delta = chunk.choices[0].delta
                finish_reason_str = chunk.choices[0].finish_reason

                # 提取内容
                content = delta.content if delta.content else None

                # 提取 reasoning (o1/o3 模型)
                reasoning_content = ThinkingExtractor.extract(
                    delta,
                    getattr(delta, "model_extra", None),
                )

                raw_tool_calls = getattr(delta, "tool_calls", None)

                # 累加工具调用
                tool_call_starts = tool_accumulator.accumulate(delta)

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
                if (
                    content
                    or reasoning_content
                    or tool_calls_delta
                    or tool_call_starts
                    or finish_reason
                ):
                    yield self.create_stream_chunk(
                        content=content,
                        reasoning_content=reasoning_content,
                        tool_calls=tool_calls_delta,
                        tool_call_starts=tool_call_starts,
                        finish_reason=finish_reason,
                        response_id=response_id,
                        stream_activity=bool(
                            raw_tool_calls
                            and not (
                                content
                                or reasoning_content
                                or tool_calls_delta
                                or finish_reason
                            )
                        ),
                    )
                elif raw_tool_calls:
                    yield self.create_stream_chunk(
                        response_id=response_id,
                        stream_activity=True,
                    )
        finally:
            await client.close()
