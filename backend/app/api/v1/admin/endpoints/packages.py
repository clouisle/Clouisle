"""Admin import/export endpoints for `.clouisle` resource packages."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import deps
from app.api.v1.endpoints.packages import _content_disposition
from app.models.package_import import ClouisleImportSession, ClouisleImportSource
from app.models.user import User
from app.schemas.clouisle_package import (
    ClouisleImportInstallOut,
    ClouisleImportInstallRequest,
    ClouisleImportPreviewOut,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.clouisle_package import ClouislePackageService
from app.services.clouisle_package_resources import get_adapter

router = APIRouter()

_ADMIN_EXPORT_ALLOWED_TYPES = {
    ClouisleResourceType.TOOL,
    ClouisleResourceType.AGENT,
    ClouisleResourceType.WORKFLOW,
    ClouisleResourceType.KNOWLEDGE_BASE,
}
_ADMIN_IMPORT_ALLOWED_TYPES = {ClouisleResourceType.TOOL, ClouisleResourceType.KNOWLEDGE_BASE}

_EXPORT_PERMISSION: dict[ClouisleResourceType, str] = {
    ClouisleResourceType.TOOL: "admin:capability:read",
    ClouisleResourceType.AGENT: "admin:app:read",
    ClouisleResourceType.WORKFLOW: "admin:app:read",
    ClouisleResourceType.KNOWLEDGE_BASE: "admin:knowledge-base:read",
}
_IMPORT_PERMISSION: dict[ClouisleResourceType, str] = {
    ClouisleResourceType.TOOL: "admin:capability:create",
    ClouisleResourceType.KNOWLEDGE_BASE: "admin:knowledge-base:create",
}
_UPDATE_PERMISSION: dict[ClouisleResourceType, str] = {
    ClouisleResourceType.TOOL: "admin:capability:update",
    ClouisleResourceType.KNOWLEDGE_BASE: "admin:knowledge-base:update",
}


def _require_admin_permission(user: User, permission: str) -> None:
    if user.is_superuser:
        return
    for role in getattr(user, "roles", []):
        for perm in getattr(role, "permissions", []):
            if perm.code in (permission, "*"):
                return
    raise BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="operation_not_permitted",
        status_code=403,
        permission=permission,
    )


def _check_admin_resource_type(
    resource_type: ClouisleResourceType, allowed_types: set[ClouisleResourceType]
) -> None:
    if resource_type not in allowed_types:
        raise BusinessError(msg_key="clouisle_invalid_resource_type", status_code=400)


@router.get("/{resource_type}/{resource_id}/export")
async def admin_export_package(
    *,
    request: Request,
    resource_type: ClouisleResourceType,
    resource_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    _check_admin_resource_type(resource_type, _ADMIN_EXPORT_ALLOWED_TYPES)
    _require_admin_permission(current_user, _EXPORT_PERMISSION[resource_type])
    adapter = get_adapter(resource_type)
    try:
        payload, dependencies, resource_name = await adapter.export(
            resource_id,
            current_user,
            check_permission=False,
            check_scope=False,
        )
    except BusinessError as exc:
        await AuditLogService.log(
            user=current_user,
            action="export_clouisle_package",
            resource_type=resource_type.value,
            resource_id=resource_id,
            resource_name=None,
            operation="export",
            status="failed",
            request=request,
            error_message=exc.msg_key or exc.msg,
        )
        raise
    files = await adapter.export_files(payload)
    content = ClouislePackageService.build_package(
        resource_type=resource_type,
        resource_id=str(resource_id),
        resource_name=resource_name,
        resource_payload=payload,
        dependencies=dependencies,
        files=files,
    )
    filename = ClouislePackageService.export_filename(resource_type, resource_name)
    await AuditLogService.log(
        user=current_user,
        action="export_clouisle_package",
        resource_type=resource_type.value,
        resource_id=resource_id,
        resource_name=resource_name,
        operation="export",
        status="success",
        request=request,
        metadata={"dependency_count": len(dependencies)},
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/import/preview", response_model=Response[ClouisleImportPreviewOut])
async def admin_preview_package_import(
    *,
    request: Request,
    team_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    content = await file.read()
    # Permission is checked after parsing the manifest so we know the resource type.
    try:
        manifest, _ = ClouislePackageService._read_package(
            file.filename or "package.clouisle", content
        )
        _check_admin_resource_type(manifest.resource_type, _ADMIN_IMPORT_ALLOWED_TYPES)
        _require_admin_permission(
            current_user, _IMPORT_PERMISSION[manifest.resource_type]
        )
        preview = await ClouislePackageService.preview(
            team_id=team_id,
            user=current_user,
            filename=file.filename or "package.clouisle",
            content=content,
            source=ClouisleImportSource.ADMIN,
            check_permission=False,
            check_team_membership=False,
        )
    except BusinessError as exc:
        await AuditLogService.log(
            user=current_user,
            action="preview_clouisle_import",
            resource_type="package",
            resource_id=None,
            resource_name=file.filename,
            operation="import_preview",
            status="failed",
            request=request,
            metadata={"team_id": str(team_id)},
            error_message=exc.msg_key or exc.msg,
        )
        raise
    await AuditLogService.log(
        user=current_user,
        action="preview_clouisle_import",
        resource_type=preview.resource_type.value,
        resource_id=None,
        resource_name=preview.resource_name,
        operation="import_preview",
        status="success" if preview.valid else "failed",
        request=request,
        metadata={
            "team_id": str(team_id),
            "package_id": str(preview.package_id),
            "dependency_count": len(preview.dependencies),
            "error_count": len(preview.errors),
            "warning_count": len(preview.warnings),
        },
    )
    return success(data=preview)


@router.post(
    "/import/{session_id}/install",
    response_model=Response[ClouisleImportInstallOut],
)
async def admin_install_package_import(
    *,
    request: Request,
    session_id: UUID,
    install_in: ClouisleImportInstallRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    try:
        session = await ClouisleImportSession.filter(
            id=session_id,
            source=ClouisleImportSource.ADMIN,
        ).first()
        if not session:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="clouisle_import_session_not_found",
                status_code=404,
            )
        resource_type = ClouisleResourceType(session.resource_type)
        _check_admin_resource_type(resource_type, _ADMIN_IMPORT_ALLOWED_TYPES)
        permission = (
            _IMPORT_PERMISSION[resource_type]
            if install_in.action.value != "update"
            else _UPDATE_PERMISSION[resource_type]
        )
        _require_admin_permission(current_user, permission)
        result = await ClouislePackageService.install(
            session_id=session_id,
            user=current_user,
            install_in=install_in,
            source=ClouisleImportSource.ADMIN,
            check_permission=False,
            check_team_membership=False,
        )
    except BusinessError as exc:
        await AuditLogService.log(
            user=current_user,
            action="install_clouisle_package",
            resource_type="package",
            resource_id=session_id,
            resource_name=None,
            operation="import_install",
            status="failed",
            request=request,
            metadata={"action": install_in.action.value},
            error_message=exc.msg_key or exc.msg,
        )
        raise
    await AuditLogService.log(
        user=current_user,
        action="install_clouisle_package",
        resource_type="package",
        resource_id=session_id,
        resource_name=None,
        operation="import_install",
        status="success" if not result.errors else "failed",
        request=request,
        metadata={
            "installed": str(result.installed) if result.installed else None,
            "updated": str(result.updated) if result.updated else None,
            "skipped": result.skipped,
            "error_count": len(result.errors),
        },
    )
    return success(data=result, msg_key="clouisle_import_installed")
