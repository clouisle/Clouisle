"""
Shared helpers for media-generation adapters.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from app.llm.errors import InvalidRequestError
from app.llm.types.base import MediaContent

_ASPECT_RATIO_VALUES: dict[str, float] = {
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "1:1": 1.0,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
}


def append_prompt_directives(prompt: str, *directives: str | None) -> str:
    """Append provider-agnostic hints to the base prompt."""
    extras = [
        directive.strip() for directive in directives if directive and directive.strip()
    ]
    if not extras:
        return prompt
    return f"{prompt}\n\n" + "\n".join(extras)


def closest_aspect_ratio(width: int | None, height: int | None) -> str:
    """Return the closest supported aspect ratio for a size pair."""
    if not width or not height or width <= 0 or height <= 0:
        return "1:1"

    target = width / height
    return min(
        _ASPECT_RATIO_VALUES,
        key=lambda ratio: abs(_ASPECT_RATIO_VALUES[ratio] - target),
    )


def infer_format(value: str | None, default: str) -> str:
    """Infer a media format from a URL/path."""
    if not value:
        return default

    suffix = Path(value).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    return default


def media_content_to_data_uri(
    content: MediaContent,
    *,
    default_mime: str,
    provider: str,
    model: str,
    field_name: str,
) -> str:
    """Return a remote URL or inline data URI for providers that support both."""
    if content.url:
        return content.url

    mime_type = default_mime

    if content.base64:
        data = content.base64
        if data.startswith("data:"):
            return data
        return f"data:{mime_type};base64,{data}"

    if content.file_path:
        guessed_mime, _ = mimetypes.guess_type(content.file_path)
        if guessed_mime:
            mime_type = guessed_mime
        file_bytes = Path(content.file_path).read_bytes()
        encoded = base64.b64encode(file_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    raise InvalidRequestError(
        message=f"{field_name} must include url, base64, or file_path",
        field=field_name,
        provider=provider,
        model=model,
    )


def require_remote_url(
    content: MediaContent,
    *,
    provider: str,
    model: str,
    field_name: str,
) -> str:
    """Luma currently expects a remote asset URL for image references."""
    if content.url:
        return content.url

    raise InvalidRequestError(
        message=f"{field_name} must provide a remote URL for provider {provider}",
        field=field_name,
        provider=provider,
        model=model,
    )
