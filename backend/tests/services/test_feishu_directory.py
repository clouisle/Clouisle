import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.user import User
from app.schemas.user import User as UserSchema
from app.services import feishu_directory

_real_directory_exclusions = feishu_directory._self_service_directory_exclusions


@pytest.fixture(autouse=True)
def no_self_service_links(monkeypatch):
    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        AsyncMock(return_value=(set(), set())),
    )


class Query:
    def __init__(self, result=None, results=None):
        self.result = result
        self.results = results or []

    def using_db(self, _connection):
        return self

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    def exclude(self, **_kwargs):
        return self

    async def exists(self):
        return False

    def __await__(self):
        async def _result():
            return self.results

        return _result().__await__()


class Connection:
    pass


@asynccontextmanager
async def _transaction():
    yield Connection()


@pytest.mark.asyncio
async def test_sync_adds_stable_id_suffix_only_when_username_is_taken(monkeypatch):
    created = []
    existing_usernames = {"Ada Lovelace"}

    async def create_user(**kwargs):
        user = SimpleNamespace(id=uuid4(), **kwargs)
        created.append(user)
        existing_usernames.add(user.username)
        return user

    class UsernameQuery(Query):
        async def exists(self):
            return self.result is not None

    def user_filter(**kwargs):
        if "username" in kwargs:
            exists = kwargs["username"] == "Ada_Lovelace"
            return UsernameQuery(
                SimpleNamespace(username=kwargs["username"]) if exists else None
            )
        return Query()

    async def create_binding(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(User, "filter", user_filter)
    monkeypatch.setattr(User, "create", create_user)
    monkeypatch.setattr(feishu_directory.FeishuUser, "filter", lambda **kwargs: Query())
    monkeypatch.setattr(feishu_directory.FeishuUser, "create", create_binding)
    monkeypatch.setattr(feishu_directory, "assign_default_role", _async_noop)
    monkeypatch.setattr(feishu_directory, "assign_default_team", _async_noop)
    monkeypatch.setattr(feishu_directory.SiteSetting, "get_value", _async_locale)
    monkeypatch.setattr(feishu_directory.AuditLogService, "log", _async_noop)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "ou_conflict", "open", None, "Ada Lovelace", "ada@example.com", None
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    expected_suffix = hashlib.sha256(b"ou_conflict").hexdigest()[:10]
    assert result.created == 1
    assert created[0].username == f"Ada_Lovelace_{expected_suffix}"


@pytest.mark.asyncio
async def test_sync_creates_user_and_persists_feishu_identity(monkeypatch):
    user_id = uuid4()
    created = []
    audit = []

    async def create_user(**kwargs):
        user = SimpleNamespace(id=user_id, **kwargs)
        created.append(user)
        return user

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(User, "filter", lambda **kwargs: Query())
    monkeypatch.setattr(User, "create", create_user)
    monkeypatch.setattr(feishu_directory.FeishuUser, "filter", lambda **kwargs: Query())

    async def create_binding(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(feishu_directory.FeishuUser, "create", create_binding)
    monkeypatch.setattr(feishu_directory, "assign_default_role", _async_noop)
    monkeypatch.setattr(feishu_directory, "assign_default_team", _async_noop)
    monkeypatch.setattr(feishu_directory.SiteSetting, "get_value", _async_locale)
    monkeypatch.setattr(feishu_directory.AuditLogService, "log", _capture(audit))

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                user_id="ou_1",
                open_id="open_1",
                union_id=None,
                name="Ada Lovelace",
                email=None,
                avatar_url=None,
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert result.created == 1
    assert result.updated == result.skipped == 0
    assert created[0].auth_source == "feishu"
    assert created[0].external_id == "ou_1"
    assert created[0].username == "Ada_Lovelace"
    assert audit[0]["changes"]["after"]["external_id"] == "ou_1"


@pytest.mark.asyncio
async def test_sync_updates_only_existing_feishu_identity(monkeypatch):
    user_id = uuid4()
    existing = SimpleNamespace(
        id=user_id,
        username="old-name",
        email="old@example.com",
        auth_source="feishu",
        external_id="ou_1",
    )
    existing.save = AsyncMock()
    feishu_binding = SimpleNamespace(user_id=user_id)
    lookup_kwargs = []

    def lookup(**kwargs):
        lookup_kwargs.append(kwargs)
        return Query(existing if "id" in kwargs or "auth_source" in kwargs else None)

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(User, "filter", lookup)
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **kwargs: Query(feishu_binding)
    )
    monkeypatch.setattr(feishu_directory, "assign_default_role", _async_noop)
    monkeypatch.setattr(feishu_directory, "assign_default_team", _async_noop)
    monkeypatch.setattr(feishu_directory.AuditLogService, "log", _async_noop)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                user_id="ou_1",
                open_id="open_1",
                union_id=None,
                name="Ada Updated",
                email="ada@example.com",
                avatar_url=None,
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert result.updated == 1
    assert result.created == result.skipped == 0
    assert existing.username == "old-name"
    assert existing.email == "ada@example.com"
    assert existing.auth_source == "feishu"
    assert lookup_kwargs == [{"id": user_id}, {"email": "ada@example.com"}]
    assert feishu_binding.user_id == user_id


def test_placeholder_email_satisfies_the_api_response_email_contract():
    email = feishu_directory.placeholder_email("ou_1")
    assert email.endswith(feishu_directory.PLACEHOLDER_EMAIL_DOMAIN)
    assert feishu_directory.is_placeholder_email(email)
    assert feishu_directory.is_placeholder_email(
        "feishu-legacy@accounts.clouisle.invalid"
    )
    assert not feishu_directory.is_placeholder_email("ada@example.org")
    assert feishu_directory.placeholder_email("ou_1") == email
    user = UserSchema(
        id=uuid4(),
        username="feishu_ada",
        email=email,
        created_at=datetime.now(UTC),
        auth_source="feishu",
        external_id="ou_1",
    )
    assert str(user.email) == email


@pytest.mark.asyncio
async def test_sync_replaces_legacy_placeholder_email_with_the_feishu_email(
    monkeypatch,
):
    user_id = uuid4()
    legacy = SimpleNamespace(
        id=user_id,
        username="feishu_ada",
        email="feishu-legacy@accounts.clouisle.invalid",
        auth_source="feishu",
        external_id="ou_1",
        save=AsyncMock(),
    )
    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(User, "filter", lambda **kwargs: Query(legacy))
    monkeypatch.setattr(
        feishu_directory.FeishuUser,
        "filter",
        lambda **kwargs: Query(SimpleNamespace(user_id=user_id)),
    )
    monkeypatch.setattr(feishu_directory.AuditLogService, "log", _async_noop)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                user_id="ou_1",
                open_id="open_1",
                union_id=None,
                name="Ada",
                email="ada@example.org",
                avatar_url=None,
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert result.updated == 1
    assert legacy.email == "ada@example.org"
    legacy.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_department_teams_creates_stable_teams_and_adds_multi_department_users(
    monkeypatch,
):
    teams = []
    memberships = []
    mappings = []
    users = {"u1": SimpleNamespace(id=uuid4()), "u2": SimpleNamespace(id=uuid4())}

    async def create_team(**kwargs):
        team = SimpleNamespace(
            id=kwargs["id"], name=kwargs["name"], team_id=kwargs["id"], save=AsyncMock()
        )
        teams.append(team)
        return team

    async def create_mapping(**kwargs):
        mapping = SimpleNamespace(
            department_id=kwargs["department_id"], team_id=kwargs["team_id"]
        )
        mappings.append(mapping)
        return mapping

    async def get_or_create_membership(**kwargs):
        key = (kwargs["team"].id, kwargs["user"].id)
        existing = next(
            (membership for membership in memberships if membership.key == key), None
        )
        if existing:
            return existing, False
        membership = SimpleNamespace(key=key, **kwargs)
        memberships.append(membership)
        return membership, True

    def mapping_filter(**kwargs):
        return Query(
            next(
                (
                    mapping
                    for mapping in mappings
                    if mapping.department_id == kwargs["department_id"]
                ),
                None,
            )
        )

    def team_filter(**kwargs):
        return Query(
            next(
                (
                    team
                    for team in teams
                    if team.id == kwargs.get("id") or team.name == kwargs.get("name")
                ),
                None,
            )
        )

    def binding_filter(**kwargs):
        return Query(SimpleNamespace(user_id=users[kwargs["feishu_user_id"]].id))

    def user_filter(**kwargs):
        return Query(
            next((user for user in users.values() if user.id == kwargs.get("id")), None)
        )

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping, "filter", mapping_filter
    )
    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping, "create", create_mapping
    )
    monkeypatch.setattr(feishu_directory.Team, "filter", team_filter)
    monkeypatch.setattr(feishu_directory.Team, "create", create_team)
    monkeypatch.setattr(feishu_directory.FeishuUser, "filter", binding_filter)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory.TeamMember, "get_or_create", get_or_create_membership
    )

    departments = [
        SimpleNamespace(department_id="dept-a", name="Research"),
        SimpleNamespace(department_id="dept-b", name="Research"),
    ]
    members = [
        feishu_directory.FeishuDirectoryUser(
            "u1", "o1", None, "Ada", None, None, frozenset({"dept-a", "dept-b"})
        ),
        feishu_directory.FeishuDirectoryUser(
            "u2", "o2", None, "Lin", None, None, frozenset({"dept-b"})
        ),
    ]

    assert await feishu_directory.sync_department_teams(departments, members) == 2
    assert len(teams) == 2
    assert {team.name for team in teams} == {"Research", "Research (dept-b)"}
    assert len(memberships) == 3
    assert await feishu_directory.sync_department_teams(departments, members) == 0
    assert len(teams) == 2
    assert len(memberships) == 3


