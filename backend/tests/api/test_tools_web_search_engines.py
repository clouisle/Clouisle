"""Site-enabled web search providers exposed to tool configuration surfaces."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import tools
from app.schemas.response import BusinessError
from app.schemas.web_search import WebSearchConfigOut
from app.services import web_search_config


def _config(**overrides) -> WebSearchConfigOut:
    values = {
        "default_engine": "tavily",
        "tavily_enabled": False,
        "bocha_enabled": False,
        "searxng_enabled": False,
        "tavily_api_key_configured": False,
        "bocha_api_key_configured": False,
        "searxng_base_url": "",
        "searxng_auth_token_configured": False,
        "legacy_credentials_present": False,
    }
    values.update(overrides)
    return WebSearchConfigOut(**values)


def _user(*permission_codes: str):
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        is_active=True,
        locale="en",
        roles=[
            SimpleNamespace(
                permissions=[SimpleNamespace(code=code) for code in permission_codes]
            )
        ],
    )


@pytest.mark.asyncio
async def test_returns_only_enabled_providers_in_catalog_order(monkeypatch):
    monkeypatch.setattr(
        tools,
        "get_web_search_config",
        AsyncMock(return_value=_config(bocha_enabled=True, searxng_enabled=True)),
    )

    response = await tools.list_web_search_engines(_user("tool:read"))

    assert response["data"] == ["bocha", "searxng"]
    assert "auto" not in response["data"]
    assert "tavily" not in response["data"]


@pytest.mark.asyncio
async def test_returns_every_enabled_provider(monkeypatch):
    monkeypatch.setattr(
        tools,
        "get_web_search_config",
        AsyncMock(
            return_value=_config(
                tavily_enabled=True,
                bocha_enabled=True,
                searxng_enabled=True,
            )
        ),
    )

    response = await tools.list_web_search_engines(_user("tool:read"))

    assert response["data"] == ["tavily", "bocha", "searxng"]


@pytest.mark.asyncio
async def test_returns_no_providers_when_all_disabled(monkeypatch):
    monkeypatch.setattr(
        tools, "get_web_search_config", AsyncMock(return_value=_config())
    )

    response = await tools.list_web_search_engines(_user("tool:read"))

    assert response["data"] == []


@pytest.mark.asyncio
async def test_returns_no_providers_when_site_configuration_missing(monkeypatch):
    # No ToolConfig row at all; the configuration service reports every
    # provider as disabled rather than raising.
    monkeypatch.setattr(
        web_search_config, "_get_global_config", AsyncMock(return_value=None)
    )

    response = await tools.list_web_search_engines(_user("tool:read"))

    assert response["data"] == []


@pytest.mark.asyncio
async def test_response_never_leaks_configuration_details(monkeypatch):
    monkeypatch.setattr(
        tools,
        "get_web_search_config",
        AsyncMock(
            return_value=_config(
                default_engine="searxng",
                searxng_enabled=True,
                searxng_base_url="https://searxng.internal.example",
                searxng_auth_token_configured=True,
                tavily_api_key_configured=True,
                legacy_credentials_present=True,
            )
        ),
    )

    response = await tools.list_web_search_engines(_user("tool:read"))

    assert response["data"] == ["searxng"]
    serialized = repr(response)
    assert "searxng.internal.example" not in serialized
    assert "https://" not in serialized
    assert "configured" not in serialized
    assert "legacy" not in serialized


def _http_app(user=None) -> FastAPI:
    app = FastAPI()
    app.include_router(tools.router, prefix="/tools")

    if user is not None:

        async def current_user():
            return user

        app.dependency_overrides[deps.get_current_active_user] = current_user

    @app.exception_handler(BusinessError)
    async def _business_error(_, exc: BusinessError):
        return JSONResponse({"error": exc.msg_key}, status_code=exc.status_code)

    return app


def test_http_response_is_redacted_and_reaches_tool_readers(monkeypatch):
    monkeypatch.setattr(
        tools,
        "get_web_search_config",
        AsyncMock(
            return_value=_config(
                default_engine="searxng",
                searxng_enabled=True,
                searxng_base_url="https://searxng.internal.example",
                searxng_auth_token_configured=True,
                tavily_api_key_configured=True,
                legacy_credentials_present=True,
            )
        ),
    )

    response = TestClient(_http_app(_user("tool:read"))).get(
        "/tools/web-search/engines"
    )

    assert response.status_code == 200
    assert response.json()["data"] == ["searxng"]
    body = response.text
    assert "searxng.internal.example" not in body
    assert "https://" not in body
    assert "configured" not in body
    assert "legacy" not in body
    assert "auto" not in body


def test_http_request_without_tool_read_is_denied(monkeypatch):
    monkeypatch.setattr(
        tools, "get_web_search_config", AsyncMock(return_value=_config())
    )

    response = TestClient(_http_app(_user())).get("/tools/web-search/engines")

    assert response.status_code == 403
    assert response.json() == {"error": "operation_not_permitted"}
