from typing import Any, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
from app.core.timezone import now_utc
from app.models.user import User
from app.models.api_key import APIKey
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyResponse,
    APIKeyCreateResponse,
    APIKeyStats,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)

router = APIRouter()


@router.get("/", response_model=Response[PageData[APIKeyResponse]])
async def list_api_keys(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = Query(
        None, description="Filter by status: active, inactive, expired"
    ),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    search: Optional[str] = Query(None, description="Search by name"),
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    List all API keys with optional filters.
    Admin can see all keys, regular users can only see their own.
    """
    skip = (page - 1) * page_size
    now = now_utc()

    # Build query - admin sees all, regular user sees only their own
    if current_user.is_superuser:
        query = APIKey.all()
    else:
        query = APIKey.filter(user_id=current_user.id)

    # User filter (only for admin)
    if user_id and current_user.is_superuser:
        query = query.filter(user_id=user_id)

    # Status filter
    if status == "active":
        query = query.filter(
            is_active=True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
    elif status == "inactive":
        query = query.filter(is_active=False)
    elif status == "expired":
        query = query.filter(expires_at__lt=now)

    # Search filter
    if search:
        query = query.filter(name__icontains=search)

    total = await query.count()
    api_keys = await query.offset(skip).limit(page_size).order_by("-created_at").prefetch_related("user")
    
    return success(
        data={
            "items": api_keys,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/stats", response_model=Response[APIKeyStats])
async def get_api_key_stats(
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    Get API key statistics.
    """
    now = now_utc()
    
    # Admin sees all, regular user sees only their own
    if current_user.is_superuser:
        base_query = APIKey.all()
    else:
        base_query = APIKey.filter(user_id=current_user.id)

    total = await base_query.count()
    active = await base_query.filter(
        is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).count()
    inactive = await base_query.filter(is_active=False).count()
    expired = await base_query.filter(expires_at__lt=now).count()

    return success(
        data={
            "total": total,
            "active": active,
            "inactive": inactive,
            "expired": expired,
        }
    )


@router.post("/", response_model=Response[APIKeyCreateResponse])
async def create_api_key(
    *,
    data: APIKeyCreate,
    current_user: User = Depends(deps.PermissionChecker("apikey:create")),
) -> Any:
    """
    Create a new API key.
    The full key is only returned once at creation time.
    """
    # Generate API key
    full_key, key_prefix, key_hash = APIKey.generate_key()

    # Create API key record
    api_key = await APIKey.create(
        name=data.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        user_id=current_user.id,
        scopes=data.scopes,
        rate_limit=data.rate_limit,
        expires_at=data.expires_at,
    )

    # Return response with full key
    response_data = {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "user_id": api_key.user_id,
        "key": full_key,  # Only returned once
        "scopes": api_key.scopes,
        "rate_limit": api_key.rate_limit,
        "is_active": api_key.is_active,
        "expires_at": api_key.expires_at,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "updated_at": api_key.updated_at,
    }

    return success(data=response_data, msg_key="api_key_created")


@router.get("/{api_key_id}", response_model=Response[APIKeyResponse])
async def get_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    Get a specific API key by ID.
    """
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("user").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission - admin can see all, user can only see their own
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    return success(data=api_key)


@router.put("/{api_key_id}", response_model=Response[APIKeyResponse])
async def update_api_key(
    *,
    api_key_id: UUID,
    data: APIKeyUpdate,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Update an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    await api_key.update_from_dict(update_data)
    await api_key.save()

    return success(data=api_key, msg_key="api_key_updated")


@router.delete("/{api_key_id}", response_model=Response[APIKeyResponse])
async def delete_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:delete")),
) -> Any:
    """
    Delete an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    # Store for response
    api_key_data = APIKeyResponse.model_validate(api_key)
    
    # Delete
    await api_key.delete()

    return success(data=api_key_data, msg_key="api_key_deleted")


@router.post("/{api_key_id}/activate", response_model=Response[APIKeyResponse])
async def activate_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Activate an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    if api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_active",
        )

    api_key.is_active = True
    await api_key.save()

    return success(data=api_key, msg_key="api_key_activated")


@router.post("/{api_key_id}/deactivate", response_model=Response[APIKeyResponse])
async def deactivate_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Deactivate an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    if not api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_inactive",
        )

    api_key.is_active = False
    await api_key.save()

    return success(data=api_key, msg_key="api_key_deactivated")
