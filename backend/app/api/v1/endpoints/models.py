"""
API endpoints for AI Model management.
"""

import time
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from tortoise.expressions import Q

from app.api import deps
from app.models.model import (
    Model,
    ModelProvider as OrmModelProvider,
    ModelType as OrmModelType,
    PROVIDER_DEFAULTS,
)
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelUpdate,
    ModelResponse,
    ModelBrief,
    ProviderInfo,
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


@router.get("/providers", response_model=Response[list[ProviderInfo]])
async def get_providers() -> Any:
    """
    Get list of supported model providers with their default configurations.
    No authentication required.
    """
    providers = []
    for provider_enum in OrmModelProvider:
        defaults = PROVIDER_DEFAULTS.get(provider_enum)
        if defaults:
            name_val = defaults.get("name")
            name = name_val if isinstance(name_val, str) else provider_enum.value
            base_url_val = defaults.get("base_url")
            base_url = base_url_val if isinstance(base_url_val, str) else None
            icon_val = defaults.get("icon")
            icon = icon_val if isinstance(icon_val, str) else provider_enum.value
            providers.append(
                {
                    "code": provider_enum.value,
                    "name": name,
                    "base_url": base_url,
                    "icon": icon,
                }
            )
        else:
            providers.append(
                {
                    "code": provider_enum.value,
                    "name": provider_enum.value,
                    "base_url": None,
                    "icon": provider_enum.value,
                }
            )
    return success(data=providers)


@router.get("/types", response_model=Response[list[dict]])
async def get_model_types() -> Any:
    """
    Get list of supported model types.
    Only returns types that have implemented adapters.
    No authentication required.
    """
    # 仅返回已实现适配器的模型类型
    types = [
        {"code": OrmModelType.CHAT.value, "name": "Chat", "description": "对话模型"},
        {
            "code": OrmModelType.EMBEDDING.value,
            "name": "Embedding",
            "description": "嵌入模型",
        },
        {"code": OrmModelType.TTS.value, "name": "TTS", "description": "语音合成"},
        {"code": OrmModelType.STT.value, "name": "STT", "description": "语音识别"},
        {
            "code": OrmModelType.TEXT_TO_IMAGE.value,
            "name": "Text to Image",
            "description": "文生图",
        },
        # 以下类型暂未实现适配器，待实现后启用：
        # {"code": ModelType.RERANK.value, "name": "Rerank", "description": "重排序模型"},
        # {"code": ModelType.TEXT_TO_VIDEO.value, "name": "Text to Video", "description": "文生视频"},
        # {"code": ModelType.IMAGE_TO_VIDEO.value, "name": "Image to Video", "description": "图生视频"},
    ]
    return success(data=types)


@router.get("/", response_model=Response[PageData[ModelResponse]])
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    search: Optional[str] = Query(None, description="Search by name or model_id"),
    current_user: User = Depends(deps.PermissionChecker("model:read")),
) -> Any:
    """
    List all models with pagination and filters.
    Requires model:read permission.
    """
    skip = (page - 1) * page_size

    # Build query
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


@router.get("/available", response_model=Response[list[ModelBrief]])
async def get_available_models(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of available (enabled) models for dropdown selection.
    Only returns enabled models.
    """
    query = Model.filter(is_enabled=True)

    if model_type:
        query = query.filter(model_type=model_type)

    models = await query.order_by("sort_order", "name")
    return success(data=models)


@router.get("/default/{model_type}", response_model=Response[ModelBrief | None])
async def get_default_model(
    model_type: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get the default model for a specific type.
    Returns None if no default is set.
    """
    model = await Model.filter(
        model_type=model_type,
        is_default=True,
        is_enabled=True,
    ).first()

    return success(data=model)


@router.post("/", response_model=Response[ModelResponse])
async def create_model(
    *,
    model_in: ModelCreate,
    current_user: User = Depends(deps.PermissionChecker("model:create")),
) -> Any:
    """
    Create a new model configuration.
    Requires model:create permission.
    """
    # Check for duplicate provider + model_id
    existing = await Model.filter(
        provider=model_in.provider.value, model_id=model_in.model_id
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS,
            msg_key="model_already_exists",
        )

    # If setting as default, unset other defaults of same type
    if model_in.is_default:
        await Model.filter(
            model_type=model_in.model_type.value, is_default=True
        ).update(is_default=False)

    # Create model
    model_data = model_in.model_dump()
    model_data["provider"] = model_in.provider.value
    model_data["model_type"] = model_in.model_type.value

    model = await Model.create(**model_data)
    return success(data=ModelResponse.model_validate(model), msg_key="model_created")


@router.get("/{model_id}", response_model=Response[ModelResponse])
async def get_model(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("model:read")),
) -> Any:
    """
    Get a specific model by ID.
    Requires model:read permission.
    """
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
    current_user: User = Depends(deps.PermissionChecker("model:update")),
) -> Any:
    """
    Update a model configuration.
    Requires model:update permission.
    """
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    update_data = model_in.model_dump(exclude_unset=True)

    # Handle api_key special case: empty string means clear
    if "api_key" in update_data:
        if update_data["api_key"] == "":
            update_data["api_key"] = None

    # If setting as default, unset other defaults of same type
    if update_data.get("is_default"):
        await (
            Model.filter(model_type=model.model_type, is_default=True)
            .exclude(id=model_id)
            .update(is_default=False)
        )

    await model.update_from_dict(update_data)
    await model.save()

    # Refresh to get updated timestamps
    model = await Model.get(id=model_id)
    return success(data=ModelResponse.model_validate(model), msg_key="model_updated")


