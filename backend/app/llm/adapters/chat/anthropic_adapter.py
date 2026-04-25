"""
Anthropic Claude Chat 适配器

支持 Anthropic Claude API，包括 extended thinking 功能。
"""

import json
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
    ToolCall,
    FunctionCall,
)

from .base import BaseChatAdapter

logger = logging.getLogger(__name__)


class AnthropicAdapter(BaseChatAdapter):
    """
    Anthropic Claude Chat 适配器

    特点：
    - 使用 Anthropic SDK 直接调用
    - thinking 通过 content blocks 返回: [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]
    - 流式时有 thinking_delta 事件
    - 工具调用通过 tool_use content block
    """

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """
        转换消息格式为 Anthropic 格式

        Returns:
            (system_prompt, messages) 元组
        """
        system_prompt: str | None = None
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            role_value = msg.role.value if hasattr(msg.role, "value") else msg.role

            # 系统消息单独处理
            if role_value == MessageRole.SYSTEM.value:
                content = msg.content
                if isinstance(content, list):
                    # 提取文本
                    texts = []
                    for part in content:
                        if hasattr(part, "text") and part.text:
                            texts.append(part.text)
                        elif isinstance(part, dict) and part.get("text"):
                            texts.append(part["text"])
                    content = "\n".join(texts)
                system_prompt = content
                continue

            # 处理 assistant 消息
            if role_value == MessageRole.ASSISTANT.value:
                content_blocks: list[dict[str, Any]] = []

                # 如果有 thinking，添加 thinking block
                if self.thinking_enabled and msg.reasoning_content:
                    content_blocks.append(
                        {
                            "type": "thinking",
                            "thinking": msg.reasoning_content,
                        }
                    )

                # 添加文本内容
                if msg.content:
                    if isinstance(msg.content, str):
                        content_blocks.append(
                            {
                                "type": "text",
                                "text": msg.content,
                            }
                        )
                    elif isinstance(msg.content, list):
                        for part in msg.content:
                            if hasattr(part, "text") and part.text:
                                content_blocks.append(
                                    {
                                        "type": "text",
                                        "text": part.text,
                                    }
                                )

                # 添加工具调用
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        args: str | dict = tc.function.arguments
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.function.name,
                                "input": args,
                            }
                        )

                if content_blocks:
                    anthropic_messages.append(
                        {
                            "role": "assistant",
                            "content": content_blocks,
                        }
                    )
                continue

            # 处理 tool 消息
            if role_value == MessageRole.TOOL.value:
                content = msg.content
                if isinstance(content, list):
                    texts = []
                    for part in content:
                        if hasattr(part, "text") and part.text:
                            texts.append(part.text)
                        elif isinstance(part, dict) and part.get("text"):
                            texts.append(part["text"])
                    content = "\n".join(texts)

                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": content or "",
                            }
                        ],
                    }
                )
                continue

            # 处理 user 消息
            content = msg.content
            if isinstance(content, list):
                content_blocks = []
                for part in content:
                    if hasattr(part, "type"):
                        part_type = (
                            part.type.value
                            if hasattr(part.type, "value")
                            else part.type
                        )
                        if part_type == "text" and hasattr(part, "text"):
                            content_blocks.append({"type": "text", "text": part.text})
                        elif part_type == "image" and hasattr(part, "image"):
                            img = part.image
                            if img is not None and img.base64:
                                img_format = (
                                    img.format
                                    if hasattr(img, "format") and img.format
                                    else "png"
                                )
                                content_blocks.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": f"image/{img_format}",
                                            "data": img.base64,
                                        },
                                    }
                                )
                            elif img is not None and img.url:
                                content_blocks.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "url",
                                            "url": img.url,
                                        },
                                    }
                                )
                    elif isinstance(part, dict):
                        content_blocks.append(part)
                content = content_blocks if content_blocks else []  # type: ignore[assignment]

            anthropic_messages.append(
                {
                    "role": "user",
                    "content": content if content else "",
                }
            )

        return system_prompt, anthropic_messages

    def convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """转换工具定义为 Anthropic 格式"""
        if not tools:
            return None

        return [
            {
                "name": tool.function.name,
                "description": tool.function.description or "",
                "input_schema": tool.function.parameters,
            }
            for tool in tools
        ]

    def _extract_response(
        self, response: Any
    ) -> tuple[str | None, str | None, list[ToolCall] | None]:
        """
        从 Anthropic 响应中提取内容

        Returns:
            (content, reasoning_content, tool_calls) 元组
        """
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            block_type = getattr(block, "type", None)

            # Log block type for debugging
            logger.debug(f"Processing block type: {block_type}, block: {block}")

            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    content_parts.append(text)
            elif block_type == "thinking":
                # ThinkingBlock has 'thinking' attribute
                thinking = getattr(block, "thinking", "")
                if thinking:
                    thinking_parts.append(thinking)
                    logger.debug(f"Extracted thinking content: {thinking[:100]}...")
            elif block_type == "tool_use":
                tool_id = getattr(block, "id", str(uuid.uuid4()))
                name = getattr(block, "name", "")
                tool_input = getattr(block, "input", {})
                if isinstance(tool_input, dict):
                    tool_input = json.dumps(tool_input)
                tool_calls.append(
                    ToolCall(
                        id=tool_id,
                        type="function",
                        function=FunctionCall(
                            name=name,
                            arguments=tool_input or "{}",
                        ),
                    )
                )

        content = "".join(content_parts).strip() or None
        reasoning = "".join(thinking_parts).strip() or None

        logger.debug(f"Extracted content length: {len(content) if content else 0}")
        logger.debug(
            f"Extracted reasoning length: {len(reasoning) if reasoning else 0}"
        )

        return content, reasoning, tool_calls or None

    def _map_finish_reason(self, stop_reason: str | None) -> FinishReason:
        """映射 Anthropic stop_reason 到 FinishReason"""
        if stop_reason == "tool_use":
            return FinishReason.TOOL_CALLS
        elif stop_reason == "max_tokens":
            return FinishReason.LENGTH
        elif stop_reason in ("end_turn", "stop_sequence"):
            return FinishReason.STOP
        return FinishReason.STOP

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式调用"""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        try:
            system_prompt, anthropic_messages = self._convert_messages(messages)
            anthropic_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": anthropic_messages,
                "max_tokens": self.max_tokens or 4096,
            }

            if system_prompt:
                request_params["system"] = system_prompt
            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if anthropic_tools:
                request_params["tools"] = anthropic_tools

            # Response format/schema support
            # Anthropic uses output_config parameter (requires SDK >= 0.80.0)
            # NOTE: output_config and thinking cannot be used together
            has_output_config = False
            if "response_format" in kwargs and kwargs["response_format"] is not None:
                response_format = kwargs["response_format"]
                logger.info(f"Anthropic adapter: response_format={response_format}")
                if isinstance(response_format, dict):
                    if response_format.get("type") == "json_schema":
                        # Extract the schema
                        json_schema_config = response_format.get("json_schema", {})
                        schema = json_schema_config.get("schema")
                        if schema:
                            # Use Anthropic's output_config format
                            # Note: additionalProperties must be False for Anthropic
                            if "additionalProperties" not in schema:
                                schema["additionalProperties"] = False
                            request_params["output_config"] = {
                                "format": {"type": "json_schema", "schema": schema}
                            }
                            has_output_config = True
                            logger.info(
                                "Anthropic adapter: Using output_config with schema"
                            )
                    elif response_format.get("type") == "json_object":
                        # Simple JSON mode - use a generic object schema
                        request_params["output_config"] = {
                            "format": {
                                "type": "json_schema",
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                },
                            }
                        }
                        has_output_config = True
                        logger.info(
                            "Anthropic adapter: Using output_config with generic object schema"
                        )

            # 启用 thinking (only if not using output_config)
            if self.thinking_enabled and not has_output_config:
                thinking_config: dict[str, Any] = {"type": "enabled"}
                if self.thinking_budget:
                    thinking_config["budget_tokens"] = self.thinking_budget
                request_params["thinking"] = thinking_config
                logger.info("Anthropic adapter: Enabled thinking")
            elif self.thinking_enabled and has_output_config:
                logger.warning(
                    "Anthropic adapter: Thinking disabled because output_config is used (they cannot be used together)"
                )

            # Regular response
            response = await client.messages.create(
                **request_params,
                extra_body=self.get_passthrough_body() or None,
            )

            # 提取内容
            content, reasoning_content, tool_calls = self._extract_response(response)

            # 解析 finish_reason
            finish_reason = self._map_finish_reason(response.stop_reason)

            # 解析 usage
            usage = Usage()
            if response.usage:
                usage = Usage(
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.input_tokens
                    + response.usage.output_tokens,
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
        from anthropic import AsyncAnthropic

        # Check if structured output is requested
        # If so, use non-streaming API and simulate streaming
        if "response_format" in kwargs and kwargs["response_format"] is not None:
            # Call non-streaming API which supports output_config
            response = await self.chat(messages, tools, **kwargs)

            # Simulate streaming by yielding the content in chunks
            if response.content:
                # Split content into smaller chunks to simulate streaming
                chunk_size = 10  # characters per chunk
                content = response.content
                for i in range(0, len(content), chunk_size):
                    chunk_text = content[i : i + chunk_size]
                    yield self.create_stream_chunk(
                        content=chunk_text,
                        response_id=response.id,
                    )

            # Yield reasoning content if present
            if response.reasoning_content:
                yield self.create_stream_chunk(
                    reasoning_content=response.reasoning_content,
                    response_id=response.id,
                )

            # Yield final chunk with finish reason and usage
            yield self.create_stream_chunk(
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
                usage=response.usage,
                response_id=response.id,
            )
            return

        # Regular streaming without structured output
        client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        try:
            system_prompt, anthropic_messages = self._convert_messages(messages)
            anthropic_tools = self.convert_tools(tools)

            request_params: dict[str, Any] = {
                "model": self.model_id,
                "messages": anthropic_messages,
                "max_tokens": self.max_tokens or 4096,
            }

            if system_prompt:
                request_params["system"] = system_prompt
            if self.temperature is not None:
                request_params["temperature"] = self.temperature
            if self.top_p is not None:
                request_params["top_p"] = self.top_p
            if anthropic_tools:
                request_params["tools"] = anthropic_tools

            # 启用 thinking
            if self.thinking_enabled:
                thinking_config: dict[str, Any] = {"type": "enabled"}
                if self.thinking_budget:
                    thinking_config["budget_tokens"] = self.thinking_budget
                request_params["thinking"] = thinking_config

            extra_body = self.get_passthrough_body() or None
            response_id = str(uuid.uuid4())

            # 用于累积工具调用
            current_tool_use: dict[str, Any] | None = None
            tool_calls: list[ToolCall] = []

            async with client.messages.stream(
                **request_params,
                extra_body=extra_body,
            ) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", None)

                    # 处理 content_block_start
                    if event_type == "content_block_start":
                        content_block = getattr(event, "content_block", None)
                        if content_block:
                            block_type = getattr(content_block, "type", None)
                            if block_type == "tool_use":
                                current_tool_use = {
                                    "id": getattr(
                                        content_block, "id", str(uuid.uuid4())
                                    ),
                                    "name": getattr(content_block, "name", ""),
                                    "input": "",
                                }
                        continue

                    # 处理 content_block_delta
                    if event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if not delta:
                            continue

                        delta_type = getattr(delta, "type", None)

                        # 文本增量
                        if delta_type == "text_delta":
                            text = getattr(delta, "text", None)
                            if text:
                                yield self.create_stream_chunk(
                                    content=text,
                                    response_id=response_id,
                                )

                        # thinking 增量
                        elif delta_type == "thinking_delta":
                            thinking = getattr(delta, "thinking", None)
                            if thinking:
                                yield self.create_stream_chunk(
                                    reasoning_content=thinking,
                                    response_id=response_id,
                                )

                        # 工具调用输入增量
                        elif delta_type == "input_json_delta":
                            if current_tool_use is not None:
                                partial_json = getattr(delta, "partial_json", "")
                                current_tool_use["input"] += partial_json

                        continue

                    # 处理 content_block_stop
                    if event_type == "content_block_stop":
                        if current_tool_use is not None:
                            # 完成一个工具调用
                            tool_calls.append(
                                ToolCall(
                                    id=current_tool_use["id"],
                                    type="function",
                                    function=FunctionCall(
                                        name=current_tool_use["name"],
                                        arguments=current_tool_use["input"] or "{}",
                                    ),
                                )
                            )
                            current_tool_use = None
                        continue

                    # 处理 message_stop
                    if event_type == "message_stop":
                        continue

                    # 处理 message_delta (包含 stop_reason)
                    if event_type == "message_delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            stop_reason = getattr(delta, "stop_reason", None)
                            finish_reason = self._map_finish_reason(stop_reason)

                            # 如果有工具调用，一起返回
                            yield self.create_stream_chunk(
                                tool_calls=tool_calls if tool_calls else None,
                                finish_reason=finish_reason,
                                response_id=response_id,
                            )
        finally:
            await client.close()
