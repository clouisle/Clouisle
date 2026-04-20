from __future__ import annotations

import re

from app.core.i18n import has_translation, t


_TRANSLATION_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$", re.IGNORECASE)
_UNSAFE_ERROR_PATTERNS = (
    re.compile(r"\bTraceback\b", re.IGNORECASE),
    re.compile(r"\bFile \".+\", line \d+"),
    re.compile(r"\bException:\b"),
    re.compile(r"\bat .+:\d+:\d+\b"),
    re.compile(r"(/private/|/tmp/|[A-Z]:\\\\)"),
)


def is_safe_user_visible_error(message: str | None) -> bool:
    if not message:
        return False

    normalized = message.strip()
    if not normalized:
        return False

    if len(normalized) > 400:
        return False

    if "\n" in normalized:
        return False

    if _TRANSLATION_KEY_PATTERN.fullmatch(normalized):
        return False

    return not any(pattern.search(normalized) for pattern in _UNSAFE_ERROR_PATTERNS)



def resolve_user_visible_error(
    message: str | None,
    *,
    fallback_key: str = "tool_execution_failed",
) -> str:
    if not message:
        return t(fallback_key)

    normalized = message.strip()
    if not normalized:
        return t(fallback_key)

    if has_translation(normalized):
        return t(normalized)

    if is_safe_user_visible_error(normalized):
        return normalized

    return t(fallback_key)
