from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import users
from app.schemas.response import BusinessError, error
from app.schemas.user import UserCreate, UserUpdate


class _Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.count_result = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    def distinct(self):
        self.calls.append(("distinct", (), {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    async def count(self):
        return self.count_result

    async def first(self):
        return self.result

    async def all(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


class _Permission:
    def __init__(self, code):
        self.code = code


class _Role:
    def __init__(self, *codes):
        self.permissions = [_Permission(code) for code in codes]


def _user(**overrides):
    values = {
        "id": uuid4(),
        "username": "disposable-user",
        "email": "disposable@example.com",
        "is_active": True,
        "approval_status": "approved",
        "is_superuser": False,
        "email_verified": True,
        "avatar_url": None,
        "locale": "en",
        "created_at": datetime.now(UTC),
        "last_login": None,
        "auth_source": "local",
        "external_id": None,
        "force_password_change": False,
        "password_expiration_exempt": False,
        "password_changed_at": datetime.now(UTC) - timedelta(days=10),
        "password_expires_at": datetime.now(UTC) + timedelta(days=2),
        "password_expiration_notified_at": None,
        "save": AsyncMock(),
        "delete": AsyncMock(),
        "update_from_dict": AsyncMock(),
        "roles": SimpleNamespace(clear=AsyncMock(), add=AsyncMock()),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def fake_request():
    return MagicMock()


@pytest.fixture
def admin():
    return _user(username="admin")


@pytest.fixture
def users_client():
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/admin/users")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc):
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

    current_user = _user(roles=[])

    async def fake_current_user():
        return current_user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    try:
        yield TestClient(app), current_user
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/api/v1/admin/users", None),
        (
            "post",
            "/api/v1/admin/users",
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "password": "not-a-real-secret",
            },
        ),
        ("post", f"/api/v1/admin/users/{uuid4()}/activate", None),
        ("delete", f"/api/v1/admin/users/{uuid4()}", None),
    ],
)
def test_user_routes_require_matching_permissions(users_client, method, path, json):
    client, _ = users_client

    response = client.request(method, path, json=json)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_read_users_applies_filters_and_pagination(admin):
    found = _user()
    query = _Query([found], count=1)
    serialized = {"id": found.id, "username": found.username}

    with (
        patch.object(users.User, "all", return_value=query),
        patch.object(
            users, "serialize_user_with_sso", AsyncMock(return_value=serialized)
        ),
    ):
        response = await users.read_users(
            page=2,
            page_size=5,
            status=["active", "inactive", "pending"],
            search="disposable",
            role=["editor"],
            exclude_user_id=[admin.id],
            current_user=admin,
        )

    assert response["data"] == {
        "items": [serialized],
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    assert ("offset", (5,), {}) in query.calls
    assert ("limit", (5,), {}) in query.calls
    assert any(call[0] == "exclude" for call in query.calls)
    assert any(call[0] == "distinct" for call in query.calls)


@pytest.mark.anyio
async def test_user_stats_counts_each_state(admin):
    all_query = _Query(count=8)
    active = _Query(count=5)
    inactive = _Query(count=2)
    pending = _Query(count=1)

    with (
        patch.object(users.User, "all", return_value=all_query),
        patch.object(
            users.User, "filter", side_effect=[active, inactive, pending]
        ) as user_filter,
    ):
        response = await users.get_user_stats(current_user=admin)

    assert response["data"] == {
        "total": 8,
        "active": 5,
        "inactive": 2,
        "pending": 1,
    }
    assert user_filter.call_args_list[1].kwargs == {
        "is_active": False,
        "approval_status": "approved",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("duplicate", "expected_key"),
    [("username", "user_with_username_exists"), ("email", "user_with_email_exists")],
)
async def test_create_user_rejects_duplicates(
    fake_request, admin, duplicate, expected_key
):
    queries = [_Query(_user())]
    if duplicate == "email":
        queries.insert(0, _Query(None))

    with (
        patch.object(users.User, "filter", side_effect=queries),
        pytest.raises(BusinessError) as exc,
    ):
        await users.create_user(
            request=fake_request,
            user_in=UserCreate(
                username="new-user",
                email="new-user@example.com",
                password="not-a-real-secret",
            ),
            current_user=admin,
        )

    assert exc.value.msg_key == expected_key


@pytest.mark.anyio
async def test_create_user_hashes_password_uses_default_locale_and_audits(
    fake_request, admin
):
    created = _user(username="new-user", locale="zh")
    create = AsyncMock(return_value=created)
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", side_effect=[_Query(None), _Query(None)]),
        patch.object(users.User, "create", create),
        patch.object(users.User, "get", return_value=_Query(created)),
        patch.object(users.SiteSetting, "get_value", AsyncMock(return_value="zh")),
        patch.object(users.security, "get_password_hash", return_value="hashed-value"),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(
            users,
            "serialize_user_with_sso",
            AsyncMock(return_value={"id": created.id}),
        ),
    ):
        response = await users.create_user(
            request=fake_request,
            user_in=UserCreate(
                username="new-user",
                email="new-user@example.com",
                password="not-a-real-secret",
                locale=None,
            ),
            current_user=admin,
        )

    assert response["data"] == {"id": created.id}
    assert create.await_args.kwargs["hashed_password"] == "hashed-value"
    assert create.await_args.kwargs["locale"] == "zh"
    assert "password" not in create.await_args.kwargs
    assert audit.await_args.kwargs["action"] == "create_user"


@pytest.mark.anyio
async def test_create_user_persistence_failure_skips_audit(fake_request, admin):
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", side_effect=[_Query(None), _Query(None)]),
        patch.object(users.SiteSetting, "get_value", AsyncMock(return_value="en")),
        patch.object(
            users.User, "create", AsyncMock(side_effect=RuntimeError("db down"))
        ),
        patch.object(users.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="db down"),
    ):
        await users.create_user(
            request=fake_request,
            user_in=UserCreate(
                username="new-user",
                email="new-user@example.com",
                password="not-a-real-secret",
            ),
            current_user=admin,
        )

    audit.assert_not_awaited()


@pytest.mark.anyio
async def test_read_user_handles_missing_and_found(admin):
    found = _user()
    serialized = {"id": found.id}

    with (
        patch.object(users.User, "filter", side_effect=[_Query(None), _Query(found)]),
        patch.object(
            users, "serialize_user_with_sso", AsyncMock(return_value=serialized)
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await users.read_user_by_id(uuid4(), current_user=admin)

    assert exc.value.status_code == 404

    with (
        patch.object(users.User, "filter", return_value=_Query(found)),
        patch.object(
            users, "serialize_user_with_sso", AsyncMock(return_value=serialized)
        ),
    ):
        response = await users.read_user_by_id(found.id, current_user=admin)

    assert response["data"] == serialized


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "user", "expected_key"),
    [
        (users.activate_user, None, "user_with_id_not_exists"),
        (users.activate_user, _user(is_active=True), "user_already_active"),
        (users.deactivate_user, None, "user_with_id_not_exists"),
        (
            users.deactivate_user,
            _user(is_superuser=True),
            "cannot_deactivate_superuser",
        ),
        (users.deactivate_user, _user(is_active=False), "user_already_inactive"),
    ],
)
async def test_activation_boundaries(fake_request, admin, function, user, expected_key):
    with (
        patch.object(users.User, "filter", return_value=_Query(user)),
        pytest.raises(BusinessError) as exc,
    ):
        await function(fake_request, uuid4(), current_user=admin)

    assert exc.value.msg_key == expected_key


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "initial_active", "expected_active", "action"),
    [
        (users.activate_user, False, True, "activate_user"),
        (users.deactivate_user, True, False, "deactivate_user"),
    ],
)
async def test_activation_changes_state_notifies_and_audits(
    fake_request, admin, function, initial_active, expected_active, action
):
    target = _user(is_active=initial_active)
    audit = AsyncMock()
    notify = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.User, "get", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(users.AutoNotificationService, "send_to_user", notify),
        patch.object(
            users,
            "serialize_user_with_sso",
            AsyncMock(return_value={"id": target.id}),
        ),
    ):
        response = await function(fake_request, target.id, current_user=admin)

    assert response["data"] == {"id": target.id}
    assert target.is_active is expected_active
    assert target.approval_status == "approved"
    target.save.assert_awaited_once_with(update_fields=["is_active", "approval_status"])
    assert audit.await_args.kwargs["action"] == action
    notify.assert_awaited_once()


