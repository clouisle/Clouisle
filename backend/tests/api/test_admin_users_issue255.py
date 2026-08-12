from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import users as users_endpoints
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.user import UserCreate, UserUpdate


def query_returning(*, first=None, all=None, count=0) -> MagicMock:
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.all = AsyncMock(return_value=[] if all is None else all)
    query.count = AsyncMock(return_value=count)
    query.filter.return_value = query
    query.exclude.return_value = query
    query.distinct.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.prefetch_related.return_value = query
    return query


def user(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "username": "alice",
        "email": "alice@example.com",
        "is_active": False,
        "is_superuser": False,
        "approval_status": "pending",
        "locale": "en",
        "force_password_change": False,
        "password_expiration_exempt": False,
        "password_changed_at": None,
        "password_expires_at": None,
        "last_login": None,
        "save": AsyncMock(),
        "delete": AsyncMock(),
        "update_from_dict": AsyncMock(),
        "roles": SimpleNamespace(
            clear=AsyncMock(), add=AsyncMock(), all=AsyncMock(return_value=[])
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_read_users_applies_filters_and_returns_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed_user = user()
    query = query_returning(all=[listed_user], count=1)
    query.prefetch_related = AsyncMock(return_value=[listed_user])
    model = MagicMock()
    model.all.return_value = query
    monkeypatch.setattr(users_endpoints, "User", model)
    serialize = AsyncMock(return_value={"id": str(listed_user.id)})
    monkeypatch.setattr(users_endpoints, "serialize_user_with_sso", serialize)

    result = await users_endpoints.read_users(
        page=2,
        page_size=5,
        status=["active", "inactive", "pending"],
        search="alice",
        role=["admin"],
        exclude_user_id=[uuid4()],
        current_user=user(),
    )

    assert result["data"] == {
        "items": [{"id": str(listed_user.id)}],
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    query.offset.assert_called_once_with(5)
    query.exclude.assert_called_once()
    query.distinct.assert_called_once()
    serialize.assert_awaited_once_with(listed_user)


@pytest.mark.parametrize(
    ("username_exists", "email_exists", "expected_code"),
    [
        (True, False, ResponseCode.USERNAME_EXISTS),
        (False, True, ResponseCode.EMAIL_EXISTS),
    ],
)
@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_identity(
    monkeypatch: pytest.MonkeyPatch,
    username_exists: bool,
    email_exists: bool,
    expected_code: ResponseCode,
) -> None:
    model = MagicMock()
    model.filter.side_effect = [
        query_returning(first=user() if username_exists else None),
        query_returning(first=user() if email_exists else None),
    ]
    monkeypatch.setattr(users_endpoints, "User", model)

    with pytest.raises(BusinessError) as exc_info:
        await users_endpoints.create_user(
            request=MagicMock(),
            user_in=UserCreate(
                username="alice", email="alice@example.com", password="Secret123!"
            ),
            current_user=user(),
        )

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_create_user_uses_default_locale_and_returns_created_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = user(locale="zh")
    model = MagicMock()
    model.filter.side_effect = [query_returning(), query_returning()]
    model.create = AsyncMock(return_value=created)
    model.get.return_value.prefetch_related = AsyncMock(return_value=created)
    monkeypatch.setattr(users_endpoints, "User", model)
    monkeypatch.setattr(
        users_endpoints.SiteSetting, "get_value", AsyncMock(return_value="zh")
    )
    monkeypatch.setattr(
        users_endpoints.security, "get_password_hash", MagicMock(return_value="hashed")
    )
    monkeypatch.setattr(users_endpoints.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        users_endpoints,
        "serialize_user_with_sso",
        AsyncMock(return_value={"id": str(created.id)}),
    )

    result = await users_endpoints.create_user(
        request=MagicMock(),
        user_in=UserCreate(
            username="alice",
            email="alice@example.com",
            password="Secret123!",
            locale=None,
        ),
        current_user=user(),
    )

    assert result["data"] == {"id": str(created.id)}
    assert model.create.await_args.kwargs["locale"] == "zh"
    assert model.create.await_args.kwargs["hashed_password"] == "hashed"


@pytest.mark.parametrize(
    ("smtp_enabled", "rate_result", "found_users", "expected_code"),
    [
        (False, (True, 0, 100), [], ResponseCode.EMAIL_SEND_FAILED),
        (True, (False, 100, 0), [], ResponseCode.RATE_LIMITED),
        (True, (True, 0, 100), [], ResponseCode.NOT_FOUND),
        (True, (True, 99, 1), [user(), user()], ResponseCode.RATE_LIMITED),
    ],
)
@pytest.mark.asyncio
async def test_send_email_guards(
    monkeypatch: pytest.MonkeyPatch,
    smtp_enabled: bool,
    rate_result: tuple[bool, int, int],
    found_users: list[SimpleNamespace],
    expected_code: ResponseCode,
) -> None:
    monkeypatch.setattr(
        users_endpoints.SiteSetting,
        "get_value",
        AsyncMock(return_value=smtp_enabled),
    )
    monkeypatch.setattr(
        users_endpoints, "check_bulk_email_rate", AsyncMock(return_value=rate_result)
    )
    model = MagicMock()
    model.filter.return_value = query_returning(all=found_users)
    monkeypatch.setattr(users_endpoints, "User", model)

    with pytest.raises(BusinessError) as exc_info:
        await users_endpoints.send_email_to_users(
            data=users_endpoints.SendEmailRequest(
                subject="Notice", content="Hello", user_ids=[uuid4(), uuid4()]
            ),
            background_tasks=MagicMock(),
            current_user=user(),
        )

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_send_email_queues_allowed_recipients_and_skips_limited_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipients = [
        user(),
        user(username="bob", email="bob@example.com"),
        user(email=None),
    ]
    model = MagicMock()
    model.filter.return_value = query_returning(all=recipients)
    monkeypatch.setattr(users_endpoints, "User", model)
    monkeypatch.setattr(
        users_endpoints.SiteSetting, "get_value", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        users_endpoints,
        "check_bulk_email_rate",
        AsyncMock(return_value=(True, 0, 100)),
    )
    monkeypatch.setattr(
        users_endpoints,
        "check_recipient_email_rate",
        AsyncMock(side_effect=[(True, 4), (False, 0)]),
    )
    increment_recipient = AsyncMock()
    increment_bulk = AsyncMock()
    monkeypatch.setattr(
        users_endpoints, "increment_recipient_email_count", increment_recipient
    )
    monkeypatch.setattr(users_endpoints, "increment_bulk_email_count", increment_bulk)
    background_tasks = MagicMock()
    current_user = user()

    result = await users_endpoints.send_email_to_users(
        data=users_endpoints.SendEmailRequest(
            subject="Notice", content="Hello", user_ids=[item.id for item in recipients]
        ),
        background_tasks=background_tasks,
        current_user=current_user,
    )

    assert result["data"] == {"sent_count": 1, "skipped_count": 1, "total": 3}
    background_tasks.add_task.assert_called_once()
    increment_recipient.assert_awaited_once_with("alice@example.com")
    increment_bulk.assert_awaited_once_with(str(current_user.id), 1)


@pytest.mark.parametrize(
    ("endpoint", "existing_user", "expected_code"),
    [
        (users_endpoints.activate_user, None, ResponseCode.USER_NOT_FOUND),
        (
            users_endpoints.activate_user,
            user(is_active=True),
            ResponseCode.USER_ALREADY_ACTIVE,
        ),
        (
            users_endpoints.deactivate_user,
            user(is_active=True, is_superuser=True),
            ResponseCode.CANNOT_DEACTIVATE_SUPERUSER,
        ),
        (
            users_endpoints.deactivate_user,
            user(is_active=False),
            ResponseCode.USER_ALREADY_INACTIVE,
        ),
        (users_endpoints.delete_user, None, ResponseCode.USER_NOT_FOUND),
        (
            users_endpoints.delete_user,
            user(is_superuser=True),
            ResponseCode.CANNOT_DELETE_SUPERUSER,
        ),
    ],
)
@pytest.mark.asyncio
async def test_user_state_guards(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: object,
    existing_user: SimpleNamespace | None,
    expected_code: ResponseCode,
) -> None:
    model = MagicMock()
    model.filter.return_value = query_returning(first=existing_user)
    monkeypatch.setattr(users_endpoints, "User", model)

    with pytest.raises(BusinessError) as exc_info:
        await endpoint(MagicMock(), uuid4(), user())  # type: ignore[operator]

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_activate_user_saves_audits_notifies_and_serializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = user()
    refreshed = user(id=target.id, is_active=True, approval_status="approved")
    model = MagicMock()
    model.filter.return_value = query_returning(first=target)
    model.get.return_value.prefetch_related = AsyncMock(return_value=refreshed)
    monkeypatch.setattr(users_endpoints, "User", model)
    audit = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(users_endpoints.AuditLogService, "log", audit)
    monkeypatch.setattr(users_endpoints.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(
        users_endpoints,
        "serialize_user_with_sso",
        AsyncMock(return_value={"id": str(target.id), "status": "active"}),
    )

    result = await users_endpoints.activate_user(MagicMock(), target.id, user())

    assert target.is_active is True
    assert target.approval_status == "approved"
    target.save.assert_awaited_once_with(update_fields=["is_active", "approval_status"])
    audit.assert_awaited_once()
    notify.assert_awaited_once()
    assert result["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_update_user_rejects_invalid_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = user()
    model = MagicMock()
    model.filter.return_value = query_returning(first=target)
    monkeypatch.setattr(users_endpoints, "User", model)
    monkeypatch.setattr(
        users_endpoints,
        "validate_password",
        AsyncMock(return_value=(False, ["too_short"])),
    )

    with pytest.raises(BusinessError) as exc_info:
        await users_endpoints.update_user(
            request=MagicMock(),
            user_id=target.id,
            user_in=UserUpdate(password="weak"),
            current_user=user(),
        )

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    assert exc_info.value.data == {"errors": {"password": ["too_short"]}}
    target.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_updates_password_and_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = user()
    refreshed = user(id=target.id)
    admin_role = SimpleNamespace(name="admin")
    model = MagicMock()
    model.filter.return_value = query_returning(first=target)
    model.get.return_value.prefetch_related = AsyncMock(return_value=refreshed)
    role_model = MagicMock()
    role_model.filter.side_effect = [
        query_returning(first=admin_role),
        query_returning(first=None),
    ]
    monkeypatch.setattr(users_endpoints, "User", model)
    monkeypatch.setattr(users_endpoints, "Role", role_model)
    monkeypatch.setattr(
        users_endpoints, "validate_password", AsyncMock(return_value=(True, []))
    )
    monkeypatch.setattr(
        users_endpoints.security, "get_password_hash", MagicMock(return_value="hashed")
    )
    audit = AsyncMock()
    monkeypatch.setattr(users_endpoints.AuditLogService, "log", audit)
    notify = AsyncMock()
    monkeypatch.setattr(users_endpoints.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(
        users_endpoints, "serialize_user_with_sso", AsyncMock(return_value={"ok": True})
    )

    result = await users_endpoints.update_user(
        request=MagicMock(),
        user_id=target.id,
        user_in=UserUpdate(password="Strong123!", roles=["admin", "missing"]),
        current_user=user(),
    )

    target.update_from_dict.assert_awaited_once_with({"hashed_password": "hashed"})
    target.roles.clear.assert_awaited_once()
    target.roles.add.assert_awaited_once_with(admin_role)
    assert audit.await_args.kwargs["changes"]["before"]["roles"] == []
    assert audit.await_args.kwargs["changes"]["after"]["roles"] == ["admin"]
    notify.assert_awaited_once()
    assert result["data"] == {"ok": True}


@pytest.mark.asyncio
async def test_bulk_force_password_change_validates_and_handles_missing_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(BusinessError) as empty_error:
        await users_endpoints.bulk_force_password_change(
            MagicMock(),
            users_endpoints.BulkForcePasswordChangeRequest(user_ids=[]),
            user(),
        )
    assert empty_error.value.code == ResponseCode.VALIDATION_ERROR

    model = MagicMock()
    model.filter.return_value = query_returning(all=[])
    monkeypatch.setattr(users_endpoints, "User", model)
    with pytest.raises(BusinessError) as missing_error:
        await users_endpoints.bulk_force_password_change(
            MagicMock(),
            users_endpoints.BulkForcePasswordChangeRequest(user_ids=[uuid4()]),
            user(),
        )
    assert missing_error.value.code == ResponseCode.USER_NOT_FOUND


@pytest.mark.asyncio
async def test_password_expiration_stats_disabled_avoids_user_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        users_endpoints.SiteSetting, "get_value", AsyncMock(return_value=False)
    )
    model = MagicMock()
    monkeypatch.setattr(users_endpoints, "User", model)

    result = await users_endpoints.get_password_expiration_stats(user())

    assert result["data"].model_dump() == {
        "total_users": 0,
        "expired_count": 0,
        "expiring_soon_count": 0,
        "force_change_count": 0,
        "exempt_count": 0,
    }
    model.filter.assert_not_called()


@pytest.mark.asyncio
async def test_get_expiring_passwords_filters_and_serializes_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    target = user(
        password_changed_at=now - timedelta(days=10),
        password_expires_at=now - timedelta(days=1),
        last_login=now - timedelta(days=2),
    )
    query = query_returning(all=[target], count=1)
    model = MagicMock()
    model.filter.return_value = query
    monkeypatch.setattr(users_endpoints, "User", model)
    monkeypatch.setattr(
        users_endpoints.SiteSetting, "get_value", AsyncMock(return_value=7)
    )

    result = await users_endpoints.get_expiring_passwords(
        page=2, page_size=10, filter="expired", current_user=user()
    )

    page = result["data"]
    assert (page.total, page.page, page.page_size) == (1, 2, 10)
    assert page.items[0].username == "alice"
    assert page.items[0].days_until_expiration == -2
    query.offset.assert_called_once_with(10)
    assert query.filter.call_args.kwargs["password_expires_at__lt"] is not None


@pytest.mark.asyncio
async def test_dependency_exception_propagates_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("database unavailable")
    model = MagicMock()
    model.filter.side_effect = failure
    monkeypatch.setattr(users_endpoints, "User", model)
    audit = AsyncMock()
    monkeypatch.setattr(users_endpoints.AuditLogService, "log", audit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await users_endpoints.read_user_by_id(uuid4(), user())

    audit.assert_not_awaited()
