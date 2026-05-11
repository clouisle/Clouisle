from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.tools import test_tool as execute_test_tool
from app.models.tool import CustomToolType, ToolType
from app.schemas.tool import CodeConfigSchema, ToolExecuteRequest
from app.services.sandbox.compiler import normalize_code_config
from app.services.sandbox.models import (
    SandboxArtifactSpec,
    SandboxExecutionMetadata,
    SandboxJobSource,
)


class DummyUser:
    is_superuser = False
    locale = "zh"


class DummyTool:
    def __init__(self):
        self.name = "python_runner"
        self.type = ToolType.CUSTOM
        self.custom_type = CustomToolType.CODE
        self.team_id = uuid4()
        self.code_config = {
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
        }


class DummyFilterResult:
    def __init__(self, tool):
        self.tool = tool

    async def first(self):
        return self.tool


@pytest.mark.anyio
async def test_test_tool_routes_saved_code_tools_through_sandbox_gateway():
    request = ToolExecuteRequest(name="python_runner", arguments={"x": 1})
    custom_tool = DummyTool()
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
        metadata=SandboxExecutionMetadata(duration_ms=777, total_ms=777),
    )

    with (
        patch(
            "app.api.v1.endpoints.tools.tool_registry.get_tool",
            return_value=None,
        ),
        patch(
            "app.api.v1.endpoints.tools.check_team_access",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=DummyFilterResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.compile_code_config_job",
            return_value=compiled_job,
        ) as mock_compile,
        patch(
            "app.api.v1.endpoints.tools.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=runtime_result),
        ) as mock_submit,
    ):
        response = await execute_test_tool(
            request,
            team_id=custom_tool.team_id,
            current_user=DummyUser(),
        )

    mock_compile.assert_called_once_with(
        code_config=custom_tool.code_config,
        params={"x": 1},
        timeout=45.0,
        source=SandboxJobSource.TOOL,
    )
    mock_submit.assert_awaited_once_with(compiled_job, timeout_seconds=50.0)
    assert response["data"].success is True
    assert response["data"].result == {"ok": True}
    assert response["data"].logs == "done"
    assert response["data"].duration_ms == 777
    assert len(response["data"].artifacts) == 1
    assert response["data"].artifacts[0].path == "/workspace/output/result.json"
    assert response["data"].artifacts[0].description == "result file"


def test_normalize_code_config_maps_legacy_dependencies():
    normalized = normalize_code_config(
        {
            "language": "python",
            "code": "return 1",
            "dependencies": ["requests==2.32.3"],
            "python_package_index_url": " https://mirror.example.com/simple/ ",
            "node_package_registry_url": " https://registry.example.com/npm/ ",
            "runtime_profile": "standard",
            "shell": False,
        }
    )

    assert normalized["python_packages"] == ["requests==2.32.3"]
    assert normalized["js_packages"] == []
    assert normalized["python_package_index_url"] == "https://mirror.example.com/simple"
    assert normalized["node_package_registry_url"] == "https://registry.example.com/npm"
    assert "dependencies" not in normalized
    assert "runtime_profile" not in normalized
    assert "shell" not in normalized


def test_code_config_schema_maps_legacy_dependencies_for_readback():
    code_config = CodeConfigSchema(
        language="python",
        code="return 1",
        dependencies=["requests==2.32.3"],
        python_package_index_url=" https://mirror.example.com/simple/ ",
        node_package_registry_url=" https://registry.example.com/npm/ ",
    )

    assert code_config.python_packages == ["requests==2.32.3"]
    assert code_config.js_packages == []
    assert code_config.python_package_index_url == "https://mirror.example.com/simple"
    assert code_config.node_package_registry_url == "https://registry.example.com/npm"
