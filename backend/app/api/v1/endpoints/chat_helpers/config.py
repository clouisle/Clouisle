"""
Configuration utilities for chat.
"""

from app.core.config import settings
from app.models.agent import Agent


def _has_tool_runtime(agent: Agent) -> bool:
    return bool(
        agent.tools_config
        or agent.enable_memory
        or agent.enable_image_generation
        or agent.enable_video_generation
    )


def get_language_instruction(user_locale: str | None = None) -> str:
    """Get language instruction based on user locale."""
    if not user_locale:
        return ""

    language_map = {
        "zh": "请用中文回复。",
        "en": "Please reply in English.",
        "ja": "日本語で返信してください。",
        "ko": "한국어로 답변해 주세요.",
        "es": "Por favor responde en español.",
        "fr": "Veuillez répondre en français.",
        "de": "Bitte antworten Sie auf Deutsch.",
        "it": "Si prega di rispondere in italiano.",
        "pt": "Por favor, responda em português.",
        "ru": "Пожалуйста, ответьте на русском языке.",
    }

    return language_map.get(user_locale, "")


def build_system_prompt_with_language(
    system_prompt: str, user_locale: str | None = None
) -> str:
    """Build system prompt with language instruction."""
    language_instruction = get_language_instruction(user_locale)
    if language_instruction:
        return f"{system_prompt}\n\n{language_instruction}"
    return system_prompt


def get_streaming_config(agent: Agent) -> dict:
    """Get streaming configuration from agent or use defaults."""
    config = agent.streaming_config or {}

    global_timeout_default = (
        settings.STREAM_GLOBAL_TIMEOUT_WITH_TOOLS
        if _has_tool_runtime(agent)
        else settings.STREAM_GLOBAL_TIMEOUT
    )

    return {
        "global_timeout": config.get("global_timeout", global_timeout_default),
        "heartbeat_interval": config.get(
            "heartbeat_interval", settings.STREAM_HEARTBEAT_INTERVAL
        ),
        "idle_timeout": config.get("idle_timeout", settings.STREAM_IDLE_TIMEOUT),
        "tool_timeouts": {
            "http": config.get("tool_timeouts", {}).get(
                "http", settings.STREAM_TOOL_TIMEOUT_HTTP
            ),
            "code": config.get("tool_timeouts", {}).get(
                "code", settings.STREAM_TOOL_TIMEOUT_CODE
            ),
            "mcp": config.get("tool_timeouts", {}).get(
                "mcp", settings.STREAM_TOOL_TIMEOUT_MCP
            ),
            "download": config.get("tool_timeouts", {}).get(
                "download", settings.STREAM_TOOL_TIMEOUT_DOWNLOAD
            ),
        },
    }
