from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints.tools import execute_code_directly
from app.schemas.tool import CodeExecuteRequest
from app.services.sandbox.models import (
    SandboxArtifactSpec,
    SandboxExecutionMetadata,
    SandboxJobSource,
)


class DummyUser:
    pass


class TestExecuteCodeDirectly:
    @pytest.mark.anyio
    async def test_execute_code_directly_routes_runtime_fields(self):
        request = CodeExecuteRequest(
            language="python",
            code="return {'ok': True}",
            params={"x": 1},
            timeout=30,
            python_packages=["requests==2.32.3"],
            command=["python"],
        )

        with (
            patch(
                "app.api.v1.endpoints.tools.compile_code_config_job",
                return_value=SimpleNamespace(
                    limits=SimpleNamespace(timeout_seconds=30.0),
                ),
            ) as mock_compile,
            patch(
                "app.api.v1.endpoints.tools.sandbox_gateway.submit_and_wait",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        success=True,
                        result={"ok": True},
                        error=None,
                        stdout="hello",
                        artifacts=[],
                        metadata=SandboxExecutionMetadata(
                            duration_ms=321, total_ms=321
                        ),
                    )
                ),
            ) as mock_submit,
        ):
            response = await execute_code_directly(request, DummyUser())

        assert response["data"].success is True
        assert response["data"].result == {"ok": True}
        assert response["data"].logs == "hello"
        assert response["data"].artifacts == []
        assert response["data"].duration_ms == 321
        mock_compile.assert_called_once()
        mock_submit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_execute_code_directly_returns_artifacts(self):
        request = CodeExecuteRequest(
            language="python",
            code="return {'ok': True}",
            params={"x": 1},
            timeout=45,
            python_packages=["requests==2.32.3"],
            python_package_index_url=" https://mirror.example.com/simple/ ",
            node_package_registry_url=" https://registry.example.com/npm/ ",
            command=["python", "-X", "utf8"],
            artifacts=[
                {
                    "path": "/workspace/output/result.json",
                    "optional": False,
                    "description": "result file",
                }
            ],
            limits={
                "timeout_seconds": 45,
                "disk_mb": 2048,
                "max_stdout_kb": 512,
                "max_stderr_kb": 128,
            },
        )

        compiled_job = SimpleNamespace(limits=SimpleNamespace(timeout_seconds=45.0))
        runtime_result = SimpleNamespace(
            success=True,
            result={"ok": True},
            error=None,
            stdout="done",
            artifacts=[
                SandboxArtifactSpec(
                    path="/workspace/output/result.json",
                    optional=False,
                    description="result file",
                )
            ],
            metadata=SandboxExecutionMetadata(duration_ms=654, total_ms=654),
        )

        with (
            patch(
                "app.api.v1.endpoints.tools.compile_code_config_job",
                return_value=compiled_job,
            ) as mock_compile,
            patch(
                "app.api.v1.endpoints.tools.sandbox_gateway.submit_and_wait",
                new=AsyncMock(return_value=runtime_result),
            ) as mock_submit,
        ):
            response = await execute_code_directly(request, DummyUser())

        mock_compile.assert_called_once_with(
            code_config={
                "language": "python",
                "code": "return {'ok': True}",
                "command": ["python", "-X", "utf8"],
                "python_packages": ["requests==2.32.3"],
                "js_packages": [],
                "python_package_index_url": "https://mirror.example.com/simple",
                "node_package_registry_url": "https://registry.example.com/npm",
                "artifacts": [
                    {
                        "path": "/workspace/output/result.json",
                        "optional": False,
                        "description": "result file",
                    }
                ],
                "limits": {
                    "timeout_seconds": 45.0,
                    "disk_mb": 2048,
                    "max_stdout_kb": 512,
                    "max_stderr_kb": 128,
                },
            },
            params={"x": 1},
            timeout=45,
            source=SandboxJobSource.DEBUG,
        )
        mock_submit.assert_awaited_once_with(compiled_job, timeout_seconds=50.0)
        assert response["data"].success is True
        assert response["data"].logs == "done"
        assert response["data"].duration_ms == 654
        assert len(response["data"].artifacts) == 1
        assert response["data"].artifacts[0].path == "/workspace/output/result.json"
        assert response["data"].artifacts[0].description == "result file"
