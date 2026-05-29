"""Import and export `.clouisle` resource packages."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import deps
from app.models.package_import import ClouisleImportSource
from app.models.user import User
from app.schemas.clouisle_package import (
    ClouisleImportInstallRequest,
    ClouisleImportInstallOut,
    ClouisleImportPreviewOut,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, Response, success
from app.services.audit_log import AuditLogService
from app.services.clouisle_package import ClouislePackageService
from app.services.clouisle_package_resources import get_adapter

router = APIRouter()


@router.get("/{resource_type}/{resource_id}/export")
async def export_package(
    *,
    request: Request,
    resource_type: ClouisleResourceType,
    resource_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    adapter = get_adapter(resource_type)
    try:
        payload, dependencies, resource_name = await adapter.export(
            resource_id, current_user
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
async def preview_package_import(
    *,
    request: Request,
    team_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    content = await file.read()
    try:
        preview = await ClouislePackageService.preview(
            team_id=team_id,
            user=current_user,
            filename=file.filename or "package.clouisle",
            content=content,
            source=ClouisleImportSource.PLATFORM,
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
async def install_package_import(
    *,
    request: Request,
    session_id: UUID,
    install_in: ClouisleImportInstallRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    try:
        result = await ClouislePackageService.install(
            session_id=session_id,
            user=current_user,
            install_in=install_in,
            source=ClouisleImportSource.PLATFORM,
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


def _content_disposition(filename: str) -> str:
    fallback = "package.clouisle"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
