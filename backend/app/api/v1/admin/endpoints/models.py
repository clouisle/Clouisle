"""
Admin-only model management endpoints (CRUD, test, set-default).
Public endpoints (providers, types, available, default) remain in the platform router.
"""

import time
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
from app.models.model import Model
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelUpdate,
    ModelResponse,
    ModelTestRequest,
    ModelTestResponse,
    ModelProvider,
    ModelType,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=Response[PageData[ModelResponse]])
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = Query(None),
    model_type: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.PermissionChecker("admin:model:read")),
) -> Any:
    skip = (page - 1) * page_size
    query = Model.all()

    if provider:
        query = query.filter(provider=provider)
    if model_type:
        query = query.filter(model_type=model_type)
    if is_enabled is not None:
        query = query.filter(is_enabled=is_enabled)
    if search:
        query = query.filter(Q(name__icontains=search) | Q(model_id__icontains=search))

    total = await query.count()
    models = (
        await query.offset(skip).limit(page_size).order_by("sort_order", "-created_at")
    )

    return success(
        data={
            "items": [ModelResponse.model_validate(m) for m in models],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[ModelResponse])
async def create_model(
    *,
    model_in: ModelCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:model:create")),
) -> Any:
    existing = await Model.filter(
        provider=model_in.provider.value,
        model_id=model_in.model_id,
        model_type=model_in.model_type.value,
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS,
            msg_key="model_already_exists",
        )

    if model_in.is_default:
        await Model.filter(
            model_type=model_in.model_type.value, is_default=True
        ).update(is_default=False)

    model_data = model_in.model_dump()
    model_data["provider"] = model_in.provider.value
    model_data["model_type"] = model_in.model_type.value

    model = await Model.create(**model_data)
    return success(data=ModelResponse.model_validate(model), msg_key="model_created")


@router.get("/{model_id}", response_model=Response[ModelResponse])
async def get_model(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:model:read")),
) -> Any:
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )
    return success(data=ModelResponse.model_validate(model))


@router.put("/{model_id}", response_model=Response[ModelResponse])
async def update_model(
    model_id: UUID,
    model_in: ModelUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:model:update")),
) -> Any:
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    update_data = model_in.model_dump(exclude_unset=True)

    if "api_key" in update_data:
        if update_data["api_key"] == "":
            update_data["api_key"] = None

    if update_data.get("is_default"):
        await (
            Model.filter(model_type=model.model_type, is_default=True)
            .exclude(id=model_id)
            .update(is_default=False)
        )

    await model.update_from_dict(update_data)
    await model.save()

    model = await Model.get(id=model_id)
    return success(data=ModelResponse.model_validate(model), msg_key="model_updated")


@router.delete("/{model_id}", response_model=Response[ModelResponse])
async def delete_model(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:model:delete")),
) -> Any:
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    response_data = ModelResponse.model_validate(model)
    await model.delete()
    return success(data=response_data, msg_key="model_deleted")


@router.post("/{model_id}/test", response_model=Response[ModelTestResponse])
async def test_model_connection(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:model:update")),
) -> Any:
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    if _requires_api_key(provider := ModelProvider(model.provider)) and not model.api_key:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_api_key_required",
        )

    start_time = time.time()
    try:
        model_type = ModelType(model.model_type)
    except ValueError as exc:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_type_not_supported",
        ) from exc
    config = model.config or {}

    try:
        if model_type == ModelType.CHAT:
            await _test_chat_model(
                provider, model.model_id, model.api_key, model.base_url, config
            )
        elif model_type == ModelType.EMBEDDING:
            await _test_embedding_model(
                provider, model.model_id, model.api_key, model.base_url, config
            )
        elif model_type == ModelType.RERANK:
            await _test_rerank_model(
                provider, model.model_id, model.api_key, model.base_url, config
            )
        elif model_type == ModelType.TEXT_TO_IMAGE:
            _test_image_model(
                provider, model.model_id, model.api_key, model.base_url, config
            )
        elif model_type == ModelType.TEXT_TO_VIDEO:
            _test_video_model(
                provider, model.model_id, model.api_key, model.base_url, config
            )
        elif model_type in [ModelType.TTS, ModelType.STT]:
            _validate_api_key(provider, model.api_key)
        else:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="model_type_not_supported",
            )

        latency_ms = int((time.time() - start_time) * 1000)
        return success(
            data=ModelTestResponse(
                success=True,
                message="Connection successful",
                latency_ms=latency_ms,
            ),
            msg_key="model_test_success",
        )

    except BusinessError:
        raise
    except Exception as e:
        logger.exception(f"Model test failed: {e}")
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg.lower():
            error_msg = "Invalid API key"
        elif "404" in error_msg or "not found" in error_msg.lower():
            error_msg = "Model not found or not accessible"
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            return success(
                data=ModelTestResponse(
                    success=True,
                    message="Rate limit exceeded, but API key is valid",
                    latency_ms=latency_ms,
                ),
                msg_key="model_test_success",
            )
        elif "timeout" in error_msg.lower():
            error_msg = "Connection timeout"
        elif "connection" in error_msg.lower():
            error_msg = "Connection failed, check base URL"

        return success(
            data=ModelTestResponse(
                success=False,
                message=error_msg,
                latency_ms=latency_ms,
            ),
            msg_key="model_test_failed",
        )


@router.post("/{model_id}/set-default", response_model=Response[ModelResponse])
async def set_default_model(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:model:update")),
) -> Any:
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    await (
        Model.filter(model_type=model.model_type, is_default=True)
        .exclude(id=model_id)
        .update(is_default=False)
    )

    model.is_default = True
    await model.save()

    return success(
        data=ModelResponse.model_validate(model), msg_key="model_set_default"
    )


