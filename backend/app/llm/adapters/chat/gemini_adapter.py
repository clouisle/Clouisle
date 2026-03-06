"""
Google Gemini Chat 适配器

支持 Google Gemini API，包括 Gemini 2.0 Flash Thinking 的思考功能。
使用新的 google-genai SDK。
"""

import json
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


class GeminiAdapter(BaseChatAdapter):
    """
    Google Gemini Chat 适配器

    特点：
    - 使用 Google GenAI SDK (google-genai)
    - Gemini 2.0 Flash Thinking 返回 thought=True 的 parts
    - 工具调用通过 function_call part
    """

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """
        转换消息格式为 Gemini 格式

        Returns:
            (system_instruction, contents) 元组
        """
        system_instruction: str | None = None
        contents: list[dict[str, Any]] = []

        for msg in messages:
            role_value = msg.role.value if hasattr(msg.role, "value") else msg.role

            # 系统消息单独处理
            if role_value == MessageRole.SYSTEM.value:
                content = msg.content
                if isinstance(content, list):
                    texts = []
                    for part in content:
                        if hasattr(part, "text") and part.text:
                            texts.append(part.text)
                        elif isinstance(part, dict) and part.get("text"):
                            texts.append(part["text"])
                    content = "\n".join(texts)
                system_instruction = content
                continue

            # 映射角色
            gemini_role = "user" if role_value == MessageRole.USER.value else "model"

            # 处理 tool 消息 - Gemini 使用 function_response
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

                # 尝试解析为 JSON
                try:
                    response_data = json.loads(content) if content else {}
                except json.JSONDecodeError:
                    response_data = {"result": content}

                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "name": msg.tool_call_id or "unknown",
                                    "response": response_data,
                                }
                            }
                        ],
                    }
                )
                continue

            # 构建 parts
            parts: list[dict[str, Any]] = []

            # 处理 assistant 消息的 thinking
            if role_value == MessageRole.ASSISTANT.value and msg.reasoning_content:
                parts.append(
                    {
                        "thought": True,
                        "text": msg.reasoning_content,
                    }
                )

            # 处理内容
            content = msg.content
            if isinstance(content, str):
                if content:
                    parts.append({"text": content})
            elif isinstance(content, list):
                for part in content:
                    if hasattr(part, "type"):
                        part_type = (
                            part.type.value
                            if hasattr(part.type, "value")
                            else part.type
                        )
                        if part_type == "text" and hasattr(part, "text") and part.text:
                            parts.append({"text": part.text})
                        elif part_type == "image" and hasattr(part, "image"):
                            img = part.image
                            if img is not None and img.base64:
                                img_format = (
                                    img.format
                                    if hasattr(img, "format") and img.format
                                    else "png"
                                )
                                parts.append(
                                    {
                                        "inline_data": {
                                            "mime_type": f"image/{img_format}",
                                            "data": img.base64,
                                        }
                                    }
                                )
                            elif img is not None and img.url:
                                parts.append(
                                    {
                                        "file_data": {
                                            "file_uri": img.url,
                                        }
                                    }
                                )
                    elif isinstance(part, dict):
                        if part.get("text"):
                            parts.append({"text": part["text"]})

            # 处理工具调用
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args: str | dict = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    parts.append(
                        {
                            "function_call": {
                                "name": tc.function.name,
                                "args": args,
                            }
                        }
                    )

            if parts:
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": parts,
                    }
                )

        return system_instruction, contents

    def convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """转换工具定义为 Gemini 格式"""
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            func_decl: dict[str, Any] = {
                "name": tool.function.name,
                "description": tool.function.description or "",
            }
            # Gemini 使用 parameters 而不是 input_schema
            if tool.function.parameters:
                func_decl["parameters"] = tool.function.parameters
            function_declarations.append(func_decl)

        return [{"function_declarations": function_declarations}]

    def _extract_response(
        self, response: Any
    ) -> tuple[str | None, str | None, list[ToolCall] | None]:
        """
        从 Gemini 响应中提取内容

        Returns:
            (content, reasoning_content, tool_calls) 元组
        """
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        # 新 SDK 的响应结构
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return None, None, None

        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        if not content:
            return None, None, None

        parts = getattr(content, "parts", None)
        if not parts:
            return None, None, None

        for part in parts:
            # 检查是否是 thinking part
            if getattr(part, "thought", False):
                text = getattr(part, "text", "")
                if text:
                    thinking_parts.append(text)
            # 检查是否是 function_call
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                args = dict(fc.args) if hasattr(fc, "args") and fc.args else {}
                tool_calls.append(
                    ToolCall(
                        id=str(uuid.uuid4()),
                        type="function",
                        function=FunctionCall(
                            name=fc.name if hasattr(fc, "name") else "",
                            arguments=json.dumps(args),
                        ),
                    )
                )
            # 普通文本
            elif hasattr(part, "text") and part.text:
                content_parts.append(part.text)

        text_content = "".join(content_parts).strip() or None
        reasoning = "".join(thinking_parts).strip() or None

        return text_content, reasoning, tool_calls or None

    def _map_finish_reason(self, finish_reason: Any) -> FinishReason:
        """映射 Gemini finish_reason 到 FinishReason"""
        if finish_reason is None:
            return FinishReason.STOP

        reason_str = str(finish_reason).upper()
        if "STOP" in reason_str:
            return FinishReason.STOP
        elif "MAX_TOKENS" in reason_str or "LENGTH" in reason_str:
            return FinishReason.LENGTH
        elif "SAFETY" in reason_str:
            return FinishReason.CONTENT_FILTER
        elif "TOOL" in reason_str or "FUNCTION" in reason_str:
            return FinishReason.TOOL_CALLS
        return FinishReason.STOP

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式调用"""
        from google import genai

        # 创建客户端，支持自定义 base_url
        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            # google-genai 使用 http_options 设置自定义端点
            client_kwargs["http_options"] = {"base_url": self.base_url}
        client = genai.Client(**client_kwargs)

        system_instruction, contents = self._convert_messages(messages)
        gemini_tools = self.convert_tools(tools)

        # 构建生成配置
        generation_config: dict[str, Any] = {}
        if self.temperature is not None:
            generation_config["temperature"] = self.temperature
        if self.top_p is not None:
            generation_config["top_p"] = self.top_p
        if self.max_tokens is not None:
            generation_config["max_output_tokens"] = self.max_tokens
        # Gemini 2.0 Flash Thinking 需要设置 thinking_config
        if self.thinking_enabled:
            generation_config["thinking_config"] = {
                "thinking_budget": self.thinking_budget or 8192
            }

        # Response format/schema support
        # Gemini uses response_schema (not response_format like OpenAI)
        if "response_format" in kwargs and kwargs["response_format"] is not None:
            response_format = kwargs["response_format"]
            # Convert OpenAI format to Gemini format
            if isinstance(response_format, dict):
                if response_format.get("type") == "json_object":
                    # For simple JSON mode, we can set response_mime_type
                    generation_config["response_mime_type"] = "application/json"
                elif response_format.get("type") == "json_schema":
                    # For JSON schema, extract the schema
                    json_schema_config = response_format.get("json_schema", {})
                    schema = json_schema_config.get("schema")
                    if schema:
                        generation_config["response_schema"] = schema
                        generation_config["response_mime_type"] = "application/json"

        # 构建请求参数
        request_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "contents": contents,
        }
        if system_instruction:
            request_kwargs["config"] = {"system_instruction": system_instruction}
        if generation_config:
            if "config" in request_kwargs:
                request_kwargs["config"]["generation_config"] = generation_config
            else:
                request_kwargs["config"] = {"generation_config": generation_config}
        if gemini_tools:
            if "config" in request_kwargs:
                request_kwargs["config"]["tools"] = gemini_tools
            else:
                request_kwargs["config"] = {"tools": gemini_tools}

        # 调用
        response = await client.aio.models.generate_content(**request_kwargs)

        # 提取内容
        content, reasoning_content, tool_calls = self._extract_response(response)

        # 解析 finish_reason
        finish_reason = FinishReason.STOP
        if response.candidates:
            candidate = response.candidates[0]
            finish_reason = self._map_finish_reason(
                getattr(candidate, "finish_reason", None)
            )
            if tool_calls:
                finish_reason = FinishReason.TOOL_CALLS

        # 解析 usage
        usage = Usage()
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata:
            usage = Usage(
                prompt_tokens=getattr(usage_metadata, "prompt_token_count", 0),
                completion_tokens=getattr(usage_metadata, "candidates_token_count", 0),
                total_tokens=getattr(usage_metadata, "total_token_count", 0),
            )

        return self.create_response(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """流式调用"""
        from google import genai

        # 创建客户端，支持自定义 base_url
        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            # google-genai 使用 http_options 设置自定义端点
            client_kwargs["http_options"] = {"base_url": self.base_url}
        client = genai.Client(**client_kwargs)

        system_instruction, contents = self._convert_messages(messages)
        gemini_tools = self.convert_tools(tools)

        # 构建生成配置
        generation_config: dict[str, Any] = {}
        if self.temperature is not None:
            generation_config["temperature"] = self.temperature
        if self.top_p is not None:
            generation_config["top_p"] = self.top_p
        if self.max_tokens is not None:
            generation_config["max_output_tokens"] = self.max_tokens
        # Gemini 2.0 Flash Thinking 需要设置 thinking_config
        if self.thinking_enabled:
            generation_config["thinking_config"] = {
                "thinking_budget": self.thinking_budget or 8192
            }

        # Response format/schema support
        # Gemini uses response_schema (not response_format like OpenAI)
        if "response_format" in kwargs and kwargs["response_format"] is not None:
            response_format = kwargs["response_format"]
            # Convert OpenAI format to Gemini format
            if isinstance(response_format, dict):
                if response_format.get("type") == "json_object":
                    # For simple JSON mode, we can set response_mime_type
                    generation_config["response_mime_type"] = "application/json"
                elif response_format.get("type") == "json_schema":
                    # For JSON schema, extract the schema
                    json_schema_config = response_format.get("json_schema", {})
                    schema = json_schema_config.get("schema")
                    if schema:
                        generation_config["response_schema"] = schema
                        generation_config["response_mime_type"] = "application/json"

        # 构建请求参数
        request_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "contents": contents,
        }
        if system_instruction:
            request_kwargs["config"] = {"system_instruction": system_instruction}
        if generation_config:
            if "config" in request_kwargs:
                request_kwargs["config"]["generation_config"] = generation_config
            else:
                request_kwargs["config"] = {"generation_config": generation_config}
        if gemini_tools:
            if "config" in request_kwargs:
                request_kwargs["config"]["tools"] = gemini_tools
            else:
                request_kwargs["config"] = {"tools": gemini_tools}

        response_id = str(uuid.uuid4())
        accumulated_tool_calls: list[ToolCall] = []

        # 流式调用 - 需要先 await 获取流对象
        stream = await client.aio.models.generate_content_stream(**request_kwargs)
        async for chunk in stream:
            if not chunk.candidates:
                continue

            candidate = chunk.candidates[0]
            content = getattr(candidate, "content", None)
            if not content:
                continue

            parts = getattr(content, "parts", None)
            if not parts:
                continue

            for part in parts:
                # 检查是否是 thinking part
                if getattr(part, "thought", False):
                    text = getattr(part, "text", "")
                    if text:
                        yield self.create_stream_chunk(
                            reasoning_content=text,
                            response_id=response_id,
                        )
                # 检查是否是 function_call
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if hasattr(fc, "args") and fc.args else {}
                    accumulated_tool_calls.append(
                        ToolCall(
                            id=str(uuid.uuid4()),
                            type="function",
                            function=FunctionCall(
                                name=fc.name if hasattr(fc, "name") else "",
                                arguments=json.dumps(args),
                            ),
                        )
                    )
                # 普通文本
                elif hasattr(part, "text") and part.text:
                    yield self.create_stream_chunk(
                        content=part.text,
                        response_id=response_id,
                    )

            # 检查是否完成
            finish_reason_raw = getattr(candidate, "finish_reason", None)
            if finish_reason_raw:
                finish_reason = self._map_finish_reason(finish_reason_raw)
                if accumulated_tool_calls:
                    finish_reason = FinishReason.TOOL_CALLS

                yield self.create_stream_chunk(
                    tool_calls=accumulated_tool_calls
                    if accumulated_tool_calls
                    else None,
                    finish_reason=finish_reason,
                    response_id=response_id,
                )
