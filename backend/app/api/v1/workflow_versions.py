"""
Workflow version control API endpoints.

Provides REST API for:
- Version history management
- Version comparison and diff
- Rollback operations
- Template management
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.services.workflow.errors import translate_public_workflow_error
from app.services.workflow.versioning import (
    get_version_manager,
    VersionStatus,
)
from app.services.workflow.templates import (
    get_template_manager,
    TemplateCategory,
    TemplateVisibility,
    TemplateVariable,
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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new workflow version."""
    manager = get_version_manager()

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
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: VersionStatus | None = None,
):
    """Get version history for a workflow."""
    manager = get_version_manager()

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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a specific version."""
    manager = get_version_manager()

    _ = workflow_id
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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Publish a version."""
    manager = get_version_manager()

    _ = workflow_id
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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Archive a version."""
    manager = get_version_manager()

    _ = workflow_id
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
    current_user: Annotated[User, Depends(get_current_user)],
    from_version: str = Query(..., description="Source version ID"),
    to_version: str = Query(..., description="Target version ID"),
):
    """Get diff between two versions."""
    manager = get_version_manager()

    _ = workflow_id
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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Rollback to a previous version."""
    manager = get_version_manager()

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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Fork a workflow to create a new one."""
    manager = get_version_manager()

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
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get version statistics for a workflow."""
    manager = get_version_manager()

    stats = await manager.get_stats(UUID(workflow_id))
    return stats


# Template API Router

template_router = APIRouter(prefix="/workflow-templates", tags=["workflow-templates"])


class CreateTemplateRequest(BaseModel):
    """Request to create a template."""

    name: str
    description: str
    category: TemplateCategory
    visibility: TemplateVisibility = TemplateVisibility.PRIVATE
    nodes: list[dict]
    edges: list[dict]
    config: dict = Field(default_factory=dict)
    variables: list[dict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    icon: str | None = None


class InstantiateTemplateRequest(BaseModel):
    """Request to instantiate a template."""

    template_id: str
    variables: dict
    workflow_name: str | None = None


class RateTemplateRequest(BaseModel):
    """Request to rate a template."""

    rating: float = Field(..., ge=1, le=5)


@template_router.get("")
async def list_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    category: TemplateCategory | None = None,
    visibility: TemplateVisibility | None = None,
    tags: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List available templates."""
    manager = get_template_manager()

    templates = await manager.list_templates(
        category=category,
        visibility=visibility,
        tags=tags,
        limit=limit,
        offset=offset,
    )

    return {
        "templates": [t.to_summary() for t in templates],
        "total": len(templates),
    }


@template_router.get("/featured")
async def get_featured_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get featured templates."""
    manager = get_template_manager()

    templates = await manager.get_featured(limit=limit)
    return {"templates": [t.to_summary() for t in templates]}


@template_router.get("/search")
async def search_templates(
    current_user: Annotated[User, Depends(get_current_user)],
    query: str = Query(..., min_length=1),
    category: TemplateCategory | None = None,
    limit: int = Query(default=20, ge=1, le=50),
):
    """Search templates."""
    manager = get_template_manager()

    templates = await manager.search(
        query=query,
        category=category,
        limit=limit,
    )

    return {"templates": [t.to_summary() for t in templates]}


@template_router.get("/categories")
async def get_template_categories(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get available template categories."""
    return {
        "categories": [{"value": c.value, "name": c.name} for c in TemplateCategory]
    }


@template_router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a template by ID."""
    manager = get_template_manager()

    template = await manager.get_template(template_id)
    if not template:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_template_not_found",
            status_code=404,
        )

    return template.to_dict()


@template_router.post("")
async def create_template(
    request: CreateTemplateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new template."""
    manager = get_template_manager()

    # Convert variable dicts to TemplateVariable objects
    variables = [
        TemplateVariable(
            name=v["name"],
            label=v.get("label", v["name"]),
            description=v.get("description", ""),
            variable_type=v.get("type", "string"),
            default_value=v.get("default"),
            required=v.get("required", True),
            options=v.get("options", []),
            validation=v.get("validation", {}),
        )
        for v in request.variables
    ]

    template = await manager.create_template(
        name=request.name,
        description=request.description,
        category=request.category,
        visibility=request.visibility,
        author_id=str(current_user.id),
        author_name=current_user.username,
        nodes=request.nodes,
        edges=request.edges,
        variables=variables,
        config=request.config,
        tags=request.tags,
        icon=request.icon,
    )

    return template.to_dict()


@template_router.post("/{template_id}/instantiate")
async def instantiate_template(
    template_id: str,
    request: InstantiateTemplateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Instantiate a template to create a workflow definition."""
    manager = get_template_manager()

    try:
        workflow_def = await manager.instantiate(
            template_id=request.template_id,
            variables=request.variables,
            workflow_name=request.workflow_name,
        )
        return workflow_def
    except ValueError:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="workflow_template_instantiate_failed",
        )


@template_router.post("/{template_id}/rate")
async def rate_template(
    template_id: str,
    request: RateTemplateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Rate a template."""
    manager = get_template_manager()

    success = await manager.rate_template(
        template_id=template_id,
        user_id=str(current_user.id),
        rating=request.rating,
    )

    if not success:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="workflow_template_rating_failed",
        )

    return {"success": True}


@template_router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete a template."""
    manager = get_template_manager()

    # Check ownership (in production)
    template = await manager.get_template(template_id)
    if not template:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_template_not_found",
            status_code=404,
        )

    if template.author_id != str(current_user.id):
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="workflow_template_access_denied",
            status_code=403,
        )

    success = await manager.delete_template(template_id)
    if not success:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="workflow_template_delete_failed",
        )

    return {"success": True}


@template_router.get("/stats/summary")
async def get_template_stats(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get template statistics."""
    manager = get_template_manager()

    stats = await manager.get_stats()
    return stats
