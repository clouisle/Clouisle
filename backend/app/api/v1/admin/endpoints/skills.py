"""Admin capability Skill endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from tortoise.expressions import Q

from app.api import deps
from app.api.v1.endpoints.skills import _serialize_artifacts
from app.models.agent import Agent
from app.models.skill import Skill
from app.models.user import Team, User
from app.schemas.response import (
    BusinessError,
    PageData,
    Response,
    ResponseCode,
    success,
)
from app.schemas.skill import (
    AdminSkillDetailOut,
    AdminSkillOut,
    SkillFilterOption,
    SkillFilterOptionsOut,
    SkillImportInstallOut,
    SkillImportInstallRequest,
    SkillImportPreviewGitRequest,
    SkillImportPreviewOut,
    SkillTestRequest,
    SkillTestResponse,
    SkillUpdate,
)
from app.services.audit_log import AuditLogService
from app.services.skill import SkillService
from app.services.skill_executor import SkillExecutor
from app.services.skill_import import SkillImportService

router = APIRouter()


def _admin_skill_out(skill: Skill) -> AdminSkillOut:
    out = SkillService.to_out(skill)
    return AdminSkillOut(
        **out.model_dump(),
        team_name=skill.team.name if skill.team else None,
    )


def _admin_skill_detail(skill: Skill) -> AdminSkillDetailOut:
    out = _admin_skill_out(skill)
    return AdminSkillDetailOut(
        **out.model_dump(),
        skill_md=skill.skill_md,
        instructions=skill.instructions,
        frontmatter=skill.frontmatter or {},
        package_manifest=skill.package_manifest or {},
        execution_config=skill.execution_config or {},
        config_schema=skill.config_schema or {},
    )


def _filter_option(value: str, label: str | None = None) -> SkillFilterOption:
    return SkillFilterOption(value=value, label=label or value)


async def _get_skill(skill_id: UUID) -> Skill:
    skill = (
        await Skill.filter(id=skill_id).prefetch_related("team", "created_by").first()
    )
    if not skill:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="skill_not_found",
            status_code=404,
        )
    return skill


@router.get("", response_model=Response[PageData[AdminSkillOut]])
async def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None),
    team_id: list[UUID] | None = Query(default=None),
    include_system: bool = Query(default=True),
    enabled: bool | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    source_type: list[str] | None = Query(default=None),
    creator: list[str] | None = Query(default=None),
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    query = Skill.all().prefetch_related("team", "created_by")
    if team_id:
        scope_query = Q(team_id__in=team_id)
        if include_system:
            scope_query |= Q(team_id=None)
        query = query.filter(scope_query)
    elif not include_system:
        query = query.filter(team_id__not_isnull=True)
    if enabled is not None:
        query = query.filter(is_enabled=enabled)
    if status:
        status_values = set(status)
        if "enabled" in status_values and "disabled" not in status_values:
            query = query.filter(is_enabled=True)
        elif "disabled" in status_values and "enabled" not in status_values:
            query = query.filter(is_enabled=False)
    if source_type:
        query = query.filter(source_type__in=source_type)
    if creator:
        query = query.filter(created_by__username__in=creator)
    if search:
        query = query.filter(
            Q(name__icontains=search)
            | Q(display_name__icontains=search)
            | Q(description__icontains=search)
        )

    total = await query.count()
    skills = (
        await query.order_by("-updated_at")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return success(
        data=PageData[AdminSkillOut](
            items=[_admin_skill_out(skill) for skill in skills],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/filters", response_model=Response[SkillFilterOptionsOut])
async def get_skill_filter_options(
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    skills = await Skill.all().prefetch_related("team", "created_by")
    creator_values = sorted(
        {skill.created_by.username for skill in skills if skill.created_by}
    )
    teams = await Team.all().order_by("name")
    source_types = sorted(
        {skill.source_type.value for skill in skills if skill.source_type}
    )
    return success(
        data=SkillFilterOptionsOut(
            statuses=[_filter_option("enabled"), _filter_option("disabled")],
            sources=[_filter_option(value) for value in source_types],
            teams=[_filter_option(str(team.id), team.name) for team in teams],
            creators=[_filter_option(value) for value in creator_values],
        )
    )


@router.get("/{skill_id}", response_model=Response[AdminSkillDetailOut])
async def get_skill(
    skill_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    return success(data=_admin_skill_detail(await _get_skill(skill_id)))


@router.post("/import/preview-zip", response_model=Response[SkillImportPreviewOut])
async def preview_zip_import(
    *,
    request: Request,
    team_id: UUID | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(deps.PermissionChecker("admin:capability:create")),
) -> Any:
    content = await file.read()
    preview = await SkillImportService.preview_zip(
        team_id=team_id,
        user=current_user,
        filename=file.filename or "skills.zip",
        content=content,
        admin_mode=True,
    )
    await AuditLogService.log(
        user=current_user,
        action="admin_preview_skill_import",
        resource_type="skill",
        resource_id=None,
        resource_name=None,
        operation="import_preview",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id) if team_id else None,
            "source_type": "zip",
            "skill_count": len(preview.skills),
            "invalid_count": len(preview.invalid),
        },
    )
    return success(data=preview)


@router.post("/import/preview-git", response_model=Response[SkillImportPreviewOut])
async def preview_git_import(
    *,
    request: Request,
    preview_in: SkillImportPreviewGitRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:create")),
) -> Any:
    preview = await SkillImportService.preview_git(
        team_id=preview_in.team_id,
        user=current_user,
        repo_url=preview_in.repo_url,
        ref=preview_in.ref,
        admin_mode=True,
    )
    await AuditLogService.log(
        user=current_user,
        action="admin_preview_skill_import",
        resource_type="skill",
        resource_id=None,
        resource_name=None,
        operation="import_preview",
        status="success",
        request=request,
        metadata={
            "team_id": str(preview_in.team_id) if preview_in.team_id else None,
            "source_type": "git",
            "skill_count": len(preview.skills),
            "invalid_count": len(preview.invalid),
        },
    )
    return success(data=preview)


@router.post(
    "/import/{session_id}/install", response_model=Response[SkillImportInstallOut]
)
async def install_skill_import(
    *,
    request: Request,
    session_id: UUID,
    install_in: SkillImportInstallRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:create")),
) -> Any:
    result = await SkillImportService.install_from_session(
        session_id=session_id,
        items=install_in.items,
        is_enabled=install_in.is_enabled,
        user=current_user,
        admin_mode=True,
    )
    await AuditLogService.log(
        user=current_user,
        action="admin_install_skill_import",
        resource_type="skill",
        resource_id=session_id,
        resource_name=None,
        operation="import_install",
        status="success" if not result.errors else "failed",
        request=request,
        metadata={
            "installed_count": len(result.installed),
            "updated_count": len(result.updated),
            "skipped_count": len(result.skipped),
            "error_count": len(result.errors),
        },
    )
    return success(data=result, msg_key="skill_import_installed")


@router.patch("/{skill_id}", response_model=Response[AdminSkillDetailOut])
async def update_skill(
    *,
    request: Request,
    skill_id: UUID,
    skill_in: SkillUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    skill = await _get_skill(skill_id)
    before = {
        "name": skill.name,
        "display_name": skill.display_name,
        "is_enabled": skill.is_enabled,
        "version": skill.version,
    }
    update_data = skill_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(skill, field, value)
    await skill.save()
    skill = await _get_skill(skill_id)
    await AuditLogService.log(
        user=current_user,
        action="admin_update_skill",
        resource_type="skill",
        resource_id=skill.id,
        resource_name=skill.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": before,
            "after": {
                "name": skill.name,
                "display_name": skill.display_name,
                "is_enabled": skill.is_enabled,
                "version": skill.version,
            },
        },
        metadata={"team_id": str(skill.team_id) if skill.team_id else None},
    )
    return success(data=_admin_skill_detail(skill), msg_key="skill_updated")


@router.delete("/{skill_id}", response_model=Response[None])
async def delete_skill(
    *,
    request: Request,
    skill_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:delete")),
) -> Any:
    skill = await _get_skill(skill_id)
    referenced = await Agent.filter(
        tools_config__contains=[{"type": "skill", "skill_id": str(skill.id)}]
    ).exists()
    if referenced:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="skill_referenced_by_agent",
        )

    skill_id_for_log = skill.id
    skill_name = skill.name
    team_id = str(skill.team_id) if skill.team_id else None
    await SkillImportService.delete_private_storage(skill.package_storage_path)
    await skill.delete()
    await AuditLogService.log(
        user=current_user,
        action="admin_delete_skill",
        resource_type="skill",
        resource_id=skill_id_for_log,
        resource_name=skill_name,
        operation="delete",
        status="success",
        request=request,
        metadata={"team_id": team_id},
    )
    return success(data=None, msg_key="skill_deleted")


@router.post("/{skill_id}/test", response_model=Response[SkillTestResponse])
async def test_skill(
    *,
    request: Request,
    skill_id: UUID,
    test_in: SkillTestRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:execute")),
) -> Any:
    skill = await _get_skill(skill_id)

    from app.services.sandbox.gateway import sandbox_gateway

    session_id = await sandbox_gateway.create_session(
        team_id=str(skill.team_id) if skill.team_id else None,
    )
    try:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments=test_in.arguments,
            config=test_in.config,
            tenant_id=str(skill.team_id) if skill.team_id else None,
            session_id=session_id,
        )
    finally:
        await sandbox_gateway.cleanup_session(session_id)
    await AuditLogService.log(
        user=current_user,
        action="admin_test_skill",
        resource_type="skill",
        resource_id=skill.id,
        resource_name=skill.name,
        operation="execute",
        status="success" if result.success else "failed",
        request=request,
        metadata={
            "team_id": str(skill.team_id) if skill.team_id else None,
            "argument_keys": sorted(test_in.arguments.keys()),
            "duration_ms": result.duration_ms,
            "status": result.status.value if result.status else None,
        },
        error_message=result.error,
    )
    return success(
        data=SkillTestResponse(
            success=result.success,
            result=result.result,
            error=result.error,
            stdout=result.stdout,
            stderr=result.stderr,
            artifacts=_serialize_artifacts(result.artifacts),
            duration_ms=result.duration_ms,
        )
    )
