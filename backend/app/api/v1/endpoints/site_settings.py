from app.models import (
    SiteSetting,
    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
)
from app.schemas.site_setting import PublicSiteSettingsResponse
from app.schemas.response import Response, success
from fastapi import APIRouter

router = APIRouter()

THEME_MODE_VALUES = {"system", "light", "dark"}
THEME_BRANDING_DISPLAY_VALUES = {"full", "name_only", "icon_only", "hidden"}


def _normalize_enum(value: object, allowed_values: set[str], default: str) -> str:
    if isinstance(value, str) and value in allowed_values:
        return value
    return default


def _normalize_hex_color(value: object) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if len(stripped) not in {4, 7} or not stripped.startswith("#"):
        return ""
    hex_digits = stripped[1:]
    if all(char in "0123456789abcdefABCDEF" for char in hex_digits):
        return stripped
    return ""


def _normalize_kb_document_max_upload_size_mb(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB
    if value < KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB:
        return KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB
    if value > KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB:
        return KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB
    return value


@router.get("/public", response_model=Response[PublicSiteSettingsResponse])
async def get_public_settings():
    """Get public site settings (no authentication required)"""
    settings = await SiteSetting.get_all_by_category(public_only=True)
    return success(
        data=PublicSiteSettingsResponse(
            site_name=settings.get("site_name", "Clouisle"),
            site_description=settings.get("site_description", ""),
            site_url=settings.get("site_url", ""),
            site_icon=settings.get("site_icon", ""),
            auth_page_layout=settings.get("auth_page_layout", "centered"),
            theme_mode=_normalize_enum(
                settings.get("theme_mode"), THEME_MODE_VALUES, "system"
            ),
            theme_primary_color=_normalize_hex_color(
                settings.get("theme_primary_color")
            ),
            theme_primary_foreground_color=_normalize_hex_color(
                settings.get("theme_primary_foreground_color")
            ),
            theme_branding_display=_normalize_enum(
                settings.get("theme_branding_display"),
                THEME_BRANDING_DISPLAY_VALUES,
                "full",
            ),
            icp_record_number=settings.get("icp_record_number") or "",
            icp_record_url=settings.get("icp_record_url") or "",
            terms_enabled=bool(settings.get("terms_enabled")),
            terms_url=settings.get("terms_url") or "",
            terms_text=settings.get("terms_text") or "",
            privacy_enabled=bool(settings.get("privacy_enabled")),
            privacy_url=settings.get("privacy_url") or "",
            privacy_text=settings.get("privacy_text") or "",
            require_terms_acceptance_on_register=bool(
                settings.get("require_terms_acceptance_on_register")
            ),
            allow_registration=settings.get("allow_registration", True),
            require_approval=settings.get("require_approval", False),
            email_verification=settings.get("email_verification", True),
            enable_captcha=settings.get("enable_captcha", False),
            allow_account_deletion=settings.get("allow_account_deletion", True),
            sso_enabled=settings.get("sso_enabled", False),
            sso_allow_password_login=settings.get("sso_allow_password_login", True),
            kb_document_max_upload_size_mb=_normalize_kb_document_max_upload_size_mb(
                settings.get(
                    "kb_document_max_upload_size_mb",
                    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
                )
            ),
        )
    )
