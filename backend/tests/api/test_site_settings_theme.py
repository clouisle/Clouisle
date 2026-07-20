from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import site_settings
from app.api.v1.admin.endpoints.site_settings import _validate_setting_value
from app.api.v1.endpoints.site_settings import _normalize_enum, _normalize_hex_color
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.site_setting import (
    AutoNotificationConfigUpdate,
    SiteSettingBulkUpdate,
    SiteSettingUpdate,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dark", "dark"),
        ("light", "light"),
        ("bad", "system"),
        (None, "system"),
    ],
)
def test_normalize_enum_falls_back_for_invalid_values(value, expected):
    assert _normalize_enum(value, {"system", "light", "dark"}, "system") == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#abc", "#abc"),
        ("#abcd", "#abcd"),
        ("#A1B2C3", "#A1B2C3"),
        ("#A1B2C3CC", "#A1B2C3CC"),
        ("blue", ""),
        (None, ""),
    ],
)
def test_normalize_hex_color_falls_back_for_invalid_values(value, expected):
    assert _normalize_hex_color(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["system", "light", "dark"])
async def test_validate_theme_mode_accepts_known_values(value):
    await _validate_setting_value("theme_mode", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["auto", "", True])
async def test_validate_theme_mode_rejects_invalid_values(value):
    with pytest.raises(BusinessError):
        await _validate_setting_value("theme_mode", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["full", "name_only", "icon_only", "hidden"])
async def test_validate_branding_display_accepts_known_values(value):
    await _validate_setting_value("theme_branding_display", value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "theme_primary_color",
        "theme_card_color",
        "theme_sidebar_accent_foreground_color",
        "theme_navbar_hover_color",
        "theme_chart_5_color",
    ],
)
@pytest.mark.parametrize("value", ["#abc", "#abcd", "#123ABC", "#123ABC80", ""])
async def test_validate_theme_color_accepts_hex_or_empty(key, value):
    await _validate_setting_value(key, value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ["blue", "#12", "#12345", "#1234567", " #123ABC80 ", 123]
)
async def test_validate_theme_color_rejects_invalid_values(value):
    with pytest.raises(BusinessError):
        await _validate_setting_value("theme_sidebar_color", value)


class Query:
    def __init__(self, value=None, *, exists=False, count=0):
        self.value = value
        self.exists_value = exists
        self.count_value = count

    async def first(self):
        return self.value

    async def exists(self):
        return self.exists_value

    async def count(self):
        return self.count_value


def setting(key="site_name", value="Old", **overrides):
    values = {
        "key": key,
        "value": value,
        "value_type": "string",
        "category": "general",
        "description": "Description",
        "is_public": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_permission_checker_separates_read_and_update_access():
    read_user = SimpleNamespace(
        is_superuser=False,
        roles=[
            SimpleNamespace(permissions=[SimpleNamespace(code="admin:settings:read")])
        ],
    )

    assert (
        await site_settings.PermissionChecker("admin:settings:read")(read_user)
        is read_user
    )
    with pytest.raises(BusinessError) as exc_info:
        await site_settings.PermissionChecker("admin:settings:update")(read_user)
    assert exc_info.value.code == ResponseCode.PERMISSION_DENIED
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_settings_groups_and_missing_key(monkeypatch):
    get_all = AsyncMock(return_value={"allow_registration": True})
    monkeypatch.setattr(site_settings.SiteSetting, "get_all_by_category", get_all)

    response = await site_settings.get_all_settings(category="security")

    assert response["data"].settings == {"allow_registration": True}
    get_all.assert_awaited_once_with(category="security")

    monkeypatch.setattr(site_settings.SiteSetting, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await site_settings.get_setting("missing")
    assert exc_info.value.code == ResponseCode.NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value", "valid"),
    [
        ("icp_record_url", "https://example.test/path", True),
        ("icp_record_url", "javascript:alert(1)", False),
        ("auth_page_layout", "split", True),
        ("auth_page_layout", "wide", False),
        ("default_team_role", "viewer", True),
        ("default_team_role", "owner", False),
        ("upload_storage_backend", "S3", True),
        ("upload_storage_backend", "ftp", False),
        ("object_storage_secure", True, True),
        ("object_storage_secure", "true", False),
        ("kb_document_max_upload_size_mb", 1, True),
        ("kb_document_max_upload_size_mb", 1024, True),
        ("kb_document_max_upload_size_mb", True, False),
        ("kb_document_max_upload_size_mb", 0, False),
        ("kb_document_max_upload_size_mb", 1025, False),
    ],
)
async def test_validate_setting_boundaries(key, value, valid):
    if valid:
        await _validate_setting_value(key, value)
    else:
        with pytest.raises(BusinessError) as exc_info:
            await _validate_setting_value(key, value)
        assert exc_info.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_validate_default_team_requires_existing_active_team(monkeypatch):
    team_id = uuid4()
    monkeypatch.setattr(
        site_settings.Team,
        "filter",
        lambda **kwargs: Query(exists=kwargs == {"id": team_id, "is_deleted": False}),
    )

    await _validate_setting_value("default_team_id", str(team_id))
    with pytest.raises(BusinessError):
        await _validate_setting_value("default_team_id", str(uuid4()))
    with pytest.raises(BusinessError):
        await _validate_setting_value("default_team_id", "not-a-uuid")


@pytest.mark.asyncio
async def test_storage_update_requires_complete_object_configuration(monkeypatch):
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_all_by_category",
        AsyncMock(return_value={"object_storage_endpoint": "https://store.test"}),
    )

    with pytest.raises(BusinessError) as exc_info:
        await site_settings._validate_storage_settings_update(
            {"upload_storage_backend": "s3"}
        )
    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR

    await site_settings._validate_storage_settings_update(
        {
            "upload_storage_backend": "s3",
            "object_storage_endpoint": "https://store.test",
            "object_storage_bucket": "bucket",
            "object_storage_access_key": "test-access-key",
            "object_storage_secret_key": "test-secret",
        }
    )


