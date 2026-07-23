"""Behavioral coverage for the in-memory LLM tool registry."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.llm.tools.registry import ToolInfo, ToolParameter, ToolRegistry


async def _sum(value: int, credentials=None, request_id=None):
    return {
        "value": value,
        "credentials": credentials,
        "request_id": request_id,
    }


async def _replacement(value: int):
    return value * 2


class TestToolRegistryBehaviorCoverage:
    def test_parameter_metadata_is_rendered_and_array_defaults_to_empty_items(self):
        tool = ToolInfo(
            name="describe",
            description="Describes a record",
            parameters=[
                ToolParameter(
                    name="tags",
                    type="array",
                    description="Tag list",
                    required=True,
                    enum=["a", "b"],
                    default=["a"],
                ),
                ToolParameter(name="opaque", type="array"),
            ],
        )

        schema = tool.to_openai_schema()

        assert schema == {
            "type": "function",
            "function": {
                "name": "describe",
                "description": "Describes a record",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "description": "Tag list",
                            "enum": ["a", "b"],
                            "items": {},
                            "default": ["a"],
                        },
                        "opaque": {"type": "array", "items": {}},
                    },
                    "required": ["tags"],
                },
            },
        }
        assert tool.to_langchain_schema() == schema

    def test_explicit_parameter_schema_is_preserved_for_provider_outputs(self):
        parameter_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        }
        tool = ToolInfo(
            name="search",
            description="Searches",
            parameters_schema=parameter_schema,
        )

        openai = tool.to_openai_schema()

        assert openai["function"]["parameters"] == parameter_schema
        assert openai["function"]["parameters"] is tool.parameters_schema

    def test_malformed_required_metadata_is_rejected(self):
        with pytest.raises(ValidationError):
            ToolInfo(name="missing-description")

        with pytest.raises(ValidationError):
            ToolParameter(name="bad", type="string", enum="not-a-list")

    def test_register_lookup_name_filter_and_public_outputs(self):
        registry = ToolRegistry()
        registry.register(
            "sum", "Adds values", [ToolParameter(name="value", type="integer")]
        )(_sum)
        registry.register("double", "Doubles values")(_replacement)

        assert registry.get_tool("sum").handler is _sum
        assert registry.get_tool("missing") is None
        assert [tool.name for tool in registry.get_all_tools()] == ["sum", "double"]
        assert [
            tool.name
            for tool in registry.get_tools_by_names(["double", "missing", "sum"])
        ] == [
            "double",
            "sum",
        ]
        assert [
            tool["function"]["name"] for tool in registry.to_openai_tools(["double"])
        ] == ["double"]
        assert registry.to_langchain_tools([]) == registry.to_openai_tools()

    def test_duplicate_registration_replaces_prior_tool_and_unregister_is_idempotent(
        self,
    ):
        registry = ToolRegistry()
        registry.register("value", "first")(_sum)
        registry.register_tool(
            ToolInfo(name="value", description="second", handler=_replacement)
        )

        assert registry.get_tool("value").description == "second"
        assert registry.get_tool("value").handler is _replacement

        registry.unregister("value")
        registry.unregister("value")

        assert registry.get_all_tools() == []

    @pytest.mark.anyio
    async def test_execute_passes_only_supported_context_and_credentials(self):
        registry = ToolRegistry()
        registry.register("sum", "Adds", [ToolParameter(name="value", type="integer")])(
            _sum
        )

        result = await registry.execute(
            "sum",
            {"value": 4},
            credentials={"token": "secret"},
            request_id="request-1",
            ignored="not forwarded",
        )

        assert result == {
            "value": 4,
            "credentials": {"token": "secret"},
            "request_id": "request-1",
        }

    @pytest.mark.anyio
    async def test_execute_reports_missing_tools_and_handlers(self):
        registry = ToolRegistry()
        registry.register_tool(ToolInfo(name="unbound", description="No handler"))

        with pytest.raises(ValueError, match="Tool not found: missing"):
            await registry.execute("missing", {})
        with pytest.raises(ValueError, match="Tool has no handler: unbound"):
            await registry.execute("unbound", {})

    @pytest.mark.anyio
    async def test_sandbox_tools_take_precedence_and_expose_selected_metadata(self):
        class SandboxTool:
            initialized = None

            def __init__(self, **kwargs):
                type(self).initialized = kwargs

            async def execute(self, **arguments):
                return arguments

        registry = ToolRegistry()
        registry.register("Bash", "ordinary handler")(_replacement)
        registry.register_sandbox_tool(
            "Bash",
            SandboxTool,
            aliases=["bash"],
            tool_info=ToolInfo(name="Bash", description="Runs commands"),
        )
        agent = SimpleNamespace(id="agent-1", team_id="team-1")

        result = await registry.execute(
            "bash",
            {"command": "pwd"},
            session_id="session-1",
            allowed_commands=["pwd"],
            agent=agent,
        )

        assert result == {"command": "pwd"}
        assert SandboxTool.initialized == {
            "session_id": "session-1",
            "allowed_commands": ["pwd"],
            "agent_id": "agent-1",
            "team_id": "team-1",
        }
        assert registry.get_sandbox_tool_class("Bash") is SandboxTool
        assert registry.get_sandbox_tool_class("missing") is None
        assert [
            tool.name for tool in registry.get_sandbox_tool_infos(["missing", "Bash"])
        ] == ["Bash"]
        assert registry.to_openai_sandbox_tools()[0]["function"]["name"] == "Bash"

    def test_clear_removes_all_registry_categories(self):
        registry = ToolRegistry()
        registry.register("sum", "Adds")(_sum)
        registry.register_sandbox_tool(
            "Bash",
            type("SandboxTool", (), {}),
            tool_info=ToolInfo(name="Bash", description="Runs commands"),
        )

        registry.clear()

        assert registry.get_all_tools() == []
        assert registry.get_sandbox_tool_class("Bash") is None
        assert registry.get_sandbox_tool_infos() == []
