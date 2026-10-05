import base64
import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from app.models.skill import Skill, SkillCategory
from app.schemas.response import BusinessError
from app.services.skill import SkillService
from app.services.sandbox.models import (
    SandboxArtifact,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.skill_executor import SkillExecutionResult, SkillExecutor


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
async def test_execute_skill_stages_and_replaces_resources_on_worker(
    tmp_path, monkeypatch
):
    from app.services.sandbox.manager import SandboxManager
    from app.services.sandbox.workspace import SandboxWorkspaceManager
    from app.services.sandbox.models import SandboxBinding
    from app.services.sandbox.worker_registry import WorkerPresence

    skill = make_skill()
    session_id = uuid4().hex
    team_id = str(uuid4())
    binding = SandboxBinding(
        worker_id="worker-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
        workspace_id=session_id,
    )
    worker = WorkerPresence(
        worker_id=binding.worker_id,
        instance_id=binding.instance_id,
        node_id=binding.node_id,
        storage_id=binding.storage_id,
    )
    session_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                agent_id=None,
                team_id=team_id,
                user_id=None,
                conversation_id=None,
                disk_usage_bytes=0,
            )
        ),
        touch=AsyncMock(),
        get_active_round=AsyncMock(return_value=None),
        get_workspace_round=AsyncMock(return_value=None),
        mark_workspace_round=AsyncMock(),
    )
    session_store.get_binding = AsyncMock(return_value=binding)
    monkeypatch.setattr(
        "app.services.sandbox.manager.sandbox_session_store", session_store
    )
    monkeypatch.setattr(
        "app.services.sandbox.manager.sandbox_worker_registry",
        SimpleNamespace(get=AsyncMock(return_value=worker)),
    )
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "worker"))
    manager = SandboxManager(
        workspace_manager=workspace_manager,
        cleanup_workspaces=False,
        result_store=SimpleNamespace(
            get_result=AsyncMock(return_value=None),
            save_result=AsyncMock(side_effect=lambda result: result),
        ),
    )

    async def run_on_worker(job, *, session_id, team_id):
        return await manager.execute(
            job.model_copy(update={"binding": binding}),
            session_id=session_id,
            session_team_id=team_id,
        )

    monkeypatch.setattr(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        run_on_worker,
    )
    for content, mode in [(b"original", 0o644), (b"replacement", 0o755)]:
        skill.skill_spec = {
            "package_files": [
                {
                    "path": "scripts/run.py",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "mode": mode,
                }
            ]
        }
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id=session_id,
            tenant_id=team_id,
        )
        assert result.success is True, result.error
        assert result.result["workspace_root"] == "/workspace/skill/echo_skill"
        worker_root = workspace_manager.get_session_root(session_id)
        staged = worker_root / "skill/echo_skill/scripts/run.py"
        assert staged.read_bytes() == content
        assert staged.stat().st_mode & 0o777 == mode
        assert list((worker_root / ".skill-staging").iterdir()) == []

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "run.py"
    outside_file.write_bytes(b"untouched")
    staged.unlink()
    staged.parent.rmdir()
    for destination in (outside, tmp_path / "missing-outside"):
        staged.parent.symlink_to(destination, target_is_directory=True)
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id=session_id,
            tenant_id=team_id,
        )
        assert result.success is False
        assert outside_file.read_bytes() == b"untouched"
        assert not (tmp_path / "missing-outside").exists()
        assert list((worker_root / ".skill-staging").iterdir()) == []
        staged.parent.unlink()

    staged.parent.mkdir()
    for destination in (outside_file, staged.parent / "missing-target"):
        staged.symlink_to(destination)
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id=session_id,
            tenant_id=team_id,
        )
        assert result.success is False
        assert outside_file.read_bytes() == b"untouched"
        assert not (staged.parent / "missing-target").exists()
        assert list((worker_root / ".skill-staging").iterdir()) == []
        staged.unlink()


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


def test_build_package_input_files_ignores_invalid_and_unsafe_entries():
    encoded = base64.b64encode(b"ok").decode("ascii")
    skill = make_skill(
        skill_spec={
            "package_files": [
                "not-a-dict",
                {"path": 1, "content_base64": encoded},
                {"path": "/absolute", "content_base64": encoded},
                {"path": "../escape", "content_base64": encoded},
                {"path": "valid.txt", "content_base64": encoded, "mode": "644"},
            ]
        }
    )

    files = SkillExecutor.build_package_input_files(
        skill=skill, workspace_root="/workspace/skill/test"
    )

    assert len(files) == 1
    assert files[0].target_path == "/workspace/skill/test/valid.txt"
    assert files[0].mode is None
    assert (
        SkillExecutor.build_package_input_files(
            skill=make_skill(skill_spec={}), workspace_root="/workspace/skill/test"
        )
        == []
    )


def test_skill_workspace_root_falls_back_to_id():
    skill = make_skill(name="...---")

    assert SkillExecutor.skill_workspace_root(skill) == f"/workspace/skill/{skill.id}"


@pytest.mark.anyio
async def test_execute_skill_propagates_failed_package_staging():
    skill = make_skill(
        skill_spec={
            "package_files": [
                {
                    "path": "resource.txt",
                    "content_base64": base64.b64encode(b"resource").decode("ascii"),
                }
            ]
        },
    )
    failure = SandboxResult(
        job_id="staging-job",
        success=False,
        status=SandboxTaskStatus.FAILED,
        error="Sandbox worker unavailable",
        stderr="staging failed",
    )
    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=failure),
    ):
        result = await SkillExecutor.execute(
            skill=skill,
            arguments={"text": "hello"},
            session_id="session-1",
            tenant_id="team-1",
        )

    assert result.success is False
    assert result.status == SandboxTaskStatus.FAILED
    assert result.error == failure.error
    assert result.stderr == failure.stderr
    assert result.result is None


@pytest.mark.anyio
async def test_execute_skill_without_resources_does_not_submit_staging_job():
    with patch(
        "app.services.skill_executor.sandbox_gateway.submit_and_wait",
        new=AsyncMock(),
    ) as submit:
        result = await SkillExecutor.execute(
            skill=make_skill(),
            arguments={"text": "hello"},
            session_id="session-1",
        )

    assert result.success is True
    submit.assert_not_awaited()


def test_from_sandbox_result_copies_fields():
    source = SimpleNamespace(
        success=True,
        result={"ok": True},
        error=None,
        stdout="out",
        stderr="err",
        artifacts=[],
        metadata=SimpleNamespace(duration_ms=9),
        status=SandboxTaskStatus.COMPLETED,
    )

    result = SkillExecutor.from_sandbox_result(source)

    assert result.to_dict() == {
        "success": True,
        "result": {"ok": True},
        "error": None,
        "stdout": "out",
        "stderr": "err",
        "artifacts": [],
        "duration_ms": 9,
        "status": "completed",
    }
