from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
from app.models.user import Permission, User
from app.schemas.user import Permission as PermissionSchema, PermissionCreate
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)

router = APIRouter()


@router.get("", response_model=Response[PageData[PermissionSchema]])
async def read_permissions(
    page: int = 1,
    page_size: int = 50,
    scope: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search by permission code or description"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retrieve permissions.
    """
    query = Permission.all()
    if scope:
        query = query.filter(scope=scope)
    if search:
        query = query.filter(Q(code__icontains=search) | Q(description__icontains=search))

    total = await query.count()
    skip = (page - 1) * page_size
    permissions = await query.offset(skip).limit(page_size)

    return success(
        data={
            "items": permissions,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[PermissionSchema])
async def create_permission(
    *,
    permission_in: PermissionCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:permission:create")),
) -> Any:
    """
    Create new custom permission (non-system).
    """
    # Check if permission code already exists
    existing = await Permission.filter(code=permission_in.code).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.PERMISSION_CODE_EXISTS,
            msg_key="permission_with_code_exists",
        )

    # Custom permissions are created with is_system=False
    permission = await Permission.create(
        scope=permission_in.scope,
        code=permission_in.code,
        description=permission_in.description,
        is_system=False,
    )
    return success(data=permission, msg_key="permission_created")


@router.get("/{permission_id}", response_model=Response[PermissionSchema])
async def read_permission(
    permission_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get permission by ID.
    """
    permission = await Permission.filter(id=permission_id).first()
    if not permission:
        raise BusinessError(
            code=ResponseCode.PERMISSION_NOT_FOUND,
            msg_key="permission_not_found",
            status_code=404,
        )
    return success(data=permission)


@router.put("/{permission_id}", response_model=Response[PermissionSchema])
async def update_permission(
    *,
    permission_id: UUID,
    permission_in: PermissionCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:permission:update")),
) -> Any:
    """
    Update a permission (only custom permissions can be updated).
    """
    permission = await Permission.filter(id=permission_id).first()
    if not permission:
        raise BusinessError(
            code=ResponseCode.PERMISSION_NOT_FOUND,
            msg_key="permission_not_found",
            status_code=404,
        )

    # Prevent updating system permissions
    if permission.is_system:
        raise BusinessError(
            code=ResponseCode.CANNOT_UPDATE_SYSTEM_PERMISSION,
            msg_key="cannot_update_system_permission",
        )

    # Check if code is being changed and if it conflicts
    if permission_in.code != permission.code:
        existing = await Permission.filter(code=permission_in.code).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.PERMISSION_CODE_EXISTS,
                msg_key="permission_with_code_exists",
            )

    permission.scope = permission_in.scope
    permission.code = permission_in.code
    permission.description = permission_in.description  # type: ignore[assignment]
    await permission.save()

    return success(data=permission, msg_key="permission_updated")


@router.delete("/{permission_id}", response_model=Response[PermissionSchema])
async def delete_permission(
    permission_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:permission:delete")),
) -> Any:
    """
    Delete a permission (only custom permissions can be deleted).
    """
    permission = await Permission.filter(id=permission_id).first()
    if not permission:
        raise BusinessError(
            code=ResponseCode.PERMISSION_NOT_FOUND,
            msg_key="permission_not_found",
            status_code=404,
        )

    # Prevent deleting system permissions
    if permission.is_system:
        raise BusinessError(
            code=ResponseCode.CANNOT_DELETE_SYSTEM_PERMISSION,
            msg_key="cannot_delete_system_permission",
        )

    await permission.delete()
    return success(data=permission, msg_key="permission_deleted")
