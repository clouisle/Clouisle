"""Skills API endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.api import deps
from app.models.agent import Agent
from app.models.skill import Skill
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.skill import (
    SkillDetailOut,
    SkillImportInstallOut,
    SkillImportInstallRequest,
    SkillImportPreviewGitRequest,
    SkillImportPreviewOut,
    SkillListOut,
    SkillTestRequest,
    SkillTestResponse,
    SkillUpdate,
)
from app.schemas.tool import SandboxArtifactSchema
from app.services.audit_log import AuditLogService
from app.services.skill import SkillService
from app.services.skill_executor import SkillExecutor
from app.services.skill_import import SkillImportService

router = APIRouter()


def _serialize_artifacts(artifacts: list[Any]) -> list[SandboxArtifactSchema]:
    return [SandboxArtifactSchema.model_validate(artifact) for artifact in artifacts]


def _skill_detail(skill: Skill) -> SkillDetailOut:
    out = SkillService.to_out(skill)
    return SkillDetailOut(
        **out.model_dump(),
        skill_md=skill.skill_md,
        instructions=skill.instructions,
        frontmatter=skill.frontmatter or {},
        package_manifest=skill.package_manifest or {},
        execution_config=skill.execution_config or {},
        config_schema=skill.config_schema or {},
    )


@router.get("", response_model=Response[SkillListOut])
async def list_skills(
    team_id: UUID = Query(...),
    include_system: bool = Query(default=True),
    enabled: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    current_user: User = Depends(deps.PermissionChecker("skill:read")),
) -> Any:
    skills = await SkillService.list_available_skills(
        team_id=team_id,
        user=current_user,
        include_system=include_system,
        enabled=enabled,
        search=search,
        category=category,
    )
    system = [SkillService.to_out(skill) for skill in skills if skill.team_id is None]
    team = [SkillService.to_out(skill) for skill in skills if skill.team_id is not None]
    return success(data=SkillListOut(system=system, team=team))


@router.post("/import/preview-zip", response_model=Response[SkillImportPreviewOut])
async def preview_zip_import(
    *,
    request: Request,
    team_id: UUID | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(deps.PermissionChecker("skill:create")),
) -> Any:
    content = await file.read()
    preview = await SkillImportService.preview_zip(
        team_id=team_id,
        user=current_user,
        filename=file.filename or "skills.zip",
        content=content,
    )
    await AuditLogService.log(
        user=current_user,
        action="preview_skill_import",
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
    current_user: User = Depends(deps.PermissionChecker("skill:create")),
) -> Any:
    preview = await SkillImportService.preview_git(
        team_id=preview_in.team_id,
        user=current_user,
        repo_url=preview_in.repo_url,
        ref=preview_in.ref,
    )
    await AuditLogService.log(
        user=current_user,
        action="preview_skill_import",
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
    current_user: User = Depends(deps.PermissionChecker("skill:create")),
) -> Any:
    result = await SkillImportService.install_from_session(
        session_id=session_id,
        items=install_in.items,
        is_enabled=install_in.is_enabled,
        user=current_user,
    )
    await AuditLogService.log(
        user=current_user,
        action="install_skill_import",
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


@router.get("/{skill_id}", response_model=Response[SkillDetailOut])
async def get_skill(
    skill_id: UUID,
    team_id: UUID | None = Query(default=None),
    current_user: User = Depends(deps.PermissionChecker("skill:read")),
) -> Any:
    skill = await Skill.filter(id=skill_id).prefetch_related("created_by").first()
    if not skill:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="skill_not_found",
            status_code=404,
        )
    if skill.team_id is None:
        if team_id is not None:
            await SkillService.check_team_access(team_id, current_user)
    else:
        await SkillService.check_team_access(skill.team_id, current_user)
    return success(data=_skill_detail(skill))


@router.patch("/{skill_id}", response_model=Response[SkillDetailOut])
async def update_skill(
    *,
    request: Request,
    skill_id: UUID,
    skill_in: SkillUpdate,
    current_user: User = Depends(deps.PermissionChecker("skill:update")),
) -> Any:
    skill = await Skill.filter(id=skill_id).first()
    if not skill:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="skill_not_found",
            status_code=404,
        )

    before = {
        "name": skill.name,
        "display_name": skill.display_name,
        "is_enabled": skill.is_enabled,
        "version": skill.version,
    }
    skill = await SkillService.update_skill(skill, skill_in, current_user)
    await AuditLogService.log(
        user=current_user,
        action="update_skill",
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
    return success(data=_skill_detail(skill), msg_key="skill_updated")


@router.delete("/{skill_id}", response_model=Response[None])
async def delete_skill(
    *,
    request: Request,
    skill_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("skill:delete")),
) -> Any:
    skill = await Skill.filter(id=skill_id).first()
    if not skill:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="skill_not_found",
            status_code=404,
        )

    if skill.team_id is None:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )
    else:
        await SkillService.check_team_access(
            skill.team_id, current_user, require_admin=True
        )

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
        action="delete_skill",
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
    current_user: User = Depends(deps.PermissionChecker("skill:execute")),
) -> Any:
    skill = await Skill.filter(id=skill_id).first()
    if not skill:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="skill_not_found",
            status_code=404,
        )
    if skill.team_id is None:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )
    else:
        await SkillService.check_team_access(
            skill.team_id, current_user, require_admin=True
        )

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
        action="test_skill",
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
