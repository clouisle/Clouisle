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
