"""Approval matching across tool kinds.

The agent ``tools_config`` entry is the only user-facing switch that turns a
tool into a confirmation gate. Matching must follow the identity each tool kind
actually persists: builtin name, custom tool id/name, MCP server id/alias, and
skill id.
"""

from __future__ import annotations

from uuid import uuid4

from app.services.tool_context import get_agent_tool_require_approval


def test_agent_dict_config_is_read_and_malformed_entries_are_ignored():
    agent = {
        "tools_config": [
            None,
            "builtin",
            {"type": "builtin", "name": "get_current_time"},
            {
                "type": "builtin",
                "name": "get_current_time",
                "require_approval": True,
            },
        ]
    }

    assert get_agent_tool_require_approval(agent, "get_current_time") is True
    assert get_agent_tool_require_approval(agent, "calculate") is False
    assert get_agent_tool_require_approval({"tools_config": "broken"}, "x") is False
    assert get_agent_tool_require_approval(None, "x") is False


def test_custom_tool_approval_matches_persisted_id_or_exported_name():
    tool_id = uuid4()
    config = {
        "tools_config": [
            {
                "type": "custom",
                "tool_id": str(tool_id),
                "name": "renamed_on_export",
                "require_approval": True,
            }
        ]
    }

    assert get_agent_tool_require_approval(config, "anything", tool_id) is True
    assert get_agent_tool_require_approval(config, "anything", str(tool_id)) is True
    assert get_agent_tool_require_approval(config, "renamed_on_export") is True
    assert get_agent_tool_require_approval(config, "custom_renamed_on_export") is True
    assert get_agent_tool_require_approval(config, "unrelated") is False
    assert get_agent_tool_require_approval(config, "anything", uuid4()) is False


def test_mcp_tool_approval_matches_server_id_or_model_alias():
    server_id = uuid4()
    config = {
        "tools_config": [
            {
                "type": "mcp",
                "server_id": str(server_id),
                "name": "files",
                "require_approval": True,
            }
        ]
    }

    assert get_agent_tool_require_approval(config, "mcp_files_read", server_id) is True
    assert get_agent_tool_require_approval(config, "mcp_files_read") is True
    assert get_agent_tool_require_approval(config, "mcp_other_read") is False
    assert get_agent_tool_require_approval(config, "mcp_other_read", uuid4()) is False


def test_skill_tool_approval_covers_id_and_dynamic_skill_prefix():
    skill_id = uuid4()
    config = {
        "tools_config": [
            {"type": "skill", "skill_id": str(skill_id), "require_approval": True}
        ]
    }

    assert get_agent_tool_require_approval(config, "skill_research", skill_id) is True
    # Dynamic skill tools are materialized per skill; the prefix is the stable
    # identity even when the runtime has no tool id to compare.
    assert get_agent_tool_require_approval(config, "skill_research") is True
    assert get_agent_tool_require_approval(config, "get_current_time") is False
