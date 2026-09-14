"""
Workflow version control API endpoints.

Provides REST API for:
- Version history management
- Version comparison and diff
- Rollback operations
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api import deps
from app.api.workflow_access import check_workflow_access
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.services.workflow.errors import translate_public_workflow_error
from app.services.workflow.versioning import (
    get_version_manager,
    VersionStatus,
)


async def check_version_workflow_access(
    workflow_id: str,
    version_id: str,
    current_user: User,
    require_write: bool = False,
    required_permission: str | None = None,
) -> None:
    workflow = await check_workflow_access(
        UUID(workflow_id),
        current_user,
        require_write=require_write or required_permission is not None,
    )
    if required_permission:
        await deps.check_scoped_permission(
            current_user, required_permission, "team", workflow.team.id
        )
    version = await get_version_manager().get_version(version_id)
    if not version:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_version_not_found",
            status_code=404,
        )
    if version.workflow_id != str(workflow.id):
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_version_not_found",
            status_code=404,
        )


router = APIRouter(prefix="/workflow-versions", tags=["workflow-versions"])


# Request/Response Models


class CreateVersionRequest(BaseModel):
    """Request to create a new version."""

    workflow_id: str
    nodes: list[dict]
    edges: list[dict]
    config: dict = Field(default_factory=dict)
    description: str | None = None


class CreateVersionResponse(BaseModel):
    """Response for version creation."""

    version_id: str
    version_number: int
    status: str
    created_at: str


class VersionListResponse(BaseModel):
    """Response for version list."""

    versions: list[dict]
    total: int


class VersionDiffResponse(BaseModel):
    """Response for version diff."""

    from_version: str
    to_version: str
    diff: dict


class RollbackRequest(BaseModel):
    """Request to rollback to a version."""

    version_id: str
    create_backup: bool = True


class RollbackResponse(BaseModel):
    """Response for rollback."""

    success: bool
    new_version_id: str | None = None
    backup_version_id: str | None = None


class ForkRequest(BaseModel):
    """Request to fork a workflow."""

    version_id: str
    new_workflow_id: str
    new_name: str | None = None


class ForkResponse(BaseModel):
    """Response for fork."""

    success: bool
    new_version_id: str


# Version Endpoints


@router.post("", response_model=CreateVersionResponse)
async def create_version(
    request: CreateVersionRequest,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Create a new workflow version."""
    manager = get_version_manager()
    await check_workflow_access(
        UUID(request.workflow_id), current_user, require_write=True
    )

    version = await manager.create_version(
        workflow_id=UUID(request.workflow_id),
        definition={
            "nodes": request.nodes,
            "edges": request.edges,
            **request.config,
        },
        user_id=current_user.id,
        description=request.description or "",
    )

    return CreateVersionResponse(
        version_id=version.version_id,
        version_number=version.version_number,
        status=version.status.value,
        created_at=version.created_at.isoformat(),
    )


@router.get("/{workflow_id}/history", response_model=VersionListResponse)
async def get_version_history(
    workflow_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: VersionStatus | None = None,
):
    """Get version history for a workflow."""
    manager = get_version_manager()
    await check_workflow_access(UUID(workflow_id), current_user)

    versions = await manager.get_history(
        workflow_id=UUID(workflow_id),
        limit=limit,
        offset=offset,
        status=status,
    )

    return VersionListResponse(
        versions=[v.to_dict() for v in versions],
        total=len(versions),  # In production, get actual count
    )


@router.get("/{workflow_id}/version/{version_id}")
async def get_version(
    workflow_id: str,
    version_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Get a specific version."""
    manager = get_version_manager()

    await check_version_workflow_access(workflow_id, version_id, current_user)
    version = await manager.get_version(version_id)
    if not version:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_version_not_found",
            status_code=404,
        )

    return version.to_dict()


@router.post("/{workflow_id}/version/{version_id}/publish")
async def publish_version(
    workflow_id: str,
    version_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Publish a version."""
    manager = get_version_manager()

    await check_version_workflow_access(
        workflow_id, version_id, current_user, required_permission="workflow:publish"
    )
    try:
        version = await manager.publish_version(version_id, current_user.id)
        if not version:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="workflow_version_not_found",
                status_code=404,
            )

        return {"success": True, "status": version.status.value}
    except BusinessError:
        raise
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=translate_public_workflow_error(e),
        )


@router.post("/{workflow_id}/version/{version_id}/archive")
async def archive_version(
    workflow_id: str,
    version_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Archive a version."""
    manager = get_version_manager()

    await check_version_workflow_access(
        workflow_id, version_id, current_user, require_write=True
    )
    try:
        version = await manager.archive_version(version_id)
        if not version:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="workflow_version_not_found",
                status_code=404,
            )

        return {"success": True, "status": version.status.value}
    except BusinessError:
        raise
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=translate_public_workflow_error(e),
        )


@router.get("/{workflow_id}/diff", response_model=VersionDiffResponse)
async def get_version_diff(
    workflow_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
    from_version: str = Query(..., description="Source version ID"),
    to_version: str = Query(..., description="Target version ID"),
):
    """Get diff between two versions."""
    manager = get_version_manager()

    await check_version_workflow_access(workflow_id, from_version, current_user)
    await check_version_workflow_access(workflow_id, to_version, current_user)
    try:
        diff = await manager.diff(from_version, to_version)
        if not diff:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="workflow_version_diff_not_found",
                status_code=404,
            )

        return VersionDiffResponse(
            from_version=from_version,
            to_version=to_version,
            diff=diff.to_dict(),
        )
    except BusinessError:
        raise
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=translate_public_workflow_error(e),
        )


@router.post("/{workflow_id}/rollback", response_model=RollbackResponse)
async def rollback_version(
    workflow_id: str,
    request: RollbackRequest,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Rollback to a previous version."""
    manager = get_version_manager()

    await check_version_workflow_access(
        workflow_id, request.version_id, current_user, require_write=True
    )
    try:
        result = await manager.rollback(
            workflow_id=UUID(workflow_id),
            version_id=request.version_id,
            user_id=current_user.id,
            create_backup=request.create_backup,
        )

        return RollbackResponse(
            success=True,
            new_version_id=result.version_id,
            backup_version_id=None,
        )
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=translate_public_workflow_error(e),
        )


@router.post("/{workflow_id}/fork", response_model=ForkResponse)
async def fork_workflow(
    workflow_id: str,
    request: ForkRequest,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Fork a workflow to create a new one."""
    manager = get_version_manager()

    await check_version_workflow_access(workflow_id, request.version_id, current_user)
    await check_workflow_access(
        UUID(request.new_workflow_id), current_user, require_write=True
    )
    try:
        new_version = await manager.fork(
            workflow_id=UUID(workflow_id),
            version_id=request.version_id,
            new_workflow_id=UUID(request.new_workflow_id),
            user_id=current_user.id,
        )

        return ForkResponse(
            success=True,
            new_version_id=new_version.version_id,
        )
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=translate_public_workflow_error(e),
        )


@router.get("/{workflow_id}/stats")
async def get_version_stats(
    workflow_id: str,
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
):
    """Get version statistics for a workflow."""
    manager = get_version_manager()

    await check_workflow_access(UUID(workflow_id), current_user, require_write=True)
    stats = await manager.get_stats(UUID(workflow_id))
    return stats
