from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import teams
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamCreate, TeamMemberRole


class Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def offset(self, value):
        self.calls.append(("offset", value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args))
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def make_team(**overrides):
    values = {
        "id": uuid4(),
        "name": "Platform",
        "is_default": False,
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("search", [None, "plat"])
async def test_list_all_teams_filters_and_paginates(monkeypatch, search):
    rows = [make_team()]
    query = Query(rows, count=1)
    monkeypatch.setattr(teams.Team, "all", lambda: query)

    response = await teams.list_all_teams(
        page=2, page_size=5, search=search, current_user=SimpleNamespace()
    )

    assert response["data"] == {
        "items": rows,
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    assert ("offset", 5) in query.calls
    assert any(call[0] == "filter" for call in query.calls) is bool(search)


@pytest.mark.asyncio
async def test_create_team_rejects_duplicate(monkeypatch):
    monkeypatch.setattr(teams.Team, "filter", lambda **_kwargs: Query(make_team()))

    with pytest.raises(BusinessError) as exc:
        await teams.create_team(
            request=MagicMock(),
            team_in=TeamCreate(name="Platform"),
            current_user=SimpleNamespace(),
        )

    assert exc.value.code == ResponseCode.TEAM_NAME_EXISTS


@pytest.mark.asyncio
async def test_create_team_persists_owner_and_audits(monkeypatch):
    owner = SimpleNamespace(id=uuid4())
    created = make_team()
    hydrated = make_team(id=created.id)
    create = AsyncMock(return_value=created)
    member_create = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(teams.Team, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(teams.Team, "create", create)
    monkeypatch.setattr(teams.Team, "get", lambda **_kwargs: Query(hydrated))
    monkeypatch.setattr(teams.TeamMember, "create", member_create)
    monkeypatch.setattr(teams.AuditLogService, "log", audit)

    response = await teams.create_team(
        request=MagicMock(),
        team_in=TeamCreate(name="Platform", description="Core team"),
        current_user=owner,
    )

    assert response["data"] is hydrated
    create.assert_awaited_once_with(
        name="Platform", description="Core team", avatar_url=None, owner=owner
    )
    member_create.assert_awaited_once_with(
        team=created, user=owner, role=TeamMemberRole.OWNER
    )
    audit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("team", "code"),
    [
        (None, ResponseCode.TEAM_NOT_FOUND),
        (make_team(is_default=True), ResponseCode.CANNOT_DELETE_DEFAULT_TEAM),
    ],
)
async def test_delete_team_rejects_missing_and_default(monkeypatch, team, code):
    monkeypatch.setattr(teams.Team, "filter", lambda **_kwargs: Query(team))

    with pytest.raises(BusinessError) as exc:
        await teams.delete_team(MagicMock(), uuid4(), current_user=SimpleNamespace())

    assert exc.value.code == code


@pytest.mark.asyncio
async def test_delete_team_audits_before_deletion(monkeypatch):
    team = make_team()
    audit = AsyncMock()
    monkeypatch.setattr(teams.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(teams.AuditLogService, "log", audit)

    response = await teams.delete_team(
        MagicMock(), team.id, current_user=SimpleNamespace()
    )

    assert response["data"] is team
    audit.assert_awaited_once()
    team.delete.assert_awaited_once_with()