async def _async_noop(*_args, **_kwargs):
    return None


async def _async_locale(*_args, **_kwargs):
    return "en"


def _capture(records):
    async def capture(**kwargs):
        records.append(kwargs)

    return capture


@pytest.mark.asyncio
async def test_department_sync_handles_empty_selection_and_missing_linked_user(
    monkeypatch,
):
    assert await feishu_directory.sync_department_teams([], []) == 0

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping,
        "filter",
        lambda **_kwargs: Query(),
    )
    monkeypatch.setattr(feishu_directory.Team, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(
        feishu_directory.Team,
        "create",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="Department")),
    )
    monkeypatch.setattr(feishu_directory.FeishuDepartmentMapping, "create", AsyncMock())
    monkeypatch.setattr(
        feishu_directory.FeishuUser,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(user_id=uuid4())),
    )
    monkeypatch.setattr(feishu_directory.User, "filter", lambda **_kwargs: Query())
    membership = AsyncMock()
    monkeypatch.setattr(feishu_directory.TeamMember, "get_or_create", membership)

    count = await feishu_directory.sync_department_teams(
        [SimpleNamespace(department_id="dept", name="Department")],
        [feishu_directory.FeishuDirectoryUser("u1", "o1", None, "Ada", None, None)],
    )

    assert count == 1
    membership.assert_not_awaited()


