from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import users
from app.schemas.user import UserCreate, UserUpdate


class Query:
    def __init__(self, result=None, *, first=None, count=0):
        self.result = result
        self.first_result = first if first is not None else result
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

    def offset(self, *args):
        self.calls.append(("offset", args, {}))
        return self

    def limit(self, *args):
        self.calls.append(("limit", args, {}))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    async def count(self):
        return self.count_result

    async def first(self):
        return self.first_result

    async def all(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def admin():
    return SimpleNamespace(id=uuid4(), username="admin")


def user_record(**overrides):
    data = dict(
        id=uuid4(),
        username="alice",
        email="alice@example.com",
        is_active=True,
        approval_status="approved",
        is_superuser=False,
        email_verified=True,
        avatar_url=None,
        locale="en",
        auth_source="local",
        external_id=None,
        force_password_change=False,
        password_expiration_exempt=False,
        roles=SimpleNamespace(clear=AsyncMock(), add=AsyncMock()),
        update_from_dict=AsyncMock(),
        save=AsyncMock(),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.anyio
async def test_read_users_applies_all_optional_filters_and_serializes(monkeypatch):
    target = user_record()
    query = Query([target], count=1)
    monkeypatch.setattr(users.User, "all", lambda: query)
    monkeypatch.setattr(
        users, "serialize_user_with_sso", AsyncMock(return_value={"id": str(target.id)})
    )
    excluded = [uuid4()]

    response = await users.read_users(
        page=2,
        page_size=10,
        status=["active", "inactive", "pending"],
        search="alice",
        role=["admin"],
        exclude_user_id=excluded,
        current_user=admin(),
    )

    assert response["data"]["items"] == [{"id": str(target.id)}]
    assert ("distinct", (), {}) in query.calls
    assert ("exclude", (), {"id__in": excluded}) in query.calls
    assert ("offset", (10,), {}) in query.calls
    assert any(name == "filter" and args for name, args, _ in query.calls)
    assert any(kwargs == {"roles__name__in": ["admin"]} for _, _, kwargs in query.calls)


@pytest.mark.anyio
async def test_create_user_keeps_explicit_locale_and_serializes_created_user(
    monkeypatch,
):
    created = user_record(locale="zh")
    filters = [Query(first=None), Query(first=None)]
    monkeypatch.setattr(users.User, "filter", lambda **_kwargs: filters.pop(0))
    monkeypatch.setattr(
        users.security, "get_password_hash", lambda password: f"hash:{password}"
    )
    monkeypatch.setattr(users.SiteSetting, "get_value", AsyncMock())
    monkeypatch.setattr(users.User, "create", AsyncMock(return_value=created))
    monkeypatch.setattr(users.User, "get", lambda **_kwargs: Query(created))
    monkeypatch.setattr(users.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        users, "serialize_user_with_sso", AsyncMock(return_value={"locale": "zh"})
    )

    response = await users.create_user(
        request=SimpleNamespace(),
        user_in=UserCreate(
            username="alice",
            email="alice@example.com",
            password="Password123!",
            locale="zh",
        ),
        current_user=admin(),
    )

    users.SiteSetting.get_value.assert_not_awaited()
    users.User.create.assert_awaited_once()
    assert users.User.create.await_args.kwargs["locale"] == "zh"
    assert response["data"] == {"locale": "zh"}


@pytest.mark.anyio
async def test_update_user_without_password_skips_password_notification(monkeypatch):
    target = user_record()
    updated = user_record(username="renamed")
    monkeypatch.setattr(users.User, "filter", lambda **_kwargs: Query(target))
    monkeypatch.setattr(users.User, "get", lambda **_kwargs: Query(updated))
    monkeypatch.setattr(users.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(users.AutoNotificationService, "send_to_user", AsyncMock())
    monkeypatch.setattr(
        users,
        "serialize_user_with_sso",
        AsyncMock(return_value={"username": "renamed"}),
    )

    response = await users.update_user(
        request=SimpleNamespace(),
        user_id=target.id,
        user_in=UserUpdate(username="renamed"),
        current_user=admin(),
    )

    target.update_from_dict.assert_awaited_once_with({})
    users.AutoNotificationService.send_to_user.assert_not_awaited()
    assert response["data"] == {"username": "renamed"}
