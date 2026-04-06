"""
Chat 模型工厂 - 使用 LangChain
"""

import logging
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from app.models.model import Model, ModelProvider


class ModelConfig(Protocol):
    """模型配置协议，用于类型检查"""

    provider: str | ModelProvider
    model_id: str
    api_key: str | None
    base_url: str | None
    default_params: dict[str, Any] | None
    config: dict[str, Any] | None


logger = logging.getLogger(__name__)


def create_chat_model(model_config: Model | ModelConfig) -> BaseChatModel:
    """
    根据模型配置创建 LangChain Chat 模型实例

    Args:
        model_config: 数据库中的模型配置或临时配置对象

    Returns:
        BaseChatModel: LangChain Chat 模型实例
    """
    provider = model_config.provider
    model_id = model_config.model_id
    api_key = SecretStr(model_config.api_key) if model_config.api_key else None
    base_url = model_config.base_url

    # 从 default_params 获取默认参数
    params = model_config.default_params or {}
    temperature = params.get("temperature")
    top_p = params.get("top_p")

    # 从 config 获取额外配置
    config = model_config.config or {}
    # max_output_tokens: 优先 ORM 独立字段 > default_params > config
    max_output = getattr(model_config, "max_output_tokens", None)
    if max_output is None:
        max_output = params.get("max_tokens")
    if max_output is None:
        max_output = config.get("max_tokens")
    if max_output is not None:
        max_output = int(max_output)
    timeout = config.get("timeout", 60)

    if provider == ModelProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        if not api_key:
            raise ValueError("Anthropic requires api_key")

        thinking = None
        if config and config.get("thinking") is not None:
            thinking = config.get("thinking")
        elif params.get("thinking") is not None:
            thinking = params.get("thinking")

        anthropic_kwargs: dict[str, Any] = {
            "model": model_id,
            "anthropic_api_key": api_key,
            "anthropic_api_url": base_url,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_output or 4096,  # Anthropic 需要指定 max_tokens
            "default_request_timeout": timeout,
        }
        if thinking is not None:
            anthropic_kwargs["thinking"] = thinking

        return ChatAnthropic(**anthropic_kwargs)  # type: ignore[call-arg]

    elif provider == ModelProvider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not api_key:
            raise ValueError("Google requires api_key")

        google_kwargs: dict[str, Any] = {
            "model": model_id,
            "google_api_key": api_key,
            "max_output_tokens": max_output,
            "timeout": timeout,
        }
        if base_url:
            google_kwargs["client_options"] = {"api_endpoint": base_url}
        if temperature is not None:
            google_kwargs["temperature"] = temperature
        if top_p is not None:
            google_kwargs["top_p"] = top_p

        return ChatGoogleGenerativeAI(**google_kwargs)

    elif provider == ModelProvider.XAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.x.ai/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.AZURE_OPENAI:
        from langchain_openai import AzureChatOpenAI

        azure_config = config.get("azure", {})
        return AzureChatOpenAI(
            azure_deployment=model_id,
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=azure_config.get("api_version", "2024-02-01"),
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.DEEPSEEK:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.MOONSHOT:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.moonshot.cn/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.ZHIPU:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://open.bigmodel.cn/api/paas/v4",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.QWEN:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.BAICHUAN:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.baichuan-ai.com/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.MINIMAX:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url or "https://api.minimax.chat/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.OLLAMA:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key or SecretStr("ollama"),  # Ollama 不需要 API key
            base_url=base_url or "http://localhost:11434/v1",
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    elif provider == ModelProvider.CUSTOM:
        # 通用 OpenAI 兼容接口
        from langchain_openai import ChatOpenAI

        if not base_url:
            raise ValueError("Custom provider requires base_url")

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            top_p=top_p,
            max_completion_tokens=max_output,
            timeout=timeout,
        )

    else:
        raise ValueError(f"Unsupported provider for chat: {provider}")
