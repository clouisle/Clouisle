import base64
import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.models.skill import Skill, SkillCategory, SkillExecutionMode
from pydantic import ValidationError

from app.schemas.response import BusinessError
from app.schemas.skill import SkillCreate
from app.services.sandbox.models import SandboxJobSource, SandboxTaskStatus
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
        "execution_mode": SkillExecutionMode.LEGACY,
        "skill_spec": {
            "name": "echo_skill",
            "version": "1.0.0",
            "runtime_profile": "standard",
            "python_packages": ["requests==2.32.3"],
            "js_packages": [],
            "command_template": [
                "python",
                "-m",
                "echo",
                "{{args.text}}",
                "{{config.mode}}",
            ],
            "shell": False,
            "env": {},
            "limits": {},
            "artifacts": [],
            "metadata": {},
        },
        "config_schema": {},
        "default_config": {"mode": "safe"},
        "is_enabled": True,
    }
    data.update(overrides)
    return Skill(**data)


def test_skill_schema_rejects_shell_execution():
    payload = make_skill().skill_spec
    payload["shell"] = True

    with pytest.raises(ValidationError):
        SkillCreate(
            name="echo_skill",
            display_name="Echo Skill",
            input_schema={"type": "object"},
            skill_spec=payload,
        )


def test_instructions_mode_returns_skill_payload():
    skill = make_skill(
        execution_mode=SkillExecutionMode.INSTRUCTIONS,
        instructions="Use this Skill to echo the provided text.",
        package_path="echo-skill",
        package_hash="abc123",
        package_manifest={"file_count": 2},
    )

    result = SkillExecutor.execute_instructions_mode(
        skill=skill,
        arguments={"text": "hello"},
        config={"mode": "safe"},
    )

    assert result.success is True
    assert result.result["type"] == "skill_instructions"
    assert result.result["instructions"] == "Use this Skill to echo the provided text."
    assert result.result["arguments"] == {"text": "hello"}
    assert result.result["manifest"] == {"file_count": 2, "package_hash": "abc123"}


def test_build_tool_name_is_stable_and_prefixed():
    skill_id = uuid4()
    skill = make_skill(id=skill_id, name="Echo-Tool")

    assert (
        SkillService.build_tool_name(skill)
        == f"skill_echo_tool_{str(skill_id).replace('-', '')[:8]}"
    )


def test_render_command_template_replaces_args_and_config():
    command = SkillExecutor.render_command_template(
        ["python", "{{args.payload}}", "--mode={{config.mode}}"],
        arguments={"payload": {"ok": True}},
        config={"mode": "safe"},
    )

    assert command == ["python", '{"ok": true}', "--mode=safe"]


def test_render_command_template_rejects_missing_placeholder_value():
    with pytest.raises(BusinessError) as exc:
        SkillExecutor.render_command_template(
            ["python", "{{args.missing}}"],
            arguments={},
            config={},
        )

    assert exc.value.msg_key == "skill_command_template_variable_missing"


def test_validate_arguments_rejects_missing_required_argument():
    with pytest.raises(BusinessError) as exc:
        SkillExecutor.validate_arguments(make_skill(), {})

    assert exc.value.msg_key == "skill_argument_validation_failed"


def test_validate_arguments_rejects_wrong_type():
    with pytest.raises(BusinessError) as exc:
        SkillExecutor.validate_arguments(make_skill(), {"text": "ok", "count": "one"})

    assert exc.value.msg_key == "skill_argument_validation_failed"


@pytest.mark.anyio
async def test_execute_script_skill_submits_inline_package_to_sandbox_gateway():
    package_content = base64.b64encode(b"print('ok')\n").decode("ascii")
    skill = make_skill(
        execution_mode=SkillExecutionMode.SCRIPT,
        execution_config={
            "mode": "script",
            "runtime": "python",
            "script": "scripts/run.py",
            "limits": {"timeout_seconds": 10},
            "artifacts": [{"path": "/workspace/output/result.json", "optional": True}],
        },
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
    runtime_result = SimpleNamespace(
        success=True,
        result={"echo": "hello"},
        error=None,
        stdout="out",
        stderr="",
        artifacts=[],
        metadata=SimpleNamespace(duration_ms=12),
        status=SandboxTaskStatus.COMPLETED,
    )

    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=runtime_result),
    ) as mock_submit:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            config=None,
            tenant_id="team-1",
        )

    assert result.success is True
    mock_submit.assert_awaited_once()
    job = mock_submit.await_args.args[0]
    assert job.source == SandboxJobSource.SKILL
    assert job.tenant_id == "team-1"
    assert job.shell is False
    assert job.cwd == "/workspace/skill"
    assert job.command == ["python", "/workspace/skill/scripts/run.py"]
    assert {input_file.target_path for input_file in job.input_files} == {
        "/workspace/input/skill-input.json",
        "/workspace/skill/scripts/run.py",
    }
    staged_payload = next(
        input_file
        for input_file in job.input_files
        if input_file.target_path == "/workspace/input/skill-input.json"
    )
    staged_json = json.loads(base64.b64decode(staged_payload.content_base64).decode("utf-8"))
    assert staged_json["arguments"] == {"text": "hello"}
    assert staged_json["config"] == {"mode": "safe"}
    assert staged_json["skill"]["id"] == str(skill.id)
    assert job.artifacts[0].path == "/workspace/output/result.json"
    assert job.artifacts[0].optional is True


@pytest.mark.anyio
async def test_execute_submits_skill_job_to_sandbox_gateway():
    skill = make_skill()
    runtime_result = SimpleNamespace(
        success=True,
        result={"echo": "hello"},
        error=None,
        stdout="out",
        stderr="",
        artifacts=[],
        metadata=SimpleNamespace(duration_ms=12),
        status=SandboxTaskStatus.COMPLETED,
    )

    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=runtime_result),
    ) as mock_submit:
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            config=None,
            tenant_id="team-1",
        )

    assert result.success is True
    assert result.result == {"echo": "hello"}
    mock_submit.assert_awaited_once()
    job = mock_submit.await_args.args[0]
    assert job.source == SandboxJobSource.SKILL
    assert job.tenant_id == "team-1"
    assert job.command == ["python", "-m", "echo", "hello", "safe"]
    assert job.python_packages == ["requests==2.32.3"]
    assert job.metadata["skill_name"] == "echo_skill"
