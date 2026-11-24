"""
Pydantic schemas for AI Model management.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import ConfigDict, BaseModel, Field, ValidationInfo, field_validator
import re


_MODEL_MODALITIES = frozenset({"text", "image", "audio", "video", "file"})
# Modalities each model type may declare. Chat is the only type addressed as a
# conversation over arbitrary media; every other type has a fixed shape. OCR
# recognizes text from an image or document and never takes a text prompt, while
# embedding, rerank, and decision models return vectors or scores rather than a
# media modality, so their output set is empty.
_MODEL_TYPE_MODALITIES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "chat": (
        frozenset({"text", "image", "audio", "video", "file"}),
        frozenset({"text", "image", "audio", "video", "file"}),
    ),
    "ocr": (frozenset({"image", "file"}), frozenset({"text"})),
    "tts": (frozenset({"text"}), frozenset({"audio"})),
    "stt": (frozenset({"audio"}), frozenset({"text"})),
    "audio_generation": (frozenset({"text"}), frozenset({"audio"})),
    "text_to_image": (frozenset({"text"}), frozenset({"image"})),
    "text_to_video": (frozenset({"text"}), frozenset({"video"})),
    "embedding": (frozenset({"text"}), frozenset()),
    "rerank": (frozenset({"text"}), frozenset()),
    "decision": (frozenset({"text"}), frozenset()),
}
_MIME_TYPE_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")


def _resolve_model_type(
    model_type: "ModelType | str | None",
) -> "ModelType | None":
    """Return the enum member for a declared type, or None when unconstrained."""
    if model_type is None:
        return None
    return model_type if isinstance(model_type, ModelType) else ModelType(model_type)


def _allowed_modalities(
    model_type: "ModelType | None",
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the input and output modalities ``model_type`` accepts."""
    if model_type is None:
        return _MODEL_MODALITIES, _MODEL_MODALITIES
    return _MODEL_TYPE_MODALITIES[model_type.value]


