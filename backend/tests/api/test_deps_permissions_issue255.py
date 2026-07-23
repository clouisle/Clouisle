from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api import deps
from app.schemas.response import BusinessError, ResponseCode


def user(**overrides):
    values = {
        "is_active": True,
        "is_superuser": False,
        "approval_status": "approved",
        "locale": None,
        "roles": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def role(*permissions):
    return SimpleNamespace(
        permissions=[SimpleNamespace(code=permission) for permission in permissions]
    )


@pytest.mark.anyio
async def test_active_user_rejects_inactive_states_and_sets_locale(monkeypatch):
    for approval_status, expected_key in (
        ("pending", "pending_approval_user"),
        ("approved", "inactive_user"),
    ):
        with pytest.raises(BusinessError) as exc:
            await deps.get_current_active_user(
                user(is_active=False, approval_status=approval_status)
            )
        assert exc.value.code == ResponseCode.INACTIVE_USER
        assert exc.value.msg_key == expected_key

    set_language = Mock()
    monkeypatch.setattr(deps, "set_language", set_language)
    current = user(locale="zh")

    assert await deps.get_current_active_user(current) is current
    set_language.assert_called_once_with("zh")


@pytest.mark.anyio
async def test_superuser_dependency_enforces_privilege():
    current = user()
    with pytest.raises(BusinessError) as exc:
        await deps.get_current_active_superuser(current)
    assert exc.value.code == ResponseCode.INSUFFICIENT_PRIVILEGES

    current.is_superuser = True
    assert await deps.get_current_active_superuser(current) is current


def test_global_permission_accepts_exact_and_wildcard_codes():
    assert deps.user_has_global_permission(
        user(roles=[role("admin:users")]), "admin:users"
    )
    assert deps.user_has_global_permission(user(roles=[role("*")]), "admin:teams")
    assert not deps.user_has_global_permission(
        user(roles=[role("admin:users")]), "admin:teams"
    )


@pytest.mark.anyio
async def test_scoped_permission_queries_assignments_and_accepts_wildcard(monkeypatch):
    scope_id = uuid4()

    class Query:
        def prefetch_related(self, relation):
            assert relation == "role__permissions"
            return self

        def __await__(self):
            async def resolve():
                return [SimpleNamespace(role=role("*"))]

            return resolve().__await__()

    filtered = Mock(return_value=Query())
    monkeypatch.setattr(deps.ScopedRoleAssignment, "filter", filtered)
    current = user()

    assert await deps.user_has_scoped_permission(
        current, "workflow:update", "workflow", scope_id
    )
    filtered.assert_called_once_with(
        user=current, scope_type="workflow", scope_id=scope_id
    )


@pytest.mark.anyio
async def test_check_scoped_permission_covers_all_authorization_paths(monkeypatch):
    scope_id = uuid4()
    scoped = AsyncMock(return_value=True)
    monkeypatch.setattr(deps, "user_has_scoped_permission", scoped)

    await deps.check_scoped_permission(
        user(is_superuser=True), "workflow:update", "workflow", scope_id
    )
    await deps.check_scoped_permission(
        user(roles=[role("admin:users")]), "admin:users", "team", scope_id
    )
    await deps.check_scoped_permission(user(), "workflow:update", "workflow", scope_id)
    scoped.assert_awaited_once()

    scoped.return_value = False
    with pytest.raises(BusinessError) as exc:
        await deps.check_scoped_permission(
            user(), "workflow:update", "workflow", scope_id
        )
    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    assert exc.value.kwargs["permission"] == "workflow:update"


@pytest.mark.anyio
async def test_permission_checker_allows_superuser_and_matching_role():
    checker = deps.PermissionChecker("admin:users")
    superuser = user(is_superuser=True)
    authorized = user(roles=[role("admin:users")])

    assert await checker(superuser) is superuser
    assert await checker(authorized) is authorized

    with pytest.raises(BusinessError) as exc:
        await checker(user())
    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    assert exc.value.kwargs["permission"] == "admin:users"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("checker", "relation_name", "error_key"),
    [
        (deps.check_api_key_agent_access, "agents", "api_key_no_agent_access"),
        (
            deps.check_api_key_workflow_access,
            "workflows",
            "api_key_no_workflow_access",
        ),
    ],
)
async def test_api_key_resource_access_boundaries(checker, relation_name, error_key):
    allowed_id = uuid4()
    denied_id = uuid4()

    await checker(None, denied_id)

    relation = SimpleNamespace(all=AsyncMock(return_value=[]))
    api_key = SimpleNamespace(**{relation_name: relation})
    await checker(api_key, denied_id)

    relation.all.return_value = [SimpleNamespace(id=allowed_id)]
    await checker(api_key, allowed_id)

    with pytest.raises(BusinessError) as exc:
        await checker(api_key, denied_id)
    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    assert exc.value.msg_key == error_key


@pytest.mark.anyio
async def test_optional_user_unwraps_authentication_result(monkeypatch):
    current = user()
    authenticate = AsyncMock(side_effect=[(current, None), None])
    monkeypatch.setattr(deps, "get_current_user_or_api_key_optional", authenticate)

    assert await deps.get_current_user_optional("token", None) is current
    assert await deps.get_current_user_optional(None, None) is None
