"""Residual branch coverage for the skill service (issue #255)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.skill import SkillCategory, SkillSourceType
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.skill import SkillCreate, SkillUpdate
from app.services.skill import SkillService


def query_with_first(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


def skill(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "summarize",
        "display_name": "Summarize",
        "description": "Summarize text",
        "icon": None,
        "category": SkillCategory.OTHER,
        "version": "1.0.0",
        "source_type": SkillSourceType.ZIP,
        "source_uri": None,
        "source_ref": None,
        "source_subdir": None,
        "package_path": None,
        "package_hash": None,
        "input_schema": {},
        "default_config": {},
        "is_enabled": True,
        "import_warnings": None,
        "created_by": None,
        "created_at": now,
        "updated_at": now,
        "frontmatter": {},
        "skill_md": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_team_access_covers_all_rejections_and_successes():
    user = SimpleNamespace(is_superuser=False)
    team = SimpleNamespace()

    with (
        patch("app.services.skill.Team.filter", return_value=query_with_first(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), user)
    assert error.value.code == ResponseCode.TEAM_NOT_FOUND

    with patch("app.services.skill.Team.filter", return_value=query_with_first(team)):
        assert (
            await SkillService.check_team_access(
                uuid4(), SimpleNamespace(is_superuser=True)
            )
            is team
        )

    for membership, require_admin, expected in [
        (None, False, ResponseCode.NOT_TEAM_MEMBER),
        (SimpleNamespace(role="member"), True, ResponseCode.TEAM_ADMIN_REQUIRED),
    ]:
        with (
            patch(
                "app.services.skill.Team.filter", return_value=query_with_first(team)
            ),
            patch(
                "app.services.skill.TeamMember.filter",
                return_value=query_with_first(membership),
            ),
            pytest.raises(BusinessError) as error,
        ):
            await SkillService.check_team_access(uuid4(), user, require_admin)
        assert error.value.code == expected

    with (
        patch("app.services.skill.Team.filter", return_value=query_with_first(team)),
        patch(
            "app.services.skill.TeamMember.filter",
            return_value=query_with_first(SimpleNamespace(role="admin")),
        ),
    ):
        assert await SkillService.check_team_access(uuid4(), user, True) is team


@pytest.mark.anyio
async def test_list_available_skills_builds_optional_filters_and_search():
    expected = [skill()]
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.filter.return_value = query
    query.all = AsyncMock(return_value=expected)

    with (
        patch.object(SkillService, "check_team_access", new=AsyncMock()),
        patch("app.services.skill.Skill.filter", return_value=query) as model_filter,
    ):
        result = await SkillService.list_available_skills(
            team_id=uuid4(),
            user=SimpleNamespace(),
            include_system=False,
            enabled=False,
            search="sum",
            category="other",
        )

    assert result == expected
    assert model_filter.call_args.kwargs == {
        "is_enabled": False,
        "category": "other",
    }
    query.filter.assert_called_once()


@pytest.mark.anyio
async def test_get_skill_for_team_covers_enabled_missing_denied_and_system():
    team_id = uuid4()
    other_team_skill = skill(team_id=uuid4())
    system_skill = skill(team_id=None)

    for result, expected_code in [
        (None, ResponseCode.NOT_FOUND),
        (other_team_skill, ResponseCode.PERMISSION_DENIED),
    ]:
        query = query_with_first(result)
        with (
            patch(
                "app.services.skill.Skill.filter", return_value=query
            ) as model_filter,
            pytest.raises(BusinessError) as error,
        ):
            await SkillService.get_skill_for_team(uuid4(), team_id, enabled_only=True)
        assert error.value.code == expected_code
        assert model_filter.call_args.kwargs["is_enabled"] is True

    with patch(
        "app.services.skill.Skill.filter", return_value=query_with_first(system_skill)
    ):
        assert await SkillService.get_skill_for_team(uuid4(), team_id) is system_skill


@pytest.mark.anyio
async def test_create_skill_covers_permissions_duplicate_and_creation():
    payload = SkillCreate(name="summarize", display_name="Summarize")
    with pytest.raises(BusinessError) as error:
        await SkillService.create_skill(payload, SimpleNamespace(is_superuser=False))
    assert error.value.code == ResponseCode.PERMISSION_DENIED

    with (
        patch(
            "app.services.skill.Skill.filter",
            return_value=query_with_first(SimpleNamespace()),
        ),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.create_skill(payload, SimpleNamespace(is_superuser=True))
    assert error.value.code == ResponseCode.DUPLICATE_NAME

    team = SimpleNamespace()
    created = SimpleNamespace()
    team_payload = SkillCreate(
        team_id=uuid4(), name="summarize", display_name="Summarize"
    )
    with (
        patch.object(
            SkillService, "check_team_access", new=AsyncMock(return_value=team)
        ) as access,
        patch("app.services.skill.Skill.filter", return_value=query_with_first(None)),
        patch(
            "app.services.skill.Skill.create", new=AsyncMock(return_value=created)
        ) as create,
    ):
        assert (
            await SkillService.create_skill(
                team_payload, SimpleNamespace(is_superuser=False)
            )
            is created
        )
    access.assert_awaited_once_with(
        team_payload.team_id, create.call_args.kwargs["created_by"], require_admin=True
    )
    assert create.call_args.kwargs["team"] is team


@pytest.mark.anyio
async def test_update_skill_covers_system_permission_and_team_update():
    system_skill = skill(team_id=None)
    with pytest.raises(BusinessError) as error:
        await SkillService.update_skill(
            system_skill,
            SkillUpdate(display_name="Updated"),
            SimpleNamespace(is_superuser=False),
        )
    assert error.value.code == ResponseCode.PERMISSION_DENIED

    team_skill = skill()
    team_skill.save = AsyncMock()
    with patch.object(SkillService, "check_team_access", new=AsyncMock()) as access:
        result = await SkillService.update_skill(
            team_skill, SkillUpdate(display_name="Updated"), SimpleNamespace()
        )
    assert result.display_name == "Updated"
    access.assert_awaited_once()
    team_skill.save.assert_awaited_once()


@pytest.mark.anyio
async def test_tool_handler_forwards_tenant_and_handles_missing_agent(monkeypatch):
    result = SimpleNamespace(to_chat_payload=MagicMock(return_value={"ok": True}))
    execute = AsyncMock(return_value=result)
    monkeypatch.setattr("app.services.skill_executor.SkillExecutor.execute", execute)
    item = skill(description="", input_schema={"type": "string"})
    tool = SkillService.to_tool_info(item, config={"mode": "safe"})

    assert tool.parameters_schema == {"type": "object", "properties": {}}
    assert await tool.handler(value="x") == {"ok": True}
    assert execute.await_args.kwargs["tenant_id"] is None

    agent = SimpleNamespace(team_id=uuid4())
    await tool.handler(agent=agent, session_id="session", value="x")
    assert execute.await_args.kwargs["tenant_id"] == str(agent.team_id)


@pytest.mark.anyio
async def test_agent_skill_helpers_skip_invalid_configs_merge_and_resolve():
    item = skill(default_config={"a": 1})
    agent = SimpleNamespace(
        team_id=uuid4(),
        tools_config=[
            {"type": "http"},
            {"type": "skill"},
            {"type": "skill", "skill_id": "id", "config": {"b": 2}},
        ],
    )
    with patch.object(
        SkillService, "get_skill_for_team", new=AsyncMock(return_value=item)
    ) as get_skill:
        assert await SkillService.get_agent_skills(agent, enabled_only=True) == [
            (item, {"a": 1, "b": 2})
        ]
    get_skill.assert_awaited_once_with("id", agent.team_id, enabled_only=True)

    tool_name = SkillService.build_tool_name(item)
    with patch.object(
        SkillService, "get_agent_skills", new=AsyncMock(return_value=[(item, {"a": 1})])
    ):
        assert await SkillService.resolve_agent_skill_tool(agent, tool_name) == (
            item,
            {"a": 1},
        )

    for name, code in [
        ("http_tool", ResponseCode.NOT_FOUND),
        ("skill_missing", ResponseCode.PERMISSION_DENIED),
    ]:
        with (
            patch.object(
                SkillService, "get_agent_skills", new=AsyncMock(return_value=[])
            ),
            pytest.raises(BusinessError) as error,
        ):
            await SkillService.resolve_agent_skill_tool(agent, name)
        assert error.value.code == code


@pytest.mark.anyio
async def test_agent_definitions_and_config_validation_cover_all_branches():
    item = skill()
    agent = SimpleNamespace(team_id=uuid4())
    definition = SimpleNamespace()
    with (
        patch.object(
            SkillService, "get_agent_skills", new=AsyncMock(return_value=[(item, {})])
        ),
        patch.object(SkillService, "to_tool_definition", return_value=definition),
    ):
        assert await SkillService.get_agent_skill_definitions(agent) == [definition]

    configs = [{"type": "http"}, {"type": "skill", "skill_id": "id"}]
    with patch.object(SkillService, "get_skill_for_team", new=AsyncMock()) as get_skill:
        await SkillService.validate_agent_skill_configs(None, configs, agent.team_id)
    get_skill.assert_awaited_once_with("id", agent.team_id, enabled_only=True)

    with pytest.raises(BusinessError) as error:
        await SkillService.validate_agent_skill_configs(
            None, [{"type": "skill"}], agent.team_id
        )
    assert error.value.code == ResponseCode.BAD_REQUEST


def test_output_and_allowed_tools_cover_optional_values_and_patterns():
    creator = SimpleNamespace(id=uuid4(), username="owner")
    output = SkillService.to_out(
        skill(team_id=None, created_by=creator, import_warnings=["warning"])
    )
    assert output.is_system is True
    assert output.created_by_id == creator.id
    assert output.import_warnings == ["warning"]

    assert SkillService.parse_allowed_tools(
        skill(frontmatter={"allowed-tools": ["Read", 3]})
    ) == ["Read", "3"]
    assert SkillService.parse_allowed_tools(
        skill(skill_md="allowed-tools:\n  - Bash\n  - Read*\n")
    ) == ["Bash", "Read*"]
    assert (
        SkillService.parse_allowed_tools(skill(skill_md="allowed-tools:\ntext")) is None
    )

    assert SkillService.is_tool_allowed("Anything", []) is True
    assert SkillService.is_tool_allowed("Bash", ["Bash(command *)"]) is True
    assert SkillService.is_tool_allowed("ReadFile", ["Read*"]) is True
    assert SkillService.is_tool_allowed("Write", ["Read*", "Bash"]) is False
