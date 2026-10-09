from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import observability
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


@pytest.fixture
def observability_client():
    app = FastAPI()
    app.include_router(observability.router, prefix="/api/v1/admin/observability")

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
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_read_requires_dashboard_permission(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:user:read")]
    response = client.get("/api/v1/admin/observability/summary")
    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_read_uses_dashboard_permission(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    payload = {
        "meta": {
            "window_start": "2026-10-08T00:00:00Z",
            "window_end": "2026-10-08T01:00:00Z",
            "sampled_at": "2026-10-08T01:00:00Z",
            "period": "1h",
            "state": "no_data",
            "sample_count": 0,
        },
        "agents": {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "success_rate": None,
            "p50_ms": None,
            "p95_ms": None,
            "first_token_p95_ms": None,
            "tokens": 0,
        },
        "workflows": {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "success_rate": None,
            "p50_ms": None,
            "p95_ms": None,
            "tokens": 0,
        },
        "trend": [],
        "issues": [],
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.summary",
        new=AsyncMock(return_value=payload),
    ):
        response = client.get("/api/v1/admin/observability/summary?period=15m")
    assert response.status_code == 200
    assert response.json()["data"]["agents"]["success_rate"] is None


def test_alert_mutation_requires_observability_manage(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    response = client.post(f"/api/v1/admin/observability/alerts/{uuid4()}/acknowledge")
    assert response.status_code == 403


def test_alert_mutation_accepts_explicit_manage_permission(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:observability:manage")]
    alert_id = uuid4()
    event = {
        "id": str(alert_id),
        "rule_id": "agent-failure-rate",
        "kind": "agent-failure-rate",
        "severity": "warning",
        "title": "Failure rate",
        "detail": "Threshold exceeded",
        "affected_count": 10,
        "status": "active",
        "opened_at": "2026-10-08T00:00:00Z",
        "resolved_at": None,
        "acknowledged_at": "2026-10-08T01:00:00Z",
        "silenced_until": None,
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.acknowledge_alert",
        new=AsyncMock(return_value=event),
    ):
        response = client.post(
            f"/api/v1/admin/observability/alerts/{alert_id}/acknowledge"
        )
    assert response.status_code == 200
    assert response.json()["data"]["acknowledged_at"] is not None


def test_run_page_limit_is_bounded(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    response = client.get("/api/v1/admin/observability/runs?limit=51")
    assert response.status_code == 422


def test_trace_lookup_is_separate_and_authorized(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    run_id = uuid4()
    run_detail = AsyncMock(return_value=None)
    with patch(
        "app.api.v1.admin.endpoints.observability.service.run_detail", new=run_detail
    ):
        response = client.get(f"/api/v1/admin/observability/runs/agent/{run_id}")
    assert response.status_code == 404
    run_detail.assert_awaited_once_with("agent", run_id)


def test_run_detail_permission_is_checked_before_loading_trace(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:user:read")]
    run_detail = AsyncMock()
    with patch(
        "app.api.v1.admin.endpoints.observability.service.run_detail", new=run_detail
    ):
        response = client.get(f"/api/v1/admin/observability/runs/workflow/{uuid4()}")
    assert response.status_code == 403
    run_detail.assert_not_awaited()


def test_dependency_read_accepts_unavailable_token_counts(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    row = {
        "name": "http",
        "requests": 1,
        "completed": 1,
        "failed": 0,
        "success_rate": 1.0,
        "p50_ms": 10,
        "p95_ms": 10,
        "first_token_p95_ms": None,
        "tokens": None,
        "sample_count": 1,
    }
    payload = {
        "meta": {
            "window_start": "2026-10-08T00:00:00Z",
            "window_end": "2026-10-08T01:00:00Z",
            "sampled_at": "2026-10-08T01:00:00Z",
            "period": "1h",
            "state": "partial",
            "sample_count": 1,
        },
        "models": [],
        "tools": [row],
        "retrieval": [],
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.dependencies",
        new=AsyncMock(return_value=payload),
    ):
        response = client.get("/api/v1/admin/observability/dependencies?period=1h")

    assert response.status_code == 200
    assert response.json()["data"]["tools"][0]["tokens"] is None


@pytest.mark.parametrize("endpoint", ["summary", "runs", "dependencies"])
@pytest.mark.parametrize(
    "bounds",
    [
        {},
        {"start_time": "2026-10-08T12:00:00Z"},
        {"end_time": "2026-10-08T13:00:00Z"},
        {"start_time": "2026-10-08T12:00:00Z", "end_time": "2026-10-08T12:00:00Z"},
        {"start_time": "2026-10-08T13:00:00Z", "end_time": "2026-10-08T12:00:00Z"},
        {"start_time": "2026-10-08T12:00:00", "end_time": "2026-10-08T13:00:00Z"},
        {"start_time": "2026-10-08T12:00:00Z", "end_time": "2026-10-08T13:00:00"},
    ],
)
def test_invalid_custom_window_returns_422(observability_client, endpoint, bounds):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    with patch.object(observability.service.ObservabilityRun, "filter") as query:
        response = client.get(
            f"/api/v1/admin/observability/{endpoint}",
            params={"period": "custom", **bounds},
        )
    assert response.status_code == 422
    query.assert_not_called()


@pytest.mark.parametrize("endpoint", ["summary", "runs", "dependencies"])
def test_custom_window_uses_real_service_and_utc_metadata(
    observability_client, monkeypatch, endpoint
):
    from datetime import UTC, datetime

    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    service = observability.service
    monkeypatch.setattr(service, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(service, "_SNAPSHOT_INFLIGHT", {})

    class EmptyQuery:
        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        def __await__(self):
            async def resolve():
                return []

            return resolve().__await__()

    with patch.object(
        service.ObservabilityRun, "filter", return_value=EmptyQuery()
    ) as query:
        response = client.get(
            f"/api/v1/admin/observability/{endpoint}",
            params={
                "period": "custom",
                "start_time": "2026-10-08T14:00:00+02:00",
                "end_time": "2026-10-08T15:00:00+02:00",
            },
        )
    assert response.status_code == 200
    meta = response.json()["data"]["meta"]
    assert meta["period"] == "custom"
    assert datetime.fromisoformat(meta["window_start"]) == datetime(
        2026, 10, 8, 12, tzinfo=UTC
    )
    assert datetime.fromisoformat(meta["window_end"]) == datetime(
        2026, 10, 8, 13, tzinfo=UTC
    )
    for invocation in query.call_args_list:
        assert invocation.kwargs["submitted_at__gte"] == datetime(
            2026, 10, 8, 12, tzinfo=UTC
        )
        assert invocation.kwargs["submitted_at__lte"] == datetime(
            2026, 10, 8, 13, tzinfo=UTC
        )


@pytest.mark.parametrize("endpoint", ["summary", "runs", "dependencies"])
@pytest.mark.parametrize("period", ["15m", "1h", "24h", "7d"])
@pytest.mark.parametrize("bound", ["start_time", "end_time"])
def test_preset_rejects_explicit_bounds(observability_client, endpoint, period, bound):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    with patch.object(observability.service.ObservabilityRun, "filter") as query:
        response = client.get(
            f"/api/v1/admin/observability/{endpoint}",
            params={
                "period": period,
                bound: "2026-10-08T12:00:00Z",
            },
        )
    assert response.status_code == 422
    query.assert_not_called()


def test_run_detail_returns_loaded_trace(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:dashboard:access")]
    run_id = uuid4()
    payload = {
        "run": {
            "run_id": str(run_id),
            "source": "agent",
            "status": "completed",
            "total_tokens": 3,
            "trace_available": True,
            "trace_complete": True,
        },
        "spans": [],
        "trace": {"complete": True, "expired": False, "recorded_count": 0},
        "meta": {
            "window_start": "2026-10-08T12:00:00Z",
            "window_end": "2026-10-08T13:00:00Z",
            "sampled_at": "2026-10-08T13:00:00Z",
            "period": "1h",
            "state": "fresh",
            "sample_count": 1,
        },
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.run_detail",
        new=AsyncMock(return_value=payload),
    ):
        response = client.get(f"/api/v1/admin/observability/runs/agent/{run_id}")

    assert response.status_code == 200
    assert response.json()["data"]["run"]["total_tokens"] == 3


def test_acknowledge_missing_alert_returns_not_found(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:observability:manage")]
    with patch(
        "app.api.v1.admin.endpoints.observability.service.acknowledge_alert",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            f"/api/v1/admin/observability/alerts/{uuid4()}/acknowledge"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active alert not found"


def test_silence_alert_handles_missing_and_active_events(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:observability:manage")]
    alert_id = uuid4()
    route = f"/api/v1/admin/observability/alerts/{alert_id}/silence"
    with patch(
        "app.api.v1.admin.endpoints.observability.service.silence_alert",
        new=AsyncMock(return_value=None),
    ):
        missing = client.post(route, params={"duration_seconds": 60})
    assert missing.status_code == 404

    event = {
        "id": str(alert_id),
        "rule_id": "agent-failure-rate",
        "kind": "agent-failure-rate",
        "severity": "warning",
        "title": "Failure rate",
        "detail": "Threshold exceeded",
        "affected_count": 2,
        "status": "active",
        "opened_at": "2026-10-08T12:00:00Z",
        "resolved_at": None,
        "acknowledged_at": None,
        "silenced_until": "2026-10-08T13:00:00Z",
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.silence_alert",
        new=AsyncMock(return_value=event),
    ):
        silenced = client.post(route, params={"duration_seconds": 60})

    assert silenced.status_code == 200
    assert silenced.json()["data"]["silenced_until"] is not None


def test_alert_rule_update_handles_missing_and_existing_rules(observability_client):
    client, user = observability_client
    user.roles = [_Role("admin:observability:manage")]
    route = "/api/v1/admin/observability/alerts/rules/agent-failure-rate"
    with patch(
        "app.api.v1.admin.endpoints.observability.service.update_rule",
        new=AsyncMock(return_value=None),
    ):
        missing = client.put(route, json={"threshold": 0.75})
    assert missing.status_code == 404

    rule = {
        "id": "agent-failure-rate",
        "name": "Agent failure rate",
        "threshold": 0.75,
        "enabled": True,
        "evaluation_window_seconds": 300,
        "recovery_window_seconds": 60,
        "updated_at": "2026-10-08T13:00:00Z",
    }
    with patch(
        "app.api.v1.admin.endpoints.observability.service.update_rule",
        new=AsyncMock(return_value=rule),
    ):
        updated = client.put(route, json={"threshold": 0.75})

    assert updated.status_code == 200
    assert updated.json()["data"]["threshold"] == 0.75
