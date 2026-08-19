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
from app.llm.token_counter import count_tokens

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

    # Anthropic prompt caching requires 1024 tokens for most models and 2048
    # tokens for Claude 3 Haiku; leave 256 tokens of local estimation margin.
    _CACHE_TOKEN_MARGIN = 256
    _CACHE_CONTROL = {"type": "ephemeral"}

    def _min_cache_prefix_tokens(self) -> int:
        """Return the model-specific cache prefix floor with safety margin."""
        minimum = 2048 if "claude-3-haiku" in self.model_id.lower() else 1024
        return minimum + self._CACHE_TOKEN_MARGIN

    @property
    def cache_control_enabled(self) -> bool:
        """是否启用 prompt caching（默认开启，可通过模型 config 的 cache_control 关闭）"""
        return bool(self.config.get("cache_control", True))

    def _count_tokens(self, text: str) -> int:
        """按模型/provider 估算文本 token 数"""
        if not text:
            return 0
        return count_tokens(
            text,
            model_id=self.model_id,
            provider=getattr(self.model_config, "provider", None),
        )

    def _message_text(self, msg: dict[str, Any]) -> str:
        """提取 Anthropic 消息的可计数文本"""
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if not isinstance(result_content, str):
                            result_content = json.dumps(
                                result_content, ensure_ascii=False, default=str
                            )
                        texts.append(result_content)
            return "\n".join(texts)
        return ""

    def _is_real_user_message(self, msg: dict[str, Any]) -> bool:
        """真用户消息：role=user 且不是 tool_result 包裹，且非空"""
        if msg.get("role") != "user":
            return False
        content = msg.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            if content[0].get("type") == "tool_result":
                return False
        return bool(content)

    def _mark_message_cache_breakpoint(self, msg: dict[str, Any]) -> None:
        """在消息第一个文本块上打缓存断点"""
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": self._CACHE_CONTROL,
                }
            ]
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    block["cache_control"] = self._CACHE_CONTROL
                    break

    def _apply_cache_breakpoints(
        self,
        system_prompt: str | None,
        anthropic_messages: list[dict[str, Any]],
        anthropic_tools: list[dict] | None,
    ) -> tuple[
        str | list[dict[str, Any]] | None,
        list[dict[str, Any]],
        list[dict] | None,
    ]:
        """
        为 system / tools / 历史消息添加 Anthropic prompt caching 断点。

        策略（Anthropic 官方多轮对话模式）：
        - system prompt：整个缓存（稳定前缀）
        - tools：最后一个工具打点（system+tools 前缀）
        - 第一条真 user 消息：工具循环期间前缀稳定，可复用
        - 倒数第二条真 user 消息：缓存几乎全部历史，跨轮次命中

        每个断点前缀估算 token 不足最小要求时跳过（避免 API 400）。
        """
        if not self.cache_control_enabled:
            return system_prompt, anthropic_messages, anthropic_tools

        system_tokens = self._count_tokens(system_prompt or "")

        # tools 断点：缓存 system + tools 前缀
        tools_tokens = 0
        if anthropic_tools:
            tools_tokens = self._count_tokens(
                json.dumps(anthropic_tools, ensure_ascii=False)
            )
            if system_tokens + tools_tokens >= self._min_cache_prefix_tokens():
                anthropic_tools[-1] = {
                    **anthropic_tools[-1],
                    "cache_control": self._CACHE_CONTROL,
                }

        # system 断点
        new_system: str | list[dict[str, Any]] | None = system_prompt
        if system_prompt and system_tokens >= self._min_cache_prefix_tokens():
            new_system = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": self._CACHE_CONTROL,
                }
            ]

        # 消息断点：第一条 + 倒数第二条真 user 消息
        cumulative = system_tokens + tools_tokens
        user_breakpoints: list[tuple[int, int]] = []
        for index, msg in enumerate(anthropic_messages):
            cumulative += self._count_tokens(self._message_text(msg))
            if self._is_real_user_message(msg):
                user_breakpoints.append((index, cumulative))

        targets: list[tuple[int, int]] = []
        if user_breakpoints:
            targets.append(user_breakpoints[0])
            if (
                len(user_breakpoints) >= 2
                and user_breakpoints[-2][0] != user_breakpoints[0][0]
            ):
                targets.append(user_breakpoints[-2])

        for index, prefix_tokens in targets:
            if prefix_tokens >= self._min_cache_prefix_tokens():
                self._mark_message_cache_breakpoint(anthropic_messages[index])

        return new_system, anthropic_messages, anthropic_tools

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
            timeout=self.http_timeout,
        )

        try:
            system_prompt, anthropic_messages = self._convert_messages(messages)
            anthropic_tools = self.convert_tools(tools)
            system_prompt, anthropic_messages, anthropic_tools = (
                self._apply_cache_breakpoints(
                    system_prompt, anthropic_messages, anthropic_tools
                )
            )

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
            if not has_output_config:
                if self.thinking_enabled:
                    thinking_config: dict[str, Any] = {"type": "enabled"}
                    if self.thinking_budget:
                        thinking_config["budget_tokens"] = self.thinking_budget
                    request_params["thinking"] = thinking_config
                else:
                    request_params["thinking"] = {"type": "disabled"}
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
                    cache_read_tokens=getattr(
                        response.usage, "cache_read_input_tokens", 0
                    )
                    or 0,
                    cache_creation_tokens=getattr(
                        response.usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                    total_input_tokens=(
                        response.usage.input_tokens
                        + (getattr(response.usage, "cache_read_input_tokens", 0) or 0)
                        + (
                            getattr(response.usage, "cache_creation_input_tokens", 0)
                            or 0
                        )
                    ),
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
            timeout=self.http_timeout,
        )

        try:
            system_prompt, anthropic_messages = self._convert_messages(messages)
            anthropic_tools = self.convert_tools(tools)
            system_prompt, anthropic_messages, anthropic_tools = (
                self._apply_cache_breakpoints(
                    system_prompt, anthropic_messages, anthropic_tools
                )
            )

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
            else:
                request_params["thinking"] = {"type": "disabled"}

            extra_body = self.get_passthrough_body() or None
            response_id = str(uuid.uuid4())

            # 用于累积工具调用
            current_tool_use: dict[str, Any] | None = None
            tool_calls: list[ToolCall] = []
            stream_usage_values = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            }
            stream_usage_seen = False

            def merge_stream_usage(usage_data: Any) -> None:
                nonlocal stream_usage_seen
                if not usage_data:
                    return
                stream_usage_seen = True
                for field in stream_usage_values:
                    value = getattr(usage_data, field, None)
                    if value is not None:
                        stream_usage_values[field] = max(
                            stream_usage_values[field], int(value or 0)
                        )

            async with client.messages.stream(
                **request_params,
                extra_body=extra_body,
            ) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", None)

                    if event_type == "message_start":
                        message = getattr(event, "message", None)
                        merge_stream_usage(getattr(message, "usage", None))
                        continue

                    # 处理 content_block_start
                    if event_type == "content_block_start":
                        content_block = getattr(event, "content_block", None)
                        if content_block:
                            block_type = getattr(content_block, "type", None)
                            if block_type == "tool_use":
                                tool_call_id = getattr(
                                    content_block, "id", None
                                ) or str(uuid.uuid4())
                                tool_call_name = getattr(content_block, "name", "")
                                current_tool_use = {
                                    "id": tool_call_id,
                                    "name": tool_call_name,
                                    "input": "",
                                }
                                tool_call_starts = None
                                if tool_call_name:
                                    tool_call_starts = [
                                        ToolCall(
                                            id=tool_call_id,
                                            type="function",
                                            function=FunctionCall(
                                                name=tool_call_name,
                                                arguments="{}",
                                            ),
                                        )
                                    ]
                                yield self.create_stream_chunk(
                                    response_id=response_id,
                                    tool_call_starts=tool_call_starts,
                                    stream_activity=True,
                                )
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
                                yield self.create_stream_chunk(
                                    response_id=response_id,
                                    stream_activity=True,
                                )

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

                    # 处理 message_delta (包含 stop_reason 和 usage)
                    if event_type == "message_delta":
                        delta = getattr(event, "delta", None)
                        merge_stream_usage(getattr(event, "usage", None))

                        usage = None
                        if stream_usage_seen:
                            input_tokens = stream_usage_values["input_tokens"]
                            output_tokens = stream_usage_values["output_tokens"]
                            cache_read_tokens = stream_usage_values[
                                "cache_read_input_tokens"
                            ]
                            cache_creation_tokens = stream_usage_values[
                                "cache_creation_input_tokens"
                            ]
                            total_input_tokens = (
                                input_tokens + cache_read_tokens + cache_creation_tokens
                            )
                            usage = Usage(
                                prompt_tokens=input_tokens,
                                completion_tokens=output_tokens,
                                total_tokens=total_input_tokens + output_tokens,
                                cache_read_tokens=cache_read_tokens,
                                cache_creation_tokens=cache_creation_tokens,
                                total_input_tokens=total_input_tokens,
                            )

                        if delta:
                            stop_reason = getattr(delta, "stop_reason", None)
                            finish_reason = self._map_finish_reason(stop_reason)

                            # 如果有工具调用，一起返回
                            yield self.create_stream_chunk(
                                tool_calls=tool_calls if tool_calls else None,
                                finish_reason=finish_reason,
                                usage=usage,
                                response_id=response_id,
                            )
                        elif usage:
                            yield self.create_stream_chunk(
                                usage=usage,
                                response_id=response_id,
                            )
                        continue

        finally:
            await client.close()
