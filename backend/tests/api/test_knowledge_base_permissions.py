from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


@pytest.fixture
def kb_permission_client():
    app = FastAPI()
    app.include_router(knowledge_bases.router, prefix="/api/v1/knowledge-bases")
    app.include_router(knowledge_bases.router, prefix="/api/v1/admin/knowledge-bases")

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
        locale="en",
    )

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_admin_kb_route_requires_admin_permission(kb_permission_client):
    client, user = kb_permission_client
    user.roles = [_Role("kb:read")]

    response = client.get("/api/v1/admin/knowledge-bases")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


@pytest.mark.anyio
async def test_platform_kb_route_uses_team_membership_not_global_permission(
    kb_permission_client,
):
    _, user = kb_permission_client
    user.roles = [_Role("admin:knowledge-base:read")]
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/knowledge-bases"))

    result = await knowledge_bases.require_kb_read(request, user)

    assert result is user
