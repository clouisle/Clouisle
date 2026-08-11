"""
Admin-only model management endpoints (CRUD, discovery, test, set-default).
Public endpoints (providers, types, available, default) remain in the platform router.
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
from app.core.i18n import t
from app.models.model import Model, get_effective_model_base_url
from app.models.user import User
from app.schemas.model import (
    ModelCreate,
    ModelUpdate,
    ModelResponse,
    ModelDiscoveryItem,
    ModelDiscoveryRequest,
    ModelDiscoveryResponse,
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
from app.core.model_endpoint_policy import (
    ModelEndpointPolicyError,
    ensure_model_endpoint_allowed,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _effective_model_base_url(
    provider: ModelProvider | str,
    base_url: str | None,
    model_type: ModelType | str | None = None,
) -> str | None:
    return get_effective_model_base_url(provider, model_type, base_url)


async def _ensure_model_endpoint_allowed(
    provider: ModelProvider | str,
    base_url: str | None,
    model_type: ModelType | str | None = None,
) -> str | None:
    effective_base_url = _effective_model_base_url(provider, base_url, model_type)
    try:
        await ensure_model_endpoint_allowed(effective_base_url)
    except ModelEndpointPolicyError as exc:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key=exc.msg_key,
            origin=exc.origin or "",
        ) from exc
    return effective_base_url


@router.get("", response_model=Response[PageData[ModelResponse]])
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[list[str]] = Query(None),
    model_type: Optional[list[str]] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(deps.PermissionChecker("admin:model:read")),
) -> Any:
    skip = (page - 1) * page_size
    query = Model.all()

    if provider:
        query = query.filter(provider__in=provider).distinct()
    if model_type:
        query = query.filter(model_type__in=model_type).distinct()
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
    await _ensure_model_endpoint_allowed(
        model_in.provider, model_in.base_url, model_in.model_type
    )

    if model_in.is_default:
        await Model.filter(
            model_type=model_in.model_type.value, is_default=True
        ).update(is_default=False)

    model_data = model_in.model_dump()
    model_data["provider"] = model_in.provider.value
    model_data["model_type"] = model_in.model_type.value
    model_data["provider_display_name"] = (
        model_in.provider_display_name.strip()
        if model_in.provider_display_name and model_in.provider_display_name.strip()
        else None
    )

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
    if "provider_display_name" in update_data:
        display_name = update_data["provider_display_name"]
        update_data["provider_display_name"] = (
            display_name.strip() if display_name and display_name.strip() else None
        )
    candidate_base_url = update_data.get("base_url", model.base_url)
    await _ensure_model_endpoint_allowed(
        model.provider, candidate_base_url, model.model_type
    )

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

    if (
        _requires_api_key(provider := ModelProvider(model.provider))
        and not model.api_key
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_api_key_required",
        )

    start_time = time.monotonic()
    try:
        model_type = ModelType(model.model_type)
    except ValueError as exc:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_type_not_supported",
        ) from exc
    await _ensure_model_endpoint_allowed(provider, model.base_url, model_type)
    default_params = model.default_params or {}
    config = model.config or {}

    try:
        if model_type == ModelType.CHAT:
            await _test_chat_model(
                provider,
                model.model_id,
                model.api_key,
                model.base_url,
                default_params,
                config,
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
            await _test_image_model(
                provider,
                model.model_id,
                model.api_key,
                model.base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.TEXT_TO_VIDEO:
            await _test_video_model(
                provider,
                model.model_id,
                model.api_key,
                model.base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.TTS:
            await _test_tts_model(
                provider,
                model.model_id,
                model.api_key,
                model.base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.AUDIO_GENERATION:
            await _test_audio_generation_model(
                provider,
                model.model_id,
                model.api_key,
                model.base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.STT:
            _validate_api_key(provider, model.api_key)
        else:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="model_type_not_supported",
            )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        return success(
            data=ModelTestResponse(
                success=True,
                message=t("model_test_connection_successful"),
                latency_ms=latency_ms,
            ),
            msg_key="model_test_success",
        )

    except BusinessError:
        raise
    except Exception as exc:
        logger.exception(
            "Model test failed: provider=%s model=%s type=%s",
            provider.value,
            model.model_id,
            model_type.value,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        if _is_model_test_rate_limited(exc) and model_type != ModelType.TEXT_TO_VIDEO:
            return success(
                data=ModelTestResponse(
                    success=True,
                    message=t("model_test_rate_limit_but_valid"),
                    latency_ms=latency_ms,
                ),
                msg_key="model_test_success",
            )
        return _model_test_failure_response(
            error=exc,
            latency_ms=latency_ms,
            provider=provider,
            model_id=model.model_id,
            model_type=model_type,
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
    default_params = test_request.default_params or {}
    config = test_request.config or {}
    await _ensure_model_endpoint_allowed(provider, base_url, model_type)

    start_time = time.monotonic()

    try:
        if model_type == ModelType.CHAT:
            await _test_chat_model(
                provider,
                model_id,
                api_key,
                base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.EMBEDDING:
            await _test_embedding_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.RERANK:
            await _test_rerank_model(provider, model_id, api_key, base_url, config)
        elif model_type == ModelType.TEXT_TO_IMAGE:
            await _test_image_model(
                provider,
                model_id,
                api_key,
                base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.TEXT_TO_VIDEO:
            await _test_video_model(
                provider,
                model_id,
                api_key,
                base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.TTS:
            await _test_tts_model(
                provider,
                model_id,
                api_key,
                base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.AUDIO_GENERATION:
            await _test_audio_generation_model(
                provider,
                model_id,
                api_key,
                base_url,
                default_params,
                config,
            )
        elif model_type == ModelType.STT:
            _validate_api_key(provider, api_key)
        else:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="model_type_not_supported",
            )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        return success(
            data=ModelTestResponse(
                success=True,
                message=t("model_test_connection_successful"),
                latency_ms=latency_ms,
            ),
            msg_key="model_test_success",
        )

    except BusinessError:
        raise
    except Exception as exc:
        logger.exception(
            "Model test failed: provider=%s model=%s type=%s",
            provider.value,
            model_id,
            model_type.value,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        if _is_model_test_rate_limited(exc) and model_type != ModelType.TEXT_TO_VIDEO:
            return success(
                data=ModelTestResponse(
                    success=True,
                    message=t("model_test_rate_limit_but_valid"),
                    latency_ms=latency_ms,
                ),
                msg_key="model_test_success",
            )
        return _model_test_failure_response(
            error=exc,
            latency_ms=latency_ms,
            provider=provider,
            model_id=model_id,
            model_type=model_type,
        )


_MODEL_DISCOVERY_TIMEOUT_SECONDS = 15.0
_MODEL_DISCOVERY_MAX_TOKEN_LIMIT = 2_147_483_647
_MODEL_DISCOVERY_CONTEXT_LENGTH_KEYS = (
    "context_length",
    "contextLength",
    "context_window",
    "contextWindow",
    "max_context_length",
    "maxContextLength",
    "input_token_limit",
    "inputTokenLimit",
)
_MODEL_DISCOVERY_MAX_OUTPUT_TOKENS_KEYS = (
    "max_output_tokens",
    "maxOutputTokens",
    "max_completion_tokens",
    "maxCompletionTokens",
    "max_tokens",
    "maxTokens",
    "output_token_limit",
    "outputTokenLimit",
)
_MODEL_DISCOVERY_CAPABILITY_KEYS = {
    "vision": ("vision", "supports_vision", "supportsVision"),
    "function_call": (
        "function_call",
        "functionCall",
        "tools",
        "function_calling",
        "functionCalling",
        "supports_function_call",
        "supportsFunctionCall",
        "tool_calling",
        "toolCalling",
    ),
    "streaming": ("streaming", "supports_streaming", "supportsStreaming"),
    "json_mode": (
        "json_mode",
        "structured_output",
        "structuredOutput",
        "jsonMode",
        "supports_json_mode",
        "supportsJsonMode",
    ),
}
_MODEL_DISCOVERY_MAX_MODELS = 200
_MODEL_DISCOVERY_SUPPORTED_PROVIDERS = frozenset(
    {
        ModelProvider.OPENAI,
        ModelProvider.OPENAI_RESPONSES,
        ModelProvider.ANTHROPIC,
        ModelProvider.GOOGLE,
        ModelProvider.DEEPSEEK,
        ModelProvider.MOONSHOT,
        ModelProvider.ZHIPU,
        ModelProvider.QWEN,
        ModelProvider.BAICHUAN,
        ModelProvider.MINIMAX,
        ModelProvider.VOLCENGINE,
        ModelProvider.SILICONFLOW,
        ModelProvider.XAI,
        ModelProvider.OLLAMA,
        ModelProvider.CUSTOM,
    }
)


@router.post("/discover", response_model=Response[ModelDiscoveryResponse])
async def discover_models(
    discovery_request: ModelDiscoveryRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:model:create")),
) -> Any:
    """List models exposed by a provider without persisting the supplied key."""
    provider = discovery_request.provider
    if provider not in _MODEL_DISCOVERY_SUPPORTED_PROVIDERS:
        return _model_discovery_failure("model_discovery_not_supported")

    base_url = _normalize_model_discovery_base_url(discovery_request.base_url)
    if not base_url:
        return _model_discovery_failure("model_discovery_base_url_invalid")
    try:
        await ensure_model_endpoint_allowed(base_url)
    except ModelEndpointPolicyError:
        return _model_discovery_failure("model_endpoint_not_allowlisted")

    api_key = (discovery_request.api_key or "").strip()
    if _requires_api_key(provider) and not api_key:
        return _model_discovery_failure("model_discovery_api_key_required")

    endpoint, headers, params = _build_model_discovery_request(
        provider, base_url, api_key
    )
    try:
        async with httpx.AsyncClient(
            timeout=_MODEL_DISCOVERY_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            discovered_models = _parse_discovered_models(provider, response.json())
    except (httpx.HTTPError, ValueError):
        return _model_discovery_failure("model_discovery_failed")

    message = t("model_discovery_success", count=len(discovered_models))
    return success(
        data=ModelDiscoveryResponse(
            success=True,
            message=message,
            models=discovered_models,
        ),
        msg=message,
    )


def _model_discovery_failure(msg_key: str) -> dict:
    message = t(msg_key)
    return success(
        data=ModelDiscoveryResponse(success=False, message=message, models=[]),
        msg=message,
    )


def _normalize_model_discovery_base_url(value: str) -> str | None:
    base_url = value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        not base_url
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return None
    return base_url


def _append_model_discovery_path(base_url: str, path: str) -> str:
    normalized_path = path.strip("/")
    if base_url.endswith(f"/{normalized_path}"):
        return base_url
    return f"{base_url}/{normalized_path}"


def _build_model_discovery_request(
    provider: ModelProvider,
    base_url: str,
    api_key: str,
) -> tuple[str, dict[str, str], dict[str, str] | None]:
    if provider == ModelProvider.OLLAMA:
        return _append_model_discovery_path(base_url, "api/tags"), {}, None
    if provider == ModelProvider.ANTHROPIC:
        if base_url.endswith("/v1/models"):
            endpoint = base_url
        elif base_url.endswith("/v1"):
            endpoint = _append_model_discovery_path(base_url, "models")
        else:
            endpoint = _append_model_discovery_path(base_url, "v1/models")
        return (
            endpoint,
            {
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
            },
            None,
        )
    if provider == ModelProvider.GOOGLE:
        return _append_model_discovery_path(base_url, "models"), {}, {"key": api_key}
    return (
        _append_model_discovery_path(base_url, "models"),
        {"Authorization": f"Bearer {api_key}"},
        None,
    )


def _parse_discovered_models(
    provider: ModelProvider,
    payload: Any,
) -> list[ModelDiscoveryItem]:
    if not isinstance(payload, dict):
        raise ValueError("Model list response is not an object")

    native_models_key = provider in {ModelProvider.GOOGLE, ModelProvider.OLLAMA}
    raw_models = payload.get("models") if native_models_key else payload.get("data")
    if raw_models is None:
        raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("Model list response does not contain models")

    discovered_models: list[ModelDiscoveryItem] = []
    seen_model_ids: set[str] = set()
    for item in raw_models:
        if not isinstance(item, dict):
            continue

        raw_model_id = item.get("name") if native_models_key else item.get("id")
        if not isinstance(raw_model_id, str):
            raw_model_id = item.get("id") or item.get("name")
        if not isinstance(raw_model_id, str):
            continue

        model_id = raw_model_id.strip()
        if provider == ModelProvider.GOOGLE:
            model_id = model_id.removeprefix("models/")
        if not model_id or len(model_id) > 100 or model_id in seen_model_ids:
            continue

        raw_name = (
            item.get("display_name") or item.get("displayName") or item.get("name")
        )
        name = raw_name.strip() if isinstance(raw_name, str) else model_id
        if not name or len(name) > 100:
            name = model_id

        top_provider = item.get("top_provider")
        discovered_models.append(
            ModelDiscoveryItem(
                id=model_id,
                name=name,
                context_length=_extract_discovery_token_limit(
                    (item,), _MODEL_DISCOVERY_CONTEXT_LENGTH_KEYS
                ),
                max_output_tokens=_extract_discovery_token_limit(
                    (item, top_provider), _MODEL_DISCOVERY_MAX_OUTPUT_TOKENS_KEYS
                ),
                capabilities=_extract_discovery_capabilities(item),
            )
        )
        seen_model_ids.add(model_id)
        if len(discovered_models) == _MODEL_DISCOVERY_MAX_MODELS:
            break

    return discovered_models


def _extract_discovery_token_limit(
    sources: tuple[Any, ...], keys: tuple[str, ...]
) -> int | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                parsed_value = value
            elif isinstance(value, str) and value.strip().isdecimal():
                parsed_value = int(value.strip())
            else:
                continue
            if 0 < parsed_value <= _MODEL_DISCOVERY_MAX_TOKEN_LIMIT:
                return parsed_value
    return None


def _extract_discovery_capabilities(item: dict[str, Any]) -> dict[str, bool] | None:
    capabilities: dict[str, bool] = {}
    declared_capabilities = item.get("capabilities")
    sources = (item, declared_capabilities)
    for capability, keys in _MODEL_DISCOVERY_CAPABILITY_KEYS.items():
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if isinstance(value, bool):
                    capabilities[capability] = value
                    break
            if capability in capabilities:
                break

    features: set[str] = set()
    for source in (
        declared_capabilities,
        item.get("supported_parameters"),
        item.get("supportedParameters"),
    ):
        if isinstance(source, list):
            features.update(
                value.strip().lower().replace("-", "_").replace(" ", "_")
                for value in source
                if isinstance(value, str)
            )
    if features & {"vision", "image_input", "multimodal", "image_to_text"}:
        capabilities.setdefault("vision", True)
    if features & {
        "function_call",
        "function_calling",
        "functions",
        "tools",
        "tool_calling",
    }:
        capabilities.setdefault("function_call", True)
    if features & {"json_mode", "response_format", "structured_outputs"}:
        capabilities.setdefault("json_mode", True)

    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        input_modalities = architecture.get("input_modalities")
        if isinstance(input_modalities, list) and any(
            isinstance(value, str) and value.lower() == "image"
            for value in input_modalities
        ):
            capabilities.setdefault("vision", True)

    return capabilities or None


_MODEL_TEST_MAX_ERROR_DETAIL_LENGTH = 400
_MODEL_TEST_TRANSLATION_KEY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$", re.IGNORECASE
)
_MODEL_TEST_UNSAFE_DETAIL_PATTERNS = (
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r'\bfile\s+"[^"]+", line \d+', re.IGNORECASE),
    re.compile(r"\bexception\b", re.IGNORECASE),
    re.compile(r"(/private/|/tmp/|[A-Z]:\\)"),
)
_MODEL_TEST_CREDENTIAL_PATTERNS = (
    (
        re.compile(r"(?i)\bbearer\s+[^\s,;}\]]+"),
        "Bearer ***",
    ),
    (
        re.compile(
            r"(?i)(\b(?:api[_-]?key|access[_-]?token|token|secret|password|authorization)"
            r"\b\s*(?:[:=]\s*|['\"]\s*:\s*['\"]))[^,\s;}\]'\"]+"
        ),
        r"\1***",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{4,}\b"), "sk-***"),
    (
        re.compile(r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|key)=)[^&#\s]+"),
        r"\1***",
    ),
    (re.compile(r"(https?://)[^/\s:@]+:[^@/\s]+@"), r"\1***:***@"),
)


def _model_test_error_text(error: Exception) -> str:
    message = getattr(error, "message", None)
    if isinstance(message, str) and message.strip():
        return message
    return str(error)


def _sanitize_model_test_error(error_text: str) -> str | None:
    if not error_text or "\n" in error_text:
        return None

    detail = error_text.strip()
    if (
        not detail
        or len(detail) > _MODEL_TEST_MAX_ERROR_DETAIL_LENGTH
        or _MODEL_TEST_TRANSLATION_KEY_PATTERN.fullmatch(detail)
        or any(pattern.search(detail) for pattern in _MODEL_TEST_UNSAFE_DETAIL_PATTERNS)
    ):
        return None

    for pattern, replacement in _MODEL_TEST_CREDENTIAL_PATTERNS:
        detail = pattern.sub(replacement, detail)

    return detail if len(detail) <= _MODEL_TEST_MAX_ERROR_DETAIL_LENGTH else None


def _is_model_test_rate_limited(error: Exception) -> bool:
    raw_error = _model_test_error_text(error)
    return getattr(error, "status_code", None) == 429 or (
        "429" in raw_error or "rate limit" in raw_error.lower()
    )


def _model_test_error_reason(error: Exception) -> str:
    raw_error = _model_test_error_text(error)
    normalized_error = raw_error.lower()
    status_code = getattr(error, "status_code", None)

    if (
        status_code == 401
        or "401" in raw_error
        or "unauthorized" in normalized_error
        or "authentication" in normalized_error
    ):
        return t("model_test_invalid_api_key")
    if (
        status_code in {403, 404}
        or "404" in raw_error
        or "not found" in normalized_error
    ):
        return t("model_test_model_not_accessible")
    if _is_model_test_rate_limited(error):
        return t("model_test_rate_limited")
    if "timeout" in normalized_error or "timed out" in normalized_error:
        return t("model_test_connection_timeout")
    if "connection" in normalized_error or "connect" in normalized_error:
        return t("model_test_connection_failed_check_base_url")
    if "has no attribute 'choices'" in normalized_error:
        return t("model_test_chat_response_incompatible")

    detail = _sanitize_model_test_error(raw_error)
    if detail:
        return t("model_test_provider_error_details", error=detail)
    return t("model_test_unexpected_error")


def _model_test_failure_response(
    *,
    error: Exception,
    latency_ms: int,
    provider: ModelProvider,
    model_id: str,
    model_type: ModelType,
) -> dict:
    message = t(
        "model_test_failed",
        provider=provider.value,
        model=model_id,
        model_type=model_type.value,
        error=_model_test_error_reason(error),
    )
    return success(
        data=ModelTestResponse(
            success=False,
            message=message,
            latency_ms=latency_ms,
        ),
        msg=message,
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
    default_params: dict,
    config: dict,
) -> None:
    from app.llm.types import Message, MessageRole
    from app.llm.adapters.chat import (
        OpenAIAdapter,
        DeepSeekAdapter,
        MoonshotAdapter,
        OllamaAdapter,
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
            self.default_params = default_params
            self.max_output_tokens = default_params.get("max_tokens")
            self.config = config

    temp_model = TempModel()
    provider_value = provider.value if hasattr(provider, "value") else str(provider)

    adapter: object
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
        adapter = MoonshotAdapter(temp_model)
    elif provider_value == ModelProvider.ZHIPU.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="zhipu")
    elif provider_value == ModelProvider.QWEN.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="qwen")
    elif provider_value == ModelProvider.BAICHUAN.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="baichuan")
    elif provider_value == ModelProvider.MINIMAX.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="minimax")
    elif provider_value == ModelProvider.OLLAMA.value:
        adapter = OllamaAdapter(temp_model)
    elif provider_value == ModelProvider.CUSTOM.value:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint="custom")
    else:
        adapter = OpenAICompatibleAdapter(temp_model, provider_hint=provider_value)

    messages = [Message(role=MessageRole.USER, content="Hi")]
    response = await adapter.chat(messages)

    if not response.content:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_response",
        )


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
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="model_test_embedding_response_incompatible",
            )
        raise

    if not result or len(result) == 0:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_embedding_result",
        )


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
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_rerank_result",
        )


async def _test_image_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    default_params: dict,
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = default_params
            self.config = config

    from app.llm.adapters.image import create_image_adapter

    adapter = create_image_adapter(cast(Model, TempModel()))
    from app.llm.types.image import ImageGenerationRequest

    request_params: dict[str, Any] = {
        "prompt": "A simple connection test image",
        "num_images": 1,
    }
    if provider == ModelProvider.OPENAI_RESPONSES:
        request_params["quality"] = "low"

    response = await adapter.generate(ImageGenerationRequest(**request_params))
    if not response.images or not any(
        image.image.has_content() for image in response.images
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_response",
        )


async def _test_tts_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    default_params: dict,
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = default_params
            self.config = config

    from app.llm.adapters.audio import create_tts_adapter
    from app.llm.types import TTSRequest

    adapter = create_tts_adapter(cast(Model, TempModel()))
    voice = default_params.get("speaker") or default_params.get("voice")
    response = await adapter.synthesize(
        TTSRequest(text="Hello", voice=str(voice) if voice else None)
    )
    if not response.audio.has_content():
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_response",
        )


async def _test_audio_generation_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    default_params: dict,
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = default_params
            self.config = config

    from app.llm.adapters.audio import create_audio_generation_adapter
    from app.llm.types import AudioGenerationRequest

    adapter = create_audio_generation_adapter(cast(Model, TempModel()))
    response = await adapter.generate(
        AudioGenerationRequest(prompt="A short, gentle bell sound")
    )
    if not response.audio.has_content():
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="model_test_empty_response",
        )


async def _test_video_model(
    provider: ModelProvider,
    model_id: str,
    api_key: str | None,
    base_url: Optional[str],
    default_params: dict,
    config: dict,
) -> None:
    _validate_api_key(provider, api_key)

    class TempModel:
        def __init__(self):
            self.provider = provider
            self.model_id = model_id
            self.api_key = api_key
            self.base_url = base_url
            self.default_params = default_params
            self.config = config

    from app.llm.adapters.video import create_video_adapter
    from app.llm.errors import ProviderError
    from app.llm.types import TaskStatus, VideoGenerationRequest

    adapter = create_video_adapter(cast(Model, TempModel()))
    request_params: dict[str, Any] = {"prompt": "A simple connection test video"}
    if "duration" in default_params:
        request_params["duration"] = default_params["duration"]
    if "aspect_ratio" in default_params:
        request_params["aspect_ratio"] = default_params["aspect_ratio"]

    response = await adapter.generate(VideoGenerationRequest(**request_params))
    pending_statuses = {TaskStatus.PENDING, TaskStatus.PROCESSING}
    deadline = time.monotonic() + float(config.get("poll_timeout_s", 120))
    poll_interval = float(config.get("poll_interval_ms", 3000)) / 1000

    while response.status in pending_statuses and time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        response = await adapter.get_status(response.task_id)

    if response.status in pending_statuses:
        raise ProviderError(
            message=t("model_test_connection_timeout"),
            provider=provider.value,
            model=model_id,
        )
    if (
        response.status == TaskStatus.COMPLETED
        and response.video
        and response.video.has_content()
    ):
        return

    raise ProviderError(
        message=response.error
        or t("video_generation_failed", error=response.status.value),
        provider=provider.value,
        model=model_id,
    )