@pytest.mark.anyio
async def test_activation_save_failure_has_no_audit_or_notification(
    fake_request, admin
):
    target = _user(is_active=False, save=AsyncMock(side_effect=RuntimeError("db down")))
    audit = AsyncMock()
    notify = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(users.AutoNotificationService, "send_to_user", notify),
        pytest.raises(RuntimeError, match="db down"),
    ):
        await users.activate_user(fake_request, target.id, current_user=admin)

    audit.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.anyio
async def test_update_user_validates_password_before_persistence(fake_request, admin):
    target = _user()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(
            users, "validate_password", AsyncMock(return_value=(False, ["too short"]))
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await users.update_user(
            request=fake_request,
            user_id=target.id,
            user_in=UserUpdate(password="weak"),
            current_user=admin,
        )

    assert exc.value.msg_key == "password_validation_failed"
    assert exc.value.data == {"errors": {"password": ["too short"]}}
    target.save.assert_not_awaited()


@pytest.mark.anyio
async def test_update_user_password_roles_audit_and_notification(fake_request, admin):
    target = _user()
    role = SimpleNamespace(name="editor")
    audit = AsyncMock()
    notify = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.Role, "filter", side_effect=[_Query(role), _Query(None)]),
        patch.object(users.User, "get", return_value=_Query(target)),
        patch.object(users, "validate_password", AsyncMock(return_value=(True, []))),
        patch.object(users.security, "get_password_hash", return_value="hashed-value"),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(users.AutoNotificationService, "send_to_user", notify),
        patch.object(
            users,
            "serialize_user_with_sso",
            AsyncMock(return_value={"id": target.id}),
        ),
    ):
        response = await users.update_user(
            request=fake_request,
            user_id=target.id,
            user_in=UserUpdate(
                email="updated@example.com",
                password="not-a-real-secret",
                roles=["editor", "missing"],
            ),
            current_user=admin,
        )

    assert response["data"] == {"id": target.id}
    target.roles.clear.assert_awaited_once()
    target.roles.add.assert_awaited_once_with(role)
    update = target.update_from_dict.await_args.args[0]
    assert update["hashed_password"] == "hashed-value"
    assert "password" not in update
    assert audit.await_args.kwargs["metadata"]["fields_updated"] == [
        "email",
        "password",
        "roles",
    ]
    notify.assert_awaited_once()


