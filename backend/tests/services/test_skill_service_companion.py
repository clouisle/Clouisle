from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError, ResponseCode
from app.services.skill import SkillService


def query(value):
    result = MagicMock()
    result.first = AsyncMock(return_value=value)
    return result


@pytest.mark.anyio
async def test_team_access_covers_missing_membership_role_and_superuser():
    team = SimpleNamespace()
    regular = SimpleNamespace(is_superuser=False)

    with (
        patch("app.services.skill.Team.filter", return_value=query(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), regular)
    assert error.value.code == ResponseCode.TEAM_NOT_FOUND

    with (
        patch("app.services.skill.Team.filter", return_value=query(team)),
        patch("app.services.skill.TeamMember.filter", return_value=query(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), regular)
    assert error.value.code == ResponseCode.NOT_TEAM_MEMBER

    with (
        patch("app.services.skill.Team.filter", return_value=query(team)),
        patch(
            "app.services.skill.TeamMember.filter",
            return_value=query(SimpleNamespace(role="member")),
        ),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), regular, require_admin=True)
    assert error.value.code == ResponseCode.TEAM_ADMIN_REQUIRED

    with patch("app.services.skill.Team.filter", return_value=query(team)):
        assert (
            await SkillService.check_team_access(
                uuid4(), SimpleNamespace(is_superuser=True)
            )
            is team
        )


@pytest.mark.anyio
async def test_create_skill_covers_system_permission_duplicate_and_create():
    payload = SimpleNamespace(
        team_id=None,
        name="echo",
        display_name="Echo",
        description=None,
        icon=None,
        category="other",
        version="1",
        input_schema={},
        skill_spec={},
        config_schema={},
        default_config={},
        is_enabled=True,
    )
    regular = SimpleNamespace(is_superuser=False)

    with pytest.raises(BusinessError) as error:
        await SkillService.create_skill(payload, regular)
    assert error.value.code == ResponseCode.PERMISSION_DENIED

    admin = SimpleNamespace(is_superuser=True)
    with (
        patch("app.services.skill.Skill.filter", return_value=query(SimpleNamespace())),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.create_skill(payload, admin)
    assert error.value.code == ResponseCode.DUPLICATE_NAME

    created = SimpleNamespace()
    with (
        patch("app.services.skill.Skill.filter", return_value=query(None)),
        patch(
            "app.services.skill.Skill.create", new=AsyncMock(return_value=created)
        ) as create,
    ):
        assert await SkillService.create_skill(payload, admin) is created
    assert create.await_args.kwargs["created_by"] is admin


@pytest.mark.anyio
async def test_agent_skill_resolution_and_validation_cover_rejections():
    agent = SimpleNamespace(team_id=uuid4(), tools_config=[])

    with pytest.raises(BusinessError) as error:
        await SkillService.resolve_agent_skill_tool(agent, "other")
    assert error.value.code == ResponseCode.NOT_FOUND

    with pytest.raises(BusinessError) as error:
        await SkillService.resolve_agent_skill_tool(agent, "skill_missing")
    assert error.value.code == ResponseCode.PERMISSION_DENIED

    with pytest.raises(BusinessError) as error:
        await SkillService.validate_agent_skill_configs(
            agent, [{"type": "skill"}], agent.team_id
        )
    assert error.value.code == ResponseCode.BAD_REQUEST

    get_skill = AsyncMock()
    with patch.object(SkillService, "get_skill_for_team", new=get_skill):
        await SkillService.validate_agent_skill_configs(
            None,
            [{"type": "builtin"}, {"type": "skill", "skill_id": "id"}],
            agent.team_id,
        )
    get_skill.assert_awaited_once_with("id", agent.team_id, enabled_only=True)


def test_allowed_tools_cover_frontmatter_markdown_patterns_and_denial():
    assert SkillService.parse_allowed_tools(
        SimpleNamespace(frontmatter={"allowed-tools": ["Read", 3]}, skill_md="")
    ) == ["Read", "3"]
    assert SkillService.parse_allowed_tools(
        SimpleNamespace(
            frontmatter={}, skill_md="allowed-tools:\n  - Bash(npx *)\n  - Read*\n"
        )
    ) == ["Bash(npx *)", "Read*"]
    assert (
        SkillService.parse_allowed_tools(
            SimpleNamespace(frontmatter={}, skill_md="none")
        )
        is None
    )
    assert SkillService.is_tool_allowed("Anything", [])
    assert SkillService.is_tool_allowed("ReadFile", ["Read*"])
    assert SkillService.is_tool_allowed("Bash", ["Bash(npx *)"])
    assert not SkillService.is_tool_allowed("Write", ["Read"])
