from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import packages as admin_packages
from app.models.package_import import ClouisleImportSource
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallOut,
    ClouisleImportPreviewOut,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _SessionQuery:
    def __init__(self, session):
        self._session = session

    async def first(self):
        return self._session


@pytest.fixture
def admin_packages_client():
    app = FastAPI()
    app.include_router(admin_packages.router, prefix="/api/v1/admin/packages")

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

    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        roles=[],
    )

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def _preview(resource_type: ClouisleResourceType) -> ClouisleImportPreviewOut:
    return ClouisleImportPreviewOut(
        session_id=uuid4(),
        package_id=uuid4(),
        resource_type=resource_type,
        resource_name="Imported Resource",
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


def test_admin_package_preview_requires_admin_kb_permission(admin_packages_client):
    client, user = admin_packages_client
    user.roles = [_Role("kb:create")]

    with (
        patch(
            "app.api.v1.admin.endpoints.packages.ClouislePackageService._read_package",
            return_value=(
                SimpleNamespace(resource_type=ClouisleResourceType.KNOWLEDGE_BASE),
                {},
            ),
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/v1/admin/packages/import/preview",
            data={"team_id": str(uuid4())},
            files={"file": ("kb.clouisle", b"package", "application/octet-stream")},
        )

    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_admin_package_preview_uses_admin_source(admin_packages_client):
    client, user = admin_packages_client
    user.roles = [_Role("admin:knowledge-base:create")]

    preview = _preview(ClouisleResourceType.KNOWLEDGE_BASE)
    preview_mock = AsyncMock(return_value=preview)
    with (
        patch(
            "app.api.v1.admin.endpoints.packages.ClouislePackageService._read_package",
            return_value=(
                SimpleNamespace(resource_type=ClouisleResourceType.KNOWLEDGE_BASE),
                {},
            ),
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.ClouislePackageService.preview",
            preview_mock,
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/v1/admin/packages/import/preview",
            data={"team_id": str(uuid4())},
            files={"file": ("kb.clouisle", b"package", "application/octet-stream")},
        )

    assert response.status_code == 200
    assert preview_mock.await_args.kwargs["source"] == ClouisleImportSource.ADMIN
    assert preview_mock.await_args.kwargs["check_permission"] is False
    assert preview_mock.await_args.kwargs["check_team_membership"] is False


def test_admin_package_preview_rejects_platform_resource_types(admin_packages_client):
    client, user = admin_packages_client
    user.roles = [_Role("admin:capability:create")]

    with (
        patch(
            "app.api.v1.admin.endpoints.packages.ClouislePackageService._read_package",
            return_value=(
                SimpleNamespace(resource_type=ClouisleResourceType.AGENT),
                {},
            ),
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/v1/admin/packages/import/preview",
            data={"team_id": str(uuid4())},
            files={"file": ("agent.clouisle", b"package", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert response.json()["msg"]


def test_admin_package_install_filters_admin_sessions(admin_packages_client):
    client, user = admin_packages_client
    user.roles = [_Role("admin:capability:create")]
    session_id = uuid4()
    install_mock = AsyncMock(return_value=ClouisleImportInstallOut(skipped=True))

    with (
        patch(
            "app.api.v1.admin.endpoints.packages.ClouisleImportSession.filter",
            return_value=_SessionQuery(
                SimpleNamespace(resource_type=ClouisleResourceType.TOOL.value)
            ),
        ) as filter_mock,
        patch(
            "app.api.v1.admin.endpoints.packages.ClouislePackageService.install",
            install_mock,
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            f"/api/v1/admin/packages/import/{session_id}/install",
            json={"action": "install", "dependency_mapping": {}},
        )

    assert response.status_code == 200
    assert filter_mock.call_args.kwargs == {
        "id": session_id,
        "source": ClouisleImportSource.ADMIN,
    }
    assert install_mock.await_args.kwargs["source"] == ClouisleImportSource.ADMIN
    assert install_mock.await_args.kwargs["check_permission"] is False
    assert install_mock.await_args.kwargs["check_team_membership"] is False


def test_admin_package_install_update_requires_update_permission(admin_packages_client):
    client, user = admin_packages_client
    user.roles = [_Role("admin:capability:create")]

    with (
        patch(
            "app.api.v1.admin.endpoints.packages.ClouisleImportSession.filter",
            return_value=_SessionQuery(
                SimpleNamespace(resource_type=ClouisleResourceType.TOOL.value)
            ),
        ),
        patch(
            "app.api.v1.admin.endpoints.packages.AuditLogService.log",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            f"/api/v1/admin/packages/import/{uuid4()}/install",
            json={"action": "update", "dependency_mapping": {}},
        )

    assert response.status_code == 403
    assert response.json()["code"] == 3000
