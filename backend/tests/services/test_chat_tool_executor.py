"""Authorized dispatch contract for chat tool calls.

Every managed operation needs a real actor and team; these tests assert the
dispatcher forwards that trusted context and the real operation contract, with
the persistence boundary stubbed so no database is required.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import execute_tool_call
from app.llm.tools.registry import ToolInfo, tool_registry
from app.utils.tool_output import ToolExecutionResult
from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope


def _patch_policy_boundary(monkeypatch, user):
    """Run the real invoke resolver but skip the persistence boundary."""
    from app.services import builtin_tools, tool_execution

    async def execute(definition, operation, arguments, context, invoke, **kwargs):
        return await invoke(arguments, None)

    monkeypatch.setattr(tool_execution, "execute_stored_tool", execute)
    monkeypatch.setattr(
        builtin_tools,
        "get_builtin_definition",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="definition")),
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )


def _identity(conversation_id, ticket="call-1") -> RuntimeToolIdentity:
    return RuntimeToolIdentity(
        run_id=uuid4(),
        tool_call_id=ticket,
        entrypoint="chat",
        entrypoint_id=str(conversation_id),
        interactive=True,
    )


class TestChatToolExecutor:
    @pytest.mark.anyio
    async def test_inspect_asset_dispatches_with_authorized_context(self, monkeypatch):
        asset = SimpleNamespace(
            id=uuid4(),
            display_filename="file.txt",
            content_type="text/plain",
            size=4,
            source=SimpleNamespace(value="upload"),
        )
        svc = MagicMock()
        svc.capabilities = MagicMock(return_value=["inspect", "read", "sandbox"])
        agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), attachment_config={})
        user = SimpleNamespace(id=uuid4())
        conversation_id = uuid4()
        monkeypatch.setattr(
            "app.services.asset_access.resolve_authorized_asset_ref",
            AsyncMock(return_value=asset),
        )
        monkeypatch.setattr("app.services.asset.asset_service", svc)
        _patch_policy_boundary(monkeypatch, user)

        with tool_identity_scope(_identity(conversation_id)):
            result = await execute_tool_call(
                "inspect_asset",
                {"ref": "abcd"},
                agent=agent,
                user=user,
                conversation_id=str(conversation_id),
            )

        assert json.loads(result) == {
            "ref": "abcd",
            "filename": "file.txt",
            "content_type": "text/plain",
            "size": 4,
            "source": "upload",
            "capabilities": ["inspect", "read", "sandbox"],
        }

    @pytest.mark.anyio
    async def test_skill_executes_after_authorization_with_tool_contract(
        self, monkeypatch
    ):
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
        team_id = uuid4()
        agent = SimpleNamespace(id=uuid4(), team_id=team_id, tools_config=[])
        user = SimpleNamespace(id=uuid4())
        conversation_id = uuid4()
        tool_info = ToolInfo(
            name="skill_demo_skill_12345678",
            description="Run demo skill",
            parameters_schema={"type": "object", "properties": {}},
            handler=handler,
        )
        monkeypatch.setattr(
            "app.services.skill.SkillService.resolve_agent_skill_tool",
            AsyncMock(return_value=(skill, {"mode": "safe"})),
        )
        to_tool_info = MagicMock(return_value=tool_info)
        monkeypatch.setattr(
            "app.services.skill.SkillService.to_tool_info", to_tool_info
        )
        _patch_policy_boundary(monkeypatch, user)

        with tool_identity_scope(_identity(conversation_id, "call-skill")):
            result = await execute_tool_call(
                "skill_demo_skill_12345678",
                {"text": "hello"},
                agent=agent,
                user=user,
                conversation_id=str(conversation_id),
                session_id="session-1",
            )

        assert isinstance(result, ToolExecutionResult)
        assert result.display_result == {"success": True, "result": {"text": "hello"}}
        assert json.loads(result.llm_result) == {
            "success": True,
            "result": {"text": "hello"},
        }
        to_tool_info.assert_called_once_with(skill, config={"mode": "safe"})

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
    async def test_builtin_forwards_authorized_actor_and_current_images(
        self, monkeypatch
    ):
        async def handler(current_images=None):
            return {"current_images": current_images}

        previous_tool = tool_registry.get_tool("current_image_probe")
        tool_registry.register(
            name="current_image_probe",
            description="Probe current images",
        )(handler)
        team_id = uuid4()
        agent = SimpleNamespace(id=uuid4(), team_id=team_id, tools_config=[])
        user = SimpleNamespace(id=uuid4())
        execute = AsyncMock(return_value={"current_images": [{"url": "kept"}]})
        monkeypatch.setattr(
            "app.services.tool.ToolExecutor.execute_builtin_tool", execute
        )
        monkeypatch.setattr(
            "app.models.user.User.get_or_none", AsyncMock(return_value=user)
        )
        try:
            with tool_identity_scope(_identity(uuid4(), "call-images")):
                result = await execute_tool_call(
                    "current_image_probe",
                    {},
                    agent=agent,
                    user=user,
                    current_images=[{"url": "data:image/png;base64,cmVm"}],
                )
        finally:
            tool_registry.unregister("current_image_probe")
            if previous_tool is not None:
                tool_registry.register_tool(previous_tool)

        assert result == {"current_images": [{"url": "kept"}]}
        kwargs = execute.await_args.kwargs
        assert kwargs["team_id"] == team_id
        assert kwargs["agent"] is agent
        assert kwargs["user"] is user
        assert kwargs["current_images"] == [{"url": "data:image/png;base64,cmVm"}]
