import base64
import json
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.models.skill import Skill, SkillCategory
from app.schemas.response import BusinessError
from app.services.skill import SkillService
from app.services.skill_executor import SkillExecutor


def make_skill(**overrides) -> Skill:
    data = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "echo_skill",
        "display_name": "Echo Skill",
        "description": "Echo a value",
        "icon": None,
        "category": SkillCategory.CODE,
        "version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["text"],
        },
        "skill_md": "---\nname: echo_skill\ndescription: Echo a value\n---\nUse this Skill to echo text.",
        "instructions": "Use this Skill to echo text.",
        "frontmatter": {"name": "echo_skill", "description": "Echo a value"},
        "package_manifest": {"file_count": 1},
        "skill_spec": {
            "package_files": [],
        },
        "config_schema": {},
        "default_config": {"mode": "safe"},
        "is_enabled": True,
    }
    data.update(overrides)
    return Skill(**data)


def test_build_tool_name_is_stable_and_prefixed():
    skill_id = uuid4()
    skill = make_skill(id=skill_id, name="Echo-Tool")

    assert (
        SkillService.build_tool_name(skill)
        == f"skill_echo_tool_{str(skill_id).replace('-', '')[:8]}"
    )


def test_skill_to_tool_info_uses_skill_json_schema():
    skill = make_skill(name="Echo-Tool")
    tool_info = SkillService.to_tool_info(skill)

    tool_schema = tool_info.to_openai_schema()
    tool_definition = SkillService.to_tool_definition(skill)

    assert tool_schema["function"]["name"] == tool_definition.function.name
    assert tool_schema["function"]["parameters"] == skill.input_schema
    assert tool_info.parameters_schema == skill.input_schema


def test_validate_arguments_rejects_missing_required_argument():
    with pytest.raises(BusinessError) as exc:
        SkillExecutor.validate_arguments(make_skill(), {})

    assert exc.value.msg_key == "skill_argument_validation_failed"


def test_validate_arguments_rejects_wrong_type():
    with pytest.raises(BusinessError) as exc:
        SkillExecutor.validate_arguments(make_skill(), {"text": "ok", "count": "one"})

    assert exc.value.msg_key == "skill_argument_validation_failed"


@pytest.mark.anyio
async def test_execute_skill_returns_instructions_without_sandbox():
    skill = make_skill(package_hash="abc123")

    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(),
    ) as mock_submit:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            config={"tone": "plain"},
            tenant_id="team-1",
        )

    assert result.success is True
    assert result.result["type"] == "skill_instructions"
    assert result.result["instructions"] == "Use this Skill to echo text."
    assert result.result["arguments"] == {"text": "hello"}
    assert result.result["config"] == {"mode": "safe", "tone": "plain"}
    assert result.result["manifest"] == {"file_count": 1, "package_hash": "abc123"}
    assert result.result["workspace_root"] == "/workspace/skill/echo_skill"
    mock_submit.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_skill_stages_package_resources_when_session_exists():
    package_content = base64.b64encode(b"print('ok')\n").decode("ascii")
    skill = make_skill(
        skill_spec={
            "package_files": [
                {
                    "path": "scripts/run.py",
                    "content_base64": package_content,
                    "mode": 0o644,
                }
            ]
        },
    )
    workspace_root = uuid4().hex

    class FakeWorkspace:
        def __init__(self):
            from pathlib import Path
            import tempfile

            self.root = Path(tempfile.mkdtemp(prefix="skill-workspace-"))

    workspace = FakeWorkspace()

    class FakeWorkspaceManager:
        def resolve_workspace_path(self, workspace, path):
            return workspace.root / path.removeprefix("/workspace/")

    with patch(
        "app.services.skill_executor.sandbox_gateway.get_session_workspace",
        new=AsyncMock(return_value=workspace),
    ), patch(
        "app.services.skill_executor.sandbox_gateway._get_workspace_manager",
        return_value=FakeWorkspaceManager(),
    ):
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id=workspace_root,
            tenant_id="team-1",
        )

    assert result.success is True
    staged = workspace.root / "skill" / "echo_skill" / "scripts" / "run.py"
    assert staged.read_text() == "print('ok')\n"


@pytest.mark.anyio
async def test_execute_skill_ignores_script_execution_config():
    skill = make_skill(
        execution_config={
            "mode": "script",
            "runtime": "python",
            "script": "scripts/run.py",
        },
    )

    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(),
    ) as mock_submit:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            tenant_id="team-1",
        )

    assert result.success is True
    assert result.result["type"] == "skill_instructions"
    mock_submit.assert_not_awaited()


def test_instruction_display_result_hides_full_instructions():
    skill = make_skill()
    result = SkillExecutor.build_instruction_result(
        skill=skill,
        arguments={"text": "hello"},
        config={},
        workspace_root="/workspace/skill/echo_skill",
    )

    display = result.to_dict()
    display_json = json.dumps(display, ensure_ascii=False)
    assert display["result"]["type"] == "skill_instructions"
    assert "Use this Skill to echo text." not in display_json

    llm_payload = json.loads(result.to_llm_payload())
    assert llm_payload["result"]["instructions"] == "Use this Skill to echo text."
    assert "artifact_guidance" in llm_payload["result"]
    assert "artifact" in llm_payload["result"]["artifact_guidance"]
    assert "artifact_guidance" not in display_json