@pytest.mark.anyio
async def test_update_user_save_failure_skips_audit(fake_request, admin):
    target = _user(save=AsyncMock(side_effect=RuntimeError("db down")))
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="db down"),
    ):
        await users.update_user(
            request=fake_request,
            user_id=target.id,
            user_in=UserUpdate(email="updated@example.com"),
            current_user=admin,
        )

    audit.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("target", "expected_key"),
    [
        (None, "user_with_id_not_exists"),
        (_user(is_superuser=True), "cannot_delete_superuser"),
    ],
)
async def test_delete_user_boundaries(fake_request, admin, target, expected_key):
    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        pytest.raises(BusinessError) as exc,
    ):
        await users.delete_user(fake_request, uuid4(), current_user=admin)

    assert exc.value.msg_key == expected_key


@pytest.mark.anyio
async def test_delete_user_audits_and_deletes(fake_request, admin):
    target = _user()
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(
            users,
            "serialize_user_with_sso",
            AsyncMock(return_value={"id": target.id}),
        ),
    ):
        response = await users.delete_user(fake_request, target.id, current_user=admin)

    assert response["data"] == {"id": target.id}
    audit.assert_awaited_once()
    target.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_failure_propagates_after_audit(fake_request, admin):
    target = _user(delete=AsyncMock(side_effect=RuntimeError("db down")))
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="db down"),
    ):
        await users.delete_user(fake_request, target.id, current_user=admin)

    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_force_password_change_sets_flag_notifies_and_audits(fake_request, admin):
    target = _user(force_password_change=False)
    audit = AsyncMock()
    notify = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(users.AutoNotificationService, "send_to_user", notify),
    ):
        await users.force_password_change(fake_request, target.id, current_user=admin)

    assert target.force_password_change is True
    target.save.assert_awaited_once()
    notify.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "force_password_change"


