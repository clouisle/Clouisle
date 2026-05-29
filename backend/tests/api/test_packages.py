from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import packages
from app.models.package_import import ClouisleImportSource
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallOut,
    ClouisleImportPreviewOut,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, error


@pytest.fixture
def packages_client():
    app = FastAPI()
    app.include_router(packages.router, prefix="/api/v1/packages")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code,
                msg=exc.msg,
                msg_key=exc.msg_key,
                data=exc.data,
                **exc.kwargs,
            ),
        )

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_platform_package_preview_uses_platform_source(packages_client):
    preview = ClouisleImportPreviewOut(
        session_id=uuid4(),
        package_id=uuid4(),
        resource_type=ClouisleResourceType.TOOL,
        resource_name="Imported Tool",
        source_resource_id=str(uuid4()),
        format_version="1",
        app_version="0.1.0",
        exported_at=datetime.now(UTC),
        valid=True,
        errors=[],
        warnings=[],
        dependencies=[],
        conflict=None,
        allowed_actions=[ClouisleConflictAction.INSTALL],
        default_action=ClouisleConflictAction.INSTALL,
    )
    preview_mock = AsyncMock(return_value=preview)

    with (
        patch(
            "app.api.v1.endpoints.packages.ClouislePackageService.preview",
            preview_mock,
        ),
        patch(
            "app.api.v1.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = packages_client.post(
            "/api/v1/packages/import/preview",
            data={"team_id": str(uuid4())},
            files={"file": ("tool.clouisle", b"package", "application/octet-stream")},
        )

    assert response.status_code == 200
    assert preview_mock.await_args.kwargs["source"] == ClouisleImportSource.PLATFORM


def test_platform_package_install_uses_platform_source(packages_client):
    install_mock = AsyncMock(return_value=ClouisleImportInstallOut(skipped=True))
    session_id = uuid4()

    with (
        patch(
            "app.api.v1.endpoints.packages.ClouislePackageService.install",
            install_mock,
        ),
        patch(
            "app.api.v1.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = packages_client.post(
            f"/api/v1/packages/import/{session_id}/install",
            json={"action": "install", "dependency_mapping": {}},
        )

    assert response.status_code == 200
    assert install_mock.await_args.kwargs["source"] == ClouisleImportSource.PLATFORM
