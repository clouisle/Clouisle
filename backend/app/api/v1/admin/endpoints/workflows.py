"""Admin workflow management endpoints."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from tortoise.expressions import Q

from app.api import deps
from app.core.i18n import t
from app.models.user import Team, User
from app.models.workflow import (
    TriggerType,
    Workflow,
    WorkflowStatus,
    WorkflowVersion,
    WorkflowVisibility,
)
from app.schemas.response import (
    BusinessError,
    PageData,
    Response,
    ResponseCode,
    success,
)
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListItem,
    WorkflowOut,
    WorkflowUpdate,
)
from app.services.audit_log import AuditLogService

router = APIRouter()


def _option(value: str, label: str | None = None) -> dict[str, str]:
    return {"value": value, "label": label or value}


async def _get_workflow(workflow_id: UUID, *, detail: bool = False) -> Workflow:
    query = Workflow.filter(id=workflow_id)
    if detail:
        query = query.prefetch_related("team", "created_by")
    workflow = await query.first()
    if not workflow:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )
    return workflow


def _workflow_list_item(workflow: Workflow) -> dict[str, Any]:
    item = WorkflowListItem.model_validate(workflow).model_dump()
    item["team_id"] = workflow.team_id
    item["team_name"] = workflow.team.name if workflow.team else None
    item["created_by_id"] = workflow.created_by_id
    item["created_by_name"] = (
        workflow.created_by.username if workflow.created_by else None
    )
    item["total_tokens"] = workflow.total_tokens
    item["version"] = workflow.version
    return item


@router.get("", response_model=Response[PageData[dict]])
async def list_workflows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: list[WorkflowStatus] | None = Query(None),
    visibility: list[WorkflowVisibility] | None = Query(None),
    trigger_type: list[TriggerType] | None = Query(None),
    team_id: list[UUID] | None = Query(None),
    creator: list[str] | None = Query(None),
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    query = Workflow.all()

    if search:
        query = query.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    if status:
        query = query.filter(status__in=status)
    if visibility:
        query = query.filter(visibility__in=visibility)
    if trigger_type:
        query = query.filter(trigger_type__in=trigger_type)
    if team_id:
        query = query.filter(team_id__in=team_id)
    if creator:
        query = query.filter(created_by__username__in=creator)

    total = await query.count()
    skip = (page - 1) * page_size
    workflows = (
        await query.prefetch_related("team", "created_by")
        .order_by("-updated_at")
        .offset(skip)
        .limit(page_size)
    )
    return success(
        data={
            "items": [_workflow_list_item(workflow) for workflow in workflows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/filters", response_model=Response[dict[str, list[dict[str, str]]]])
async def get_workflow_filter_options(
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    teams = await Team.all().order_by("name")
    creator_values = cast(
        list[str],
        await Workflow.filter(created_by_id__isnull=False)
        .order_by("created_by__username")
        .distinct()
        .values_list("created_by__username", flat=True),
    )
    creator_values = sorted(creator_values)
    return success(
        data={
            "statuses": [
                _option(WorkflowStatus.DRAFT.value),
                _option(WorkflowStatus.PUBLISHED.value),
                _option(WorkflowStatus.ARCHIVED.value),
            ],
            "visibilities": [
                _option(WorkflowVisibility.PRIVATE.value),
                _option(WorkflowVisibility.TEAM.value),
                _option(WorkflowVisibility.PUBLIC.value),
            ],
            "trigger_types": [
                _option(TriggerType.MANUAL.value),
                _option(TriggerType.CRON.value),
                _option(TriggerType.WEBHOOK.value),
            ],
            "teams": [_option(str(team.id), team.name) for team in teams],
            "creators": [_option(value) for value in creator_values],
        }
    )


@router.post("", response_model=Response[WorkflowOut])
async def create_workflow(
    request: Request,
    workflow_in: WorkflowCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:app:create")),
) -> Any:
    team = await Team.filter(id=workflow_in.team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    existing = await Workflow.filter(
        team_id=workflow_in.team_id,
        name=workflow_in.name,
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="workflow_name_exists",
        )

    default_definition = {
        "nodes": [
            {
                "id": "user_input-1",
                "type": "user_input",
                "position": {"x": 250, "y": 100},
                "data": {
                    "type": "user_input",
                    "label": t("node_label_start"),
                    "config": {},
                    "parameters": [
                        {
                            "id": "query",
                            "name": "query",
                            "type": "text",
                            "required": True,
                        }
                    ],
                },
            },
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }

    workflow = await Workflow.create(
        name=workflow_in.name,
        description=workflow_in.description,
        icon=workflow_in.icon,
        visibility=WorkflowVisibility(workflow_in.visibility),
        team=team,
        definition=default_definition,
        variables=[],
        created_by=current_user,
    )
    workflow = await Workflow.get(id=workflow.id).prefetch_related("team", "created_by")
    await AuditLogService.log(
        user=current_user,
        action="admin_create_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "team_id": str(team.id),
            "team_name": team.name,
            "visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_created",
    )


@router.get("/{workflow_id}", response_model=Response[WorkflowOut])
async def get_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    workflow = await _get_workflow(workflow_id, detail=True)
    return success(data=WorkflowOut.model_validate(workflow).model_dump())


@router.put("/{workflow_id}", response_model=Response[WorkflowOut])
async def update_workflow(
    request: Request,
    workflow_id: UUID,
    workflow_in: WorkflowUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:app:update")),
) -> Any:
    workflow = await _get_workflow(workflow_id, detail=True)

    if workflow_in.name is not None and workflow_in.name != workflow.name:
        existing = (
            await Workflow.filter(team_id=workflow.team_id, name=workflow_in.name)
            .exclude(id=workflow_id)
            .first()
        )
        if existing:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="workflow_name_exists",
            )

    updated_fields = []
    old_version = workflow.version

    if workflow_in.name is not None:
        workflow.name = workflow_in.name
        updated_fields.append("name")
    if workflow_in.description is not None:
        workflow.description = workflow_in.description
        updated_fields.append("description")
    if workflow_in.icon is not None:
        workflow.icon = workflow_in.icon
        updated_fields.append("icon")
    if workflow_in.definition is not None:
        workflow.definition = workflow_in.definition
        workflow.version += 1
        updated_fields.append("definition")
    if workflow_in.variables is not None:
        workflow.variables = workflow_in.variables
        updated_fields.append("variables")
    if workflow_in.trigger_type is not None:
        workflow.trigger_type = workflow_in.trigger_type
        updated_fields.append("trigger_type")
    if workflow_in.trigger_config is not None:
        workflow.trigger_config = workflow_in.trigger_config
        updated_fields.append("trigger_config")
    if workflow_in.visibility is not None:
        workflow.visibility = WorkflowVisibility(workflow_in.visibility)
        updated_fields.append("visibility")
    if workflow_in.embed_config is not None:
        workflow.embed_config = workflow_in.embed_config
        updated_fields.append("embed_config")

    await workflow.save()
    workflow = await Workflow.get(id=workflow_id).prefetch_related("team", "created_by")
    await AuditLogService.log(
        user=current_user,
        action="admin_update_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"version": old_version},
            "after": {"version": workflow.version},
        },
        metadata={
            "fields_updated": updated_fields,
            "team_id": str(workflow.team_id),
            "visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_updated",
    )


@router.post("/{workflow_id}/publish", response_model=Response[WorkflowOut])
async def publish_workflow(
    request: Request,
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:publish")),
) -> Any:
    workflow = await _get_workflow(workflow_id, detail=True)
    old_status = workflow.status
    existing_version = await WorkflowVersion.filter(
        workflow_id=workflow_id, version=workflow.version
    ).first()
    if not existing_version:
        await WorkflowVersion.create(
            workflow_id=workflow_id,
            version=workflow.version,
            definition=workflow.definition,
            variables=workflow.variables,
            trigger_type=workflow.trigger_type,
            trigger_config=workflow.trigger_config,
            description=t("workflow_published_version_desc"),
            created_by=current_user,
        )

    workflow.status = WorkflowStatus.PUBLISHED
    await workflow.save()
    await AuditLogService.log(
        user=current_user,
        action="admin_publish_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"status": old_status.value},
            "after": {"status": workflow.status.value},
        },
        metadata={
            "team_id": str(workflow.team_id),
            "visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_published",
    )


@router.post("/{workflow_id}/unpublish", response_model=Response[WorkflowOut])
async def unpublish_workflow(
    request: Request,
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:publish")),
) -> Any:
    workflow = await _get_workflow(workflow_id, detail=True)
    old_status = workflow.status
    workflow.status = WorkflowStatus.DRAFT
    await workflow.save()
    await AuditLogService.log(
        user=current_user,
        action="admin_unpublish_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"status": old_status.value},
            "after": {"status": workflow.status.value},
        },
        metadata={
            "team_id": str(workflow.team_id),
            "visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_unpublished",
    )


@router.post("/{workflow_id}/duplicate", response_model=Response[WorkflowOut])
async def duplicate_workflow(
    request: Request,
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:duplicate")),
) -> Any:
    workflow = await _get_workflow(workflow_id)
    new_workflow = await Workflow.create(
        name=t("workflow_copy_suffix", name=workflow.name),
        description=workflow.description,
        icon=workflow.icon,
        team_id=workflow.team_id,
        definition=workflow.definition,
        variables=workflow.variables,
        status=WorkflowStatus.DRAFT,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        visibility=WorkflowVisibility.PRIVATE,
        created_by=current_user,
    )
    new_workflow = await Workflow.get(id=new_workflow.id).prefetch_related(
        "team", "created_by"
    )
    await AuditLogService.log(
        user=current_user,
        action="admin_duplicate_workflow",
        resource_type="workflow",
        resource_id=new_workflow.id,
        resource_name=new_workflow.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "source_workflow_id": str(workflow.id),
            "new_workflow_id": str(new_workflow.id),
            "team_id": str(workflow.team_id),
            "source_visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    return success(
        data=WorkflowOut.model_validate(new_workflow).model_dump(),
        msg_key="workflow_duplicated",
    )


@router.delete("/{workflow_id}", response_model=Response[dict])
async def delete_workflow(
    request: Request,
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:delete")),
) -> Any:
    workflow = await _get_workflow(workflow_id)
    await AuditLogService.log(
        user=current_user,
        action="admin_delete_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="delete",
        status="success",
        request=request,
        metadata={
            "team_id": str(workflow.team_id),
            "visibility": workflow.visibility.value,
            "trigger_type": workflow.trigger_type.value,
            "version": workflow.version,
        },
    )
    await workflow.delete()
    return success(data={"id": str(workflow_id)}, msg_key="workflow_deleted")
