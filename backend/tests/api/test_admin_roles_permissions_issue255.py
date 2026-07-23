from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import permissions, roles
from app.schemas.response import BusinessError, ResponseCode, error
from app.schemas.user import PermissionCreate, RoleCreate


class Query:
    def __init__(self, *, first=None, rows=None, count=0, scopes=None):
        self.first_value = first
        self.rows = [] if rows is None else rows
        self.count_value = count
        self.scopes = [] if scopes is None else scopes
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
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

    def values_list(self, *args, **kwargs):
        self.calls.append(("values_list", args, kwargs))
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    def __await__(self):
        async def resolve():
            return (
                self.scopes
                if self.calls and self.calls[-1][0] == "values_list"
                else self.rows
            )

        return resolve().__await__()


class PermissionCode:
    def __init__(self, code):
        self.code = code


class RoleWithPermissions:
    def __init__(self, *codes):
        self.permissions = [PermissionCode(code) for code in codes]


@pytest.fixture
def admin_client():
    app = FastAPI()
    app.include_router(roles.router, prefix="/api/v1/admin/roles")
    app.include_router(permissions.router, prefix="/api/v1/admin/permissions")

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

    user = SimpleNamespace(is_superuser=False, roles=[])

    async def current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path", "required"),
    [
        ("get", "/roles", "admin:role:read"),
        ("post", "/roles", "admin:role:create"),
        ("put", f"/roles/{uuid4()}", "admin:role:update"),
        ("delete", f"/roles/{uuid4()}", "admin:role:delete"),
        ("get", "/permissions", "admin:permission:read"),
        ("post", "/permissions", "admin:permission:create"),
        ("put", f"/permissions/{uuid4()}", "admin:permission:update"),
        ("delete", f"/permissions/{uuid4()}", "admin:permission:delete"),
    ],
)
def test_routes_enforce_their_specific_permission(admin_client, method, path, required):
    client, user = admin_client
    user.roles = [RoleWithPermissions("admin:unrelated")]

    response = client.request(method, f"/api/v1/admin{path}", json={})

    assert response.status_code == 403
    assert response.json()["code"] == ResponseCode.PERMISSION_DENIED
    user.roles = [RoleWithPermissions(required)]


@pytest.mark.anyio
async def test_role_list_filters_paginates_and_returns_rows(monkeypatch):
    row = SimpleNamespace(id=uuid4())
    query = Query(rows=[row], count=3)
    monkeypatch.setattr(roles.Role, "all", lambda: query)

    result = await roles.read_roles(
        page=2, page_size=1, search="ops", current_user=object()
    )

    assert result["data"] == {"items": [row], "total": 3, "page": 2, "page_size": 1}
    assert [call[0] for call in query.calls] == [
        "filter",
        "offset",
        "limit",
        "prefetch_related",
    ]
    assert query.calls[1][1] == (1,)


@pytest.mark.anyio
async def test_role_detail_handles_found_and_missing(monkeypatch):
    role = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=role))
    assert (await roles.read_role(role.id, current_user=object()))["data"] is role

    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=None))
    with pytest.raises(BusinessError) as exc:
        await roles.read_role(uuid4(), current_user=object())
    assert (exc.value.code, exc.value.status_code) == (ResponseCode.ROLE_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_create_role_rejects_duplicate_before_create(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=object()))
    monkeypatch.setattr(roles.Role, "create", create)

    with pytest.raises(BusinessError) as exc:
        await roles.create_role(role_in=RoleCreate(name="ops"), current_user=object())

    assert exc.value.code == ResponseCode.ROLE_NAME_EXISTS
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_role_assigns_known_permissions_and_reloads(monkeypatch):
    relation = SimpleNamespace(add=AsyncMock())
    created = SimpleNamespace(id=uuid4(), permissions=relation)
    loaded = SimpleNamespace(id=created.id)
    known = PermissionCode("admin:user:read")
    role_filter = MagicMock(return_value=Query(first=None))
    permission_filter = MagicMock(side_effect=[Query(first=known), Query(first=None)])
    create = AsyncMock(return_value=created)
    get = MagicMock(return_value=Query(first=loaded, rows=loaded))
    monkeypatch.setattr(roles.Role, "filter", role_filter)
    monkeypatch.setattr(roles.Role, "create", create)
    monkeypatch.setattr(roles.Role, "get", get)
    monkeypatch.setattr(roles.Permission, "filter", permission_filter)

    result = await roles.create_role(
        role_in=RoleCreate(
            name="ops", permissions=["admin:user:read", "missing:permission"]
        ),
        current_user=object(),
    )

    assert result["data"] is loaded
    create.assert_awaited_once_with(name="ops", description=None, is_system_role=False)
    relation.add.assert_awaited_once_with(known)
    assert permission_filter.call_count == 2