@pytest.mark.anyio
async def test_reset_password_expiration_persists_and_audits(fake_request, admin):
    target = _user()
    expiration = datetime.now(UTC) + timedelta(days=90)
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(
            users.PasswordExpirationService,
            "calculate_expiration_date",
            AsyncMock(return_value=expiration),
        ),
        patch.object(users.AuditLogService, "log", audit),
    ):
        await users.reset_password_expiration(
            fake_request, target.id, current_user=admin
        )

    assert target.password_expires_at == expiration
    assert target.password_expiration_notified_at is None
    assert (
        audit.await_args.kwargs["changes"]["password_expires_at"]
        == expiration.isoformat()
    )


@pytest.mark.anyio
async def test_exemption_clears_forced_change_and_audits(fake_request, admin):
    target = _user(force_password_change=True)
    audit = AsyncMock()

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", audit),
    ):
        await users.exempt_password_expiration(
            fake_request,
            target.id,
            users.ExemptPasswordExpirationRequest(exempt=True),
            current_user=admin,
        )

    assert target.password_expiration_exempt is True
    assert target.force_password_change is False
    assert audit.await_args.kwargs["changes"] == {"password_expiration_exempt": True}


@pytest.mark.anyio
async def test_bulk_force_password_change_validation_and_success(fake_request, admin):
    with pytest.raises(BusinessError) as empty_error:
        await users.bulk_force_password_change(
            fake_request,
            users.BulkForcePasswordChangeRequest(user_ids=[]),
            current_user=admin,
        )
    assert empty_error.value.msg_key == "no_users_selected"

    with (
        patch.object(users.User, "filter", return_value=_Query([])),
        pytest.raises(BusinessError) as missing_error,
    ):
        await users.bulk_force_password_change(
            fake_request,
            users.BulkForcePasswordChangeRequest(user_ids=[uuid4()]),
            current_user=admin,
        )
    assert missing_error.value.msg_key == "no_users_found"

    targets = [_user(), _user()]
    audit = AsyncMock()
    notify = AsyncMock()
    requested_ids = [target.id for target in targets]
    with (
        patch.object(users.User, "filter", return_value=_Query(targets)),
        patch.object(users.AuditLogService, "log", audit),
        patch.object(users.AutoNotificationService, "send_to_user", notify),
    ):
        response = await users.bulk_force_password_change(
            fake_request,
            users.BulkForcePasswordChangeRequest(user_ids=requested_ids),
            current_user=admin,
        )

    assert response["data"] == {"count": 2}
    assert all(target.force_password_change for target in targets)
    assert notify.await_count == 2
    assert audit.await_args.kwargs["metadata"] == {
        "user_ids": [str(user_id) for user_id in requested_ids],
        "count": 2,
    }


