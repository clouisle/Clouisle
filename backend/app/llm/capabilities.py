"""Effective chat input capabilities for model configuration and its adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit
from app.llm.types.base import ContentType
from app.models.model import Model, ModelProvider, ModelType


@dataclass(frozen=True)
class InputModalityLimits:
    """Known input limits; ``None`` means the adapter does not know the limit."""

    max_bytes: int | None = None


@dataclass(frozen=True)
class InputCapabilities:
    """Adapter-supported input modalities after model declaration intersection."""

    modalities: frozenset[ContentType]
    mime_types: Mapping[ContentType, frozenset[str] | None]
    limits: Mapping[ContentType, InputModalityLimits]


_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_ANTHROPIC_IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)
_GOOGLE_VIDEO_MIMES = frozenset(
    {"video/mp4", "video/mpeg", "video/quicktime", "video/webm"}
)

# Provider-specific native serializers. OpenAI-compatible providers all have
# image_url serialization, but only OpenRouter's documented input_audio format
# is implemented here for audio. Generic compatible gateways are not guessed to
# accept video or file payloads.
_CHAT_ADAPTER_INPUTS: dict[ModelProvider, dict[ContentType, frozenset[str] | None]] = {
    ModelProvider.OPENAI: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.AZURE_OPENAI: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.XAI: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.DEEPSEEK: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.MOONSHOT: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.ZHIPU: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.QWEN: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.BAICHUAN: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.MINIMAX: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.VOLCENGINE: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.SILICONFLOW: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.OLLAMA: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.CUSTOM: {ContentType.IMAGE: _IMAGE_MIMES},
    ModelProvider.ANTHROPIC: {
        ContentType.IMAGE: _ANTHROPIC_IMAGE_MIMES,
        ContentType.FILE: frozenset({"application/pdf"}),
    },
    ModelProvider.GOOGLE: {
        ContentType.IMAGE: _IMAGE_MIMES,
        ContentType.AUDIO: frozenset(
            {
                "audio/wav",
                "audio/mp3",
                "audio/mpeg",
                "audio/aac",
                "audio/ogg",
                "audio/flac",
                "audio/mp4",
            }
        ),
        ContentType.VIDEO: _GOOGLE_VIDEO_MIMES,
        ContentType.FILE: frozenset({"application/pdf"}),
    },
}


def is_openrouter_url(base_url: str | None) -> bool:
    """Match only the official OpenRouter HTTPS API host."""
    if not base_url:
        return False
    parsed = urlsplit(base_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "openrouter.ai"
        and parsed.path.rstrip("/") in {"/api/v1", "/v1"}
    )


def _is_openrouter(model_config: Model) -> bool:
    provider = str(
        getattr(model_config.provider, "value", model_config.provider)
    ).lower()
    return provider == "custom" and is_openrouter_url(model_config.base_url)


def normalize_mime_type(
    mime_type: str, modality: ContentType, model_config: Model
) -> str:
    """Normalize aliases only where the selected adapter wire format requires it."""
    mime = mime_type.split(";", 1)[0].strip().lower()
    if _is_openrouter(model_config):
        aliases = {
            ContentType.AUDIO: {"audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4"},
            ContentType.VIDEO: {"video/quicktime": "video/mov"},
        }
        return aliases.get(modality, {}).get(mime, mime)
    return mime


def get_effective_input_capabilities(model_config: Model) -> InputCapabilities:
    """Return declared modalities intersected with native adapter serialization.

    Chat models without an explicit ``input_modalities`` declaration are
    considered text-only. Legacy ``vision`` flags are intentionally ignored.
    MIME and byte limits are intersected with model declarations when supplied;
    unknown limits remain unknown.
    """
    if model_config.model_type != ModelType.CHAT:
        return InputCapabilities(frozenset(), {}, {})

    capabilities = model_config.capabilities or {}
    declared = capabilities.get("input_modalities")
    if not isinstance(declared, list):
        declared = [ContentType.TEXT.value]
    declared_set = {str(value) for value in declared}
    declared_set.add(ContentType.TEXT.value)

    provider = model_config.provider
    try:
        provider = ModelProvider(provider)
    except ValueError:
        provider = None
    adapter_inputs = dict(_CHAT_ADAPTER_INPUTS.get(provider, {})) if provider else {}
    if _is_openrouter(model_config):
        adapter_inputs.update(
            {
                ContentType.AUDIO: frozenset(
                    {
                        "audio/wav",
                        "audio/mp3",
                        "audio/mpeg",
                        "audio/aiff",
                        "audio/aac",
                        "audio/ogg",
                        "audio/flac",
                        "audio/mp4",
                        "audio/x-m4a",
                    }
                ),
                ContentType.VIDEO: frozenset(
                    {"video/mp4", "video/mpeg", "video/mov", "video/webm"}
                ),
                ContentType.FILE: frozenset({"application/pdf"}),
            }
        )

    modalities = {ContentType.TEXT}
    mime_types: dict[ContentType, frozenset[str] | None] = {}
    limits: dict[ContentType, InputModalityLimits] = {}
    declared_limits = capabilities.get("input_limits")
    if not isinstance(declared_limits, dict):
        declared_limits = {}

    for modality, accepted_mimes in adapter_inputs.items():
        if modality.value not in declared_set:
            continue
        limit = declared_limits.get(modality.value)
        if not isinstance(limit, dict):
            limit = {}
        declared_mimes = limit.get("mime_types")
        if isinstance(declared_mimes, list):
            declared_mimes_set = frozenset(
                normalize_mime_type(str(mime), modality, model_config)
                for mime in declared_mimes
            )
            accepted_mimes = (
                declared_mimes_set
                if accepted_mimes is None
                else accepted_mimes & declared_mimes_set
            )
        if accepted_mimes == frozenset():
            continue
        modalities.add(modality)
        mime_types[modality] = accepted_mimes
        max_bytes = limit.get("max_bytes")
        if max_bytes is not None and (
            not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or max_bytes <= 0
        ):
            raise ValueError(
                f"input_limits.{modality.value}.max_bytes must be a positive integer"
            )
        limits[modality] = InputModalityLimits(max_bytes)

    return InputCapabilities(frozenset(modalities), mime_types, limits)
