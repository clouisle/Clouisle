from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.api.v1.admin.endpoints import feishu
from app.core.i18n import t as translate
from app.integrations.feishu import (
    FeishuAPIError,
    FeishuDirectoryUser,
)
from app.integrations.credentials import IntegrationSecretError
from app.schemas.response import BusinessError, ResponseCode


def _client(**overrides):
    client = SimpleNamespace(list_users=AsyncMock(), list_departments=AsyncMock())
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


@pytest.mark.asyncio
async def test_test_recipients_requires_enabled_notification_capability(monkeypatch):
    from app.models.feishu_user import FeishuUser

    monkeypatch.setattr(
        FeishuUser,
        "filter",
        MagicMock(side_effect=AssertionError("recipient bindings must not be queried")),
    )
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(
            return_value=SimpleNamespace(is_enabled=True, enabled_capabilities=[])
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.list_test_recipients(
            search="", current_user=SimpleNamespace(id=uuid4())
        )

    assert exc_info.value.msg_key == "feishu_notification_not_enabled"


@pytest.mark.asyncio
async def test_sync_reports_feishu_rejection_reason_without_internal_details(
    monkeypatch,
):
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(
                    side_effect=FeishuAPIError(
                        "Feishu API HTTP 400 (code 41050): no user authority error",
                        detail='{"code":41050,"msg":"no user authority error"}',
                    )
                )
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    error = exc_info.value
    assert error.code == ResponseCode.BAD_REQUEST
    assert error.msg_key == "feishu_api_error"
    assert "41050" in error.kwargs["error"]
    assert "no user authority error" in error.kwargs["error"]
    # The rendered message is what the admin sees in the integrations page.
    assert len(translate("feishu_api_error", lang="en", **error.kwargs)) < 200


@pytest.mark.asyncio
async def test_sync_reports_undecryptable_secret_as_actionable_config_error(
    monkeypatch,
):
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            side_effect=IntegrationSecretError(
                "Stored Feishu app secret cannot be decrypted"
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "feishu_secret_undecryptable"


@pytest.mark.asyncio
async def test_sync_keeps_unexpected_failures_generic(monkeypatch):
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(side_effect=RuntimeError("db down"))
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.UNKNOWN_ERROR
    assert exc_info.value.msg_key == "internal_error"


@pytest.mark.asyncio
async def test_sync_returns_synced_counts(monkeypatch):
    members = [
        FeishuDirectoryUser(
            user_id="u1",
            open_id="o1",
            union_id=None,
            name="Ada",
            email="ada@example.com",
            avatar_url=None,
        )
    ]
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(return_value=members),
                list_departments=AsyncMock(
                    return_value=[
                        SimpleNamespace(
                            department_id="0",
                            name="Acme Inc.",
                            children=[
                                SimpleNamespace(department_id="dept-a", children=[])
                            ],
                        )
                    ]
                ),
            )
        ),
    )
    synced = SimpleNamespace(created=1, updated=2, skipped=3)
    monkeypatch.setattr(feishu, "sync_directory_users", AsyncMock(return_value=synced))
    monkeypatch.setattr(feishu, "sync_department_teams", AsyncMock(return_value=2))
    response = await feishu.sync_contacts(
        request=MagicMock(),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"] == {
        "created": 1,
        "updated": 2,
        "skipped": 3,
        "teams_created": 2,
    }