@pytest.mark.anyio
async def test_password_expiration_stats_disabled_and_enabled(admin):
    with patch.object(users.SiteSetting, "get_value", AsyncMock(return_value=False)):
        disabled = await users.get_password_expiration_stats(current_user=admin)

    assert disabled["data"].total_users == 0

    counts = iter([9, 2, 3, 4, 1])

    def filtered(**_kwargs):
        return _Query(count=next(counts))

    with (
        patch.object(users.SiteSetting, "get_value", AsyncMock(side_effect=[True, 7])),
        patch.object(users.User, "filter", side_effect=filtered),
    ):
        enabled = await users.get_password_expiration_stats(current_user=admin)

    assert enabled["data"].model_dump() == {
        "total_users": 9,
        "expired_count": 2,
        "expiring_soon_count": 3,
        "force_change_count": 4,
        "exempt_count": 1,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("filter_name", ["all", "expired", "expiring", "force_change"])
async def test_expiring_passwords_filters_and_paginates(admin, filter_name):
    target = _user(last_login=datetime.now(UTC))
    query = _Query([target], count=1)

    with (
        patch.object(users.SiteSetting, "get_value", AsyncMock(return_value=7)),
        patch.object(users.User, "filter", return_value=query),
    ):
        response = await users.get_expiring_passwords(
            page=2,
            page_size=5,
            filter=filter_name,
            current_user=admin,
        )

    page = response["data"]
    assert page.total == 1
    assert page.page == 2
    assert page.items[0].id == target.id
    assert page.items[0].days_until_expiration in {1, 2}
    assert ("offset", (5,), {}) in query.calls
    if filter_name == "all":
        assert not any(call[0] == "filter" for call in query.calls)
    else:
        assert any(call[0] == "filter" for call in query.calls)


@pytest.mark.parametrize(
    ("is_active", "approval_status", "expected"),
    [
        (False, "pending", "pending"),
        (True, "pending", "active"),
        (False, "approved", "inactive"),
    ],
)
def test_get_user_status_boundaries(is_active, approval_status, expected):
    assert (
        users.get_user_status(
            _user(is_active=is_active, approval_status=approval_status)
        )
        == expected
    )


@pytest.mark.anyio
@pytest.mark.parametrize("roles_fetched", [True, False])
async def test_serialize_user_includes_roles_permissions_and_sso(roles_fetched):
    permission = SimpleNamespace(
        id=uuid4(), scope="users", code="admin:user:read", description="Read users"
    )
    role = SimpleNamespace(
        id=uuid4(),
        name="auditor",
        description="Audits users",
        is_system_role=True,
        permissions=[permission],
    )
    provider = SimpleNamespace(
        id=uuid4(),
        name="oidc",
        display_name="Company SSO",
        icon_url="https://example.com/icon.png",
    )
    connection = SimpleNamespace(
        id=uuid4(),
        provider=provider,
        provider_user_id="external-1",
        provider_username="external-user",
        provider_email="external@example.com",
        first_login=datetime.now(UTC) - timedelta(days=2),
        last_login=datetime.now(UTC),
    )
    role_query = _Query([role])
    role_manager = SimpleNamespace(all=lambda: role_query)
    target = _user(roles=[role] if roles_fetched else role_manager)
    if roles_fetched:
        target._fetched_relations = {"roles"}

    with patch(
        "app.models.user_sso_connection.UserSSOConnection.filter",
        return_value=_Query([connection]),
    ):
        serialized = await users.serialize_user_with_sso(target)

    assert serialized["status"] == "active"
    assert serialized["roles"][0]["permissions"][0]["code"] == "admin:user:read"
    assert serialized["sso_connections"][0]["provider_name"] == "oidc"
    if not roles_fetched:
        assert ("prefetch_related", ("permissions",), {}) in role_query.calls


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("smtp_enabled", "bulk_rate", "found_users", "expected_key"),
    [
        (False, (True, 0, 100), [], "smtp_not_configured"),
        (True, (False, 100, 0), [], "email_rate_limit_exceeded"),
        (True, (True, 0, 100), [], "user_not_found"),
        (True, (True, 0, 1), [_user(), _user()], "email_quota_insufficient"),
    ],
)
async def test_send_email_rejects_configuration_rate_and_recipient_boundaries(
    admin, smtp_enabled, bulk_rate, found_users, expected_key
):
    with (
        patch.object(
            users.SiteSetting, "get_value", AsyncMock(return_value=smtp_enabled)
        ),
        patch.object(users, "check_bulk_email_rate", AsyncMock(return_value=bulk_rate)),
        patch.object(users.User, "filter", return_value=_Query(found_users)),
        pytest.raises(BusinessError) as exc,
    ):
        await users.send_email_to_users(
            data=users.SendEmailRequest(
                subject="Maintenance", content="Tonight", user_ids=[uuid4()]
            ),
            background_tasks=MagicMock(),
            current_user=admin,
        )

    assert exc.value.msg_key == expected_key


