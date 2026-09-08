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
_BABEL_CATALOG_MTIMES: dict[str, int | None] = {}
_MISSING_BABEL_KEYS_LOGGED: set[tuple[str, str]] = set()


def normalize_language(lang: str | None) -> str:
    """Normalize a language code to a supported locale."""
    normalized = str(lang or Language.EN.value).lower().split("-")[0]
    if normalized not in SUPPORTED_LANGUAGES:
        return Language.EN.value
    return normalized


def _load_babel_catalog(lang: str) -> dict[str, str] | None:
    normalized = normalize_language(lang)
    po_path = LOCALES_DIR / normalized / "LC_MESSAGES" / f"{BABEL_DOMAIN}.po"
    mtime_ns = po_path.stat().st_mtime_ns if po_path.exists() else None

    if (
        normalized in _BABEL_CATALOGS
        and _BABEL_CATALOG_MTIMES.get(normalized) == mtime_ns
    ):
        return _BABEL_CATALOGS[normalized]

    if not po_path.exists():
        _BABEL_CATALOGS[normalized] = None
        _BABEL_CATALOG_MTIMES[normalized] = None
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
    _BABEL_CATALOG_MTIMES[normalized] = mtime_ns
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
        "Missing Babel translation in locale '%s'; using legacy fallback",
        normalized,
    )


def get_language() -> str:
    """Get current language from context variable"""
    return current_language.get()


def set_language(lang: str) -> None:
    """Set current language in context variable"""
    current_language.set(normalize_language(lang))


_cached_default_language: str = Language.EN.value
_cached_default_language_version: int = 0


async def get_default_language() -> str:
    """Get default language from site settings.

    This is used for system messages when no specific user locale is available,
    such as team notifications, webhook-triggered workflows, etc.
    """
    global _cached_default_language, _cached_default_language_version
    from app.models.site_setting import SiteSetting

    read_version = _cached_default_language_version
    try:
        lang = await SiteSetting.get_value("default_language", "en")
        # Only update cache if no newer write has updated the cache version
        if _cached_default_language_version == read_version:
            _cached_default_language = normalize_language(str(lang))
    except Exception:
        pass
    return _cached_default_language


def get_default_language_sync() -> str:
    """Get cached default language from site settings synchronously."""
    return _cached_default_language


def set_default_language_cache(lang: str | None) -> None:
    """Update cached default language and advance cache version."""
    global _cached_default_language, _cached_default_language_version
    _cached_default_language_version += 1
    _cached_default_language = normalize_language(lang)


async def resolve_language(
    user_locale: str | None = None,
    default_override: str | None = None,
) -> str:
    """Resolve language according to: User > System (SiteSetting) > Default ('en').

    Args:
        user_locale: Explicit user locale (from user.locale or request/parameter).
        default_override: Optional fallback if system default is absent.

    Returns:
        Normalized language code ('en', 'zh', etc.).
    """
    if user_locale and str(user_locale).strip():
        return normalize_language(user_locale)
    system_default = await get_default_language()
    if system_default and str(system_default).strip():
        return normalize_language(system_default)
    return normalize_language(default_override or Language.EN.value)