@pytest.mark.asyncio
async def test_update_existing_setting_persists_and_audits(monkeypatch):
    old = setting()
    saved = setting(value="New")
    filter_mock = MagicMock(side_effect=[Query(old), Query(old)])
    set_value = AsyncMock(return_value=saved)
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "filter", filter_mock)
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    response = await site_settings.update_setting(
        request=MagicMock(),
        key="site_name",
        data=SiteSettingUpdate(value="New"),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"].value == "New"
    set_value.assert_awaited_once_with(
        key="site_name",
        value="New",
        value_type="string",
        category="general",
        description="Description",
        is_public=True,
    )
    assert audit.await_args.kwargs["changes"] == {
        "before": {"value": "Old"},
        "after": {"value": "New"},
    }


@pytest.mark.asyncio
async def test_update_secret_setting_never_audits_secret_value(monkeypatch):
    secret_key = "object_storage_secret_key"
    old = setting(secret_key, "old-test-secret", category="storage", is_public=False)
    saved = setting(secret_key, "new-test-secret", category="storage", is_public=False)
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "filter",
        MagicMock(side_effect=[Query(old), Query(old)]),
    )
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_all_by_category",
        AsyncMock(
            return_value={
                "upload_storage_backend": "local",
                secret_key: "old-test-secret",
            }
        ),
    )
    monkeypatch.setattr(
        site_settings.SiteSetting, "set_value", AsyncMock(return_value=saved)
    )
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    await site_settings.update_setting(
        request=MagicMock(),
        key=secret_key,
        data=SiteSettingUpdate(value="new-test-secret"),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert audit.await_args.kwargs["changes"] == {
        "before": {"value": "***"},
        "after": {"value": "***"},
    }


@pytest.mark.asyncio
async def test_update_unknown_setting_rejects_without_persistence_or_audit(monkeypatch):
    monkeypatch.setattr(site_settings.SiteSetting, "filter", lambda **_kwargs: Query())
    set_value = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings.update_setting(
            request=MagicMock(),
            key="unknown_setting",
            data=SiteSettingUpdate(value="value"),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    set_value.assert_not_awaited()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_persistence_failure_skips_audit(monkeypatch):
    current = setting()
    monkeypatch.setattr(
        site_settings.SiteSetting, "filter", lambda **_kwargs: Query(current)
    )
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "set_value",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await site_settings.update_setting(
            request=MagicMock(),
            key="site_name",
            data=SiteSettingUpdate(value="New"),
            current_user=SimpleNamespace(id=uuid4()),
        )
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_update_handles_existing_default_and_unknown_keys(monkeypatch):
    existing = setting("site_name")
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "filter",
        lambda **kwargs: Query(existing if kwargs["key"] == "site_name" else None),
    )
    set_value = AsyncMock(return_value=existing)
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_all_by_category",
        AsyncMock(return_value={"site_name": "New", "allow_registration": False}),
    )
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    response = await site_settings.bulk_update_settings(
        request=MagicMock(),
        data=SiteSettingBulkUpdate(
            settings={
                "site_name": "New",
                "allow_registration": False,
                "unknown_setting": "ignored",
            }
        ),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"].settings["allow_registration"] is False
    assert set_value.await_count == 2
    assert audit.await_args.kwargs["metadata"] == {
        "updated_keys": ["site_name", "allow_registration"],
        "count": 2,
    }


@pytest.mark.asyncio
async def test_password_login_cannot_be_disabled_without_superadmin_sso(monkeypatch):
    monkeypatch.setattr(
        site_settings.UserSSOConnection,
        "filter",
        lambda **_kwargs: Query(count=0),
    )
    set_value = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings.bulk_update_settings(
            request=MagicMock(),
            data=SiteSettingBulkUpdate(settings={"sso_allow_password_login": False}),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert exc_info.value.code == ResponseCode.FORBIDDEN
    set_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_notification_get_and_update_persist_and_audit(monkeypatch):
    old_config = {"channels": ["email"], "enabled_types": []}
    get_value = AsyncMock(return_value=old_config)
    set_value = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    response = await site_settings.get_auto_notification_config()
    assert response["data"].channels == ["email"]

    valid_type = next(iter(site_settings.AutoNotificationType)).value
    response = await site_settings.update_auto_notification_config(
        request=MagicMock(),
        data=AutoNotificationConfigUpdate(
            channels=["webhook"], enabled_types=[valid_type]
        ),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"].enabled_types == [valid_type]
    set_value.assert_awaited_once_with(
        key="auto_notification_config",
        value={"channels": ["webhook"], "enabled_types": [valid_type]},
        value_type="json",
        category="notification",
        description="Auto notification configuration",
        is_public=False,
    )
    assert audit.await_args.kwargs["changes"]["before"] == old_config


@pytest.mark.asyncio
async def test_auto_notification_update_validates_before_persistence(monkeypatch):
    set_value = AsyncMock()
    monkeypatch.setattr(
        site_settings.SiteSetting, "get_value", AsyncMock(return_value={})
    )
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings.update_auto_notification_config(
            request=MagicMock(),
            data=AutoNotificationConfigUpdate(
                channels=["email"], enabled_types=["not-real"]
            ),
            current_user=SimpleNamespace(id=uuid4()),
        )
    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    set_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_category_and_audit(monkeypatch):
    set_value = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_all_by_category",
        AsyncMock(return_value={"allow_registration": True}),
    )
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)

    response = await site_settings.reset_settings(
        request=MagicMock(),
        category="security",
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"].settings == {"allow_registration": True}
    assert set_value.await_count > 0
    assert all(
        call.kwargs["category"] == "security" for call in set_value.await_args_list
    )
    assert audit.await_args.kwargs["metadata"]["count"] == set_value.await_count


@pytest.mark.asyncio
async def test_email_provider_boundaries_are_mocked(monkeypatch):
    monkeypatch.setattr(
        site_settings.SiteSetting, "get_value", AsyncMock(return_value=False)
    )
    send = AsyncMock()
    monkeypatch.setattr(site_settings, "send_email", send)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings.send_test_email(
            data=site_settings.TestEmailRequest(email="admin@example.com")
        )
    assert exc_info.value.msg_key == "smtp_not_configured"
    send.assert_not_awaited()

    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_value",
        AsyncMock(side_effect=[True, "Test Site"]),
    )
    send.return_value = False
    with pytest.raises(BusinessError) as exc_info:
        await site_settings.send_test_email(
            data=site_settings.TestEmailRequest(email="admin@example.com")
        )
    assert exc_info.value.msg_key == "email_send_failed"
    send.assert_awaited_once()

    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_value",
        AsyncMock(side_effect=[True, "Test Site"]),
    )
    send.reset_mock()
    send.return_value = True
    await site_settings.send_test_email(
        data=site_settings.TestEmailRequest(email="admin@example.com")
    )
    send.assert_awaited_once()


