"""
Token counting utilities using tiktoken.

Provides accurate token counting for various model families.
"""

import logging
from functools import lru_cache

import tiktoken

logger = logging.getLogger(__name__)

# Mapping of model providers/families to tiktoken encodings
MODEL_ENCODING_MAP = {
    # OpenAI models
    "gpt-4": "cl100k_base",
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "text-embedding-ada-002": "cl100k_base",
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    # Default for unknown models
    "default": "cl100k_base",
}

# Provider-level defaults
PROVIDER_ENCODING_MAP = {
    "openai": "cl100k_base",
    "azure": "cl100k_base",
    "anthropic": "cl100k_base",  # Claude uses similar tokenization
    "google": "cl100k_base",  # Approximate
    "deepseek": "cl100k_base",  # DeepSeek uses similar tokenization
    "qwen": "cl100k_base",  # Qwen uses similar tokenization
    "default": "cl100k_base",
}


@lru_cache(maxsize=10)
def get_encoding(encoding_name: str) -> tiktoken.Encoding:
    """Get tiktoken encoding by name (cached)."""
    return tiktoken.get_encoding(encoding_name)


def get_encoding_for_model(model_id: str, provider: str | None = None) -> tiktoken.Encoding:
    """
    Get the appropriate tiktoken encoding for a model.

    Args:
        model_id: Model identifier (e.g., "gpt-4", "gpt-4o-mini")
        provider: Optional provider name for fallback

    Returns:
        tiktoken.Encoding: The appropriate encoding
    """
    # Try exact model match first
    model_lower = model_id.lower()
    for model_prefix, encoding_name in MODEL_ENCODING_MAP.items():
        if model_lower.startswith(model_prefix):
            return get_encoding(encoding_name)

    # Try provider-level match
    if provider:
        provider_lower = provider.lower()
        encoding_name = PROVIDER_ENCODING_MAP.get(provider_lower, PROVIDER_ENCODING_MAP["default"])
        return get_encoding(encoding_name)

    # Fall back to default
    return get_encoding(MODEL_ENCODING_MAP["default"])


def count_tokens(text: str, model_id: str = "gpt-4", provider: str | None = None) -> int:
    """
    Count tokens in a text string.

    Args:
        text: Text to count tokens for
        model_id: Model identifier for tokenizer selection
        provider: Optional provider name

    Returns:
        int: Number of tokens
    """
    if not text:
        return 0

    try:
        encoding = get_encoding_for_model(model_id, provider)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed, using fallback: {e}")
        # Fallback to character-based estimation
        return max(len(text) // 4, 1)


def count_message_tokens(
    messages: list[dict],
    model_id: str = "gpt-4",
    provider: str | None = None,
) -> int:
    """
    Count tokens in a list of chat messages.

    Accounts for message overhead (role tokens, separators, etc.)

    Args:
        messages: List of message dicts with 'role' and 'content'
        model_id: Model identifier
        provider: Optional provider name

    Returns:
        int: Total token count
    """
    try:
        encoding = get_encoding_for_model(model_id, provider)

        # Token overhead per message (varies by model, using GPT-4 defaults)
        tokens_per_message = 3  # <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = 1

        total_tokens = 0
        for message in messages:
            total_tokens += tokens_per_message
            for key, value in message.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    total_tokens += len(encoding.encode(value))
                elif isinstance(value, list):
                    # Handle content arrays (for vision)
                    for item in value:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                total_tokens += len(encoding.encode(item.get("text", "")))
                            # Image tokens are handled separately by the model
                if key == "name":
                    total_tokens += tokens_per_name

        # Every reply is primed with <|start|>assistant<|message|>
        total_tokens += 3

        return total_tokens
    except Exception as e:
        logger.warning(f"Message token counting failed, using fallback: {e}")
        # Fallback: estimate from total content length
        total_content = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_content += content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        total_content += item.get("text", "")
        return max(len(total_content) // 4, 1)


def estimate_tokens_from_chars(char_count: int) -> int:
    """
    Quick estimation of tokens from character count.

    This is a fallback when tiktoken is not available.
    Rule of thumb: ~4 characters per token for English,
    ~2-3 for Chinese/Japanese.

    Args:
        char_count: Number of characters

    Returns:
        int: Estimated token count
    """
    return max(char_count // 4, 1)
