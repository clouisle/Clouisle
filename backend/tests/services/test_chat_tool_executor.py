import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.chat_helpers.tool_executor import execute_code_tool
from app.api.v1.endpoints.chat_tools import execute_tool_call
from app.llm.tools.builtin.media import ToolExecutionResult
from app.llm.tools.registry import ToolInfo, tool_registry


class TestChatToolExecutor:
    @pytest.mark.anyio
    async def test_execute_code_tool_routes_through_sandbox_gateway(self):
        tool = MagicMock()
        tool.code_config = {
            "language": "python",
            "code": "return {'value': 42}",
            "python_packages": ["requests==2.32.3"],
            "python_package_index_url": " https://mirror.example.com/simple/ ",
        }

        with (
            patch(
                "app.api.v1.endpoints.chat_helpers.tool_executor.compile_code_config_job",
                return_value=SimpleNamespace(
                    limits=SimpleNamespace(timeout_seconds=60.0),
                ),
            ) as mock_compile,
            patch(
                "app.api.v1.endpoints.chat_helpers.tool_executor.sandbox_gateway.submit_and_wait",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        success=True,
                        result={"value": 42},
                        error=None,
                        stdout="hello",
                        stderr="",
                    )
                ),
            ) as mock_submit,
        ):
            payload = await execute_code_tool(tool, {"x": 1}, timeout=60.0)

        data = json.loads(payload)
        assert data["success"] is True
        assert data["result"] == {"value": 42}
        assert data["stdout"] == "hello"
        mock_compile.assert_called_once()
        mock_submit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_execute_skill_tool_uses_normal_tool_contract(self):
        async def handler(**kwargs):
            return ToolExecutionResult(
                display_result={"success": True, "result": kwargs},
                llm_result=json.dumps({"success": True, "result": kwargs}),
            )

        skill = SimpleNamespace(
            team_id="team-1",
            name="demo_skill",
            display_name="Demo Skill",
            description="Run demo skill",
            input_schema={"type": "object", "properties": {}},
        )
        agent = SimpleNamespace(team_id="team-1")
        tool_info = ToolInfo(
            name="skill_demo_skill_12345678",
            description="Run demo skill",
            parameters_schema={"type": "object", "properties": {}},
            handler=handler,
        )

        with (
            patch(
                "app.services.skill.SkillService.resolve_agent_skill_tool",
                new=AsyncMock(return_value=(skill, {"mode": "safe"})),
            ),
            patch(
                "app.services.skill.SkillService.to_tool_info",
                return_value=tool_info,
            ) as mock_to_tool_info,
        ):
            result = await execute_tool_call(
                "skill_demo_skill_12345678",
                {"text": "hello"},
                agent=agent,
                session_id="session-1",
            )

        assert isinstance(result, ToolExecutionResult)
        assert result.display_result == {"success": True, "result": {"text": "hello"}}
        assert json.loads(result.llm_result) == {
            "success": True,
            "result": {"text": "hello"},
        }
        mock_to_tool_info.assert_called_once_with(skill, config={"mode": "safe"})

    @pytest.mark.anyio
    async def test_execute_sandbox_tool_alias(self):
        class FakeBashTool:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def execute(self, **kwargs):
                return {"success": True, "kwargs": self.kwargs, "arguments": kwargs}

        previous_bash = tool_registry.get_sandbox_tool_class("bash")
        previous_alias = tool_registry.get_sandbox_tool_class("Bash")
        tool_registry.register_sandbox_tool("bash", FakeBashTool, aliases=["Bash"])
        try:
            result = await tool_registry.execute(
                "Bash",
                {"command": "pwd"},
                session_id="session-1",
                agent=SimpleNamespace(id="agent-1", team_id="team-1"),
            )
        finally:
            if previous_bash is not None:
                tool_registry.register_sandbox_tool("bash", previous_bash)
            if previous_alias is not None:
                tool_registry.register_sandbox_tool("Bash", previous_alias)

        assert result == {
            "success": True,
            "kwargs": {
                "session_id": "session-1",
                "allowed_commands": None,
                "agent_id": "agent-1",
                "team_id": "team-1",
            },
            "arguments": {"command": "pwd"},
        }

    @pytest.mark.anyio
    async def test_execute_bash_routes_to_sandbox_tool(self):
        class FakeBashTool:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def execute(self, **kwargs):
                return {"success": True, "kwargs": self.kwargs, "arguments": kwargs}

        previous = tool_registry.get_sandbox_tool_class("bash")
        tool_registry.register_sandbox_tool("bash", FakeBashTool, aliases=["Bash"])
        try:
            agent = SimpleNamespace(id="agent-1", team_id="team-1")
            result = await execute_tool_call(
                "bash",
                {"command": "ls ."},
                agent=agent,
                session_id="session-1",
            )
        finally:
            if previous is not None:
                tool_registry.register_sandbox_tool("bash", previous, aliases=["Bash"])

        assert result == {
            "success": True,
            "kwargs": {
                "session_id": "session-1",
                "allowed_commands": None,
                "agent_id": "agent-1",
                "team_id": "team-1",
            },
            "arguments": {"command": "ls ."},
        }

    @pytest.mark.anyio
    async def test_execute_custom_code_tool_passes_session_to_sandbox_runtime(self):
        tool = SimpleNamespace(
            config={"language": "python", "code": "return {'value': 42}"},
            code_config={"language": "python", "code": "return {'value': 42}"},
        )
        agent = SimpleNamespace(id="agent-1", team_id="team-1")

        with patch(
            "app.llm.tools.sandbox.execute_code",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    success=True,
                    result={"value": 42},
                    stdout="",
                    stderr="",
                    error=None,
                )
            ),
        ) as mock_execute_code:
            from app.api.v1.endpoints.chat_tools import _execute_code_tool

            result = await _execute_code_tool(
                tool=tool,
                arguments={"x": 1},
                tool_timeouts={"code": 60},
                session_id="session-1",
                agent=agent,
            )

        assert result["success"] is True
        mock_execute_code.assert_awaited_once_with(
            language="python",
            code="return {'value': 42}",
            params={"x": 1},
            timeout=60,
            session_id="session-1",
            agent_id="agent-1",
            team_id="team-1",
        )
