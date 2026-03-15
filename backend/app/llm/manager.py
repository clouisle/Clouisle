"""
统一模型管理器

提供统一的 LLM 调用接口，从数据库加载模型配置，
根据模型类型分发到对应的适配器。

支持团队级调用，自动追踪 token 用量和配额检查。
"""

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.models.model import Model, ModelType, TeamModel, ModelProvider
from app.services.usage_tracker import usage_tracker, QuotaExceededError

from .adapters import (
    create_chat_model,
    create_embedding_model,
    create_image_adapter,
    create_rerank_adapter,
    create_tts_adapter,
    create_stt_adapter,
)
from .adapters.chat import (
    BaseChatAdapter,
    OpenAIAdapter,
    DeepSeekAdapter,
    AnthropicAdapter,
    GeminiAdapter,
    XAIAdapter,
    OpenAICompatibleAdapter,
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
    ChatResponse,
    ChatStreamChunk,
    ToolDefinition,
    ImageGenerationRequest,
    ImageGenerationResponse,
    TTSRequest,
    TTSResponse,
    STTRequest,
    STTResponse,
    RerankResponse,
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
                    provider=provider,
                    model_id=parsed_model_id,
                    model_type=model_type,
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

    def _get_chat_adapter(self, model_config: Model) -> BaseChatAdapter:
        """
        根据服务商获取对应的 Chat 适配器

        Args:
            model_config: 模型配置

        Returns:
            BaseChatAdapter: Chat 适配器实例
        """
        provider = model_config.provider
        provider_value = provider.value if hasattr(provider, "value") else str(provider)

        # 原生适配器
        if provider_value == ModelProvider.OPENAI.value:
            return OpenAIAdapter(model_config)
        elif provider_value == ModelProvider.ANTHROPIC.value:
            return AnthropicAdapter(model_config)
        elif provider_value == ModelProvider.GOOGLE.value:
            return GeminiAdapter(model_config)
        elif provider_value == ModelProvider.DEEPSEEK.value:
            return DeepSeekAdapter(model_config)
        elif provider_value == ModelProvider.XAI.value:
            return XAIAdapter(model_config)

        # OpenAI 兼容服务商
        elif provider_value == ModelProvider.AZURE_OPENAI.value:
            # Azure OpenAI 使用 OpenAI 适配器，但需要特殊处理
            return OpenAICompatibleAdapter(model_config, provider_hint="azure")
        elif provider_value == ModelProvider.MOONSHOT.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="moonshot")
        elif provider_value == ModelProvider.ZHIPU.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="zhipu")
        elif provider_value == ModelProvider.QWEN.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="qwen")
        elif provider_value == ModelProvider.BAICHUAN.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="baichuan")
        elif provider_value == ModelProvider.MINIMAX.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="minimax")
        elif provider_value == ModelProvider.VOLCENGINE.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="volcengine")
        elif provider_value == ModelProvider.OLLAMA.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="ollama")
        elif provider_value == ModelProvider.CUSTOM.value:
            return OpenAICompatibleAdapter(model_config, provider_hint="custom")

        # 默认使用 OpenAI 兼容适配器
        return OpenAICompatibleAdapter(model_config)

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
        self,
        team_id: str,
        model_id: str | None,
        model_type: ModelType = ModelType.CHAT,
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
        model_config = await self._get_model_config(model_id or None, model_type)

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
        adapter = self._get_chat_adapter(model_config)

        try:
            return await adapter.chat(converted_messages, tools=tools, **kwargs)
        except Exception as e:
            logger.exception(f"Chat error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

    async def chat_stream(
        self,
        messages: list[Message | dict],
        model_id: str | None = None,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        Chat 流式调用

        Args:
            messages: 消息列表
            model_id: 模型 ID
            tools: 工具定义列表
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        converted_messages: list[Message] = [
            Message(**m) if isinstance(m, dict) else m for m in messages
        ]

        model_config = await self._get_model_config(model_id, ModelType.CHAT)
        adapter = self._get_chat_adapter(model_config)

        try:
            async for chunk in adapter.chat_stream(
                converted_messages, tools=tools, **kwargs
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

    async def get_embedding(
        self, text: str, user_id: UUID | None = None, model_id: str | None = None
    ) -> dict:
        """
        Generate embedding vector for text.

        Args:
            text: Text to embed
            user_id: User ID (for team model lookup)
            model_id: Optional model ID override

        Returns:
            Dict with 'embedding' (list of floats) and 'model_id' (UUID)
        """
        # Get embedding model
        embedding_model = await self.get_embedding_model(model_id)

        # Generate embedding
        embedding_vector = await embedding_model.aembed_query(text)

        # Get model config to return model_id
        model_config = await self._get_model_config(model_id, ModelType.EMBEDDING)

        return {
            "embedding": embedding_vector,
            "model_id": model_config.model_id
            if hasattr(model_config, "model_id")
            else None,
        }

    # ==================== Rerank 方法 ====================

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model_id: str | None = None,
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        """
        文档重排序

        Args:
            query: 查询文本
            documents: 候选文档列表
            model_id: 模型 ID
            top_n: 返回结果数量

        Returns:
            RerankResponse: 重排序结果
        """
        model_config = await self._get_model_config(model_id, ModelType.RERANK)
        adapter = create_rerank_adapter(model_config)

        try:
            return await adapter.rerank(query, documents, top_n=top_n, **kwargs)
        except Exception as e:
            logger.exception(f"Rerank error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)

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
        model_config, team_model = await self._get_team_model(
            team_id, model_id, ModelType.CHAT
        )

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

        adapter = self._get_chat_adapter(model_config)

        try:
            result = await adapter.chat(converted_messages, tools=tools, **kwargs)

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
        tools: list[ToolDefinition] | None = None,
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
            tools: 工具定义列表
            record_usage: 是否自动记录用量（默认 True）
            **kwargs: 额外参数

        Yields:
            ChatStreamChunk: 流式响应块
        """
        # 获取团队授权的模型
        model_config, team_model = await self._get_team_model(
            team_id, model_id, ModelType.CHAT
        )

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

        adapter = self._get_chat_adapter(model_config)

        try:
            async for chunk in adapter.chat_stream(
                converted_messages, tools=tools, **kwargs
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
        model_config, _ = await self._get_team_model(team_id, model_id, ModelType.CHAT)

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
        model_config, team_model = await self._get_team_model(
            team_id, model_id, ModelType.EMBEDDING
        )

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

    async def team_rerank(
        self,
        team_id: str,
        query: str,
        documents: list[str],
        model_id: str | None = None,
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        """
        团队级文档重排序（带配额检查和用量追踪）
        """
        model_config, team_model = await self._get_team_model(
            team_id, model_id, ModelType.RERANK
        )

        try:
            await usage_tracker.check_quota_with_model(team_model)
        except QuotaExceededError as e:
            raise LLMQuotaExceededError(
                message=str(e),
                quota_type=e.quota_type,
                team_id=team_id,
                model=str(model_config.id),
            )

        adapter = create_rerank_adapter(model_config)

        try:
            result = await adapter.rerank(query, documents, top_n=top_n, **kwargs)

            total_tokens = result.usage.total_tokens if result.usage else 0
            if total_tokens <= 0:
                from app.llm.token_counter import count_tokens

                total_tokens = count_tokens(query, model_config.model_id, model_config.provider)
                total_tokens += sum(
                    count_tokens(doc, model_config.model_id, model_config.provider)
                    for doc in documents
                )
                total_tokens = max(total_tokens, 1)

            await self._check_and_record_usage(
                team_id=team_id,
                model_id=str(model_config.id),
                tokens_used=total_tokens,
            )

            return result
        except Exception as e:
            logger.exception(f"Team rerank error: {e}")
            raise self._handle_error(e, model_config.provider, model_config.model_id)


# 全局单例
model_manager = ModelManager()
