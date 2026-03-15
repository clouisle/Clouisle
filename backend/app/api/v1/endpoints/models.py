"""
Platform-side model endpoints (public/user-facing only).
Admin CRUD endpoints are in app/api/v1/admin/endpoints/models.py
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.models.model import (
    Model,
    ModelProvider as OrmModelProvider,
    ModelType as OrmModelType,
    PROVIDER_DEFAULTS,
)
from app.models.user import User
from app.schemas.model import (
    ModelBrief,
    ProviderInfo,
)
from app.schemas.response import (
    Response,
    success,
)

router = APIRouter()


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
    No authentication required.
    """
    types = [
        {"code": OrmModelType.CHAT.value, "name": "Chat", "description": "对话模型"},
        {
            "code": OrmModelType.EMBEDDING.value,
            "name": "Embedding",
            "description": "嵌入模型",
        },
        {
            "code": OrmModelType.RERANK.value,
            "name": "Rerank",
            "description": "重排序模型",
        },
        {"code": OrmModelType.TTS.value, "name": "TTS", "description": "语音合成"},
        {"code": OrmModelType.STT.value, "name": "STT", "description": "语音识别"},
        {
            "code": OrmModelType.TEXT_TO_IMAGE.value,
            "name": "Text to Image",
            "description": "文生图",
        },
    ]
    return success(data=types)


@router.get("/available", response_model=Response[list[ModelBrief]])
async def get_available_models(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get list of available (enabled) models for dropdown selection.
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
    """
    model = await Model.filter(
        model_type=model_type,
        is_default=True,
        is_enabled=True,
    ).first()

    return success(data=model)
