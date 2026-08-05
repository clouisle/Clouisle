import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxInputFileSpec,
    SandboxJob,
    SandboxJobSource,
)
from app.services.sandbox.process_launcher import ProcessLaunchResult
from app.services.sandbox.workspace import SandboxWorkspaceManager


def manager(tmp_path: Path, **overrides) -> SandboxManager:
    defaults = {
        "workspace_manager": SandboxWorkspaceManager(root=str(tmp_path)),
        "cleanup_workspaces": False,
        "result_store": SimpleNamespace(update_status=AsyncMock()),
    }
    defaults.update(overrides)
    return SandboxManager(**defaults)


def job(**overrides) -> SandboxJob:
    defaults = {"source": SandboxJobSource.DEBUG, "command": ["missing-command"]}
    defaults.update(overrides)
    return SandboxJob(**defaults)


def process(**overrides) -> ProcessLaunchResult:
    defaults = {"exit_code": 0, "stdout": "", "stderr": ""}
    defaults.update(overrides)
    return ProcessLaunchResult(**defaults)


@pytest.mark.anyio
async def test_run_job_covers_timeout_failure_and_missing_payload(tmp_path: Path):
    launcher = MagicMock()
    launcher.launch = AsyncMock(
        side_effect=[
            process(exit_code=1, timed_out=True),
            process(exit_code=2, stderr="bad command"),
        ]
    )
    service = manager(tmp_path, process_launcher=launcher)
    workspace = service.workspace_manager.prepare("job")

    timed_out = await service._run_job(
        job(command=["sleep"]), workspace, SandboxExecutionMetadata()
    )
    failed = await service._run_job(
        job(command=["false"]), workspace, SandboxExecutionMetadata()
    )
    missing_job = job(command=[])
    missing_job.command = None
    missing = await service._run_job(missing_job, workspace, SandboxExecutionMetadata())

    assert timed_out.success is False and timed_out.error
    assert failed.error == "bad command"
    assert missing.success is False and missing.error


@pytest.mark.anyio
async def test_stage_input_files_rejects_existing_target_and_applies_mode(
    tmp_path: Path,
):
    service = manager(tmp_path)
    workspace = service.workspace_manager.prepare("files")
    encoded = base64.b64encode(b"content").decode()
    first = job(
        input_files=[
            SandboxInputFileSpec(
                target_path="/workspace/input.txt",
                content_base64=encoded,
                mode=0o600,
            )
        ]
    )

    await service._stage_input_files(first, workspace)
    assert (workspace.root / "input.txt").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        await service._stage_input_files(first, workspace)


def test_snippet_commands_and_node_module_link_edges(tmp_path: Path):
    service = manager(tmp_path)
    workspace = service.workspace_manager.prepare("commands")
    script = workspace.root / "snippet.py"

    assert service._build_python_snippet_command(
        job(command=["custom-python", "-u"]), script, {}
    )[-2:] == ["-u", str(script)]
    assert service._build_javascript_snippet_command(
        job(command=["custom-node", "--flag"]), script, {}
    )[-2:] == ["--flag", str(script)]

    service._link_node_modules_into_workspace(workspace, {})
    service._link_node_modules_into_workspace(workspace, {"NODE_PATH": "/missing"})
    source = tmp_path / "modules"
    source.mkdir()
    (workspace.root / "node_modules").mkdir()
    service._link_node_modules_into_workspace(workspace, {"NODE_PATH": str(source)})
    assert not (workspace.root / "node_modules").is_symlink()


def test_runtime_command_and_snippet_parse_fallbacks(tmp_path: Path):
    service = manager(tmp_path)
    script = tmp_path / "snippet.py"

    with (
        patch("app.services.sandbox.manager.settings") as settings,
        patch("app.services.sandbox.manager.Path.exists", return_value=False),
        patch("app.services.sandbox.manager.shutil.which", return_value=None),
    ):
        settings.SANDBOX_DEFAULT_PYTHON_BINARIES = ["/missing/python"]
        assert service._python_executable({"PATH": "/missing"}) == "python3"

    assert service._resolve_command([], {}) == []
    assert service._resolve_command(["/bin/sh", "-c", "true"], {})[0] == "/bin/sh"
    assert service._resolve_command(["not-installed"], {"PATH": "/missing"}) == [
        "not-installed"
    ]

    timed_out = service._parse_snippet_result(
        process(exit_code=1, stdout="partial", timed_out=True), script
    )
    successful = service._parse_snippet_result(process(stdout=" value \n"), script)
    failed = service._parse_snippet_result(process(exit_code=3, stderr="boom"), script)
    payload = json.dumps({"success": False, "error": "unsafe", "logs": ["one"]})
    parsed = service._parse_snippet_result(
        process(stdout=f"__RESULT__{payload}__END__"), script
    )

    assert timed_out.error
    assert successful.result == "value" and successful.error is None
    assert failed.error
    assert parsed.stdout == "one" and parsed.error


@pytest.mark.anyio
async def test_result_store_and_disk_limit_boundaries(tmp_path: Path):
    no_get_store = SimpleNamespace(update_status=AsyncMock())
    service = manager(tmp_path, result_store=no_get_store)
    metadata = await service._load_or_create_metadata("new")
    assert isinstance(metadata, SandboxExecutionMetadata)

    previous = SimpleNamespace(metadata=SandboxExecutionMetadata())
    get_store = MagicMock(
        get_result=AsyncMock(return_value=previous), save_result=AsyncMock()
    )
    service = manager(tmp_path, result_store=get_store)
    assert await service._load_or_create_metadata("existing") is previous.metadata

    workspace = service.workspace_manager.prepare("limits")
    service.workspace_manager.workspace_size_bytes = MagicMock(return_value=1)
    no_measure = job().model_copy(
        update={"limits": job().limits.model_copy(update={"disk_mb": 1})}
    )
    service._enforce_disk_limit(no_measure, workspace, stage="prepare")
    service.workspace_manager.workspace_size_bytes.assert_called_once()
