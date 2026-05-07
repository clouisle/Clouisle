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
