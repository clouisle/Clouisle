import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.tools import sandbox as sandbox_module
from app.llm.tools.sandbox import (
    CodeLanguage,
    CodeSandbox,
    ExecutionResult,
    execute_code,
)
from app.services.sandbox.models import (
    SandboxArtifactSpec,
    SandboxInputFileSpec,
    SandboxJob,
)


@pytest.mark.anyio
async def test_execute_validates_language_and_missing_runtimes(monkeypatch):
    runner = CodeSandbox()

    with pytest.raises(ValueError, match="unsupported"):
        await runner.execute("unsupported", "return 1")
    assert not (await runner.execute(object(), "return 1")).success

    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _command: None)
    assert not (await runner.execute(CodeLanguage.JAVASCRIPT, "return 1")).success
    assert not (await runner.execute(CodeLanguage.PYTHON, "return 1")).success


@pytest.mark.anyio
async def test_runtime_job_keeps_dependencies_files_artifacts_and_context(monkeypatch):
    job = SandboxJob(
        language="python",
        code="return params['value']",
        command=["python"],
        python_packages=["requests==2.32.3"],
        input_files=[
            SandboxInputFileSpec(
                target_path="/workspace/input.txt", content_base64="aGVsbG8="
            )
        ],
        artifacts=[SandboxArtifactSpec(path="/workspace/output.json")],
    )
    compile_job = MagicMock(return_value=job)
    submit = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            result={"value": 7},
            error=None,
            stdout="done",
            stderr="",
        )
    )
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.settings, "SANDBOX_LEGACY_FALLBACK_ENABLED", False
    )
    monkeypatch.setattr(sandbox_module, "compile_legacy_code_job", compile_job)
    monkeypatch.setattr(sandbox_module.sandbox_gateway, "submit_and_wait", submit)

    result = await execute_code(
        "python",
        "return params['value']",
        {"value": 7},
        timeout=12,
        session_id="session-1",
        agent_id="agent-1",
        team_id="team-1",
    )

    assert result == ExecutionResult(
        success=True, result={"value": 7}, stdout="done", stderr=""
    )
    assert job.python_packages == ["requests==2.32.3"]
    assert job.input_files[0].target_path == "/workspace/input.txt"
    assert job.artifacts[0].path == "/workspace/output.json"
    submit.assert_awaited_once_with(
        job,
        timeout_seconds=17,
        session_id="session-1",
        agent_id="agent-1",
        team_id="team-1",
    )


@pytest.mark.anyio
async def test_language_wrappers_route_to_subprocess(monkeypatch):
    run = AsyncMock(return_value=ExecutionResult(success=True))
    monkeypatch.setattr(
        sandbox_module.shutil, "which", lambda command: f"/bin/{command}"
    )
    monkeypatch.setattr(CodeSandbox, "_run_subprocess", run)
    runner = CodeSandbox()

    await runner.execute("javascript", "return params.value", {"value": 1})
    javascript_command = run.await_args.args[0]
    assert javascript_command[:2] == ["node", "-e"]
    assert 'const params = {"value": 1}' in javascript_command[2]

    await runner.execute("python", "return params['value']", {"value": 2})
    python_command = run.await_args.args[0]
    assert python_command[:2] == ["/bin/python3", "-c"]
    assert "    return params['value']" in python_command[2]


@pytest.mark.anyio
async def test_runtime_failure_and_gateway_timeout_without_fallback(monkeypatch):
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.settings, "SANDBOX_LEGACY_FALLBACK_ENABLED", False
    )
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                result=None,
                error="dependency install failed",
                stdout="installing",
                stderr="failed",
            )
        ),
    )

    failure = await execute_code("python", "return 1")
    assert failure == ExecutionResult(
        success=False,
        error="dependency install failed",
        stdout="installing",
        stderr="failed",
    )

    sandbox_module.sandbox_gateway.submit_and_wait.side_effect = asyncio.TimeoutError
    timeout = await execute_code("python", "return 1")
    assert timeout.success is False
    assert timeout.error == sandbox_module.t("tool_execution_failed")