@pytest.mark.asyncio
async def test_department_team_sync_rejects_both_name_collision_paths(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Research", save=AsyncMock())
    mapping = SimpleNamespace(team_id=team.id, delete=AsyncMock())

    def collision_query(**kwargs):
        if "id" in kwargs:
            return Query(team)
        return Query(SimpleNamespace(name=kwargs["name"]))

    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping,
        "filter",
        lambda **_kwargs: Query(mapping),
    )
    monkeypatch.setattr(feishu_directory.Team, "filter", collision_query)
    with pytest.raises(ValueError, match="Team name collision"):
        await feishu_directory._get_or_create_department_team(
            SimpleNamespace(department_id="dept", name="Research"),
            connection=Connection(),
        )

    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping,
        "filter",
        lambda **_kwargs: Query(),
    )
    with pytest.raises(ValueError, match="Team name collision"):
        await feishu_directory._get_or_create_department_team(
            SimpleNamespace(department_id="dept", name="Research"),
            connection=Connection(),
        )


@pytest.mark.asyncio
async def test_directory_sync_skips_empty_and_dangling_bindings(monkeypatch):
    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory.FeishuUser,
        "filter",
        lambda **kwargs: Query(
            SimpleNamespace(user_id=uuid4())
            if kwargs["feishu_user_id"] == "dangling"
            else None
        ),
    )
    monkeypatch.setattr(feishu_directory.User, "filter", lambda **_kwargs: Query())

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                " ", "open", None, "Empty", None, None
            ),
            feishu_directory.FeishuDirectoryUser(
                "dangling", "open", None, "Dangling", None, None
            ),
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 0, 2)


@pytest.mark.asyncio
async def test_directory_exclusions_accept_only_string_profile_ids(monkeypatch):
    class LinkQuery:
        def values(self, *_fields):
            return self

        def __await__(self):
            async def result():
                return [
                    {
                        "user_id": uuid4(),
                        "provider_user_id": "provider-id",
                        "provider_data": {
                            "user_id": " profile-user ",
                            "union_id": "profile-union",
                            "open_id": 5,
                        },
                    },
                    {
                        "user_id": uuid4(),
                        "provider_user_id": "other-provider",
                        "provider_data": "not a profile",
                    },
                ]

            return result().__await__()

    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        _real_directory_exclusions,
    )
    monkeypatch.setattr(
        feishu_directory.UserSSOConnection,
        "filter",
        lambda **_kwargs: LinkQuery(),
    )
    user_ids, external_ids = await feishu_directory._self_service_directory_exclusions()

    assert len(user_ids) == 2
    assert external_ids == {
        "provider-id",
        "profile-user",
        "profile-union",
        "other-provider",
    }