@pytest.mark.asyncio
async def test_company_department_scope_syncs_company_and_descendant_teams(monkeypatch):
    members = [
        FeishuDirectoryUser(
            user_id="u1",
            open_id="o1",
            union_id=None,
            name="Ada",
            email=None,
            avatar_url=None,
            department_ids=frozenset({"dept-a"}),
        )
    ]
    company = SimpleNamespace(
        department_id="0",
        name="Company",
        children=[
            SimpleNamespace(department_id="dept-a", name="Engineering", children=[])
        ],
    )
    client = _client(
        list_users=AsyncMock(return_value=members),
        list_departments=AsyncMock(return_value=[company]),
    )
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["0"]})),
    )
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        feishu,
        "sync_directory_users",
        AsyncMock(return_value=SimpleNamespace(created=1, updated=0, skipped=0)),
    )
    sync_teams = AsyncMock(return_value=2)
    monkeypatch.setattr(feishu, "sync_department_teams", sync_teams)

    response = await feishu.sync_contacts(
        request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"]["teams_created"] == 2
    assert [
        department.department_id for department in sync_teams.await_args.args[0]
    ] == ["0", "dept-a"]
    assert sync_teams.await_args.args[1] == members
    assert client.list_users.await_args.args[0] == ["0", "dept-a"]


@pytest.mark.asyncio
async def test_department_scope_accepts_company_root_id(monkeypatch):
    client = _client(
        list_departments=AsyncMock(
            return_value=[SimpleNamespace(department_id="dept-a", children=[])]
        )
    )
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        feishu,
        "update_builtin_config",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(feishu.AuditLogService, "log", AsyncMock())

    response = await feishu.update_department_scope(
        request=MagicMock(),
        data=feishu.FeishuDepartmentScopeUpdate(department_ids=["0"]),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"] == {"department_ids": ["0"]}


@pytest.mark.asyncio
async def test_feishu_config_reads_unified_non_secret_fields(monkeypatch):
    integration = SimpleNamespace(
        config={"app_id": "cli-test", "department_ids": ["0"]},
        credentials={"app_secret": "encrypted"},
        is_enabled=True,
    )
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )
    response = await feishu.get_config(current_user=SimpleNamespace(id=uuid4()))
    assert response["data"] == {
        "app_id": "cli-test",
        "department_ids": ["0"],
        "app_secret_configured": True,
        "is_enabled": True,
    }
    assert "encrypted" not in str(response)


@pytest.mark.asyncio
async def test_feishu_config_updates_credentials_without_changing_feature_selection(
    monkeypatch,
):
    integration = SimpleNamespace(
        id=uuid4(),
        config={"department_ids": ["0"]},
        credentials={"app_secret": "encrypted"},
        is_enabled=True,
    )
    update = AsyncMock(return_value=integration)
    monkeypatch.setattr(feishu, "update_builtin_config", update)
    monkeypatch.setattr(feishu.AuditLogService, "log", AsyncMock())
    response = await feishu.update_config(
        request=MagicMock(),
        data=feishu.FeishuConfigUpdate(app_id=" cli-test ", app_secret=" new-secret "),
        current_user=SimpleNamespace(id=uuid4()),
    )
    update.assert_awaited_once_with(
        "feishu", {"app_id": "cli-test"}, {"app_secret": "new-secret"}
    )
    assert response["data"]["app_secret_configured"]
    assert "new-secret" not in str(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "integration,expected_key",
    [
        # Missing app ID or app secret: the administrator must save credentials first.
        (
            SimpleNamespace(
                config={"app_id": "", "department_ids": []},
                credentials={"app_secret": "encrypted"},
                is_enabled=True,
                enabled_capabilities=["directory_sync"],
            ),
            "feishu_not_configured",
        ),
        (
            SimpleNamespace(
                config={"app_id": "cli-test"},
                credentials={},
                is_enabled=True,
                enabled_capabilities=["directory_sync"],
            ),
            "feishu_not_configured",
        ),
        # Saved credentials but the directory capability is off.
        (
            SimpleNamespace(
                config={"app_id": "cli-test"},
                credentials={"app_secret": "encrypted"},
                is_enabled=False,
                enabled_capabilities=["directory_sync"],
            ),
            "feishu_directory_sync_disabled",
        ),
        (
            SimpleNamespace(
                config={"app_id": "cli-test"},
                credentials={"app_secret": "encrypted"},
                is_enabled=True,
                enabled_capabilities=["user_login"],
            ),
            "feishu_directory_sync_disabled",
        ),
    ],
)
async def test_configured_client_reports_actionable_errors(
    monkeypatch, integration, expected_key
):
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )

    with pytest.raises(BusinessError) as exc:
        await feishu._configured_client()

    assert exc.value.code == ResponseCode.BAD_REQUEST
    assert exc.value.msg_key == expected_key