@pytest.mark.anyio
async def test_runtime_error_falls_back_to_legacy_runner(monkeypatch):
    fallback = ExecutionResult(success=True, result="legacy")
    legacy_execute = AsyncMock(return_value=fallback)
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.settings, "SANDBOX_LEGACY_FALLBACK_ENABLED", True
    )
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(side_effect=RuntimeError("gateway unavailable")),
    )
    monkeypatch.setattr(CodeSandbox, "execute", legacy_execute)

    assert await execute_code("python", "return 1", timeout=9) is fallback
    legacy_execute.assert_awaited_once_with("python", "return 1", None)


@pytest.mark.anyio
async def test_runtime_disabled_uses_legacy_runner(monkeypatch):
    fallback = ExecutionResult(success=True, result="legacy")
    legacy_execute = AsyncMock(return_value=fallback)
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", False)
    monkeypatch.setattr(CodeSandbox, "execute", legacy_execute)

    assert await execute_code("python", "return 1") is fallback


@pytest.mark.anyio
async def test_failed_runtime_result_falls_back_to_legacy_runner(monkeypatch):
    fallback = ExecutionResult(success=True, result="legacy")
    legacy_execute = AsyncMock(return_value=fallback)
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.settings, "SANDBOX_LEGACY_FALLBACK_ENABLED", True
    )
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(return_value=SimpleNamespace(success=False)),
    )
    monkeypatch.setattr(CodeSandbox, "execute", legacy_execute)

    assert await execute_code("python", "return 1") is fallback


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "success", "result", "expected_stdout"),
    [
        ({"success": True, "result": 3, "logs": ["one", "two"]}, True, 3, "one\ntwo"),
        ({"success": False, "error": "boom", "logs": []}, False, None, ""),
    ],
)
async def test_subprocess_maps_structured_results(
    monkeypatch, payload, success, result, expected_stdout
):
    stdout = f"__RESULT__{sandbox_module.json.dumps(payload)}__END__".encode()
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(stdout, b"warning")), returncode=0
    )
    monkeypatch.setattr(
        sandbox_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    execution = await CodeSandbox()._run_subprocess(["python"], "python")

    assert execution.success is success
    assert execution.result == result
    assert execution.stdout == expected_stdout
    assert execution.stderr == "warning"


@pytest.mark.anyio
async def test_subprocess_start_error_returns_tool_failure(monkeypatch):
    monkeypatch.setattr(
        sandbox_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=OSError("cannot start")),
    )

    result = await CodeSandbox()._run_subprocess(["python"], "python")

    assert result.success is False
    assert result.error == sandbox_module.t("tool_execution_failed")


@pytest.mark.anyio
async def test_subprocess_timeout_kills_and_waits(monkeypatch):
    process = SimpleNamespace(
        communicate=MagicMock(return_value=object()),
        kill=MagicMock(),
        wait=AsyncMock(),
    )
    monkeypatch.setattr(
        sandbox_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        sandbox_module.asyncio,
        "wait_for",
        AsyncMock(side_effect=asyncio.TimeoutError),
    )

    result = await CodeSandbox(timeout=0.01)._run_subprocess(["python"], "python")

    assert result.success is False
    assert result.error == sandbox_module.t("request_timeout")
    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stdout", "stderr", "returncode", "expected_stdout"),
    [
        (b"__RESULT__not-json__END__", b"parse error", 0, "__RESULT__not-json__END__"),
        (b"plain output", b"process failed", 2, "plain output"),
        (b"plain output", b"", 0, "plain output"),
    ],
)
async def test_subprocess_maps_malformed_and_failed_output(
    monkeypatch, stdout, stderr, returncode, expected_stdout
):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(stdout, stderr)), returncode=returncode
    )
    monkeypatch.setattr(
        sandbox_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    result = await CodeSandbox()._run_subprocess(["python"], "python")

    assert result.success is False
    assert result.stdout == expected_stdout