@pytest.mark.asyncio
async def test_directory_sync_skips_email_conflict_and_username_conflict(monkeypatch):
    class ExistsQuery(Query):
        def __init__(self, exists):
            super().__init__()
            self.found = exists

        async def exists(self):
            return self.found

    def user_filter(**kwargs):
        if "email" in kwargs:
            return ExistsQuery(kwargs["email"] == "taken@example.com")
        if "username" in kwargs:
            return ExistsQuery(True)
        return Query()

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **_kwargs: Query()
    )

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "email-conflict", "o1", None, "Email", "taken@example.com", None
            ),
            feishu_directory.FeishuDirectoryUser(
                "name-conflict", "o2", None, "Taken", "free@example.com", None
            ),
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 0, 2)


@pytest.mark.asyncio
async def test_directory_sync_updates_existing_user_profile_and_skips_owned_email(
    monkeypatch,
):
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        username="known",
        email="known@accounts.clouisle.example",
        avatar_url=None,
        save=AsyncMock(),
    )
    binding = SimpleNamespace(user_id=user_id)

    class ExistsQuery(Query):
        async def exists(self):
            return True

    def user_filter(**kwargs):
        if "id" in kwargs or "auth_source" in kwargs:
            return Query(user)
        if "email" in kwargs:
            return ExistsQuery()
        return Query()

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **_kwargs: Query(binding)
    )
    monkeypatch.setattr(feishu_directory.AuditLogService, "log", _async_noop)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "linked", "o1", None, "Known", "taken@example.com", "avatar.png"
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 0, 1)
    user.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_directory_sync_reuses_auth_source_user_and_updates_avatar(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        username="old",
        email="local@example.com",
        avatar_url=None,
        save=AsyncMock(),
    )
    created_bindings = []

    class ExistsQuery(Query):
        async def exists(self):
            return False

    def user_filter(**kwargs):
        if "id" in kwargs:
            return Query()
        if "auth_source" in kwargs:
            return Query(user)
        return ExistsQuery()

    async def create_binding(**kwargs):
        created_bindings.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **_kwargs: Query()
    )
    monkeypatch.setattr(feishu_directory.FeishuUser, "create", create_binding)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "recovered", "o1", None, "Recovered", None, "avatar.png"
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 1, 0)
    assert user.email == "local@example.com"
    assert user.avatar_url == "avatar.png"
    assert created_bindings[0]["feishu_user_id"] == "recovered"
    user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_directory_sync_skips_taken_suffixed_username_and_preserves_nonplaceholder_email(
    monkeypatch,
):
    user = SimpleNamespace(
        id=uuid4(),
        username="old",
        email="local@example.com",
        avatar_url=None,
        save=AsyncMock(),
    )

    class ExistsQuery(Query):
        def __init__(self, found):
            super().__init__()
            self.found = found

        async def exists(self):
            return self.found

    def user_filter(**kwargs):
        if "username" in kwargs:
            return ExistsQuery(True)
        if "email" in kwargs:
            return ExistsQuery(False)
        if "id" in kwargs:
            return Query(user)
        if "auth_source" in kwargs:
            return Query()
        return Query()

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory.FeishuUser,
        "filter",
        lambda **kwargs: (
            Query(SimpleNamespace(user_id=user.id))
            if kwargs["feishu_user_id"] == "mapped"
            else Query()
        ),
    )

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "suffix-conflict", "o1", None, "New User", "free@example.com", None
            ),
            feishu_directory.FeishuDirectoryUser(
                "mapped", "o2", None, "Mapped", None, None
            ),
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 1, 1)
    assert user.email == "local@example.com"
    user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_department_sync_removes_stale_mapping_and_skips_excluded_members(
    monkeypatch,
):
    stale_mapping = SimpleNamespace(team_id=uuid4(), delete=AsyncMock())
    teams = []

    def mapping_filter(**_kwargs):
        return Query(stale_mapping if not teams else None)

    def team_filter(**kwargs):
        if "id" in kwargs:
            return Query()
        return Query()

    async def create_team(**kwargs):
        team = SimpleNamespace(id=kwargs["id"], name=kwargs["name"])
        teams.append(team)
        return team

    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping, "filter", mapping_filter
    )
    monkeypatch.setattr(feishu_directory.FeishuDepartmentMapping, "create", AsyncMock())
    monkeypatch.setattr(feishu_directory.Team, "filter", team_filter)
    monkeypatch.setattr(feishu_directory.Team, "create", create_team)
    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        AsyncMock(return_value=(set(), {"open-excluded"})),
    )
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **_kwargs: Query()
    )
    membership = AsyncMock()
    monkeypatch.setattr(feishu_directory.TeamMember, "get_or_create", membership)

    count = await feishu_directory.sync_department_teams(
        [SimpleNamespace(department_id="dept", name="Department")],
        [
            feishu_directory.FeishuDirectoryUser(
                "u1",
                "open-excluded",
                None,
                "Excluded",
                None,
                None,
                frozenset({"dept"}),
            )
        ],
    )

    assert count == 1
    stale_mapping.delete.assert_awaited_once()
    membership.assert_not_awaited()