@pytest.mark.parametrize(
    "key", ["feishu_not_configured", "feishu_directory_sync_disabled"]
)
def test_feishu_error_messages_are_translated(key):
    from app.core.i18n import has_translation, t

    assert has_translation(key, "en")
    assert has_translation(key, "zh")
    assert t(key, lang="zh") != t(key, lang="en")


@pytest.mark.asyncio
async def test_connection_check_uses_token_authentication_without_directory_scope(
    monkeypatch,
):
    client = _client(check_connection=AsyncMock())
    monkeypatch.setattr(
        feishu, "_configured_auth_client", AsyncMock(return_value=client)
    )

    response = await feishu.check_connection(current_user=SimpleNamespace())

    assert response["data"] == {"status": "ok"}
    client.check_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_test_message_only_sends_to_the_selected_active_binding(monkeypatch):
    user_id = uuid4()
    binding = SimpleNamespace(feishu_user_id="ou-bound")

    class BindingQuery:
        async def first(self):
            return binding

    monkeypatch.setattr(
        "app.models.feishu_user.FeishuUser.filter", lambda **kwargs: BindingQuery()
    )
    client = _client(send_user_message=AsyncMock())
    monkeypatch.setattr(
        feishu, "_configured_notification_client", AsyncMock(return_value=client)
    )

    response = await feishu.send_test_message(
        feishu.FeishuTestMessageRequest(
            user_id=str(user_id),
            title="  Health check  ",
            content="  Sent only to me.  ",
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"] == {"status": "sent"}
    client.send_user_message.assert_awaited_once_with(
        "ou-bound", "Health check", "Sent only to me."
    )


@pytest.mark.asyncio
async def test_test_message_rejects_unbound_user_without_sending(monkeypatch):
    class BindingQuery:
        async def first(self):
            return None

    monkeypatch.setattr(
        "app.models.feishu_user.FeishuUser.filter", lambda **kwargs: BindingQuery()
    )
    monkeypatch.setattr(feishu, "_configured_notification_client", AsyncMock())

    with pytest.raises(BusinessError) as exc:
        await feishu.send_test_message(
            feishu.FeishuTestMessageRequest(
                user_id=str(uuid4()), title="Test", content="Test"
            ),
            current_user=SimpleNamespace(),
        )

    assert exc.value.msg_key == "feishu_test_recipient_unavailable"


@pytest.mark.asyncio
async def test_config_update_with_blank_secret_preserves_existing_credential(
    monkeypatch,
):
    integration = SimpleNamespace(
        id=uuid4(),
        config={"department_ids": ["dept-a"]},
        credentials={"app_secret": "already-encrypted"},
        is_enabled=True,
    )
    update = AsyncMock(return_value=integration)
    monkeypatch.setattr(feishu, "update_builtin_config", update)
    monkeypatch.setattr(feishu.AuditLogService, "log", AsyncMock())

    response = await feishu.update_config(
        request=MagicMock(),
        data=feishu.FeishuConfigUpdate(app_id=" cli-updated ", app_secret="   "),
        current_user=SimpleNamespace(id=uuid4()),
    )

    update.assert_awaited_once_with("feishu", {"app_id": "cli-updated"}, None)
    assert response["data"]["app_secret_configured"] is True
    assert "already-encrypted" not in str(response)


@pytest.mark.parametrize("value", ["   "])
def test_feishu_source_validators_reject_blank_required_names(value):
    from pydantic import ValidationError
    from app.api.v1.admin.endpoints.feishu_knowledge import SourceCreate, SourceUpdate

    with pytest.raises(ValidationError):
        SourceUpdate(name=value)
    with pytest.raises(ValidationError):
        SourceCreate(knowledge_base_id=uuid4(), space_id="  ", name="Docs")
    with pytest.raises(ValidationError):
        SourceCreate(knowledge_base_id=uuid4(), space_id="space", name=value)


def test_feishu_failure_logging_never_contains_provider_body(caplog):
    secret_detail = "provider echoed tenant-app-secret"

    with caplog.at_level("WARNING", logger="app.api.v1.admin.endpoints.feishu"):
        feishu._feishu_failure(
            FeishuAPIError(
                "Feishu API HTTP 403 (code 131006): denied",
                detail=secret_detail,
                code=131006,
                status_code=403,
            ),
            "Feishu test message",
        )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "code=131006" in logged
    assert "status=403" in logged
    assert secret_detail not in logged


def test_optional_feishu_scope_validation_and_failure_mapping():
    from app.integrations.feishu import FeishuDepartment

    tree = [FeishuDepartment("0", "Acme", None, [FeishuDepartment("dept-a", "A", "0")])]
    assert feishu._flatten_department_ids(tree) == {"0", "dept-a"}

    secret_error = feishu._feishu_failure(
        IntegrationSecretError("ciphertext must stay private"), "Feishu request"
    )
    unexpected_error = feishu._feishu_failure(
        RuntimeError("database password"), "Feishu request"
    )
    assert secret_error.msg_key == "feishu_secret_undecryptable"
    assert secret_error.kwargs == {}
    assert unexpected_error.msg_key == "internal_error"
    assert unexpected_error.kwargs == {}


@pytest.mark.asyncio
async def test_test_message_maps_provider_error_without_exposing_provider_details(
    monkeypatch,
):
    from app.models.feishu_user import FeishuUser

    class BindingQuery:
        async def first(self):
            return SimpleNamespace(feishu_user_id="ou-bound")

    monkeypatch.setattr(FeishuUser, "filter", lambda **_kwargs: BindingQuery())
    client = _client(
        send_user_message=AsyncMock(
            side_effect=FeishuAPIError(
                "Feishu API HTTP 403 (code 131006): denied",
                detail="contains-private-provider-context",
            )
        )
    )
    monkeypatch.setattr(
        feishu, "_configured_notification_client", AsyncMock(return_value=client)
    )

    with pytest.raises(BusinessError) as raised:
        await feishu.send_test_message(
            feishu.FeishuTestMessageRequest(
                user_id=str(uuid4()), title="Test", content="Message"
            ),
            current_user=SimpleNamespace(),
        )

    assert raised.value.msg_key == "feishu_api_error"
    assert "contains-private-provider-context" not in raised.value.kwargs.get(
        "error", ""
    )


@pytest.mark.asyncio
async def test_department_scope_rejects_empty_and_unknown_selection_without_persisting(
    monkeypatch,
):
    client = _client(
        list_departments=AsyncMock(
            return_value=[SimpleNamespace(department_id="dept-a", children=[])]
        )
    )
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    update = AsyncMock()
    monkeypatch.setattr(feishu, "update_builtin_config", update)

    for ids in ([], ["   "], ["missing"]):
        with pytest.raises(BusinessError) as raised:
            await feishu.update_department_scope(
                request=MagicMock(),
                data=feishu.FeishuDepartmentScopeUpdate(department_ids=ids or [" "]),
                current_user=SimpleNamespace(id=uuid4()),
            )
        assert raised.value.code == ResponseCode.VALIDATION_ERROR

    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_configured_notification_client_requires_enabled_capability(monkeypatch):
    integration = SimpleNamespace(
        config={"app_id": "cli-test"},
        credentials={"app_secret": "encrypted"},
        is_enabled=True,
        enabled_capabilities=["directory_sync"],
    )
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )

    with pytest.raises(BusinessError) as raised:
        await feishu._configured_notification_client()

    assert raised.value.msg_key == "feishu_notification_not_enabled"


@pytest.mark.asyncio
async def test_test_recipient_search_uses_trimmed_username_or_email_filter(monkeypatch):
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

    integration = SimpleNamespace(
        is_enabled=True, enabled_capabilities=["notification"]
    )
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )
    monkeypatch.setattr(FeishuUser, "filter", lambda **kwargs: Query())

    response = await feishu.list_test_recipients(
        search="  ada  ", current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"] == [
        {"id": str(user.id), "username": "ada", "email": "ada@example.com"}
    ]
    search_filter = calls["filter"][0][0]
    assert search_filter.join_type == "OR"
    assert [child.filters for child in search_filter.children] == [
        {"user__username__icontains": "ada"},
        {"user__email__icontains": "ada"},
    ]
    assert calls["filter"][1] == {}
    assert calls["order_by"] == ("user__username",)
    assert calls["limit"] == 20


