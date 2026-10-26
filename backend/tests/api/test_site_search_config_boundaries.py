from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import tools as admin
from app.schemas.response import BusinessError


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/web-search/config", None),
        (
            "put",
            "/web-search/config",
            {
                "default_engine": "tavily",
                "tavily_enabled": False,
                "bocha_enabled": False,
            },
        ),
        ("post", "/web-search/test", {"query": "Shanghai weather"}),
    ],
)
def test_site_search_configuration_requires_admin_permissions(method, path, payload):
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin/tools")
    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def current_user():
        return user

    @app.exception_handler(BusinessError)
    async def denied(_, exc):
        return JSONResponse({"error": exc.msg_key}, status_code=exc.status_code)

    app.dependency_overrides[deps.get_current_active_user] = current_user
    response = getattr(TestClient(app), method)(
        "/admin/tools" + path, **({"json": payload} if payload is not None else {})
    )
    assert response.status_code == 403
