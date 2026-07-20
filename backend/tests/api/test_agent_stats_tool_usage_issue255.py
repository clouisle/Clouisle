from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import agent_stats
from app.schemas.response import BusinessError, error


class Query:
    def __init__(self, *, first=None, values=None):
        self.first_result = first
        self.values_result = values or []
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    async def first(self):
        return self.first_result

    async def values(self, *fields):
        return self.values_result


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(agent_stats.router, prefix="/api/v1/agents")

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

    return app


@pytest.fixture
def client(app):
    async def current_user():
        return SimpleNamespace(id=uuid4(), is_active=True)

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_tool_usage_requires_authentication(app):
    response = TestClient(app).get(f"/api/v1/agents/{uuid4()}/stats/tool-usage")

    assert response.status_code == 403


def test_tool_usage_returns_not_found_for_missing_agent(client, monkeypatch):
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query())

    response = client.get(f"/api/v1/agents/{uuid4()}/stats/tool-usage")

    assert response.status_code == 404
    assert response.json()["code"] == 4000


def test_tool_usage_aggregates_supported_shapes_for_24_hours(client, monkeypatch):
    agent_id = uuid4()
    query = Query(
        values=[
            {"tool_calls": [{"function": {"name": "search"}}, {"name": "fetch"}]},
            {"tool_calls": [{"name": "search"}, "invalid", {}]},
            {"tool_calls": None},
        ]
    )
    monkeypatch.setattr(
        agent_stats.Agent,
        "filter",
        lambda **kwargs: Query(first=SimpleNamespace(id=agent_id)),
    )
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **kwargs: query)

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "24h"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "period": "24h",
        "tools": [{"name": "search", "count": 2}, {"name": "fetch", "count": 1}],
        "total_calls": 3,
    }
    assert len(query.filters) == 1
    assert "created_at__gte" in query.filters[0]


def test_tool_usage_all_period_keeps_empty_result_unfiltered(client, monkeypatch):
    agent_id = uuid4()
    query = Query()
    monkeypatch.setattr(
        agent_stats.Agent,
        "filter",
        lambda **kwargs: Query(first=SimpleNamespace(id=agent_id)),
    )
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **kwargs: query)

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "all"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"period": "all", "tools": [], "total_calls": 0}
    assert query.filters == []