def resolve_language_sync(
    user_locale: str | None = None,
    default_override: str | None = None,
) -> str:
    """Resolve language synchronously according to: User > System (Cached) > Default ('en')."""
    if user_locale and str(user_locale).strip():
        return normalize_language(user_locale)
    system_default = get_default_language_sync()
    if system_default and str(system_default).strip():
        return normalize_language(system_default)
    return normalize_language(default_override or Language.EN.value)


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
        # 成功
        ResponseCode.SUCCESS: "success",
        # 通用错误 (1000-1999)
        ResponseCode.UNKNOWN_ERROR: "unknown_error",
        ResponseCode.VALIDATION_ERROR: "validation_error",
        ResponseCode.BAD_REQUEST: "bad_request",
        ResponseCode.INTERNAL_ERROR: "internal_error",
        ResponseCode.FORBIDDEN: "forbidden",
        # 认证错误 (2000-2999)
        ResponseCode.UNAUTHORIZED: "unauthorized",
        ResponseCode.INVALID_TOKEN: "invalid_token",
        ResponseCode.TOKEN_EXPIRED: "token_expired",
        ResponseCode.INVALID_CREDENTIALS: "invalid_credentials",
        ResponseCode.INACTIVE_USER: "inactive_user",
        # 权限错误 (3000-3999)
        ResponseCode.PERMISSION_DENIED: "permission_denied",
        ResponseCode.INSUFFICIENT_PRIVILEGES: "insufficient_privileges",
        ResponseCode.NOT_TEAM_MEMBER: "not_team_member",
        ResponseCode.TEAM_ADMIN_REQUIRED: "team_admin_required",
        ResponseCode.TEAM_OWNER_REQUIRED: "team_owner_required",
        # 资源错误 (4000-4999)
        ResponseCode.NOT_FOUND: "not_found",
        ResponseCode.USER_NOT_FOUND: "user_not_found",
        ResponseCode.ROLE_NOT_FOUND: "role_not_found",
        ResponseCode.PERMISSION_NOT_FOUND: "permission_not_found",
        ResponseCode.TEAM_NOT_FOUND: "team_not_found",
        ResponseCode.TEAM_MEMBER_NOT_FOUND: "team_member_not_found",
        # 注册相关错误 (5000-5099)
        ResponseCode.REGISTRATION_DISABLED: "registration_disabled",
        ResponseCode.ALREADY_EXISTS: "already_exists",
        ResponseCode.USERNAME_EXISTS: "username_exists",
        ResponseCode.EMAIL_EXISTS: "email_exists",
        ResponseCode.EMAIL_NOT_VERIFIED: "email_not_verified",
        ResponseCode.VERIFICATION_CODE_INVALID: "verification_code_invalid",
        ResponseCode.VERIFICATION_CODE_EXPIRED: "verification_token_invalid",
        ResponseCode.EMAIL_SEND_FAILED: "smtp_not_configured",
        ResponseCode.EMAIL_SEND_TOO_FREQUENT: "email_send_too_frequent",
        # 资源重复错误 (5100-5199)
        ResponseCode.ROLE_NAME_EXISTS: "role_name_exists",
        ResponseCode.PERMISSION_CODE_EXISTS: "permission_code_exists",
        ResponseCode.TEAM_NAME_EXISTS: "team_name_exists",
        ResponseCode.ALREADY_TEAM_MEMBER: "already_team_member",
        ResponseCode.DUPLICATE_NAME: "duplicate_name",
        # 操作禁止错误 (5200-5299)
        ResponseCode.CANNOT_DELETE_SYSTEM_ROLE: "cannot_delete_system_role",
        ResponseCode.CANNOT_DELETE_SUPERUSER: "cannot_delete_superuser",
        ResponseCode.CANNOT_DELETE_SYSTEM_PERMISSION: "cannot_delete_system_permission",
        ResponseCode.CANNOT_UPDATE_SYSTEM_PERMISSION: "cannot_update_system_permission",
        ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE: "cannot_modify_system_role",
        ResponseCode.CANNOT_DELETE_DEFAULT_TEAM: "cannot_delete_default_team",
        ResponseCode.CANNOT_ADD_AS_OWNER: "cannot_add_as_owner",
        ResponseCode.CANNOT_CHANGE_OWNER_ROLE: "cannot_change_owner_role",
        ResponseCode.CANNOT_PROMOTE_TO_OWNER: "cannot_promote_to_owner",
        ResponseCode.CANNOT_REMOVE_OWNER: "cannot_remove_owner",
        ResponseCode.OWNER_CANNOT_LEAVE: "owner_cannot_leave",
        ResponseCode.ROLE_IN_USE: "role_in_use",
        ResponseCode.USER_ALREADY_ACTIVE: "user_already_active",
        ResponseCode.USER_ALREADY_INACTIVE: "user_already_inactive",
        ResponseCode.CANNOT_DEACTIVATE_SUPERUSER: "cannot_deactivate_superuser",
        # 登录安全错误 (5300-5399)
        ResponseCode.ACCOUNT_LOCKED: "account_locked",
        ResponseCode.TOO_MANY_LOGIN_ATTEMPTS: "account_locked_after_attempts",
        ResponseCode.CAPTCHA_REQUIRED: "captcha_required",
        ResponseCode.CAPTCHA_INVALID: "captcha_invalid",
        ResponseCode.PASSWORD_EXPIRED: "password_expired",
        ResponseCode.FORCE_PASSWORD_CHANGE_REQUIRED: "force_password_change_required",
        ResponseCode.PASSWORD_MIN_AGE_NOT_MET: "password_min_age_not_met",
        ResponseCode.PASSWORD_RECENTLY_USED: "password_recently_used",
        # TOTP 2FA errors (5310-5319)
        ResponseCode.TOTP_REQUIRED: "totp_required",
        ResponseCode.TOTP_INVALID: "totp_invalid",
        ResponseCode.TOTP_RATE_LIMITED: "totp_rate_limited",
        ResponseCode.TOTP_NOT_ENABLED: "totp_not_enabled",
        ResponseCode.TOTP_ALREADY_ENABLED: "totp_already_enabled",
        ResponseCode.TOTP_SETUP_EXPIRED: "totp_setup_expired",
        ResponseCode.TOTP_SETUP_REQUIRED: "totp_setup_required",
        # 速率限制错误 (5400-5499)
        ResponseCode.RATE_LIMITED: "rate_limited",
        # 知识库错误 (6000-6099)
        ResponseCode.KB_NOT_FOUND: "kb_not_found",
        ResponseCode.KB_NAME_EXISTS: "kb_name_exists",
        ResponseCode.DOCUMENT_NOT_FOUND: "document_not_found",
        ResponseCode.INVALID_DOCUMENT_TYPE: "invalid_document_type",
        ResponseCode.DOCUMENT_PROCESSING_FAILED: "document_processing_failed",
        ResponseCode.CHUNK_NOT_FOUND: "chunk_not_found",
        ResponseCode.DOCUMENT_PROCESSING: "document_processing",
        # 模型相关错误 (6100-6199)
        ResponseCode.MODEL_NOT_FOUND: "model_not_found",
        ResponseCode.TEAM_MODEL_NOT_FOUND: "team_model_not_found",
        ResponseCode.TEAM_MODEL_EXISTS: "team_model_exists",
        ResponseCode.MODEL_QUOTA_EXCEEDED: "model_quota_exceeded",
        ResponseCode.MODEL_NOT_AUTHORIZED: "model_not_authorized",
        ResponseCode.MODEL_VISION_NOT_SUPPORTED: "model_vision_not_supported",
        ResponseCode.MODEL_DISABLED: "model_disabled",
        # Agent 相关错误 (6200-6299)
        ResponseCode.AGENT_NOT_FOUND: "agent_not_found",
        ResponseCode.AGENT_ACCESS_DENIED: "agent_access_denied",
        ResponseCode.AGENT_NOT_PUBLISHED: "agent_not_published",
        ResponseCode.CONVERSATION_NOT_FOUND: "conversation_not_found",
        ResponseCode.MESSAGE_NOT_FOUND: "message_not_found",
        # SSO 相关错误 (6300-6399)
        ResponseCode.SSO_PROVIDER_NOT_FOUND: "sso_provider_not_found",
        ResponseCode.SSO_SESSION_EXPIRED: "sso_session_expired",
        ResponseCode.SSO_REGISTRATION_DISABLED: "sso_registration_disabled",
        ResponseCode.SSO_AUTHENTICATION_FAILED: "sso_authentication_failed",
        ResponseCode.SSO_INVALID_CONFIGURATION: "sso_invalid_configuration",
        ResponseCode.SSO_PROVIDER_NAME_EXISTS: "sso_provider_name_exists",
        ResponseCode.PASSWORD_LOGIN_DISABLED: "password_login_disabled",
    }

    try:
        response_code = ResponseCode(code)
        key = code_to_key.get(response_code, "unknown_error")
    except ValueError:
        key = "unknown_error"

    return t(key, lang)
