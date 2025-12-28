"""
统一模型管理器

提供统一的 LLM 调用接口，从数据库加载模型配置，
根据模型类型分发到对应的适配器。

支持团队级调用，自动追踪 token 用量和配额检查。
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.models.model import Model, ModelType, TeamModel
from app.services.usage_tracker import usage_tracker, QuotaExceededError

from .adapters import (
    create_chat_model,
    create_embedding_model,
    create_image_adapter,
    create_tts_adapter,
    create_stt_adapter,
)
from .errors import (
    LLMError,
    ModelNotFoundError,
    ModelDisabledError,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ContextLengthError,
    ContentFilterError,
    QuotaExceededError as LLMQuotaExceededError,
)
from .types import (
    Message,
    MessageRole,
    ChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    Usage,
    ToolCall,
    FunctionCall,
    ToolDefinition,
    ImageGenerationRequest,
    ImageGenerationResponse,
    TTSRequest,
    TTSResponse,
    STTRequest,
    STTResponse,
)

logger = logging.getLogger(__name__)


class ModelManager:
    """
    统一模型管理器

    使用示例:
        from app.llm import model_manager

        # Chat
        response = await model_manager.chat(messages=[...])

        # Stream
        async for chunk in model_manager.chat_stream(messages=[...]):
            print(chunk.delta.content)

        # Embedding
        vectors = await model_manager.embed(["text1", "text2"])

        # 获取 LangChain 原生模型
        chat_model = await model_manager.get_chat_model()
    """

    # ==================== 内部辅助方法 ====================

    def _parse_model_identifier(
        self, identifier: str
    ) -> tuple[str | None, str | None, str | None]:
        """
        解析模型标识符

        支持的格式:
        - UUID: 数据库主键 (e.g., "550e8400-e29b-41d4-a716-446655440000")
        - 句柄: provider/model_id (e.g., "openai/gpt-4o")

        Args:
            identifier: 模型标识符

        Returns:
            (uuid, provider, model_id) 元组，未匹配的字段为 None
        """
        # 尝试解析为 UUID
        try:
            uuid.UUID(identifier)
            return (identifier, None, None)
        except ValueError:
            pass

        # 尝试解析为 provider/model_id 句柄
        if "/" in identifier:
            parts = identifier.split("/", 1)
            if len(parts) == 2:
                provider, model_id = parts
                return (None, provider, model_id)

        # 不支持单独的 model_id，因为它不是唯一的
        return (None, None, None)

    async def _get_model_config(
        self, model_id: str | None = None, model_type: ModelType = ModelType.CHAT
    ) -> Model:
        """
        获取模型配置

        Args:
            model_id: 模型标识符，支持以下格式：
                - UUID: 数据库主键
                - 句柄: "provider/model_id" 格式 (e.g., "openai/gpt-4o")
                - None: 使用该类型的默认模型
            model_type: 模型类型，仅在获取默认模型时使用

        Returns:
            Model: 模型配置对象

        Raises:
            ModelNotFoundError: 找不到模型或标识符格式无效
            ModelDisabledError: 模型已禁用
        """
        model: Model | None = None

        if model_id:
            parsed_uuid, provider, parsed_model_id = self._parse_model_identifier(
                model_id
            )

            if parsed_uuid:
                # 按 UUID 查找
                model = await Model.filter(id=parsed_uuid).first()
            elif provider and parsed_model_id:
                # 按 provider/model_id 句柄查找
                model = await Model.filter(
                    provider=provider, model_id=parsed_model_id
                ).first()
            else:
                # 无效的标识符格式
                raise ModelNotFoundError(
                    message=f"Invalid model identifier format: '{model_id}'. "
                    f"Use UUID or 'provider/model_id' format (e.g., 'openai/gpt-4o')",
                    model=model_id,
                )
        else:
            # 获取该类型的默认模型
            model = await Model.filter(model_type=model_type, is_default=True).first()
            if not model:
                # 如果没有默认模型，获取第一个启用的模型
                model = await Model.filter(
                    model_type=model_type, is_enabled=True
                ).first()

        if not model:
            raise ModelNotFoundError(
                message=f"No model found for identifier: {model_id or model_type}",
                model=model_id,
            )

        if not model.is_enabled:
            raise ModelDisabledError(
                message=f"Model {model.name} is disabled",
                model=str(model.id),
            )

        return model

    def _convert_messages(
        self, messages: list[Message]
    ) -> list[SystemMessage | HumanMessage | AIMessage | ToolMessage]:
        """将内部消息格式转换为 LangChain 消息"""
        lc_messages: list[SystemMessage | HumanMessage | AIMessage | ToolMessage] = []
        for msg in messages:
            content = msg.content
            if isinstance(content, list):
                # TODO: 处理多模态内容
                content = " ".join(part.text for part in content if part.text)

            if msg.role == MessageRole.SYSTEM:
                lc_messages.append(SystemMessage(content=content or ""))
            elif msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=content or ""))
            elif msg.role == MessageRole.ASSISTANT:
                # Convert tool_calls to LangChain format if present
                lc_tool_calls = None
                if msg.tool_calls:
                    lc_tool_calls = [
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "args": tc.function.arguments
                            if isinstance(tc.function.arguments, dict)
                            else self._safe_json_loads(tc.function.arguments),
                        }
                        for tc in msg.tool_calls
                    ]
                lc_messages.append(
                    AIMessage(content=content or "", tool_calls=lc_tool_calls or [])
                )
            elif msg.role == MessageRole.TOOL:
                lc_messages.append(
                    ToolMessage(
                        content=content or "",
                        tool_call_id=msg.tool_call_id or "",
                    )
                )

        return lc_messages

    def _safe_json_loads(self, s: str) -> dict:
        """Safely parse JSON string to dict"""
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """将内部工具定义转换为 LangChain 格式"""
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

    def _parse_response(self, response: AIMessage, model_name: str) -> ChatResponse:
        """解析 LangChain 响应为内部格式"""
        # 解析工具调用
        tool_calls = None
        if response.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id") or str(uuid.uuid4()),
                    type="function",
                    function=FunctionCall(
                        name=tc.get("name", ""),
                        arguments=json.dumps(
                            tc.get("args", {})
                        ),  # Convert dict to JSON string
                    ),
                )
                for tc in response.tool_calls
            ]

        # 确定完成原因
        finish_reason = FinishReason.STOP
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS

        # 解析 usage
        usage = Usage()
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = Usage(
                prompt_tokens=response.usage_metadata.get("input_tokens", 0),
                completion_tokens=response.usage_metadata.get("output_tokens", 0),
                total_tokens=response.usage_metadata.get("total_tokens", 0),
            )

        return ChatResponse(
            id=response.id or str(uuid.uuid4()),
            model=model_name,
            content=response.content if isinstance(response.content, str) else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    def _handle_error(self, e: Exception, provider: str, model: str) -> LLMError:
        """统一处理异常"""
        error_msg = str(e).lower()

        # Check for OpenAI NotFoundError (404)
        if (
            "notfounderror" in type(e).__name__.lower()
            or "404" in error_msg
            or "does not exist" in error_msg
            or "not found" in error_msg
        ):
            return ModelNotFoundError(
                message=str(e),
                model=model,
            )
        elif (
            "authentication" in error_msg
            or "api key" in error_msg
            or "invalid_api_key" in error_msg
        ):
            return AuthenticationError(
                message=str(e),
                provider=provider,
                model=model,
            )
        elif "rate limit" in error_msg or "rate_limit" in error_msg:
            return RateLimitError(
                message=str(e),
                provider=provider,
                model=model,
            )
        elif (
            "context length" in error_msg or "token" in error_msg and "max" in error_msg
        ):
            return ContextLengthError(
                message=str(e),
                provider=provider,
                model=model,
            )
        elif "content filter" in error_msg or "safety" in error_msg:
            return ContentFilterError(
                message=str(e),
                provider=provider,
                model=model,
            )
        else:
            return ProviderError(
                message=str(e),
                provider=provider,
                model=model,
            )

    async def _get_team_model(
        self, team_id: str, model_id: str
    ) -> tuple[Model, TeamModel]:
        """
        获取团队授权的模型

        Args:
            team_id: 团队 ID
            model_id: 模型标识符

        Returns:
            (Model, TeamModel) 元组

        Raises:
            ModelNotFoundError: 找不到模型或团队未授权该模型
            ModelDisabledError: 模型或团队授权已禁用
        """
        # 先获取模型配置
        model_config = await self._get_model_config(model_id)

        # 查找团队授权
        team_model = await TeamModel.filter(
            team_id=team_id, model_id=model_config.id
        ).first()

        if not team_model:
            raise ModelNotFoundError(
                message=f"Team {team_id} is not authorized to use model {model_config.name}",
                model=str(model_config.id),
            )

        if not team_model.is_enabled:
            raise ModelDisabledError(
                message=f"Model {model_config.name} is disabled for team {team_id}",
                model=str(model_config.id),
            )

        return model_config, team_model

    async def _check_and_record_usage(
        self,
        team_id: str,
        model_id: str,
        tokens_used: int,
        request_count: int = 1,
    ) -> None:
        """
        检查配额并记录用量

        Args:
            team_id: 团队 ID
            model_id: 模型 UUID
            tokens_used: 使用的 token 数
            request_count: 请求次数
        """
        try:
            await usage_tracker.check_and_record_usage(
                team_id=team_id,
                model_id=model_id,
                tokens_used=tokens_used,
                request_count=request_count,
            )
        except QuotaExceededError as e:
            raise LLMQuotaExceededError(
                message=str(e),
                quota_type=e.quota_type,
                team_id=team_id,
                model=model_id,
            )

    async def _stream_with_openai_sdk(
        self,
        model_config: Model,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        使用 OpenAI SDK 直接进行流式调用，以支持 reasoning_content 等扩展字段

        Args:
            model_config: 模型配置
            messages: 消息列表
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        from openai import AsyncOpenAI

        # 构建 OpenAI 客户端
        client = AsyncOpenAI(
            api_key=model_config.api_key,
            base_url=model_config.base_url,
            timeout=model_config.config.get("timeout", 60)
            if model_config.config
            else 60,
        )

        # 转换消息格式
        openai_messages = []
        for msg in messages:
            content = msg.content
            if isinstance(content, list):
                # 处理多模态内容 - convert to OpenAI vision format
                processed_content = []
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
                            # Convert our ImageContent to OpenAI's image_url format
                            img = part.image
                            if img.base64:
                                # Use data URL format for base64
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
                            elif img.url:
                                processed_content.append(
                                    {"type": "image_url", "image_url": {"url": img.url}}
                                )
                        elif part_type == "image_url" and hasattr(part, "image_url"):
                            # Legacy format - pass through
                            processed_content.append(
                                {"type": "image_url", "image_url": part.image_url}
                            )
                    elif isinstance(part, dict):
                        processed_content.append(part)
                content = processed_content if processed_content else ""

            msg_dict = {
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": content if content else "",
            }

            # Handle tool_calls for assistant messages
            if hasattr(msg, "tool_calls") and msg.tool_calls:
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

            # Handle tool_call_id for tool messages
            if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id

            openai_messages.append(msg_dict)

        # 从 default_params 获取参数（模型配置优先）
        params = model_config.default_params or {}
        config = model_config.config or {}

        # 移除 kwargs 中可能传入的参数（忽略它们，只用模型配置）
        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)
        tools = kwargs.pop("tools", None)

        # temperature: 从模型 default_params 获取
        temperature = params.get("temperature")

        # max_tokens: 从模型 config 获取
        max_tokens = config.get("max_tokens")

        # 构建请求参数
        request_params: dict[str, Any] = {
            "model": model_config.model_id,
            "messages": openai_messages,
            "stream": True,
        }

        if temperature is not None:
            request_params["temperature"] = temperature
        if max_tokens is not None:
            request_params["max_completion_tokens"] = max_tokens
        if tools is not None:
            # Convert tools to OpenAI format
            openai_tools = []
            for tool in tools:
                openai_tools.append(
                    {
                        "type": tool.type,
                        "function": {
                            "name": tool.function.name,
                            "description": tool.function.description,
                            "parameters": tool.function.parameters,
                        },
                    }
                )
            request_params["tools"] = openai_tools

        response_id = str(uuid.uuid4())

        try:
            stream = await client.chat.completions.create(**request_params)

            # Track tool calls being built up during streaming
            streaming_tool_calls: dict[
                int, dict
            ] = {}  # index -> {id, type, function: {name, arguments}}

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # 获取 content
                content = delta.content if delta.content else None

                # 获取 reasoning_content (DeepSeek R1 等模型的扩展字段)
                # 通过 model_extra 获取非标准字段
                reasoning_content = None
                if hasattr(delta, "model_extra") and delta.model_extra:
                    reasoning_content = delta.model_extra.get("reasoning_content")

                # 处理流式工具调用
                tool_calls_delta = None
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in streaming_tool_calls:
                            streaming_tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "type": tc_delta.type or "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc_delta.id:
                            streaming_tool_calls[idx]["id"] = tc_delta.id
                        if tc_delta.type:
                            streaming_tool_calls[idx]["type"] = tc_delta.type
                        if tc_delta.function:
                            if tc_delta.function.name:
                                streaming_tool_calls[idx]["function"]["name"] += (
                                    tc_delta.function.name
                                )
                            if tc_delta.function.arguments:
                                streaming_tool_calls[idx]["function"]["arguments"] += (
                                    tc_delta.function.arguments
                                )

                # 当 finish_reason 为 tool_calls 时，发送完整的工具调用
                if finish_reason == "tool_calls" and streaming_tool_calls:
                    tool_calls_delta = [
                        ToolCall(
                            id=tc["id"],
                            type=tc["type"],
                            function=FunctionCall(
                                name=tc["function"]["name"],
                                arguments=tc["function"]["arguments"],
                            ),
                        )
                        for tc in streaming_tool_calls.values()
                    ]

                # 如果有内容、reasoning 或工具调用，才 yield
                if content or reasoning_content or finish_reason or tool_calls_delta:
                    yield ChatStreamChunk(
                        id=response_id,
                        model=model_config.model_id,
                        delta=ChatStreamDelta(
                            content=content,
                            reasoning_content=reasoning_content,
                            tool_calls=tool_calls_delta,
                        ),
                        finish_reason=FinishReason(finish_reason)
                        if finish_reason
                        else None,
                    )

        finally:
            await client.close()

    # ==================== Chat 方法 ====================

    async def chat(
        self,
        messages: list[Message | dict],
        model_id: str | None = None,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """
        Chat 调用

        Args:
            messages: 消息列表，可以是 Message 对象或 dict
            model_id: 模型 ID（数据库主键或 model_id 字段），不指定则使用默认
            tools: 工具定义列表
            **kwargs: 额外参数传递给模型

        Returns:
            ChatResponse: 响应对象
        """
        # 转换 dict 为 Message
        converted_messages: list[Message] = [
            Message(**m) if isinstance(m, dict) else m for m in messages
        ]

        model_config = await self._get_model_config(model_id, ModelType.CHAT)
        chat_model = create_chat_model(model_config)

        lc_messages = self._convert_messages(converted_messages)
        lc_tools = self._convert_tools(tools)

        try:
            model_to_invoke: BaseChatModel = chat_model
            if lc_tools:
                model_to_invoke = chat_model.bind_tools(lc_tools)  # type: ignore[assignment]

            response = await model_to_invoke.ainvoke(lc_messages, **kwargs)
            return self._parse_response(response, model_config.model_id)
        except Exception as e:
            logger.exception(f"Chat error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def chat_stream(
        self,
        messages: list[Message | dict],
        model_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        Chat 流式调用

        Args:
            messages: 消息列表
            model_id: 模型 ID
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        converted_messages: list[Message] = [
            Message(**m) if isinstance(m, dict) else m for m in messages
        ]

        model_config = await self._get_model_config(model_id, ModelType.CHAT)

        try:
            # 直接使用 OpenAI SDK 进行流式调用，以支持 reasoning_content
            async for chunk in self._stream_with_openai_sdk(
                model_config, converted_messages, **kwargs
            ):
                yield chunk
        except Exception as e:
            logger.exception(f"Chat stream error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def get_chat_model(self, model_id: str | None = None) -> BaseChatModel:
        """
        获取 LangChain Chat 模型实例，用于高级用法

        Args:
            model_id: 模型 ID

        Returns:
            BaseChatModel: LangChain 模型实例
        """
        model_config = await self._get_model_config(model_id, ModelType.CHAT)
        return create_chat_model(model_config)

    # ==================== Embedding 方法 ====================

    async def embed(
        self,
        texts: list[str],
        model_id: str | None = None,
    ) -> list[list[float]]:
        """
        文本嵌入

        Args:
            texts: 文本列表
            model_id: 模型 ID

        Returns:
            list[list[float]]: 嵌入向量列表
        """
        model_config = await self._get_model_config(model_id, ModelType.EMBEDDING)
        embedding_model = create_embedding_model(model_config)

        try:
            return await embedding_model.aembed_documents(texts)
        except Exception as e:
            logger.exception(f"Embedding error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def embed_query(
        self,
        text: str,
        model_id: str | None = None,
    ) -> list[float]:
        """
        单个查询文本嵌入

        Args:
            text: 文本
            model_id: 模型 ID

        Returns:
            list[float]: 嵌入向量
        """
        model_config = await self._get_model_config(model_id, ModelType.EMBEDDING)
        embedding_model = create_embedding_model(model_config)

        try:
            return await embedding_model.aembed_query(text)
        except Exception as e:
            logger.exception(f"Embed query error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def get_embedding_model(self, model_id: str | None = None) -> Embeddings:
        """
        获取 LangChain Embedding 模型实例

        Args:
            model_id: 模型 ID

        Returns:
            Embeddings: LangChain Embedding 模型实例
        """
        model_config = await self._get_model_config(model_id, ModelType.EMBEDDING)
        return create_embedding_model(model_config)

    # ==================== Image 方法 ====================

    async def generate_image(
        self,
        request: ImageGenerationRequest | dict,
        model_id: str | None = None,
    ) -> ImageGenerationResponse:
        """
        图像生成

        Args:
            request: 图像生成请求
            model_id: 模型 ID

        Returns:
            ImageGenerationResponse: 生成结果
        """
        if isinstance(request, dict):
            request = ImageGenerationRequest(**request)

        model_config = await self._get_model_config(model_id, ModelType.TEXT_TO_IMAGE)
        adapter = create_image_adapter(model_config)

        try:
            return await adapter.generate(request)
        except LLMError:
            raise
        except Exception as e:
            logger.exception(f"Image generation error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    # ==================== Audio 方法 ====================

    async def text_to_speech(
        self,
        request: TTSRequest | dict,
        model_id: str | None = None,
    ) -> TTSResponse:
        """
        语音合成

        Args:
            request: TTS 请求
            model_id: 模型 ID

        Returns:
            TTSResponse: 合成结果
        """
        if isinstance(request, dict):
            request = TTSRequest(**request)

        model_config = await self._get_model_config(model_id, ModelType.TTS)
        adapter = create_tts_adapter(model_config)

        try:
            return await adapter.synthesize(request)
        except LLMError:
            raise
        except Exception as e:
            logger.exception(f"TTS error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def speech_to_text(
        self,
        request: STTRequest | dict,
        model_id: str | None = None,
    ) -> STTResponse:
        """
        语音识别

        Args:
            request: STT 请求
            model_id: 模型 ID

        Returns:
            STTResponse: 识别结果
        """
        if isinstance(request, dict):
            request = STTRequest(**request)

        model_config = await self._get_model_config(model_id, ModelType.STT)
        adapter = create_stt_adapter(model_config)

        try:
            return await adapter.transcribe(request)
        except LLMError:
            raise
        except Exception as e:
            logger.exception(f"STT error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    # ==================== 团队级 Chat 方法 (带用量追踪) ====================

    async def team_chat(
        self,
        team_id: str,
        messages: list[Message | dict],
        model_id: str | None = None,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """
        团队级 Chat 调用（带配额检查和用量追踪）

        Args:
            team_id: 团队 ID
            messages: 消息列表
            model_id: 模型 ID
            tools: 工具定义列表
            **kwargs: 额外参数

        Returns:
            ChatResponse: 响应对象

        Raises:
            QuotaExceededError: 配额超限
            ModelNotFoundError: 团队未授权该模型
        """
        # 获取团队授权的模型
        model_config, team_model = await self._get_team_model(team_id, model_id or "")

        # 检查配额（使用已获取的 team_model，避免重复查询）
        try:
            await usage_tracker.check_quota_with_model(team_model)
        except QuotaExceededError as e:
            raise LLMQuotaExceededError(
                message=str(e),
                quota_type=e.quota_type,
                team_id=team_id,
                model=str(model_config.id),
            )

        # 调用模型
        converted_messages: list[Message] = [
            Message(**m) if isinstance(m, dict) else m for m in messages
        ]

        chat_model = create_chat_model(model_config)
        lc_messages = self._convert_messages(converted_messages)
        lc_tools = self._convert_tools(tools)

        try:
            model_to_invoke: BaseChatModel = chat_model
            if lc_tools:
                model_to_invoke = chat_model.bind_tools(lc_tools)  # type: ignore[assignment]

            response = await model_to_invoke.ainvoke(lc_messages, **kwargs)
            result = self._parse_response(response, model_config.model_id)

            # 记录用量
            await self._check_and_record_usage(
                team_id=team_id,
                model_id=str(model_config.id),
                tokens_used=result.usage.total_tokens if result.usage else 0,
            )

            return result
        except Exception as e:
            logger.exception(f"Team chat error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def team_chat_stream(
        self,
        team_id: str,
        messages: list[Message | dict],
        model_id: str | None = None,
        record_usage: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        团队级 Chat 流式调用（带配额检查和用量追踪）

        注意：流式调用时，用量记录会在流正常结束后自动进行。
        如果调用方提前 break，用量不会被记录，除非调用方手动调用 record_stream_usage()。
        建议使用 `async with aclosing(stream)` 来确保资源正确清理。

        Args:
            team_id: 团队 ID
            messages: 消息列表
            model_id: 模型 ID
            record_usage: 是否自动记录用量（默认 True）
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        # 获取团队授权的模型
        model_config, team_model = await self._get_team_model(team_id, model_id or "")

        # 检查配额（使用已获取的 team_model，避免重复查询）
        try:
            await usage_tracker.check_quota_with_model(team_model)
        except QuotaExceededError as e:
            raise LLMQuotaExceededError(
                message=str(e),
                quota_type=e.quota_type,
                team_id=team_id,
                model=str(model_config.id),
            )

        converted_messages: list[Message] = [
            Message(**m) if isinstance(m, dict) else m for m in messages
        ]

        try:
            # 直接使用 OpenAI SDK 进行流式调用，以支持 reasoning_content
            async for chunk in self._stream_with_openai_sdk(
                model_config, converted_messages, **kwargs
            ):
                yield chunk

            # 注意：用量记录需要由调用方在流结束后主动调用 record_stream_usage()
            # 因为如果调用方使用 break 提前退出，这里的代码不会执行
        except Exception as e:
            logger.exception(f"Team chat stream error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def record_stream_usage(
        self,
        team_id: str,
        model_id: str | None,
        input_text_length: int,
        output_text_length: int,
    ) -> None:
        """
        记录流式调用的用量（供调用方在流结束后调用）

        Args:
            team_id: 团队 ID
            model_id: 模型 ID
            input_text_length: 输入文本字符数
            output_text_length: 输出文本字符数（包括 content 和 reasoning）
        """
        from app.llm.token_counter import count_tokens

        # 获取模型配置以获取正确的 model UUID
        model_config, _ = await self._get_team_model(team_id, model_id or "")

        # 使用 tiktoken 进行准确的 token 计数
        # 构造临时文本用于计数（实际使用时应该传入完整文本）
        # 这里使用字符数作为文本近似
        dummy_input = "x" * input_text_length
        dummy_output = "x" * output_text_length
        input_tokens = count_tokens(
            dummy_input, model_config.model_id, model_config.provider
        )
        output_tokens = count_tokens(
            dummy_output, model_config.model_id, model_config.provider
        )
        total_tokens = input_tokens + output_tokens

        await self._check_and_record_usage(
            team_id=team_id,
            model_id=str(model_config.id),
            tokens_used=total_tokens,
        )
        logger.debug(
            f"Recorded stream usage: {total_tokens} tokens (input={input_tokens}, output={output_tokens})"
        )

    async def team_embed(
        self,
        team_id: str,
        texts: list[str],
        model_id: str | None = None,
    ) -> list[list[float]]:
        """
        团队级文本嵌入（带配额检查和用量追踪）

        Args:
            team_id: 团队 ID
            texts: 文本列表
            model_id: 模型 ID

        Returns:
            list[list[float]]: 嵌入向量列表
        """
        # 获取团队授权的模型
        model_config, team_model = await self._get_team_model(team_id, model_id or "")

        # 检查配额（使用已获取的 team_model，避免重复查询）
        try:
            await usage_tracker.check_quota_with_model(team_model)
        except QuotaExceededError as e:
            raise LLMQuotaExceededError(
                message=str(e),
                quota_type=e.quota_type,
                team_id=team_id,
                model=str(model_config.id),
            )

        embedding_model = create_embedding_model(model_config)

        try:
            result = await embedding_model.aembed_documents(texts)

            # 使用 tiktoken 进行准确的 token 计数
            from app.llm.token_counter import count_tokens

            total_tokens = sum(
                count_tokens(t, model_config.model_id, model_config.provider)
                for t in texts
            )
            total_tokens = max(total_tokens, 1)

            # 记录用量
            await self._check_and_record_usage(
                team_id=team_id,
                model_id=str(model_config.id),
                tokens_used=total_tokens,
            )

            return result
        except Exception as e:
            logger.exception(f"Team embedding error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)


# 全局单例
model_manager = ModelManager()