@pytest.mark.anyio
async def test_send_email_queues_eligible_users_and_persists_rate_counts(admin):
    eligible = _user(username="eligible")
    missing_email = _user(email="")
    rate_limited = _user(email="limited@example.com")
    background_tasks = MagicMock()
    increment_recipient = AsyncMock()
    increment_bulk = AsyncMock()

    with (
        patch.object(users.SiteSetting, "get_value", AsyncMock(return_value=True)),
        patch.object(
            users, "check_bulk_email_rate", AsyncMock(return_value=(True, 4, 96))
        ),
        patch.object(
            users,
            "check_recipient_email_rate",
            AsyncMock(side_effect=[(True, 0), (False, 5)]),
        ),
        patch.object(users, "increment_recipient_email_count", increment_recipient),
        patch.object(users, "increment_bulk_email_count", increment_bulk),
        patch.object(
            users.User,
            "filter",
            return_value=_Query([eligible, missing_email, rate_limited]),
        ),
    ):
        response = await users.send_email_to_users(
            data=users.SendEmailRequest(
                subject="Maintenance",
                content="Tonight",
                user_ids=[eligible.id, missing_email.id, rate_limited.id],
            ),
            background_tasks=background_tasks,
            current_user=admin,
        )

    assert response["data"] == {"sent_count": 1, "skipped_count": 1, "total": 3}
    assert background_tasks.add_task.call_args.kwargs["to_email"] == eligible.email
    assert "Hi eligible" in background_tasks.add_task.call_args.kwargs["body_html"]
    increment_recipient.assert_awaited_once_with(eligible.email)
    increment_bulk.assert_awaited_once_with(str(admin.id), 1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "function",
    [
        users.update_user,
        users.force_password_change,
        users.reset_password_expiration,
        users.exempt_password_expiration,
    ],
)
async def test_user_mutations_reject_missing_user(fake_request, admin, function):
    kwargs = {"current_user": admin}
    if function is users.update_user:
        kwargs["user_in"] = UserUpdate(email="new@example.com")
    elif function is users.exempt_password_expiration:
        kwargs["data"] = users.ExemptPasswordExpirationRequest(exempt=False)

    with (
        patch.object(users.User, "filter", return_value=_Query(None)),
        pytest.raises(BusinessError) as exc,
    ):
        await function(request=fake_request, user_id=uuid4(), **kwargs)

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_exemption_false_preserves_force_change(fake_request, admin):
    target = _user(force_password_change=True)

    with (
        patch.object(users.User, "filter", return_value=_Query(target)),
        patch.object(users.AuditLogService, "log", AsyncMock()),
    ):
        await users.exempt_password_expiration(
            fake_request,
            target.id,
            users.ExemptPasswordExpirationRequest(exempt=False),
            current_user=admin,
        )

    assert target.password_expiration_exempt is False
    assert target.force_password_change is True


@pytest.mark.anyio
async def test_expiring_passwords_serializes_missing_optional_dates(admin):
    target = _user(
        password_changed_at=None,
        password_expires_at=None,
        last_login=None,
    )

    with (
        patch.object(users.SiteSetting, "get_value", AsyncMock(return_value=7)),
        patch.object(users.User, "filter", return_value=_Query([target], count=1)),
    ):
        response = await users.get_expiring_passwords(
            page=1, page_size=20, filter="all", current_user=admin
        )

    item = response["data"].items[0]
    assert item.password_changed_at is None
    assert item.password_expires_at is None
    assert item.days_until_expiration is None
    assert item.last_login is None
