from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import skills
from app.models.skill import SkillCategory, SkillSourceType
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result=None, *, count=0, exists=False):
        self.result = result
        self.total = count
        self.exists_value = exists
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    async def exists(self):
        return self.exists_value

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def make_skill(**overrides):
    team_id = uuid4()
    values = {
        "id": uuid4(),
        "team_id": team_id,
        "team": SimpleNamespace(id=team_id, name="Platform"),
        "name": "reporting",
        "display_name": "Reporting",
        "description": "Build reports",
        "icon": None,
        "category": SkillCategory.DATA,
        "version": "1.0.0",
        "source_type": SkillSourceType.ZIP,
        "source_uri": None,
        "source_ref": None,
        "source_subdir": None,
        "package_path": "reporting",
        "package_storage_path": "private/skills/reporting",
        "package_hash": "hash",
        "input_schema": {},
        "default_config": {},
        "import_warnings": [],
        "created_by": SimpleNamespace(id=uuid4(), username="author"),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "is_enabled": True,
        "skill_md": "# Reporting",
        "instructions": "Build a report.",
        "frontmatter": None,
        "package_manifest": None,
        "execution_config": None,
        "config_schema": None,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_list_skills_applies_admin_filters_and_paginates(monkeypatch):
    skill = make_skill()
    query = Query([skill], count=1)
    monkeypatch.setattr(skills.Skill, "all", MagicMock(return_value=query))

    response = await skills.list_skills(
        page=2,
        page_size=5,
        search="report",
        team_id=[skill.team_id],
        include_system=True,
        enabled=True,
        status=["enabled"],
        source_type=["zip"],
        creator=["author"],
        current_user=SimpleNamespace(),
    )

    assert response["data"].items[0].team_name == "Platform"
    assert response["data"].total == 1
    assert ("offset", (5,), {}) in query.calls
    assert ("limit", (5,), {}) in query.calls
    assert any(call[2] == {"is_enabled": True} for call in query.calls)
    assert any(call[2] == {"source_type__in": ["zip"]} for call in query.calls)
    assert any(
        call[2] == {"created_by__username__in": ["author"]} for call in query.calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_system", "status", "expected_filter"),
    [
        (False, ["disabled"], {"is_enabled": False}),
        (True, ["enabled", "disabled"], None),
    ],
)
async def test_list_skills_handles_scope_and_status_boundaries(
    monkeypatch, include_system, status, expected_filter
):
    query = Query([], count=0)
    monkeypatch.setattr(skills.Skill, "all", MagicMock(return_value=query))

    await skills.list_skills(
        page=1,
        page_size=20,
        search=None,
        team_id=None,
        include_system=include_system,
        enabled=None,
        status=status,
        source_type=None,
        creator=None,
        current_user=SimpleNamespace(),
    )

    filters = [call[2] for call in query.calls if call[0] == "filter"]
    if not include_system:
        assert {"team_id__not_isnull": True} in filters
    if expected_filter:
        assert expected_filter in filters
    else:
        assert {"is_enabled": True} not in filters
        assert {"is_enabled": False} not in filters


@pytest.mark.asyncio
async def test_get_skill_filter_options_deduplicates_and_sorts(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Platform")
    rows = [
        make_skill(team=team, created_by=SimpleNamespace(username="zoe")),
        make_skill(
            team=None,
            team_id=None,
            created_by=SimpleNamespace(username="amy"),
            source_type=SkillSourceType.GIT,
        ),
        make_skill(team=team, created_by=None),
    ]
    monkeypatch.setattr(skills.Skill, "all", MagicMock(return_value=Query(rows)))
    monkeypatch.setattr(skills.Team, "all", MagicMock(return_value=Query([team])))

    response = await skills.get_skill_filter_options(current_user=SimpleNamespace())

    data = response["data"]
    assert [item.value for item in data.creators] == ["amy", "zoe"]
    assert [item.value for item in data.sources] == ["git", "zip"]
    assert [(item.value, item.label) for item in data.teams] == [
        (str(team.id), "Platform")
    ]


@pytest.mark.asyncio
async def test_get_skill_rejects_missing_record(monkeypatch):
    monkeypatch.setattr(skills.Skill, "filter", MagicMock(return_value=Query()))

    with pytest.raises(BusinessError) as exc:
        await skills.get_skill(uuid4(), current_user=SimpleNamespace())

    assert exc.value.status_code == 404
    assert exc.value.msg_key == "skill_not_found"


@pytest.mark.asyncio
async def test_delete_skill_rejects_agent_reference(monkeypatch):
    skill = make_skill()
    monkeypatch.setattr(skills, "_get_skill", AsyncMock(return_value=skill))
    monkeypatch.setattr(
        skills.Agent, "filter", MagicMock(return_value=Query(exists=True))
    )

    with pytest.raises(BusinessError) as exc:
        await skills.delete_skill(
            request=MagicMock(), skill_id=skill.id, current_user=SimpleNamespace()
        )

    assert exc.value.msg_key == "skill_referenced_by_agent"
    skill.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_skill_removes_storage_and_audits(monkeypatch):
    skill = make_skill(team_id=None)
    audit = AsyncMock()
    remove_storage = AsyncMock()
    monkeypatch.setattr(skills, "_get_skill", AsyncMock(return_value=skill))
    monkeypatch.setattr(
        skills.Agent, "filter", MagicMock(return_value=Query(exists=False))
    )
    monkeypatch.setattr(
        skills.SkillImportService, "delete_private_storage", remove_storage
    )
    monkeypatch.setattr(skills.AuditLogService, "log", audit)

    response = await skills.delete_skill(
        request=MagicMock(), skill_id=skill.id, current_user=SimpleNamespace()
    )

    assert response["data"] is None
    skill.delete.assert_awaited_once()
    remove_storage.assert_awaited_once_with(skill.package_storage_path)
    assert audit.await_args.kwargs["metadata"] == {"team_id": None}