PROVIDER_CASES = [
    (
        "dingtalk",
        site_settings.send_test_dingtalk,
        {"notification_type": "webhook", "webhook_url": "https://notify.test"},
        {
            "notification_type": "app",
            "app_key": "key",
            "app_secret": "secret",
            "agent_id": "1",
        },
    ),
    (
        "wechat",
        site_settings.send_test_wechat,
        {"notification_type": "webhook", "webhook_url": "https://notify.test"},
        {
            "notification_type": "app",
            "corp_id": "corp",
            "secret": "secret",
            "agent_id": "1",
        },
    ),
    (
        "feishu",
        site_settings.send_test_feishu,
        {"notification_type": "webhook", "webhook_url": "https://notify.test"},
        {"notification_type": "app", "app_id": "app", "app_secret": "secret"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "endpoint", "webhook", "app"), PROVIDER_CASES)
async def test_chat_notification_provider_boundaries_are_mocked(
    monkeypatch, provider, endpoint, webhook, app
):
    module = import_module(f"app.core.{provider}")
    get_config = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(module, f"get_{provider}_config", get_config)
    monkeypatch.setattr(module, f"send_{provider}_notification", send)
    monkeypatch.setattr(
        site_settings.SiteSetting, "get_value", AsyncMock(return_value="Test Site")
    )

    get_config.return_value = {"enabled": False}
    with pytest.raises(BusinessError) as exc_info:
        await endpoint()
    assert exc_info.value.msg_key == f"{provider}_not_enabled"
    send.assert_not_awaited()

    incomplete = {key: value for key, value in webhook.items()}
    incomplete[next(key for key in incomplete if key.endswith("url"))] = ""
    get_config.return_value = {"enabled": True, **incomplete}
    with pytest.raises(BusinessError) as exc_info:
        await endpoint()
    assert exc_info.value.msg_key == f"{provider}_not_configured"
    send.assert_not_awaited()

    incomplete = {**app, next(key for key in app if "secret" in key): ""}
    get_config.return_value = {"enabled": True, **incomplete}
    with pytest.raises(BusinessError) as exc_info:
        await endpoint()
    assert exc_info.value.msg_key == f"{provider}_not_configured"
    send.assert_not_awaited()

    get_config.return_value = {"enabled": True, **webhook}
    send.return_value = False
    with pytest.raises(BusinessError) as exc_info:
        await endpoint()
    assert exc_info.value.msg_key == f"{provider}_send_failed"

    send.reset_mock()
    get_config.return_value = {"enabled": True, **app}
    send.return_value = True
    await endpoint()
    send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "endpoint", "config_key"),
    [
        ("webhook", site_settings.send_test_webhook, "url"),
        ("slack", site_settings.send_test_slack, "webhook_url"),
    ],
)
async def test_webhook_notification_provider_boundaries_are_mocked(
    monkeypatch, provider, endpoint, config_key
):
    module = import_module(f"app.core.{provider}")
    get_config = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(module, f"get_{provider}_config", get_config)
    monkeypatch.setattr(module, f"send_{provider}_notification", send)
    monkeypatch.setattr(
        site_settings.SiteSetting, "get_value", AsyncMock(return_value="Test Site")
    )

    for config, expected in [
        ({"enabled": False}, f"{provider}_not_enabled"),
        ({"enabled": True, config_key: ""}, f"{provider}_not_configured"),
    ]:
        get_config.return_value = config
        with pytest.raises(BusinessError) as exc_info:
            await endpoint()
        assert exc_info.value.msg_key == expected
    send.assert_not_awaited()

    get_config.return_value = {"enabled": True, config_key: "https://notify.test"}
    send.return_value = False
    with pytest.raises(BusinessError) as exc_info:
        await endpoint()
    assert exc_info.value.msg_key == f"{provider}_send_failed"

    send.reset_mock()
    send.return_value = True
    await endpoint()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_dispatch_success_and_provider_failure(monkeypatch):
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)
    delay = MagicMock(return_value=SimpleNamespace(id="task-123"))
    monkeypatch.setattr(site_settings.archive_old_audit_logs, "delay", delay)

    response = await site_settings.trigger_archive_audit_logs(
        request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"] == {"task_id": "task-123", "status": "pending"}
    assert audit.await_args.kwargs["status"] == "pending"

    delay.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(BusinessError) as exc_info:
        await site_settings.trigger_archive_audit_logs(
            request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
        )
    assert exc_info.value.msg_key == "archive_failed"
    assert audit.await_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_key", "expected_value"),
    [
        ("PENDING", "message", "Task is waiting to be executed"),
        ("STARTED", "message", "Task is running"),
        ("SUCCESS", "result", {"archived": 3}),
        ("FAILURE", "error", "worker failed"),
        ("RETRY", "message", "Task state: RETRY"),
    ],
)
async def test_archive_status_boundaries(
    monkeypatch, state, expected_key, expected_value
):
    task = SimpleNamespace(state=state, result={"archived": 3}, info="worker failed")
    monkeypatch.setattr("celery.result.AsyncResult", lambda *_args, **_kwargs: task)

    response = await site_settings.get_archive_task_status("task-123")

    assert response["data"][expected_key] == expected_value