@pytest.mark.asyncio
async def test_department_sync_skips_excluded_bindings_and_missing_local_users(
    monkeypatch,
):
    team = SimpleNamespace(id=uuid4(), name="Department", save=AsyncMock())
    mapping = SimpleNamespace(team_id=team.id)
    calls = 0
    excluded_user_id = uuid4()

    def binding_filter(**_kwargs):
        nonlocal calls
        calls += 1
        return Query(
            SimpleNamespace(user_id=excluded_user_id if calls == 1 else uuid4())
        )

    def user_filter(**_kwargs):
        return Query()

    monkeypatch.setattr(
        feishu_directory.Team,
        "filter",
        lambda **kwargs: Query(team if "id" in kwargs else None),
    )
    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory.FeishuDepartmentMapping,
        "filter",
        lambda **_kwargs: Query(mapping),
    )
    monkeypatch.setattr(feishu_directory.FeishuUser, "filter", binding_filter)
    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)
    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        AsyncMock(return_value=({excluded_user_id}, set())),
    )
    membership = AsyncMock()
    monkeypatch.setattr(feishu_directory.TeamMember, "get_or_create", membership)

    count = await feishu_directory.sync_department_teams(
        [SimpleNamespace(department_id="dept", name="Department")],
        [
            feishu_directory.FeishuDirectoryUser(
                "excluded", "o1", None, "Excluded", None, None, frozenset({"dept"})
            ),
            feishu_directory.FeishuDirectoryUser(
                "missing", "o2", None, "Missing", None, None, frozenset({"dept"})
            ),
        ],
    )

    assert count == 0
    assert calls == 2
    membership.assert_not_awaited()


@pytest.mark.asyncio
async def test_directory_sync_skips_excluded_id_and_excluded_legacy_user(monkeypatch):
    excluded_user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        AsyncMock(return_value=({excluded_user.id}, {"excluded-id"})),
    )
    monkeypatch.setattr(
        feishu_directory.FeishuUser, "filter", lambda **_kwargs: Query()
    )

    def user_filter(**kwargs):
        return Query(excluded_user if "auth_source" in kwargs else None)

    monkeypatch.setattr(feishu_directory.User, "filter", user_filter)

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "excluded-id", "o1", None, "Excluded ID", "one@example.com", None
            ),
            feishu_directory.FeishuDirectoryUser(
                "legacy-id", "o2", None, "Excluded legacy", "two@example.com", None
            ),
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 0, 2)


@pytest.mark.asyncio
async def test_directory_sync_skips_existing_binding_for_excluded_local_user(
    monkeypatch,
):
    excluded_user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(feishu_directory, "in_transaction", _transaction)
    monkeypatch.setattr(
        feishu_directory,
        "_self_service_directory_exclusions",
        AsyncMock(return_value=({excluded_user.id}, set())),
    )
    monkeypatch.setattr(
        feishu_directory.FeishuUser,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(user_id=excluded_user.id)),
    )
    monkeypatch.setattr(
        feishu_directory.User,
        "filter",
        lambda **_kwargs: Query(excluded_user),
    )

    result = await feishu_directory.sync_directory_users(
        [
            feishu_directory.FeishuDirectoryUser(
                "directory-id", "open-id", None, "Linked", None, None
            )
        ],
        actor=SimpleNamespace(id=uuid4()),
        request=SimpleNamespace(),
    )

    assert (result.created, result.updated, result.skipped) == (0, 0, 1)