@pytest.mark.asyncio
async def test_directory_sync_of_one_subteam_includes_ancestor_and_excludes_siblings(
    monkeypatch,
):
    dept_a = SimpleNamespace(department_id="dept-a", children=[])
    dept_b = SimpleNamespace(department_id="dept-b", children=[])
    company = SimpleNamespace(department_id="0", children=[dept_a, dept_b])
    client = _client(
        list_departments=AsyncMock(return_value=[company]),
        list_users=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        feishu,
        "sync_directory_users",
        AsyncMock(return_value=SimpleNamespace(created=0, updated=0, skipped=0)),
    )
    sync_teams = AsyncMock(return_value=1)
    monkeypatch.setattr(feishu, "sync_department_teams", sync_teams)

    response = await feishu.sync_contacts(
        request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"]["teams_created"] == 1
    assert [item.department_id for item in sync_teams.await_args.args[0]] == [
        "0",
        "dept-a",
    ]
    assert client.list_users.await_args.args[0] == ["dept-a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("root_denied", [False, True])
async def test_subteam_sync_queries_only_scoped_users_with_real_client(
    monkeypatch, root_denied
):
    from app.integrations import feishu as feishu_transport

    dept_a = SimpleNamespace(department_id="dept-a", children=[])
    dept_b = SimpleNamespace(department_id="dept-b", children=[])
    company = SimpleNamespace(department_id="0", children=[dept_a, dept_b])
    queried_departments = []

    async def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token"})
        assert request.url.path.endswith("/users/find_by_department")
        department_id = request.url.params["department_id"]
        queried_departments.append(department_id)
        if department_id == "0" and root_denied:
            return httpx.Response(
                403, json={"code": 41050, "msg": "no user authority error"}
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "user_id": f"user-{department_id}",
                            "open_id": f"open-{department_id}",
                            "name": f"Employee {department_id}",
                            "department_ids": [department_id],
                        }
                    ],
                    "has_more": False,
                },
            },
        )

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        feishu_transport.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    client = feishu_transport.FeishuClient.__new__(feishu_transport.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"
    client.list_departments = AsyncMock(return_value=[company])
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        feishu,
        "get_builtin_integration",
        AsyncMock(return_value=SimpleNamespace(config={"department_ids": ["dept-a"]})),
    )
    sync_users = AsyncMock(
        return_value=SimpleNamespace(created=1, updated=0, skipped=0)
    )
    sync_teams = AsyncMock(return_value=2)
    monkeypatch.setattr(feishu, "sync_directory_users", sync_users)
    monkeypatch.setattr(feishu, "sync_department_teams", sync_teams)

    response = await feishu.sync_contacts(
        request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"]["created"] == 1
    assert queried_departments == ["dept-a"]
    members = sync_users.await_args.args[0]
    assert [member.user_id for member in members] == ["user-dept-a"]
    assert members[0].department_ids == frozenset({"dept-a"})
    assert [item.department_id for item in sync_teams.await_args.args[0]] == [
        "0",
        "dept-a",
    ]
    assert sync_teams.await_args.args[1] == members