@pytest.mark.anyio
async def test_update_role_guards_missing_system_and_duplicate_before_save(monkeypatch):
    save = AsyncMock()
    custom = SimpleNamespace(
        name="old", description=None, is_system_role=False, save=save
    )
    outcomes = iter([None, SimpleNamespace(is_system_role=True), custom, object()])
    monkeypatch.setattr(
        roles.Role, "filter", lambda **kwargs: Query(first=next(outcomes))
    )

    with pytest.raises(BusinessError) as missing:
        await roles.update_role(
            role_id=uuid4(), role_in=roles.RoleUpdate(name="new"), current_user=object()
        )
    with pytest.raises(BusinessError) as system:
        await roles.update_role(
            role_id=uuid4(), role_in=roles.RoleUpdate(name="new"), current_user=object()
        )
    with pytest.raises(BusinessError) as duplicate:
        await roles.update_role(
            role_id=uuid4(), role_in=roles.RoleUpdate(name="new"), current_user=object()
        )

    assert missing.value.code == ResponseCode.ROLE_NOT_FOUND
    assert system.value.code == ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE
    assert duplicate.value.code == ResponseCode.ROLE_NAME_EXISTS
    save.assert_not_awaited()


@pytest.mark.anyio
async def test_update_role_persists_fields_then_reloads(monkeypatch):
    role_id = uuid4()
    role = SimpleNamespace(
        name="old", description="before", is_system_role=False, save=AsyncMock()
    )
    loaded = SimpleNamespace(id=role_id)
    monkeypatch.setattr(
        roles.Role,
        "filter",
        lambda **kwargs: Query(first=role if "id" in kwargs else None),
    )
    monkeypatch.setattr(
        roles.Role, "get", lambda **kwargs: Query(first=loaded, rows=loaded)
    )

    result = await roles.update_role(
        role_id=role_id,
        role_in=roles.RoleUpdate(name="new", description="after"),
        current_user=object(),
    )

    assert result["data"] is loaded
    assert (role.name, role.description) == ("new", "after")
    role.save.assert_awaited_once()


@pytest.mark.anyio
async def test_update_role_save_failure_does_not_reload(monkeypatch):
    role = SimpleNamespace(
        name="old",
        description=None,
        is_system_role=False,
        save=AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    get = MagicMock()
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=role))
    monkeypatch.setattr(roles.Role, "get", get)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await roles.update_role(
            role_id=uuid4(),
            role_in=roles.RoleUpdate(description="new"),
            current_user=object(),
        )

    get.assert_not_called()


@pytest.mark.anyio
async def test_role_permission_assignment_guards_before_clear(monkeypatch):
    clear = AsyncMock()
    system = SimpleNamespace(
        is_system_role=True, permissions=SimpleNamespace(clear=clear)
    )
    outcomes = iter([None, system])
    monkeypatch.setattr(
        roles.Role, "filter", lambda **kwargs: Query(first=next(outcomes))
    )

    for expected in (
        ResponseCode.ROLE_NOT_FOUND,
        ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE,
    ):
        with pytest.raises(BusinessError) as exc:
            await roles.update_role_permissions(
                role_id=uuid4(),
                permissions_in=roles.RolePermissionsUpdate(permissions=["x"]),
                current_user=object(),
            )
        assert exc.value.code == expected

    clear.assert_not_awaited()


@pytest.mark.anyio
async def test_role_permission_assignment_replaces_and_validates(monkeypatch):
    relation = SimpleNamespace(clear=AsyncMock(), add=AsyncMock())
    role = SimpleNamespace(id=uuid4(), is_system_role=False, permissions=relation)
    permission = PermissionCode("admin:user:read")
    loaded = SimpleNamespace(id=role.id)
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=role))
    monkeypatch.setattr(
        roles.Role, "get", lambda **kwargs: Query(first=loaded, rows=loaded)
    )
    monkeypatch.setattr(
        roles.Permission, "filter", lambda **kwargs: Query(first=permission)
    )

    result = await roles.update_role_permissions(
        role_id=role.id,
        permissions_in=roles.RolePermissionsUpdate(permissions=[permission.code]),
        current_user=object(),
    )

    assert result["data"] is loaded
    relation.clear.assert_awaited_once()
    relation.add.assert_awaited_once_with(permission)


