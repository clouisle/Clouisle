"""
Tool utilities for chat.
"""

from app.models.agent import Agent, Tool


async def get_agent_tools(agent: Agent) -> list[dict]:
    """Get all tools configured for an agent."""
    if not agent.tools:
        return []

    # Fetch all tools in one query
    all_tools = await Tool.filter(id__in=agent.tools, is_active=True).all()
    tool_map = {str(t.id): t for t in all_tools}

    tools = []
    for tool_id in agent.tools:
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
    if not agent.tools:
        return {}

    # Fetch all tools in one query
    all_tools = await Tool.filter(id__in=agent.tools, is_active=True).all()
    tool_map = {str(t.id): t for t in all_tools}

    display_names = {}
    for tool_id in agent.tools:
        tool = tool_map.get(str(tool_id))
        if tool:
            # Use localized name if available
            if user_locale and tool.i18n_names and user_locale in tool.i18n_names:
                display_names[tool.name] = tool.i18n_names[user_locale]
            else:
                display_names[tool.name] = tool.name

    return display_names
