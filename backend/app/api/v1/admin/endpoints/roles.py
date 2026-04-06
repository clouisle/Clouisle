from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tortoise.expressions import Q

from app.api import deps
from app.models.user import Role, Permission, User
from app.schemas.user import Role as RoleSchema, RoleCreate
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)

router = APIRouter()


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermissionsUpdate(BaseModel):
    permissions: List[str]  # List of permission codes


@router.get("", response_model=Response[PageData[RoleSchema]])
async def read_roles(
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = Query(
        None, description="Search by role name or description"
    ),
    current_user: User = Depends(deps.PermissionChecker("admin:role:read")),
) -> Any:
    """
    Retrieve roles.
    """
    query = Role.all()

    if search:
        query = query.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    total = await query.count()
    skip = (page - 1) * page_size
    roles = await query.offset(skip).limit(page_size).prefetch_related("permissions")

    return success(
        data={
            "items": roles,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[RoleSchema])
async def create_role(
    *,
    role_in: RoleCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:role:create")),
) -> Any:
    """
    Create new role.
    """
    # Check if role name already exists
    existing = await Role.filter(name=role_in.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ROLE_NAME_EXISTS,
            msg_key="role_with_name_exists",
        )

    role = await Role.create(
        name=role_in.name,
        description=role_in.description,
        is_system_role=False,
    )

    # Add permissions
    if role_in.permissions:
        for perm_code in role_in.permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                await role.permissions.add(perm)

    # Reload with permissions
    role = await Role.get(id=role.id).prefetch_related("permissions")
    return success(data=role, msg_key="role_created")


@router.get("/{role_id}", response_model=Response[RoleSchema])
async def read_role(
    role_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:role:read")),
) -> Any:
    """
    Get role by ID.
    """
    role = await Role.filter(id=role_id).prefetch_related("permissions").first()
    if not role:
        raise BusinessError(
            code=ResponseCode.ROLE_NOT_FOUND,
            msg_key="role_not_found",
            status_code=404,
        )
    return success(data=role)


@router.put("/{role_id}", response_model=Response[RoleSchema])
async def update_role(
    *,
    role_id: UUID,
    role_in: RoleUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:role:update")),
) -> Any:
    """
    Update a role.
    """
    role = await Role.filter(id=role_id).first()
    if not role:
        raise BusinessError(
            code=ResponseCode.ROLE_NOT_FOUND,
            msg_key="role_not_found",
            status_code=404,
        )

    if role.is_system_role:
        raise BusinessError(
            code=ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE,
            msg_key="cannot_modify_system_role",
        )

    # Check if name is being changed and if it conflicts
    if role_in.name and role_in.name != role.name:
        existing = await Role.filter(name=role_in.name).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.ROLE_NAME_EXISTS,
                msg_key="role_with_name_exists",
            )
        role.name = role_in.name

    if role_in.description is not None:
        role.description = role_in.description

    await role.save()

    role = await Role.get(id=role_id).prefetch_related("permissions")
    return success(data=role, msg_key="role_updated")


@router.put("/{role_id}/permissions", response_model=Response[RoleSchema])
async def update_role_permissions(
    *,
    role_id: UUID,
    permissions_in: RolePermissionsUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:role:update")),
) -> Any:
    """
    Update role permissions (replace all).
    """
    role = await Role.filter(id=role_id).first()
    if not role:
        raise BusinessError(
            code=ResponseCode.ROLE_NOT_FOUND,
            msg_key="role_not_found",
            status_code=404,
        )

    if role.is_system_role:
        raise BusinessError(
            code=ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE,
            msg_key="cannot_modify_system_role_permissions",
        )

    # Clear existing permissions
    await role.permissions.clear()

    # Add new permissions
    for perm_code in permissions_in.permissions:
        perm = await Permission.filter(code=perm_code).first()
        if not perm:
            raise BusinessError(
                code=ResponseCode.PERMISSION_NOT_FOUND,
                msg_key="permission_code_not_found",
                perm_code=perm_code,
            )
        await role.permissions.add(perm)

    role = await Role.get(id=role_id).prefetch_related("permissions")
    return success(data=role, msg_key="role_permissions_updated")


@router.delete("/{role_id}", response_model=Response[RoleSchema])
async def delete_role(
    role_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:role:delete")),
) -> Any:
    """
    Delete a role.
    """
    role = await Role.filter(id=role_id).prefetch_related("permissions").first()
    if not role:
        raise BusinessError(
            code=ResponseCode.ROLE_NOT_FOUND,
            msg_key="role_not_found",
            status_code=404,
        )

    if role.is_system_role:
        raise BusinessError(
            code=ResponseCode.CANNOT_DELETE_SYSTEM_ROLE,
            msg_key="cannot_delete_system_role",
        )

    # Check if role is assigned to any users
    users_with_role = await User.filter(roles=role).count()
    if users_with_role > 0:
        raise BusinessError(
            code=ResponseCode.ROLE_IN_USE,
            msg_key="role_in_use",
            count=users_with_role,
        )

    await role.delete()
    return success(data=role, msg_key="role_deleted")