@pytest.mark.anyio
async def test_role_permission_missing_code_stops_add_and_reload(monkeypatch):
    relation = SimpleNamespace(clear=AsyncMock(), add=AsyncMock())
    role = SimpleNamespace(is_system_role=False, permissions=relation)
    get = MagicMock()
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=role))
    monkeypatch.setattr(roles.Permission, "filter", lambda **kwargs: Query(first=None))
    monkeypatch.setattr(roles.Role, "get", get)

    with pytest.raises(BusinessError) as exc:
        await roles.update_role_permissions(
            role_id=uuid4(),
            permissions_in=roles.RolePermissionsUpdate(permissions=["missing"]),
            current_user=object(),
        )

    assert exc.value.code == ResponseCode.PERMISSION_NOT_FOUND
    relation.clear.assert_awaited_once()
    relation.add.assert_not_awaited()
    get.assert_not_called()


@pytest.mark.anyio
async def test_delete_role_guards_usage_then_deletes(monkeypatch):
    role = SimpleNamespace(is_system_role=False, delete=AsyncMock())
    monkeypatch.setattr(roles.Role, "filter", lambda **kwargs: Query(first=role))
    user_count = MagicMock(side_effect=[Query(count=2), Query(count=0), Query(count=0)])
    scoped_count = MagicMock(side_effect=[Query(count=1), Query(count=0)])
    monkeypatch.setattr(roles.User, "filter", user_count)
    monkeypatch.setattr(roles.ScopedRoleAssignment, "filter", scoped_count)

    with pytest.raises(BusinessError) as global_use:
        await roles.delete_role(uuid4(), current_user=object())
    with pytest.raises(BusinessError) as scoped_use:
        await roles.delete_role(uuid4(), current_user=object())
    result = await roles.delete_role(uuid4(), current_user=object())

    assert global_use.value.code == scoped_use.value.code == ResponseCode.ROLE_IN_USE
    assert result["data"] is role
    role.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_role_rejects_missing_and_system(monkeypatch):
    outcomes = iter([None, SimpleNamespace(is_system_role=True)])
    monkeypatch.setattr(
        roles.Role, "filter", lambda **kwargs: Query(first=next(outcomes))
    )

    with pytest.raises(BusinessError) as missing:
        await roles.delete_role(uuid4(), current_user=object())
    with pytest.raises(BusinessError) as system:
        await roles.delete_role(uuid4(), current_user=object())

    assert missing.value.code == ResponseCode.ROLE_NOT_FOUND
    assert system.value.code == ResponseCode.CANNOT_DELETE_SYSTEM_ROLE


@pytest.mark.anyio
async def test_permission_scopes_merge_filter_and_sort(monkeypatch):
    query = Query(scopes=["team", "", "custom"])
    monkeypatch.setattr(permissions.Permission, "all", lambda: query)
    monkeypatch.setattr(
        permissions.SystemPermissions,
        "get_all_definitions",
        lambda: [{"scope": "admin"}, {"scope": "team"}],
    )

    result = await permissions.read_permission_scopes(current_user=object())

    assert result["data"] == [
        {"value": "admin", "label": "admin"},
        {"value": "custom", "label": "custom"},
        {"value": "team", "label": "team"},
    ]


@pytest.mark.anyio
async def test_permission_list_filters_search_and_paginates(monkeypatch):
    row = SimpleNamespace(id=uuid4())
    query = Query(rows=[row], count=4)
    monkeypatch.setattr(permissions.Permission, "all", lambda: query)

    result = await permissions.read_permissions(
        page=2,
        page_size=2,
        scope=["admin", "team"],
        search="read",
        current_user=object(),
    )

    assert result["data"] == {"items": [row], "total": 4, "page": 2, "page_size": 2}
    assert [call[0] for call in query.calls] == [
        "filter",
        "distinct",
        "filter",
        "offset",
        "limit",
    ]
    assert query.calls[0][2] == {"scope__in": ["admin", "team"]}
    assert query.calls[3][1] == (2,)


