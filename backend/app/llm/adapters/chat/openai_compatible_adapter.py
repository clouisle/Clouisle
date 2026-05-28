"""
OpenAI 兼容接口适配器

用于支持 OpenRouter、Together、Moonshot、智谱、通义千问等 OpenAI 兼容服务商。
也支持通过 OpenAI 兼容层转发的 Claude/Gemini API。
"""

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


class OpenAICompatibleAdapter(BaseChatAdapter):
    """
    OpenAI 兼容接口适配器

    特点：
    - 支持各种 OpenAI 兼容服务商
    - 支持通过 OpenRouter 等转发的 Claude/Gemini API
    - 自动检测实际模型类型，应用对应的解析逻辑
    """

    # 各服务商的默认 base_url
    PROVIDER_BASE_URLS: dict[str, str] = {
        "moonshot": "https://api.moonshot.cn/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "baichuan": "https://api.baichuan-ai.com/v1",
        "minimax": "https://api.minimax.chat/v1",
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
        "ollama": "http://localhost:11434/v1",
    }

    def __init__(self, model_config: Any, provider_hint: str | None = None):
        """
        初始化适配器

        Args:
            model_config: 模型配置
            provider_hint: 服务商提示，用于确定默认 base_url
        """
        super().__init__(model_config)
        self._provider_hint = provider_hint
        self._actual_provider = self._detect_actual_provider()

    def _detect_actual_provider(self) -> str:
        """
        检测实际的模型提供商

        用于处理通过 OpenRouter 等转发的 Claude/Gemini API
        """
        model_id = self.model_id.lower()

        # 检测是否是转发的 Claude
        if "claude" in model_id or "anthropic" in model_id:
            return "anthropic"

        # 检测是否是转发的 Gemini
        if "gemini" in model_id or "google" in model_id:
            return "google"

        # 检测是否是 DeepSeek
        if "deepseek" in model_id:
            return "deepseek"

        return "openai"

    def _get_base_url(self) -> str | None:
        """获取 base_url"""
        if self.base_url:
            return self.base_url

        if self._provider_hint:
            return self.PROVIDER_BASE_URLS.get(self._provider_hint.lower())

        return None

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

            # DeepSeek 特殊处理：assistant 消息需要 reasoning_content
            if (
                role_value == MessageRole.ASSISTANT.value
                and self._actual_provider == "deepseek"
            ):
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

        base_url = self._get_base_url()
        api_key = self.api_key

        # Ollama 不需要 API key
        if self._provider_hint == "ollama" and not api_key:
            api_key = "ollama"

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
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
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools
            if self._provider_hint == "zhipu":
                thinking = self.get_effective_thinking()
                if self.thinking_enabled:
                    request_params["thinking"] = (
                        thinking
                        if isinstance(thinking, dict) and "type" in thinking
                        else {"type": "enabled"}
                    )
                else:
                    request_params["thinking"] = {"type": "disabled"}
            # Reasoning effort (only when thinking is enabled)
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

            # 提取 reasoning（支持转发的模型）
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

        base_url = self._get_base_url()
        api_key = self.api_key

        # Ollama 不需要 API key
        if self._provider_hint == "ollama" and not api_key:
            api_key = "ollama"

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
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
                request_params["max_tokens"] = self.max_tokens
            if openai_tools:
                request_params["tools"] = openai_tools
                if self._provider_hint == "zhipu":
                    request_params["tool_stream"] = True
            if self._provider_hint == "zhipu":
                thinking = self.get_effective_thinking()
                if self.thinking_enabled:
                    request_params["thinking"] = (
                        thinking
                        if isinstance(thinking, dict) and "type" in thinking
                        else {"type": "enabled"}
                    )
                else:
                    request_params["thinking"] = {"type": "disabled"}
            # Reasoning effort (only when thinking is enabled)
            if self.thinking_enabled and self.reasoning_effort:
                request_params["reasoning_effort"] = self.reasoning_effort

            # Add response_format if provided in kwargs
            if "response_format" in kwargs and kwargs["response_format"] is not None:
                request_params["response_format"] = kwargs["response_format"]

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

                # 提取 reasoning（支持转发的模型）
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
