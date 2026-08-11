from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import team_models
from app.schemas.model import (
    TeamModelBatchCreate,
    TeamModelBatchDelete,
    TeamModelCreate,
    TeamModelUpdate,
)
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberRole


class Query:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    async def first(self):
        return self.result

    async def values_list(self, *args, **kwargs):
        self.calls.append(("values_list", args, kwargs))
        return self.result

    async def delete(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def model(**overrides):
    values = {
        "id": uuid4(),
        "name": "GPT",
        "provider": "openai",
        "provider_display_name": None,
        "model_id": "gpt-4o",
        "model_type": "chat",
        "is_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def authorization(item=None, **overrides):
    now = datetime.now(UTC)
    item = item or model()
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "model_id": item.id,
        "model": item,
        "daily_token_limit": None,
        "monthly_token_limit": None,
        "daily_request_limit": None,
        "monthly_request_limit": None,
        "daily_tokens_used": 0,
        "monthly_tokens_used": 0,
        "daily_requests_used": 0,
        "monthly_requests_used": 0,
        "is_enabled": True,
        "priority": 0,
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def assert_error(exc_info, code, status_code):
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.anyio
async def test_check_team_admin_permission_covers_missing_denied_and_allowed(
    monkeypatch,
):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(is_superuser=False)

    monkeypatch.setattr(
        team_models.Team,
        "filter",
        MagicMock(side_effect=[Query(None), Query(team), Query(team), Query(team)]),
    )
    monkeypatch.setattr(
        team_models.TeamMember,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(role=TeamMemberRole.MEMBER)),
                Query(SimpleNamespace(role=TeamMemberRole.ADMIN)),
            ]
        ),
    )

    with pytest.raises(BusinessError) as missing:
        await team_models.check_team_admin_permission(team.id, user)
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as no_membership:
        await team_models.check_team_admin_permission(team.id, user)
    assert_error(no_membership, ResponseCode.TEAM_ADMIN_REQUIRED, 403)

    with pytest.raises(BusinessError) as wrong_role:
        await team_models.check_team_admin_permission(team.id, user)
    assert_error(wrong_role, ResponseCode.TEAM_ADMIN_REQUIRED, 403)

    assert await team_models.check_team_admin_permission(team.id, user) is team

    user.is_superuser = True
    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    assert await team_models.check_team_admin_permission(team.id, user) is team


