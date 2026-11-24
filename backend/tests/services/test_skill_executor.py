import json
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.models.skill import Skill, SkillCategory
from app.schemas.response import BusinessError
from app.services.skill import SkillService
from app.services.sandbox.models import SandboxArtifact, SandboxTaskStatus
from app.services.skill_executor import SkillExecutionResult, SkillExecutor


def make_skill(**overrides) -> Skill:
    data = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "echo-skill",
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
        "skill_md": "---\nname: echo-skill\ndescription: Echo a value\n---\nUse this Skill to echo text.",
        "instructions": "Use this Skill to echo text.",
        "frontmatter": {
            "name": "echo-skill",
            "description": "Echo a value",
            "allowed-tools": "Read Write",
        },
        "package_manifest": {
            "files": [
                {"path": "SKILL.md", "size": 72},
                {"path": "scripts/run.py", "size": 128},
            ],
            "file_count": 2,
        },
        "skill_spec": {
            "package_files": [
                {
                    "path": "scripts/run.py",
                    "content_base64": "cHJpbnQoMSk=",
                    "mode": 0o755,
                }
            ],
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
async def test_execute_skill_returns_instructions_without_staging():
    skill = make_skill(package_hash="abc123")

    with patch(
        "app.services.skill_executor.SkillWorkspaceSync.ensure_skills",
        new=AsyncMock(),
    ) as mock_sync:
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
    assert result.result["skill_root"] == (
        f"/workspace/skills/echo-skill-{str(skill.id).replace('-', '')}"
    )
    assert result.result["file_count"] == 2
    assert result.result["files_staged"] is False
    assert result.result["files"] == [
        {"path": "SKILL.md", "size": 72},
        {"path": "scripts/run.py", "size": 128},
    ]
    assert result.result["allowed_tools"] == ["Read", "Write"]
    mock_sync.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_skill_syncs_package_into_session_workspace():
    skill = make_skill(package_hash="abc123")

    with patch(
        "app.services.skill_executor.SkillWorkspaceSync.ensure_skills",
        new=AsyncMock(return_value=[str(skill.id)]),
    ) as mock_sync:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id="session-1",
            tenant_id="team-1",
            agent_id="agent-1",
        )

    assert result.success is True
    assert result.result["files_staged"] is True
    mock_sync.assert_awaited_once_with(
        session_id="session-1",
        skills=[skill],
        team_id="team-1",
        agent_id="agent-1",
    )


@pytest.mark.anyio
async def test_legacy_skill_without_package_files_is_not_reported_as_staged():
    """Rows imported before package files existed have no workspace directory."""
    skill = make_skill(skill_spec={"package_files": []})

    with patch(
        "app.services.skill_executor.SkillWorkspaceSync.ensure_skills",
        new=AsyncMock(return_value=[]),
    ):
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id="session-1",
        )

    assert result.result["files_staged"] is False


@pytest.mark.anyio
async def test_execute_skill_propagates_sync_failure():
    skill = make_skill()

    with patch(
        "app.services.skill_executor.SkillWorkspaceSync.ensure_skills",
        new=AsyncMock(
            side_effect=BusinessError(code=5000, msg_key="skill_package_sync_failed")
        ),
    ):
        with pytest.raises(BusinessError) as exc:
            await SkillExecutor.execute(
                skill=skill,
                arguments={"text": "hello"},
                session_id="session-1",
            )

    assert exc.value.msg_key == "skill_package_sync_failed"


def test_instruction_display_result_hides_full_instructions():
    skill = make_skill()
    skill_root = f"/workspace/skills/echo-skill-{str(skill.id).replace('-', '')}"
    result = SkillExecutor.build_instruction_result(
        skill=skill,
        arguments={"text": "hello"},
        config={},
        skill_root=skill_root,
    )

    display = result.to_dict()
    display_json = json.dumps(display, ensure_ascii=False)
    assert display["result"]["type"] == "skill_instructions"
    assert display["result"]["skill_root"] == skill_root
    assert display["result"]["file_count"] == 2
    assert "Use this Skill to echo text." not in display_json

    llm_payload = json.loads(result.to_llm_payload())
    assert llm_payload["result"]["instructions"] == "Use this Skill to echo text."
    assert llm_payload["result"]["files"][1]["path"] == "scripts/run.py"
    assert "artifact_guidance" in llm_payload["result"]
    assert "artifact" in llm_payload["result"]["artifact_guidance"]
    assert "artifact_guidance" not in display_json


def test_execution_result_serializes_artifacts_and_output_summaries():
    artifact = SandboxArtifact(
        path="/workspace/output/report.txt",
        filename="report.txt",
        file_type="file",
        size=6,
        content_type="text/plain",
        storage_path="skills/report.txt",
        url="https://example.test/report.txt",
    )
    result = SkillExecutionResult(
        success=False,
        result={"reason": "failed"},
        error="boom",
        stdout="x" * 2100,
        stderr="y" * 2100,
        artifacts=[artifact],
        duration_ms=12,
        status=SandboxTaskStatus.FAILED,
    )

    display = result.to_dict()
    llm_payload = json.loads(result.to_llm_payload())
    chat_payload = result.to_chat_payload()

    assert display["artifacts"][0]["filename"] == "report.txt"
    assert llm_payload["artifact_count"] == 1
    assert llm_payload["stdout_summary"] == "x" * 2000
    assert llm_payload["stderr_summary"] == "y" * 2000
    assert chat_payload.display_result == display
    assert json.loads(chat_payload.llm_result) == llm_payload


@pytest.mark.parametrize(
    ("value", "expected", "matches"),
    [
        ("text", "string", True),
        (1, "integer", True),
        (True, "integer", False),
        (1.5, "number", True),
        (True, "boolean", True),
        ([], "array", True),
        ({}, "object", True),
        (None, ["string", "null"], True),
        ("text", "boolean", False),
    ],
)
def test_matches_json_types(value, expected, matches):
    assert SkillExecutor._matches_json_type(value, expected) is matches


def test_listed_files_ignores_malformed_manifest_entries():
    skill = make_skill(
        package_manifest={
            "files": [
                "not-a-dict",
                {"path": 1},
                {"path": "references/guide.md"},
            ],
            "file_count": 3,
        }
    )

    assert SkillExecutor.listed_files(skill) == [
        {"path": "references/guide.md", "size": None}
    ]
    assert SkillExecutor.listed_files(make_skill(package_manifest={})) == []


def test_allowed_tools_absent_returns_none():
    skill = make_skill(frontmatter={"name": "echo-skill", "description": "Echo"})

    assert SkillExecutor.allowed_tools(skill) is None
