from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.services.skill import SkillService


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("team", "membership", "require_admin", "message"),
    [
        (None, None, False, "team_not_found"),
        (SimpleNamespace(), None, False, "not_team_member"),
        (
            SimpleNamespace(),
            SimpleNamespace(role="member"),
            True,
            "team_admin_required",
        ),
    ],
)
async def test_check_team_access_rejects_invalid_access(
    team, membership, require_admin, message
):
    user = SimpleNamespace(is_superuser=False)
    team_query = MagicMock(first=AsyncMock(return_value=team))
    member_query = MagicMock(first=AsyncMock(return_value=membership))

    with (
        patch("app.services.skill.Team.filter", return_value=team_query),
        patch("app.services.skill.TeamMember.filter", return_value=member_query),
        pytest.raises(BusinessError) as exc,
    ):
        await SkillService.check_team_access(uuid4(), user, require_admin=require_admin)

    assert exc.value.msg_key == message


@pytest.mark.anyio
async def test_check_team_access_allows_superuser_without_membership_lookup():
    team = SimpleNamespace()
    user = SimpleNamespace(is_superuser=True)
    team_query = MagicMock(first=AsyncMock(return_value=team))

    with (
        patch("app.services.skill.Team.filter", return_value=team_query),
        patch("app.services.skill.TeamMember.filter") as member_filter,
    ):
        assert await SkillService.check_team_access(uuid4(), user) is team

    member_filter.assert_not_called()


@pytest.mark.anyio
async def test_get_agent_skills_skips_invalid_entries_and_merges_config():
    skill = SimpleNamespace(default_config={"shared": "default", "base": True})
    agent = SimpleNamespace(
        team_id=uuid4(),
        tools_config=[
            {"type": "builtin"},
            {"type": "skill"},
            {
                "type": "skill",
                "skill_id": "skill-1",
                "config": {"shared": "agent"},
            },
        ],
    )

    with patch.object(
        SkillService, "get_skill_for_team", new=AsyncMock(return_value=skill)
    ) as get_skill:
        result = await SkillService.get_agent_skills(agent, enabled_only=True)

    assert result == [(skill, {"shared": "agent", "base": True})]
    get_skill.assert_awaited_once_with("skill-1", agent.team_id, enabled_only=True)


@pytest.mark.anyio
async def test_resolve_agent_skill_tool_handles_invalid_missing_and_match():
    agent = SimpleNamespace()
    skill = SimpleNamespace()

    with pytest.raises(BusinessError) as invalid:
        await SkillService.resolve_agent_skill_tool(agent, "builtin_echo")
    assert invalid.value.msg_key == "skill_not_found"

    with (
        patch.object(
            SkillService,
            "get_agent_skills",
            new=AsyncMock(return_value=[(skill, {"mode": "safe"})]),
        ),
        patch.object(SkillService, "build_tool_name", return_value="skill_echo"),
    ):
        assert await SkillService.resolve_agent_skill_tool(agent, "skill_echo") == (
            skill,
            {"mode": "safe"},
        )
        with pytest.raises(BusinessError) as missing:
            await SkillService.resolve_agent_skill_tool(agent, "skill_other")

    assert missing.value.msg_key == "skill_not_configured_for_agent"


@pytest.mark.anyio
async def test_validate_agent_skill_configs_requires_id_and_checks_skills():
    with pytest.raises(BusinessError) as exc:
        await SkillService.validate_agent_skill_configs(
            None, [{"type": "builtin"}, {"type": "skill"}], "team-1"
        )
    assert exc.value.msg_key == "skill_id_required"

    with patch.object(SkillService, "get_skill_for_team", new=AsyncMock()) as get_skill:
        await SkillService.validate_agent_skill_configs(
            None, [{"type": "skill", "skill_id": "skill-1"}], "team-1"
        )
    get_skill.assert_awaited_once_with("skill-1", "team-1", enabled_only=True)


def test_allowed_tools_support_frontmatter_markdown_and_patterns():
    assert SkillService.parse_allowed_tools(
        SimpleNamespace(frontmatter={"allowed-tools": ["Read", 3]}, skill_md="")
    ) == ["Read", "3"]
    assert SkillService.parse_allowed_tools(
        SimpleNamespace(
            frontmatter={}, skill_md="allowed-tools:\n  - Bash\n  - Read*\n"
        )
    ) == ["Bash", "Read*"]
    assert (
        SkillService.parse_allowed_tools(
            SimpleNamespace(frontmatter={}, skill_md="No tools configured")
        )
        is None
    )
    assert SkillService.is_tool_allowed("Anything", [])
    assert SkillService.is_tool_allowed("Bash", ["Bash(npx test *)"])
    assert SkillService.is_tool_allowed("ReadFile", ["Read*"])
    assert not SkillService.is_tool_allowed("Write", ["Read*"])