@router.delete("/{model_id}", response_model=Response[ModelResponse])
async def delete_model(
    model_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("model:delete")),
) -> Any:
    """
    Delete a model configuration.
    Requires model:delete permission.
    """
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
    current_user: User = Depends(deps.PermissionChecker("model:update")),
) -> Any:
    """
    Test model connection by making a simple API call.
    Requires model:update permission.
    """
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    if not model.api_key:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_api_key_required",
        )

    # 复用 test_model_config 的测试逻辑
    start_time = time.time()
    provider = ModelProvider(model.provider)
    model_type = ModelType(model.model_type)
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
        elif model_type == ModelType.TEXT_TO_IMAGE:
            _validate_api_key(provider, model.api_key)
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
            error_msg = "Rate limit exceeded, but API key is valid"
            return success(
                data=ModelTestResponse(
                    success=True,
                    message=error_msg,
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
    current_user: User = Depends(deps.PermissionChecker("model:update")),
) -> Any:
    """
    Set a model as the default for its type.
    Requires model:update permission.
    """
    model = await Model.filter(id=model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    # Unset other defaults of same type (exclude current model)
    await (
        Model.filter(model_type=model.model_type, is_default=True)
        .exclude(id=model_id)
        .update(is_default=False)
    )

    # Set this model as default
    model.is_default = True
    await model.save()

    return success(
        data=ModelResponse.model_validate(model), msg_key="model_set_default"
    )


@router.post("/test", response_model=Response[ModelTestResponse])
async def test_model_config(
    test_request: ModelTestRequest,
    current_user: User = Depends(deps.PermissionChecker("model:create")),
) -> Any:
    """
    Test model configuration before creating.
    Makes a simple API call to verify the connection works.
    Requires model:create permission.
    """
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
        elif model_type == ModelType.TEXT_TO_IMAGE:
            # 图像生成测试成本较高，只验证 API 密钥格式
            _validate_api_key(provider, api_key)
        elif model_type in [ModelType.TTS, ModelType.STT]:
            # 音频测试成本较高，只验证 API 密钥格式
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

        # 解析错误信息
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg.lower():
            error_msg = "Invalid API key"
        elif "404" in error_msg or "not found" in error_msg.lower():
            error_msg = "Model not found or not accessible"
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            error_msg = "Rate limit exceeded, but API key is valid"
            # Rate limit 说明密钥有效，返回成功
            return success(
                data=ModelTestResponse(
                    success=True,
                    message=error_msg,
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


def _validate_api_key(provider: ModelProvider, api_key: str) -> None:
    """Validate API key format for providers"""
    if provider == ModelProvider.OPENAI:
        if not api_key.startswith("sk-"):
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="invalid_api_key_format",
            )
    elif provider == ModelProvider.ANTHROPIC:
        if not api_key.startswith("sk-ant-"):
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="invalid_api_key_format",
            )


async def _test_chat_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str,
    base_url: Optional[str],
    config: dict,
) -> None:
    """Test chat model by making a simple completion request"""
    from langchain_core.messages import HumanMessage

    # 构建临时配置
    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = {}
            self.config = config

    from app.llm.adapters.chat.factory import create_chat_model

    chat_model = create_chat_model(TempModel())

    # 发送一个简单的测试消息
    messages = [HumanMessage(content="Hi")]
    response = await chat_model.ainvoke(messages)

    if not response.content:
        raise ValueError("Empty response from model")


async def _test_embedding_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str,
    base_url: Optional[str],
    config: dict,
) -> None:
    """Test embedding model by embedding a simple text"""

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.config = config

    from app.llm.adapters.embedding.factory import create_embedding_model

    embedding_model = create_embedding_model(TempModel())

    # 嵌入一个简单的测试文本
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
