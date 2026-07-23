from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import team_models
from app.schemas.response import BusinessError, ResponseCode, error


class _Query:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class _Model:
    value = None
    filters = []

    @classmethod
    def filter(cls, **kwargs):
        cls.filters.append(kwargs)
        return _Query(cls.value)


@pytest.fixture(autouse=True)
def reset_models():
    _Model.value = None
    _Model.filters = []


@pytest.fixture
def quota_client():
    app = FastAPI()
    app.include_router(team_models.router, prefix="/api/v1/teams")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(code=exc.code, msg_key=exc.msg_key),
        )

    async def unauthenticated():
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="not_authenticated",
            status_code=401,
        )

    app.dependency_overrides[deps.get_current_user] = unauthenticated
    return TestClient(app)


def test_quota_route_requires_authentication(quota_client):
    response = quota_client.get(f"/api/v1/teams/{uuid4()}/models/quota")

    assert response.status_code == 401
    assert response.json()["code"] == ResponseCode.UNAUTHORIZED


@pytest.mark.anyio
async def test_quota_rejects_missing_team(monkeypatch):
    monkeypatch.setattr(team_models, "Team", _Model)
    user = SimpleNamespace(id=uuid4(), is_superuser=False)

    with pytest.raises(BusinessError) as caught:
        await team_models.get_team_models_quota(uuid4(), user)

    assert caught.value.status_code == 404
    assert caught.value.msg_key == "team_not_found"


@pytest.mark.anyio
async def test_quota_rejects_non_member(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    _Model.value = team

    class TeamMember(_Model):
        value = None

    monkeypatch.setattr(team_models, "Team", _Model)
    monkeypatch.setattr(team_models, "TeamMember", TeamMember)
    monkeypatch.setattr(team_models, "TeamModel", _Model)
    user = SimpleNamespace(id=uuid4(), is_superuser=False)

    with pytest.raises(BusinessError) as caught:
        await team_models.get_team_models_quota(team.id, user)

    assert caught.value.status_code == 403
    assert caught.value.msg_key == "not_team_member"
    assert len(_Model.filters) == 2


@pytest.mark.anyio
async def test_quota_reports_usage_and_exact_limit_boundaries(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    model_without_limit = SimpleNamespace(
        id=uuid4(), name="Unlimited", model_type="llm"
    )
    model_at_daily_limit = SimpleNamespace(id=uuid4(), name="Daily", model_type="llm")
    model_over_monthly_limit = SimpleNamespace(
        id=uuid4(), name="Monthly", model_type="embedding"
    )
    authorizations = [
        SimpleNamespace(
            model=model_without_limit,
            daily_token_limit=None,
            daily_tokens_used=0,
            monthly_token_limit=0,
            monthly_tokens_used=0,
            is_enabled=True,
        ),
        SimpleNamespace(
            model=model_at_daily_limit,
            daily_token_limit=100,
            daily_tokens_used=100,
            monthly_token_limit=300,
            monthly_tokens_used=100,
            is_enabled=True,
        ),
        SimpleNamespace(
            model=model_over_monthly_limit,
            daily_token_limit=3,
            daily_tokens_used=1,
            monthly_token_limit=200,
            monthly_tokens_used=250,
            is_enabled=False,
        ),
    ]

    class TeamModel(_Model):
        value = authorizations

    _Model.value = team
    monkeypatch.setattr(team_models, "Team", _Model)
    monkeypatch.setattr(team_models, "TeamMember", _Model)
    monkeypatch.setattr(team_models, "TeamModel", TeamModel)
    user = SimpleNamespace(id=uuid4(), is_superuser=False)

    response = await team_models.get_team_models_quota(team.id, user)

    assert response["data"] == [
        {
            "model_id": model_without_limit.id,
            "model_name": "Unlimited",
            "model_type": "llm",
            "daily_token_limit": None,
            "daily_tokens_used": 0,
            "daily_token_percent": None,
            "monthly_token_limit": 0,
            "monthly_tokens_used": 0,
            "monthly_token_percent": None,
            "is_enabled": True,
            "is_quota_exceeded": False,
        },
        {
            "model_id": model_at_daily_limit.id,
            "model_name": "Daily",
            "model_type": "llm",
            "daily_token_limit": 100,
            "daily_tokens_used": 100,
            "daily_token_percent": 100.0,
            "monthly_token_limit": 300,
            "monthly_tokens_used": 100,
            "monthly_token_percent": 33.33,
            "is_enabled": True,
            "is_quota_exceeded": True,
        },
        {
            "model_id": model_over_monthly_limit.id,
            "model_name": "Monthly",
            "model_type": "embedding",
            "daily_token_limit": 3,
            "daily_tokens_used": 1,
            "daily_token_percent": 33.33,
            "monthly_token_limit": 200,
            "monthly_tokens_used": 250,
            "monthly_token_percent": 125.0,
            "is_enabled": False,
            "is_quota_exceeded": True,
        },
    ]


@pytest.mark.anyio
async def test_superuser_gets_empty_quota_without_membership_lookup(monkeypatch):
    team = SimpleNamespace(id=uuid4())

    class TeamModel(_Model):
        value = []

    class TeamMember(_Model):
        @classmethod
        def filter(cls, **_kwargs):
            raise AssertionError("superuser should not require team membership")

    _Model.value = team
    monkeypatch.setattr(team_models, "Team", _Model)
    monkeypatch.setattr(team_models, "TeamMember", TeamMember)
    monkeypatch.setattr(team_models, "TeamModel", TeamModel)
    user = SimpleNamespace(id=uuid4(), is_superuser=True)

    response = await team_models.get_team_models_quota(team.id, user)

    assert response["data"] == []