def validate_model_capabilities(
    value: dict[str, Any] | None, model_type: "ModelType | str | None" = None
) -> dict[str, Any] | None:
    """Validate canonical modality declarations while retaining extension keys.

    Declarations are always checked against the modality vocabulary and, when
    ``model_type`` is supplied, against the modalities that type can accept, so
    an OCR model cannot claim a text prompt or a non-text answer.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("capabilities must be an object")

    capabilities = dict(value)
    legacy_vision = capabilities.pop("vision", None)
    if "input_modalities" not in capabilities and isinstance(legacy_vision, bool):
        capabilities["input_modalities"] = (
            ["text", "image"] if legacy_vision else ["text"]
        )

    resolved = _resolve_model_type(model_type)
    allowed_input, allowed_output = _allowed_modalities(resolved)

    for key, allowed in (
        ("input_modalities", allowed_input),
        ("output_modalities", allowed_output),
    ):
        modalities = capabilities.get(key)
        if modalities is None and key not in capabilities:
            continue
        if not isinstance(modalities, list) or any(
            not isinstance(modality, str) or modality not in _MODEL_MODALITIES
            for modality in modalities
        ):
            raise ValueError(
                f"{key} must be a list of text, image, audio, video, or file"
            )
        # ``allowed`` is the full vocabulary when the type is unknown, so the
        # per-type check only has meaning once a type is declared.
        if resolved is not None:
            unsupported = sorted(
                {modality for modality in modalities if modality not in allowed}
            )
            if unsupported:
                raise ValueError(
                    f"{key} cannot declare {', '.join(unsupported)} "
                    f"for model type '{resolved.value}'"
                )

    input_limits = capabilities.get("input_limits")
    if input_limits is not None:
        if not isinstance(input_limits, dict):
            raise ValueError("input_limits must be an object")
        for modality, limits in input_limits.items():
            if modality not in _MODEL_MODALITIES:
                raise ValueError(f"input_limits.{modality} has an unsupported modality")
            if resolved is not None and modality not in allowed_input:
                raise ValueError(
                    f"input_limits.{modality} is not an input modality "
                    f"of model type '{resolved.value}'"
                )
            if not isinstance(limits, dict):
                raise ValueError(f"input_limits.{modality} must be an object")
            max_bytes = limits.get("max_bytes")
            if max_bytes is not None and (
                not isinstance(max_bytes, int)
                or isinstance(max_bytes, bool)
                or max_bytes <= 0
            ):
                raise ValueError(
                    f"input_limits.{modality}.max_bytes must be a positive integer"
                )
            mime_types = limits.get("mime_types")
            if mime_types is not None and (
                not isinstance(mime_types, list)
                or any(
                    not isinstance(mime, str) or not _MIME_TYPE_RE.fullmatch(mime)
                    for mime in mime_types
                )
            ):
                raise ValueError(
                    f"input_limits.{modality}.mime_types must be a list of valid MIME types or null"
                )
    return capabilities


def _validate_capabilities_field(
    value: dict[str, Any] | None, info: ValidationInfo
) -> dict[str, Any] | None:
    # ``model_type`` precedes ``capabilities`` in ModelCreate, so it is already
    # resolved here. ModelUpdate omits it and re-validates in the endpoint
    # against the stored model type.
    return validate_model_capabilities(value, info.data.get("model_type"))


class ModelProvider(str, Enum):
    """Supported model providers"""

    # General LLM providers
    OPENAI = "openai"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    DEEPSEEK = "deepseek"
    MOONSHOT = "moonshot"
    ZHIPU = "zhipu"
    QWEN = "qwen"
    BAICHUAN = "baichuan"
    MINIMAX = "minimax"
    VOLCENGINE = "volcengine"  # 火山引擎 (豆包)
    SILICONFLOW = "siliconflow"
    XAI = "xai"  # Grok

    # Local deployment
    OLLAMA = "ollama"

    # Video generation
    RUNWAY = "runway"
    PIKA = "pika"
    LUMA = "luma"
    KLING = "kling"

    # Image generation
    STABILITY = "stability"
    MIDJOURNEY = "midjourney"

    # Decision models (non-generative typed decisions)
    TYPESAFE = "typesafe"

    # OCR / document understanding
    MISTRAL = "mistral"

    # Custom/OpenAI-compatible
    CUSTOM = "custom"


class ModelType(str, Enum):
    """Model type classification"""

    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    TTS = "tts"
    STT = "stt"
    AUDIO_GENERATION = "audio_generation"
    TEXT_TO_IMAGE = "text_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    DECISION = "decision"
    OCR = "ocr"


class ProviderInfo(BaseModel):
    """Provider information for frontend display"""

    code: str
    name: str
    base_url: Optional[str] = None
    icon: str


# ============ Request Schemas ============


class ModelCreate(BaseModel):
    """Schema for creating a new model"""

    name: str = Field(..., min_length=1, max_length=100, description="Display name")
    provider: ModelProvider = Field(..., description="Provider identifier")
    model_id: str = Field(
        ..., min_length=1, max_length=100, description="Model identifier"
    )
    model_type: ModelType = Field(..., description="Model type")
    provider_display_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional user-facing provider or gateway name",
    )
    base_url: Optional[str] = Field(None, max_length=512, description="Custom API URL")
    api_key: Optional[str] = Field(
        None, max_length=1024, description="API key (optional for local providers)"
    )
    context_length: Optional[int] = Field(None, ge=1, description="Context length")
    max_output_tokens: Optional[int] = Field(
        None, ge=1, description="Max output tokens"
    )
    input_price: Optional[Decimal] = Field(
        None, ge=0, decimal_places=6, description="Input price per 1M tokens"
    )
    output_price: Optional[Decimal] = Field(
        None, ge=0, decimal_places=6, description="Output price per 1M tokens"
    )
    default_params: Optional[dict[str, Any]] = Field(
        None, description="Default inference parameters"
    )
    capabilities: Optional[dict[str, Any]] = Field(
        None,
        description="Input/output modalities and model capabilities; input_modalities uses text, image, audio, video, file",
    )
    _validate_capabilities = field_validator("capabilities", mode="before")(
        _validate_capabilities_field
    )
    config: Optional[dict[str, Any]] = Field(
        None, description="Additional configuration"
    )
    is_enabled: bool = Field(True, description="Whether model is enabled")
    is_default: bool = Field(False, description="Whether this is the default model")
    sort_order: int = Field(0, description="Sort order")


class ModelUpdate(BaseModel):
    """Schema for updating a model"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider_display_name: Optional[str] = Field(None, max_length=100)
    base_url: Optional[str] = Field(None, max_length=512)
    api_key: Optional[str] = Field(
        None, max_length=1024, description="Empty string to clear"
    )
    context_length: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    input_price: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    output_price: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    default_params: Optional[dict[str, Any]] = None
    capabilities: Optional[dict[str, Any]] = Field(
        None,
        description="Input/output modalities and model capabilities; input_modalities uses text, image, audio, video, file",
    )
    _validate_capabilities = field_validator("capabilities", mode="before")(
        _validate_capabilities_field
    )
    config: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None


# ============ Response Schemas ============


