from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.tools import test_tool as execute_test_tool
from app.models.tool import CustomToolType, ToolType
from app.models.tool_approval import ExecutionEntrypoint
from app.schemas.tool import (
    CodeConfigSchema,
    ToolCreateInput,
    ToolExecuteRequest,
    ToolUpdateInput,
)
from app.services.sandbox.compiler import normalize_code_config
from app.services.sandbox.models import SandboxArtifact


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
async def test_test_tool_routes_saved_tools_through_unified_executor():
    request = ToolExecuteRequest(name="python_runner", arguments={"x": 1})
    custom_tool = DummyTool()
    artifact = SandboxArtifact(
        path="/workspace/output/result.json",
        optional=False,
        description="result file",
        file_type="file",
        size=12,
        checksum="abc123",
        content_type="application/json",
        storage_path="sandbox/job/result.json",
        url="/api/v1/files/sandbox/job/result.json",
        filename="result.json",
    )
    execute = AsyncMock(
        return_value={
            "success": True,
            "result": {"ok": True},
            "error": None,
            "stdout": "done",
            "stderr": "",
            "artifacts": [artifact.model_dump(mode="json")],
        }
    )

    with (
        patch(
            "app.api.v1.endpoints.tools.tool_registry.get_tool",
            return_value=None,
        ),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=DummyFilterResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await execute_test_tool(
            request,
            team_id=custom_tool.team_id,
            current_user=DummyUser(),
        )

    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom_tool
    assert args_arg == {"x": 1}
    assert execute.await_args.kwargs["operation"] == "python_runner"
    context = execute.await_args.kwargs["context"]
    assert context.entrypoint is ExecutionEntrypoint.TOOL_TEST
    assert context.team_id == custom_tool.team_id
    assert context.interactive is True
    assert response["data"].success is True
    assert response["data"].result == {"ok": True}
    assert response["data"].logs == "done"
    assert response["data"].duration_ms is not None
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


def test_code_config_schema_maps_javascript_dependencies():
    code_config = CodeConfigSchema(
        language="javascript",
        code="return 1",
        dependencies=["lodash"],
    )

    assert code_config.python_packages == []
    assert code_config.js_packages == ["lodash"]


def test_tool_names_accept_identifiers_and_reject_invalid_values():
    assert ToolCreateInput(name="weather_api", display_name="Weather").name == (
        "weather_api"
    )
    assert ToolUpdateInput(name=None).name is None

    with pytest.raises(ValueError, match="tool_name_invalid_format"):
        ToolCreateInput(name="2-weather", display_name="Weather")

    with pytest.raises(ValueError, match="tool_name_invalid_format"):
        ToolUpdateInput(name="weather-api")
