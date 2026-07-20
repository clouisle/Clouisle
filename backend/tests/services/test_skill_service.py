"""Behavior tests for the skill service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError, ResponseCode
from app.schemas.skill import SkillCreate, SkillUpdate
from app.services.skill import SkillService


def first_result(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.anyio
async def test_check_team_access_rejects_non_member():
    team = SimpleNamespace()
    user = SimpleNamespace(is_superuser=False)

    with (
        patch("app.services.skill.Team.filter", return_value=first_result(team)),
        patch("app.services.skill.TeamMember.filter", return_value=first_result(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), user)

    assert error.value.code == ResponseCode.NOT_TEAM_MEMBER
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_get_skill_for_team_allows_system_skill_and_filters_enabled():
    skill = SimpleNamespace(team_id=None)
    skill_id = uuid4()

    with patch(
        "app.services.skill.Skill.filter", return_value=first_result(skill)
    ) as mock_filter:
        result = await SkillService.get_skill_for_team(
            skill_id, uuid4(), enabled_only=True
        )

    assert result is skill
    mock_filter.assert_called_once_with(id=skill_id, is_enabled=True)


@pytest.mark.anyio
async def test_get_skill_for_team_rejects_other_team_skill():
    skill = SimpleNamespace(team_id=uuid4())

    with (
        patch("app.services.skill.Skill.filter", return_value=first_result(skill)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.get_skill_for_team(uuid4(), uuid4())

    assert error.value.code == ResponseCode.PERMISSION_DENIED
    assert error.value.msg_key == "skill_access_denied"


@pytest.mark.anyio
async def test_create_skill_rejects_duplicate_team_name():
    payload = SkillCreate(team_id=uuid4(), name="reporting", display_name="Reporting")
    user = SimpleNamespace()
    team = SimpleNamespace()

    with (
        patch.object(
            SkillService, "check_team_access", new=AsyncMock(return_value=team)
        ) as mock_access,
        patch("app.services.skill.Skill.filter", return_value=first_result(object())),
        patch("app.services.skill.Skill.create", new=AsyncMock()) as mock_create,
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.create_skill(payload, user)

    assert error.value.code == ResponseCode.DUPLICATE_NAME
    mock_access.assert_awaited_once_with(payload.team_id, user, require_admin=True)
    mock_create.assert_not_awaited()


@pytest.mark.anyio
async def test_update_skill_requires_superuser_for_system_skill():
    skill = SimpleNamespace(team_id=None, save=AsyncMock())
    user = SimpleNamespace(is_superuser=False)

    with pytest.raises(BusinessError) as error:
        await SkillService.update_skill(
            skill, SkillUpdate(display_name="New name"), user
        )

    assert error.value.msg_key == "skill_system_admin_required"
    skill.save.assert_not_awaited()


@pytest.mark.anyio
async def test_get_agent_skills_merges_default_and_agent_config():
    first_skill = SimpleNamespace(default_config={"timeout": 10, "mode": "safe"})
    agent = SimpleNamespace(
        team_id=uuid4(),
        tools_config=[
            {"type": "builtin", "name": "search"},
            {"type": "skill"},
            {
                "type": "skill",
                "skill_id": "skill-1",
                "config": {"timeout": 30},
            },
        ],
    )

    with patch.object(
        SkillService, "get_skill_for_team", new=AsyncMock(return_value=first_skill)
    ) as mock_get:
        result = await SkillService.get_agent_skills(agent, enabled_only=True)

    assert result == [(first_skill, {"timeout": 30, "mode": "safe"})]
    mock_get.assert_awaited_once_with("skill-1", agent.team_id, enabled_only=True)


@pytest.mark.anyio
async def test_resolve_agent_skill_tool_rejects_unknown_skill_tool():
    agent = SimpleNamespace()

    with (
        patch.object(SkillService, "get_agent_skills", new=AsyncMock(return_value=[])),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.resolve_agent_skill_tool(agent, "skill_missing_12345678")

    assert error.value.code == ResponseCode.PERMISSION_DENIED
    assert error.value.msg_key == "skill_not_configured_for_agent"


@pytest.mark.anyio
async def test_validate_agent_skill_configs_requires_skill_id():
    with pytest.raises(BusinessError) as error:
        await SkillService.validate_agent_skill_configs(
            None, [{"type": "skill", "config": {}}], uuid4()
        )

    assert error.value.code == ResponseCode.BAD_REQUEST
    assert error.value.msg_key == "skill_id_required"