@router.post("/test", response_model=Response[ModelTestResponse])
async def test_model_config(
    test_request: ModelTestRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:model:create")),
) -> Any:
    provider = test_request.provider
    model_id = test_request.model_id
    model_type = test_request.model_type
    api_key = test_request.api_key
    base_url = test_request.base_url
    config = test_request.config or {}

    start_time = time.time()

    try:
        if model_type == ModelType.CHAT:
            await _test_chat_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.EMBEDDING:
            await _test_embedding_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.RERANK:
            await _test_rerank_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.TEXT_TO_IMAGE:
            _test_image_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.TEXT_TO_VIDEO:
            _test_video_model(provider, model_id, api_key, base_url, config)
        elif model_type in [ModelType.TTS, ModelType.STT]:
            _validate_api_key(provider, api_key)
        else:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="model_type_not_supported",
            )

        latency_ms = int((time.time() - start_time) * 1000)
        return success(
            data=ModelTestResponse(
                success=True,
                message="Connection successful",
                latency_ms=latency_ms,
            ),
            msg_key="model_test_success",
        )

    except BusinessError:
        raise
    except Exception as e:
        logger.exception(f"Model test failed: {e}")
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg.lower():
            error_msg = "Invalid API key"
        elif "404" in error_msg or "not found" in error_msg.lower():
            error_msg = "Model not found or not accessible"
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            return success(
                data=ModelTestResponse(
                    success=True,
                    message="Rate limit exceeded, but API key is valid",
                    latency_ms=latency_ms,
                ),
                msg_key="model_test_success",
            )
        elif "timeout" in error_msg.lower():
            error_msg = "Connection timeout"
        elif "connection" in error_msg.lower():
            error_msg = "Connection failed, check base URL"

        return success(
            data=ModelTestResponse(
                success=False,
                message=error_msg,
                latency_ms=latency_ms,
            ),
            msg_key="model_test_failed",
        )


def _validate_api_key(provider: ModelProvider, api_key: str | None) -> None:
    if not _requires_api_key(provider):
        return
    if provider == ModelProvider.OPENAI:
        if not api_key or not api_key.startswith("sk-"):
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="invalid_api_key_format",
            )
    elif provider == ModelProvider.ANTHROPIC:
        if not api_key or not api_key.startswith("sk-ant-"):
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="invalid_api_key_format",
            )


def _requires_api_key(provider: ModelProvider) -> bool:
    return provider != ModelProvider.OLLAMA


async def _test_chat_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    config: dict,
) -> None:
    from app.llm.types import Message, MessageRole
    from app.llm.adapters.chat import (
        OpenAIAdapter,
        DeepSeekAdapter,
        AnthropicAdapter,
        GeminiAdapter,
        XAIAdapter,
        OpenAICompatibleAdapter,
    )

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = {}
            self.config = config

    temp_model = TempModel()
    provider_value = provider.value if hasattr(provider, "value") else str(provider)

    if provider_value == ModelProvider.OPENAI.value:
        adapter = OpenAIAdapter(temp_model)
    elif provider_value == ModelProvider.ANTHROPIC.value:
        adapter = AnthropicAdapter(temp_model)
    elif provider_value == ModelProvider.GOOGLE.value:
        adapter = GeminiAdapter(temp_model)
    elif provider_value == ModelProvider.XAI.value:
        adapter = XAIAdapter(temp_model)
    elif provider_value == ModelProvider.AZURE_OPENAI.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="azure")
    elif provider_value == ModelProvider.DEEPSEEK.value:
        adapter = DeepSeekAdapter(temp_model)
    elif provider_value == ModelProvider.MOONSHOT.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="moonshot")
    elif provider_value == ModelProvider.ZHIPU.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="zhipu")
    elif provider_value == ModelProvider.QWEN.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="qwen")
    elif provider_value == ModelProvider.BAICHUAN.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="baichuan")
    elif provider_value == ModelProvider.MINIMAX.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="minimax")
    elif provider_value == ModelProvider.OLLAMA.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="ollama")
    elif provider_value == ModelProvider.CUSTOM.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="custom")
    else:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint=provider_value)

    messages = [Message(role=MessageRole.USER, content="Hi")]
    response = await adapter.chat(messages)

    if not response.content:
        raise ValueError("Empty response from model")


async def _test_embedding_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    config: dict,
) -> None:
    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.config = config

    from app.llm.adapters.embedding.factory import create_embedding_model

    embedding_model = create_embedding_model(TempModel())

    try:
        result = await embedding_model.aembed_query("test")
    except AttributeError as e:
        if "'str' object has no attribute 'data'" in str(e):
            raise ValueError(
                "API response format is not compatible with OpenAI. "
                "The endpoint may not support the embeddings API or returns a non-standard format."
            )
        raise

    if not result or len(result) == 0:
        raise ValueError("Empty embedding result")


async def _test_rerank_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    config: dict,
) -> None:
    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = {}
            self.max_output_tokens = None
            self.config = config

    from app.llm.adapters.rerank import create_rerank_adapter

    adapter = create_rerank_adapter(TempModel())
    result = await adapter.rerank(
        query="What is artificial intelligence?",
        documents=[
            "Artificial intelligence is the simulation of human intelligence by machines.",
            "Bananas are a tropical fruit rich in potassium.",
        ],
        top_n=2,
    )

    if not result.results:
        raise ValueError("Empty rerank result")


def _test_image_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.config = config

    from app.llm.adapters.image import create_image_adapter

    create_image_adapter(TempModel())


def _test_video_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.config = config

    from app.llm.adapters.video import create_video_adapter

    create_video_adapter(TempModel())
