"""
Pydantic schemas for AI Model management.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ModelProvider(str, Enum):
    """Supported model providers"""

    # General LLM providers
    OPENAI = "openai"
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

    # Custom/OpenAI-compatible
    CUSTOM = "custom"


class ModelType(str, Enum):
    """Model type classification"""

    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    TTS = "tts"
    STT = "stt"
    TEXT_TO_IMAGE = "text_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"


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
    base_url: Optional[str] = Field(None, max_length=512, description="Custom API URL")
    api_key: str = Field(
        ..., min_length=1, max_length=1024, description="API key (required)"
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
        None, description="Model capabilities"
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
    base_url: Optional[str] = Field(None, max_length=512)
    api_key: Optional[str] = Field(
        None, max_length=1024, description="Empty string to clear"
    )
    context_length: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    input_price: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    output_price: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    default_params: Optional[dict[str, Any]] = None
    capabilities: Optional[dict[str, Any]] = None
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

    class Config:
        from_attributes = True


class ModelBrief(BaseModel):
    """Brief model info for dropdown selections"""

    id: UUID
    name: str
    provider: str
    model_id: str
    model_type: str
    capabilities: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


class ModelTestRequest(BaseModel):
    """Schema for testing model configuration before creation"""

    provider: ModelProvider = Field(..., description="Provider identifier")
    model_id: str = Field(
        ..., min_length=1, max_length=100, description="Model identifier"
    )
    model_type: ModelType = Field(..., description="Model type")
    base_url: Optional[str] = Field(None, max_length=512, description="Custom API URL")
    api_key: str = Field(..., min_length=1, max_length=1024, description="API key")
    config: Optional[dict[str, Any]] = Field(
        None, description="Additional configuration"
    )


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

    class Config:
        from_attributes = True


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