class ModelResponse(BaseModel):
    """Schema for model response (API key hidden)"""

    id: UUID
    name: str
    provider: str
    provider_display_name: Optional[str] = None
    model_id: str
    model_type: str
    base_url: Optional[str] = None
    has_api_key: bool = Field(description="Whether API key is configured")
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    input_price: Optional[Decimal] = None
    output_price: Optional[Decimal] = None
    default_params: Optional[dict[str, Any]] = None
    capabilities: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    is_enabled: bool
    is_default: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelBrief(BaseModel):
    """Brief model info for dropdown selections"""

    id: UUID
    name: str
    provider: str
    provider_display_name: Optional[str] = None
    model_id: str
    model_type: str
    capabilities: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class ModelTestRequest(BaseModel):
    """Schema for testing model configuration before creation"""

    provider: ModelProvider = Field(..., description="Provider identifier")
    model_id: str = Field(
        ..., min_length=1, max_length=100, description="Model identifier"
    )
    model_type: ModelType = Field(..., description="Model type")
    base_url: Optional[str] = Field(None, max_length=512, description="Custom API URL")
    api_key: Optional[str] = Field(
        None, max_length=1024, description="API key (optional for local providers)"
    )
    default_params: Optional[dict[str, Any]] = Field(
        None, description="Default inference parameters"
    )
    config: Optional[dict[str, Any]] = Field(
        None, description="Additional configuration"
    )


class ModelDiscoveryRequest(BaseModel):
    """Connection details used to list models without storing credentials."""

    provider: ModelProvider = Field(..., description="Provider identifier")
    base_url: str = Field(..., min_length=1, max_length=512, description="API base URL")
    api_key: Optional[str] = Field(
        None, max_length=1024, description="API key (optional for local providers)"
    )


class ModelDiscoveryItem(BaseModel):
    """A remotely discoverable model that can be saved by this form."""

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    context_length: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    capabilities: Optional[dict[str, Any]] = None


class ModelDiscoveryResponse(BaseModel):
    """Result of a remote model-list request."""

    success: bool
    message: str
    models: list[ModelDiscoveryItem]


class ModelTestResponse(BaseModel):
    """Schema for model test response"""

    success: bool = Field(..., description="Whether the test was successful")
    message: str = Field(..., description="Test result message")
    latency_ms: Optional[int] = Field(
        None, description="Response latency in milliseconds"
    )


# ============ Team Model Authorization Schemas ============


class TeamModelCreate(BaseModel):
    """授权团队使用模型"""

    model_id: UUID = Field(..., description="模型 ID")
    daily_token_limit: Optional[int] = Field(
        None, ge=0, description="每日 Token 限额，null 表示无限制"
    )
    monthly_token_limit: Optional[int] = Field(
        None, ge=0, description="每月 Token 限额，null 表示无限制"
    )
    daily_request_limit: Optional[int] = Field(
        None, ge=0, description="每日请求次数限额，null 表示无限制"
    )
    monthly_request_limit: Optional[int] = Field(
        None, ge=0, description="每月请求次数限额，null 表示无限制"
    )
    is_enabled: bool = Field(True, description="是否启用")
    priority: int = Field(0, description="优先级")


class TeamModelUpdate(BaseModel):
    """更新团队模型授权配置"""

    daily_token_limit: Optional[int] = Field(None, ge=0)
    monthly_token_limit: Optional[int] = Field(None, ge=0)
    daily_request_limit: Optional[int] = Field(None, ge=0)
    monthly_request_limit: Optional[int] = Field(None, ge=0)
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None


class TeamModelBatchCreate(BaseModel):
    """批量授权模型"""

    model_ids: list[UUID] = Field(..., min_length=1, description="模型 ID 列表")
    daily_token_limit: Optional[int] = Field(None, ge=0)
    monthly_token_limit: Optional[int] = Field(None, ge=0)
    daily_request_limit: Optional[int] = Field(None, ge=0)
    monthly_request_limit: Optional[int] = Field(None, ge=0)


class TeamModelBatchDelete(BaseModel):
    """批量撤销授权"""

    model_ids: list[UUID] = Field(..., min_length=1, description="模型 ID 列表")


class TeamModelResponse(BaseModel):
    """团队模型授权响应"""

    id: UUID
    team_id: UUID
    model_id: UUID
    model: ModelBrief = Field(..., description="模型信息")

    # 配额设置
    daily_token_limit: Optional[int] = None
    monthly_token_limit: Optional[int] = None
    daily_request_limit: Optional[int] = None
    monthly_request_limit: Optional[int] = None

    # 当前用量
    daily_tokens_used: int = 0
    monthly_tokens_used: int = 0
    daily_requests_used: int = 0
    monthly_requests_used: int = 0

    # 状态
    is_enabled: bool
    priority: int

    # 时间戳
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamModelQuotaStatus(BaseModel):
    """团队模型配额状态"""

    model_id: UUID
    model_name: str
    model_type: str

    # 每日配额
    daily_token_limit: Optional[int] = None
    daily_tokens_used: int = 0
    daily_token_percent: Optional[float] = None

    # 每月配额
    monthly_token_limit: Optional[int] = None
    monthly_tokens_used: int = 0
    monthly_token_percent: Optional[float] = None

    # 状态
    is_enabled: bool
    is_quota_exceeded: bool = False