@pytest.mark.anyio
async def test_permission_detail_handles_found_and_missing(monkeypatch):
    permission = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=permission)
    )
    assert (await permissions.read_permission(permission.id, current_user=object()))[
        "data"
    ] is permission

    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await permissions.read_permission(uuid4(), current_user=object())
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_NOT_FOUND,
        404,
    )


@pytest.mark.anyio
async def test_create_permission_duplicate_and_success(monkeypatch):
    payload = PermissionCreate(scope="custom", code="custom:read", description="Read")
    create = AsyncMock()
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=object())
    )
    monkeypatch.setattr(permissions.Permission, "create", create)

    with pytest.raises(BusinessError) as exc:
        await permissions.create_permission(
            permission_in=payload, current_user=object()
        )
    assert exc.value.code == ResponseCode.PERMISSION_CODE_EXISTS
    create.assert_not_awaited()

    created = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=None)
    )
    create.return_value = created
    result = await permissions.create_permission(
        permission_in=payload, current_user=object()
    )
    assert result["data"] is created
    create.assert_awaited_once_with(
        scope="custom", code="custom:read", description="Read", is_system=False
    )


@pytest.mark.anyio
async def test_update_permission_guards_missing_system_and_duplicate(monkeypatch):
    payload = PermissionCreate(scope="custom", code="new:read")
    custom = SimpleNamespace(code="old:read", is_system=False, save=AsyncMock())
    outcomes = iter([None, SimpleNamespace(is_system=True), custom, object()])
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=next(outcomes))
    )

    with pytest.raises(BusinessError) as missing:
        await permissions.update_permission(
            permission_id=uuid4(), permission_in=payload, current_user=object()
        )
    with pytest.raises(BusinessError) as system:
        await permissions.update_permission(
            permission_id=uuid4(), permission_in=payload, current_user=object()
        )
    with pytest.raises(BusinessError) as duplicate:
        await permissions.update_permission(
            permission_id=uuid4(), permission_in=payload, current_user=object()
        )

    assert missing.value.code == ResponseCode.PERMISSION_NOT_FOUND
    assert system.value.code == ResponseCode.CANNOT_UPDATE_SYSTEM_PERMISSION
    assert duplicate.value.code == ResponseCode.PERMISSION_CODE_EXISTS
    custom.save.assert_not_awaited()


@pytest.mark.anyio
async def test_update_permission_persists_and_propagates_failure(monkeypatch):
    permission = SimpleNamespace(
        scope="old",
        code="same:read",
        description=None,
        is_system=False,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=permission)
    )
    payload = PermissionCreate(scope="new", code="same:read", description="Updated")

    result = await permissions.update_permission(
        permission_id=uuid4(), permission_in=payload, current_user=object()
    )
    assert result["data"] is permission
    assert (permission.scope, permission.description) == ("new", "Updated")
    permission.save.assert_awaited_once()

    permission.save = AsyncMock(side_effect=RuntimeError("write failed"))
    with pytest.raises(RuntimeError, match="write failed"):
        await permissions.update_permission(
            permission_id=uuid4(), permission_in=payload, current_user=object()
        )


@pytest.mark.anyio
async def test_delete_permission_guards_and_propagates_delete_failure(monkeypatch):
    custom = SimpleNamespace(is_system=False, delete=AsyncMock())
    outcomes = iter([None, SimpleNamespace(is_system=True), custom])
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=next(outcomes))
    )

    with pytest.raises(BusinessError) as missing:
        await permissions.delete_permission(uuid4(), current_user=object())
    with pytest.raises(BusinessError) as system:
        await permissions.delete_permission(uuid4(), current_user=object())
    result = await permissions.delete_permission(uuid4(), current_user=object())

    assert missing.value.code == ResponseCode.PERMISSION_NOT_FOUND
    assert system.value.code == ResponseCode.CANNOT_DELETE_SYSTEM_PERMISSION
    assert result["data"] is custom
    custom.delete.assert_awaited_once()

    failing = SimpleNamespace(
        is_system=False, delete=AsyncMock(side_effect=RuntimeError("delete failed"))
    )
    monkeypatch.setattr(
        permissions.Permission, "filter", lambda **kwargs: Query(first=failing)
    )
    with pytest.raises(RuntimeError, match="delete failed"):
        await permissions.delete_permission(uuid4(), current_user=object())
