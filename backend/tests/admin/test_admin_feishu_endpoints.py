from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import feishu
from app.schemas.response import BusinessError, ResponseCode


def _integration(
    *,
    app_id="cli-test",
    app_secret="encrypted",
    enabled=True,
    capabilities=("directory_sync", "notification"),
    department_ids=None,
):
    config = {"app_id": app_id, "department_ids": ["0"]}
    if department_ids is not None:
        config["department_ids"] = department_ids
    return SimpleNamespace(
        config=config,
        credentials={"app_secret": app_secret} if app_secret else {},
        is_enabled=enabled,
        enabled_capabilities=list(capabilities),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper", "integration", "expected"),
    [
        ("_configured_client", _integration(app_id=""), "feishu_not_configured"),
        (
            "_configured_client",
            _integration(enabled=False),
            "feishu_directory_sync_disabled",
        ),
        (
            "_configured_notification_client",
            _integration(app_secret=""),
            "feishu_notification_not_configured",
        ),
        (
            "_configured_notification_client",
            _integration(capabilities=("directory_sync",)),
            "feishu_notification_not_enabled",
        ),
    ],
)
async def test_configured_feishu_clients_reject_unavailable_configuration(
    monkeypatch, helper, integration, expected
):
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )
    new_client = MagicMock(side_effect=AssertionError("invalid config made a client"))
    monkeypatch.setattr(feishu, "_new_client", new_client)

    with pytest.raises(BusinessError) as raised:
        await getattr(feishu, helper)()

    assert raised.value.msg_key == expected
    new_client.assert_not_called()


@pytest.mark.asyncio
async def test_configured_feishu_client_accepts_enabled_directory(monkeypatch):
    client = object()
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=_integration())
    )
    new_client = MagicMock(return_value=client)
    monkeypatch.setattr(feishu, "_new_client", new_client)

    assert await feishu._configured_client() is client
    new_client.assert_called_once_with("cli-test", "encrypted")


def test_feishu_agent_chat_secret_normalization_branches():
    normalize = feishu.FeishuAgentChatConfigUpdate.normalize_secret

    assert normalize(None) is None
    assert normalize("   ") is None
    assert normalize("  sufficiently-long  ") == "sufficiently-long"
    with pytest.raises(ValueError, match="feishu_agent_chat_secret_too_short"):
        normalize(" short ")


@pytest.mark.asyncio
async def test_test_recipient_search_without_term_returns_bindings(monkeypatch):
    from app.models.feishu_user import FeishuUser

    user = SimpleNamespace(id=uuid4(), username="ada", email="ada@example.com")
    binding = SimpleNamespace(user_id=user.id, user=user)
    calls = {}

    class Query:
        def select_related(self, *fields):
            calls["select_related"] = fields
            return self

        def filter(self, *args, **kwargs):
            calls["filter"] = (args, kwargs)
            return self

        def order_by(self, *fields):
            calls["order_by"] = fields
            return self

        def limit(self, count):
            calls["limit"] = count
            return self

        def __await__(self):
            async def rows():
                return [binding]

            return rows().__await__()

    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=_integration())
    )
    monkeypatch.setattr(FeishuUser, "filter", lambda **_kwargs: Query())

    response = await feishu.list_test_recipients(
        search="  ", current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"] == [
        {"id": str(user.id), "username": "ada", "email": "ada@example.com"}
    ]
    assert "filter" not in calls


@pytest.mark.asyncio
async def test_update_feishu_config_rejects_whitespace_app_id(monkeypatch):
    update = AsyncMock(side_effect=AssertionError("invalid app id was persisted"))
    monkeypatch.setattr(feishu, "update_builtin_config", update)

    with pytest.raises(BusinessError) as raised:
        await feishu.update_config(
            request=MagicMock(),
            data=feishu.FeishuConfigUpdate(app_id="   "),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert raised.value.code == ResponseCode.VALIDATION_ERROR
    update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("department_ids", [[], "0"])
async def test_sync_rejects_missing_or_invalid_department_scope(
    monkeypatch, department_ids
):
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=_integration(department_ids=department_ids)),
    )
    configured_client = AsyncMock(side_effect=AssertionError("sync ran without scope"))
    monkeypatch.setattr(feishu, "_configured_client", configured_client)

    with pytest.raises(BusinessError) as raised:
        await feishu.sync_contacts(
            request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
        )

    assert raised.value.code == ResponseCode.VALIDATION_ERROR
    configured_client.assert_not_awaited()
