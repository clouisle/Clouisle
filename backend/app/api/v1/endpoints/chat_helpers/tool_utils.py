"""
Tool utilities for chat.
"""

from app.models.agent import Agent
from app.models.tool import Tool


async def get_agent_tools(agent: Agent) -> list[dict]:
    """Get all custom tools configured for an agent."""
    tools_config = list(agent.tools_config or [])
    tool_ids = [
        config.get("tool_id") for config in tools_config if config.get("tool_id")
    ]
    if not tool_ids:
        return []

    all_tools = await Tool.filter(id__in=tool_ids, is_enabled=True).all()
    tool_map = {str(t.id): t for t in all_tools}

    tools: list[dict] = []
    for tool_id in tool_ids:
        tool = tool_map.get(str(tool_id))
        if tool:
            tools.append(
                {
                    "id": tool.id,
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "type": tool.type,
                }
            )

    return tools


async def get_tool_display_names(
    agent: Agent, user_locale: str | None = None
) -> dict[str, str]:
    """Get tool display names for the given locale."""
    _ = user_locale
    tools_config = list(agent.tools_config or [])
    tool_ids = [
        config.get("tool_id") for config in tools_config if config.get("tool_id")
    ]
    if not tool_ids:
        return {}

    all_tools = await Tool.filter(id__in=tool_ids, is_enabled=True).all()
    tool_map = {str(t.id): t for t in all_tools}

    display_names: dict[str, str] = {}
    for tool_id in tool_ids:
        tool = tool_map.get(str(tool_id))
        if tool:
            display_names[tool.name] = tool.display_name

    return display_names
