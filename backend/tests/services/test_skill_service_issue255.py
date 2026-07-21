"""Issue #255 branch coverage for the skill service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError, ResponseCode
from app.services.skill import SkillService


def first_result(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.anyio
async def test_check_team_access_covers_missing_superuser_and_admin_requirement():
    user = SimpleNamespace(is_superuser=False)

    with (
        patch("app.services.skill.Team.filter", return_value=first_result(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), user)
    assert error.value.code == ResponseCode.TEAM_NOT_FOUND

    team = SimpleNamespace()
    superuser = SimpleNamespace(is_superuser=True)
    with patch("app.services.skill.Team.filter", return_value=first_result(team)):
        assert await SkillService.check_team_access(uuid4(), superuser) is team

    membership = SimpleNamespace(role="member")
    with (
        patch("app.services.skill.Team.filter", return_value=first_result(team)),
        patch(
            "app.services.skill.TeamMember.filter",
            return_value=first_result(membership),
        ),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.check_team_access(uuid4(), user, require_admin=True)
    assert error.value.code == ResponseCode.TEAM_ADMIN_REQUIRED


@pytest.mark.anyio
async def test_get_skill_for_team_rejects_missing_skill():
    with (
        patch("app.services.skill.Skill.filter", return_value=first_result(None)),
        pytest.raises(BusinessError) as error,
    ):
        await SkillService.get_skill_for_team(uuid4(), uuid4())

    assert error.value.code == ResponseCode.NOT_FOUND
    assert error.value.msg_key == "skill_not_found"


@pytest.mark.parametrize(
    ("skill", "expected"),
    [
        (
            SimpleNamespace(frontmatter={"allowed-tools": ["Read", 3]}, skill_md=""),
            ["Read", "3"],
        ),
        (
            SimpleNamespace(
                frontmatter={},
                skill_md="allowed-tools:\n  - Bash\n  - Read*\n",
            ),
            ["Bash", "Read*"],
        ),
        (SimpleNamespace(frontmatter={}, skill_md="no tools"), None),
    ],
)
def test_parse_allowed_tools_covers_frontmatter_markdown_and_missing(skill, expected):
    assert SkillService.parse_allowed_tools(skill) == expected


@pytest.mark.parametrize(
    ("tool_name", "allowed_tools", "expected"),
    [
        ("Anything", [], True),
        ("Bash", ["Bash(npx impeccable *)"], True),
        ("ReadFile", ["Read*"], True),
        ("Write", ["Read*", "Bash"], False),
    ],
)
def test_is_tool_allowed_covers_empty_exact_wildcard_and_rejection(
    tool_name, allowed_tools, expected
):
    assert SkillService.is_tool_allowed(tool_name, allowed_tools) is expected