@pytest.mark.anyio
async def test_list_team_models_authorization_and_type_filter(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(is_superuser=False)
    auth = authorization()
    query = Query([auth])
    validate = MagicMock(return_value="validated")

    monkeypatch.setattr(
        team_models.Team,
        "filter",
        MagicMock(side_effect=[Query(None), Query(team), Query(team)]),
    )
    monkeypatch.setattr(
        team_models.TeamMember,
        "filter",
        MagicMock(side_effect=[Query(None), Query(SimpleNamespace())]),
    )
    monkeypatch.setattr(team_models.TeamModel, "filter", MagicMock(return_value=query))
    monkeypatch.setattr(team_models.TeamModelResponse, "model_validate", validate)

    with pytest.raises(BusinessError) as missing:
        await team_models.list_team_models(team.id, current_user=user)
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as denied:
        await team_models.list_team_models(team.id, current_user=user)
    assert_error(denied, ResponseCode.NOT_TEAM_MEMBER, 403)

    response = await team_models.list_team_models(team.id, "chat", user)
    assert response["data"] == ["validated"]
    assert ("filter", (), {"model__model_type": "chat"}) in query.calls
    assert ("order_by", ("-priority", "created_at"), {}) in query.calls
    validate.assert_called_once_with(auth)


@pytest.mark.anyio
async def test_add_team_model_validates_resources_and_duplicate(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    item = model()
    auth_in = TeamModelCreate(model_id=item.id)
    monkeypatch.setattr(
        team_models.Team,
        "filter",
        MagicMock(side_effect=[Query(None), Query(team), Query(team)]),
    )
    monkeypatch.setattr(
        team_models.Model, "filter", MagicMock(side_effect=[Query(None), Query(item)])
    )
    monkeypatch.setattr(
        team_models.TeamModel, "filter", MagicMock(return_value=Query(object()))
    )

    with pytest.raises(BusinessError) as missing_team:
        await team_models.add_team_model(team.id, object(), auth_in, object())
    assert_error(missing_team, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as missing_model:
        await team_models.add_team_model(team.id, object(), auth_in, object())
    assert_error(missing_model, ResponseCode.MODEL_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as duplicate:
        await team_models.add_team_model(team.id, object(), auth_in, object())
    assert duplicate.value.code == ResponseCode.TEAM_MODEL_EXISTS


@pytest.mark.anyio
async def test_add_team_model_returns_provider_data_and_records_side_effects(
    monkeypatch,
):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    item = model(
        provider="anthropic",
        provider_display_name="Acme Anthropic Gateway",
        model_id="claude-sonnet-4-5",
    )
    created = authorization(item, team_id=team.id)
    reloaded = authorization(item, id=created.id, team_id=team.id)
    notify = AsyncMock()
    audit = AsyncMock()

    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(
        team_models.Model, "filter", MagicMock(return_value=Query(item))
    )
    monkeypatch.setattr(
        team_models.TeamModel, "filter", MagicMock(return_value=Query(None))
    )
    monkeypatch.setattr(
        team_models.TeamModel, "create", AsyncMock(return_value=created)
    )
    monkeypatch.setattr(
        team_models.TeamModel, "get", MagicMock(return_value=Query(reloaded))
    )
    monkeypatch.setattr(team_models.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)

    response = await team_models.add_team_model(
        team.id,
        object(),
        TeamModelCreate(model_id=item.id, daily_token_limit=100, priority=3),
        SimpleNamespace(),
    )

    assert response["data"]["model"]["provider"] == "anthropic"
    assert (
        response["data"]["model"]["provider_display_name"] == "Acme Anthropic Gateway"
    )
    assert response["data"]["model"]["model_id"] == "claude-sonnet-4-5"
    notify.assert_awaited_once()
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["metadata"]["model_id"] == str(item.id)


@pytest.mark.anyio
async def test_update_team_model_missing_and_partial_update(monkeypatch):
    item = authorization()
    query = Query(item)
    audit = AsyncMock()
    monkeypatch.setattr(
        team_models.TeamModel,
        "filter",
        MagicMock(side_effect=[Query(None), query]),
    )
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as missing:
        await team_models.update_team_model(
            item.team_id, item.model_id, object(), TeamModelUpdate(), object()
        )
    assert_error(missing, ResponseCode.TEAM_MODEL_NOT_FOUND, 404)

    response = await team_models.update_team_model(
        item.team_id,
        item.model_id,
        object(),
        TeamModelUpdate(daily_token_limit=250, is_enabled=False),
        object(),
    )
    assert response["data"]["daily_token_limit"] == 250
    assert response["data"]["is_enabled"] is False
    item.save.assert_awaited_once()
    assert audit.await_args.kwargs["metadata"]["updated_fields"] == [
        "daily_token_limit",
        "is_enabled",
    ]


@pytest.mark.anyio
async def test_remove_team_model_missing_and_success(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    item = authorization()
    item.team = team
    notify = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(
        team_models.TeamModel,
        "filter",
        MagicMock(side_effect=[Query(None), Query(item)]),
    )
    monkeypatch.setattr(team_models.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as missing:
        await team_models.remove_team_model(
            item.team_id, item.model_id, object(), object()
        )
    assert_error(missing, ResponseCode.TEAM_MODEL_NOT_FOUND, 404)

    response = await team_models.remove_team_model(
        item.team_id, item.model_id, object(), object()
    )
    assert response["data"] == {
        "team_id": str(item.team_id),
        "model_id": str(item.model_id),
    }
    item.delete.assert_awaited_once()
    notify.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_batch_add_skips_existing_and_unknown_models(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    existing_id, unknown_id = uuid4(), uuid4()
    new_model = model()
    created = authorization(new_model, team_id=team.id)
    notify = AsyncMock()
    audit = AsyncMock()

    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(
        team_models.Model, "filter", MagicMock(return_value=Query([new_model]))
    )
    monkeypatch.setattr(
        team_models.TeamModel,
        "filter",
        MagicMock(return_value=Query([existing_id])),
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(team_models.TeamModel, "create", create)
    monkeypatch.setattr(team_models.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)

    response = await team_models.batch_add_team_models(
        team.id,
        object(),
        TeamModelBatchCreate(
            model_ids=[existing_id, unknown_id, new_model.id], daily_token_limit=1000
        ),
        object(),
    )

    assert [entry["model_id"] for entry in response["data"]] == [new_model.id]
    create.assert_awaited_once()
    notify.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_batch_add_missing_team_and_empty_result_omit_notification(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    model_id = uuid4()
    notify = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(
        team_models.Team, "filter", MagicMock(side_effect=[Query(None), Query(team)])
    )
    monkeypatch.setattr(team_models.Model, "filter", MagicMock(return_value=Query([])))
    monkeypatch.setattr(
        team_models.TeamModel, "filter", MagicMock(return_value=Query([]))
    )
    monkeypatch.setattr(team_models.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)
    batch = TeamModelBatchCreate(model_ids=[model_id])

    with pytest.raises(BusinessError) as missing:
        await team_models.batch_add_team_models(team.id, object(), batch, object())
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    response = await team_models.batch_add_team_models(
        team.id, object(), batch, object()
    )
    assert response["data"] == []
    notify.assert_not_awaited()
    audit.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("deleted_count", "names", "notification_count"),
    [(0, ["GPT"], 0), (1, [], 0), (2, ["GPT", "Claude"], 1)],
)
async def test_batch_remove_notification_conditions(
    monkeypatch, deleted_count, names, notification_count
):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    model_ids = [uuid4(), uuid4()]
    team_model_rows = [
        SimpleNamespace(model=SimpleNamespace(name=name)) for name in names
    ]
    notify = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(
        team_models.TeamModel,
        "filter",
        MagicMock(side_effect=[Query(team_model_rows), Query(deleted_count)]),
    )
    monkeypatch.setattr(team_models.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(team_models.AuditLogService, "log", audit)

    response = await team_models.batch_remove_team_models(
        team.id,
        object(),
        TeamModelBatchDelete(model_ids=model_ids),
        object(),
    )
    assert response["data"]["deleted_count"] == deleted_count
    assert notify.await_count == notification_count
    assert audit.await_args.kwargs["metadata"]["model_names"] == names


@pytest.mark.anyio
async def test_batch_remove_requires_existing_team(monkeypatch):
    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(None)))
    with pytest.raises(BusinessError) as missing:
        await team_models.batch_remove_team_models(
            uuid4(),
            object(),
            TeamModelBatchDelete(model_ids=[uuid4()]),
            object(),
        )
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint",
    [team_models.get_team_available_models, team_models.get_team_models_quota],
)
async def test_read_endpoints_reject_missing_team_and_nonmembers(monkeypatch, endpoint):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(is_superuser=False)
    monkeypatch.setattr(
        team_models.Team,
        "filter",
        MagicMock(side_effect=[Query(None), Query(team)]),
    )
    monkeypatch.setattr(
        team_models.TeamMember, "filter", MagicMock(return_value=Query(None))
    )

    with pytest.raises(BusinessError) as missing:
        await endpoint(team.id, current_user=user)
    assert_error(missing, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as denied:
        await endpoint(team.id, current_user=user)
    assert_error(denied, ResponseCode.NOT_TEAM_MEMBER, 403)


@pytest.mark.anyio
async def test_available_models_filters_type_and_preserves_provider(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    item = model(provider="anthropic", model_id="claude-sonnet-4-5")
    query = Query([authorization(item)])
    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(team_models.TeamModel, "filter", MagicMock(return_value=query))

    response = await team_models.get_team_available_models(
        team.id, "chat", SimpleNamespace(is_superuser=True)
    )
    assert response["data"] == [
        {
            "id": item.id,
            "name": "GPT",
            "provider": "anthropic",
            "provider_display_name": None,
            "model_id": "claude-sonnet-4-5",
            "model_type": "chat",
        }
    ]
    assert ("filter", (), {"model__model_type": "chat"}) in query.calls


@pytest.mark.anyio
async def test_quota_reports_unlimited_and_daily_or_monthly_exceeded(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    unlimited = authorization()
    daily = authorization(
        daily_token_limit=100,
        daily_tokens_used=100,
        monthly_token_limit=1000,
        monthly_tokens_used=250,
    )
    monthly = authorization(
        daily_token_limit=100,
        daily_tokens_used=25,
        monthly_token_limit=200,
        monthly_tokens_used=250,
    )
    monkeypatch.setattr(team_models.Team, "filter", MagicMock(return_value=Query(team)))
    monkeypatch.setattr(
        team_models.TeamModel,
        "filter",
        MagicMock(return_value=Query([unlimited, daily, monthly])),
    )

    response = await team_models.get_team_models_quota(
        team.id, SimpleNamespace(is_superuser=True)
    )
    rows = response["data"]
    assert rows[0]["daily_token_percent"] is None
    assert rows[0]["monthly_token_percent"] is None
    assert rows[0]["is_quota_exceeded"] is False
    assert rows[1]["daily_token_percent"] == 100.0
    assert rows[1]["monthly_token_percent"] == 25.0
    assert rows[1]["is_quota_exceeded"] is True
    assert rows[2]["daily_token_percent"] == 25.0
    assert rows[2]["monthly_token_percent"] == 125.0
    assert rows[2]["is_quota_exceeded"] is True
