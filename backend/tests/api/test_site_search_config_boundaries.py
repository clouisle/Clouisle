from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import tools as admin
from app.api.v1.endpoints import tools as platform
from app.schemas.response import BusinessError


@pytest.mark.anyio
@pytest.mark.parametrize("module", [admin, platform])
async def test_generic_search_config_routes_never_return_or_mutate_secrets(
    module, monkeypatch
):
    from app.models.tool_config import ToolConfig

    monkeypatch.setattr(
        ToolConfig,
        "filter",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy search access must be rejected before DB")
        ),
    )
    user = SimpleNamespace(is_superuser=True)
    for team_id in [None, uuid4()]:
        operations = [
            module.get_tool_config("web_search", team_id=team_id, current_user=user),
            module.create_tool_config(
                data={
                    "tool_name": "web_search",
                    "credentials": {"TAVILY_API_KEY": "secret"},
                },
                team_id=team_id,
                current_user=user,
                **({"request": None} if module is platform else {}),
            ),
            module.update_tool_config(
                "web_search",
                data={"credentials": {}},
                team_id=team_id,
                current_user=user,
                **({"request": None} if module is platform else {}),
            ),
            module.delete_tool_config(
                "web_search",
                team_id=team_id,
                current_user=user,
                **({"request": None} if module is platform else {}),
            ),
        ]
        for operation in operations:
            with pytest.raises(BusinessError) as exc:
                await operation
            assert exc.value.msg_key == "web_search_site_managed"


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
