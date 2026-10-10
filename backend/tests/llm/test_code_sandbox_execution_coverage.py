import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.tools import sandbox as sandbox_module
from app.llm.tools.sandbox import ExecutionResult, execute_code


@pytest.mark.anyio
async def test_execute_code_returns_sandbox_runtime_result(monkeypatch):
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                result={"answer": 42},
                error=None,
                stdout="done",
                stderr="",
            )
        ),
    )

    result = await execute_code("python", "return 42")

    assert result == ExecutionResult(
        success=True,
        result={"answer": 42},
        stdout="done",
        stderr="",
    )


@pytest.mark.anyio
async def test_gateway_failure_never_executes_code_on_caller(
    monkeypatch, tmp_path: Path
):
    marker = tmp_path / "caller-executed"
    code = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unsafe')\n"
        "return 1"
    )
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(side_effect=RuntimeError("sandbox worker unavailable")),
    )

    result = await execute_code("python", code)

    assert result.success is False
    assert result.error == sandbox_module.t("tool_execution_failed")
    assert not marker.exists()


@pytest.mark.anyio
async def test_failed_runtime_result_never_falls_back_to_caller(
    monkeypatch, tmp_path: Path
):
    marker = tmp_path / "caller-executed"
    code = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unsafe')\n"
        "return 1"
    )
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        sandbox_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                result=None,
                error="execution failed",
                stdout="started",
                stderr="failed",
            )
        ),
    )

    result = await execute_code("python", code)

    assert result == ExecutionResult(
        success=False,
        error="execution failed",
        stdout="started",
        stderr="failed",
    )
    assert not marker.exists()


@pytest.mark.anyio
async def test_runtime_disabled_and_gateway_timeout_fail_closed(
    monkeypatch, tmp_path: Path
):
    marker = tmp_path / "caller-executed"
    code = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unsafe')\n"
        "return 1"
    )
    submit = AsyncMock(side_effect=asyncio.TimeoutError)
    monkeypatch.setattr(sandbox_module.sandbox_gateway, "submit_and_wait", submit)
    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", False)

    disabled = await execute_code("python", code)
    assert disabled.success is False
    submit.assert_not_awaited()

    monkeypatch.setattr(sandbox_module.settings, "SANDBOX_RUNTIME_ENABLED", True)
    timed_out = await execute_code("python", code)
    assert timed_out.success is False
    assert timed_out.error == sandbox_module.t("tool_execution_failed")
    assert not marker.exists()
