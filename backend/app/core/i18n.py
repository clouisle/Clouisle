"""
Internationalization (i18n) module for multi-language support.
Currently supports: English (en), Chinese (zh)
"""

import logging
from contextvars import ContextVar
from enum import Enum
from pathlib import Path
from typing import Optional

from babel.messages import pofile

from app.core.i18n_legacy import TRANSLATIONS

logger = logging.getLogger(__name__)

# Context variable to store current language per request
current_language: ContextVar[str] = ContextVar("current_language", default="en")


class Language(str, Enum):
    """Supported languages"""

    EN = "en"
    ZH = "zh"


SUPPORTED_LANGUAGES = {lang.value for lang in Language}
LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
BABEL_DOMAIN = "messages"
_BABEL_CATALOGS: dict[str, dict[str, str] | None] = {}
_MISSING_BABEL_KEYS_LOGGED: set[tuple[str, str]] = set()


def normalize_language(lang: str | None) -> str:
    """Normalize a language code to a supported locale."""
    normalized = str(lang or Language.EN.value).lower().split("-")[0]
    if normalized not in SUPPORTED_LANGUAGES:
        return Language.EN.value
    return normalized


def _load_babel_catalog(lang: str) -> dict[str, str] | None:
    normalized = normalize_language(lang)
    if normalized in _BABEL_CATALOGS:
        return _BABEL_CATALOGS[normalized]

    po_path = LOCALES_DIR / normalized / "LC_MESSAGES" / f"{BABEL_DOMAIN}.po"
    if not po_path.exists():
        _BABEL_CATALOGS[normalized] = None
        return None

    with po_path.open("r", encoding="utf-8") as file_obj:
        catalog = pofile.read_po(file_obj)

    messages: dict[str, str] = {}
    for key, message in catalog._messages.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(message.string, str) and message.string:
            messages[key] = message.string

    _BABEL_CATALOGS[normalized] = messages
    return messages


def _get_babel_message(key: str, lang: str) -> str | None:
    messages = _load_babel_catalog(lang)
    if not messages:
        return None
    return messages.get(key)


def _log_missing_babel_key(lang: str, key: str) -> None:
    normalized = normalize_language(lang)
    marker = (normalized, key)
    if marker in _MISSING_BABEL_KEYS_LOGGED:
        return
    _MISSING_BABEL_KEYS_LOGGED.add(marker)
    logger.warning(
        "Missing Babel translation for key '%s' in locale '%s'; using legacy fallback",
        key,
        normalized,
    )


def get_language() -> str:
    """Get current language from context variable"""
    return current_language.get()


def set_language(lang: str) -> None:
    """Set current language in context variable"""
    current_language.set(normalize_language(lang))


async def get_default_language() -> str:
    """Get default language from site settings.

    This is used for system messages when no specific user locale is available,
    such as team notifications, webhook-triggered workflows, etc.
    """
    from app.models.site_setting import SiteSetting

    lang = await SiteSetting.get_value("default_language", "en")
    return normalize_language(str(lang))


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """
    Translate a message key to the current language.

    Args:
        key: Message key to translate
        lang: Optional language override (defaults to current context language)
        **kwargs: Format arguments for the message

    Returns:
        Translated message string
    """
    if lang is None:
        lang = get_language()

    normalized_lang = normalize_language(lang)

    message = _get_babel_message(key, normalized_lang)
    if message is None and normalized_lang != Language.EN.value:
        message = _get_babel_message(key, Language.EN.value)

    if message is None:
        _log_missing_babel_key(normalized_lang, key)
        translations = TRANSLATIONS.get(key, {})
        message = translations.get(normalized_lang) or translations.get(
            Language.EN.value, key
        )

    # Apply format arguments
    if kwargs:
        try:
            message = message.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return message


def has_translation(key: str, lang: Optional[str] = None) -> bool:
    """Return whether a translation key exists in Babel or legacy catalogs."""
    if not key:
        return False

    if lang is None:
        lang = get_language()

    normalized_lang = normalize_language(lang)

    if _get_babel_message(key, normalized_lang) is not None:
        return True

    if normalized_lang != Language.EN.value:
        if _get_babel_message(key, Language.EN.value) is not None:
            return True

    translations = TRANSLATIONS.get(key, {})
    return bool(
        translations.get(normalized_lang) or translations.get(Language.EN.value)
    )


def get_code_message(code: int, lang: Optional[str] = None) -> str:
    """
    Get translated message for a ResponseCode.
    Maps ResponseCode values to translation keys.
    """
    from app.schemas.response import ResponseCode

    # Map ResponseCode to translation key
    code_to_key = {
        ResponseCode.SUCCESS: "success",
        ResponseCode.UNKNOWN_ERROR: "unknown_error",
        ResponseCode.VALIDATION_ERROR: "validation_error",
        ResponseCode.UNAUTHORIZED: "unauthorized",
        ResponseCode.INVALID_TOKEN: "invalid_token",
        ResponseCode.TOKEN_EXPIRED: "token_expired",
        ResponseCode.INVALID_CREDENTIALS: "invalid_credentials",
        ResponseCode.INACTIVE_USER: "inactive_user",
        ResponseCode.PERMISSION_DENIED: "permission_denied",
        ResponseCode.INSUFFICIENT_PRIVILEGES: "insufficient_privileges",
        ResponseCode.NOT_FOUND: "not_found",
        ResponseCode.USER_NOT_FOUND: "user_not_found",
        ResponseCode.ROLE_NOT_FOUND: "role_not_found",
        ResponseCode.PERMISSION_NOT_FOUND: "permission_not_found",
        ResponseCode.REGISTRATION_DISABLED: "registration_disabled",
        ResponseCode.ALREADY_EXISTS: "already_exists",
        ResponseCode.USERNAME_EXISTS: "username_exists",
        ResponseCode.EMAIL_EXISTS: "email_exists",
        ResponseCode.EMAIL_NOT_VERIFIED: "email_not_verified",
        ResponseCode.VERIFICATION_CODE_INVALID: "verification_code_invalid",
        ResponseCode.VERIFICATION_CODE_EXPIRED: "verification_token_invalid",
        ResponseCode.EMAIL_SEND_FAILED: "smtp_not_configured",
        ResponseCode.EMAIL_SEND_TOO_FREQUENT: "email_send_too_frequent",
        ResponseCode.ROLE_NAME_EXISTS: "role_name_exists",
        ResponseCode.PERMISSION_CODE_EXISTS: "permission_code_exists",
        ResponseCode.CANNOT_DELETE_SYSTEM_ROLE: "cannot_delete_system_role",
        ResponseCode.CANNOT_DELETE_SUPERUSER: "cannot_delete_superuser",
        ResponseCode.CANNOT_DELETE_SYSTEM_PERMISSION: "cannot_delete_system_permission",
        ResponseCode.CANNOT_UPDATE_SYSTEM_PERMISSION: "cannot_update_system_permission",
        ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE: "cannot_modify_system_role",
        ResponseCode.ROLE_IN_USE: "role_in_use",
        ResponseCode.ACCOUNT_LOCKED: "account_locked",
        ResponseCode.TOO_MANY_LOGIN_ATTEMPTS: "account_locked_after_attempts",
        ResponseCode.CAPTCHA_REQUIRED: "captcha_required",
        ResponseCode.CAPTCHA_INVALID: "captcha_invalid",
    }

    try:
        response_code = ResponseCode(code)
        key = code_to_key.get(response_code, "unknown_error")
    except ValueError:
        key = "unknown_error"

    return t(key, lang)
