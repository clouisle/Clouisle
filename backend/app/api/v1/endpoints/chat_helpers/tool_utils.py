"""
Tool utilities for chat.
"""

from app.models.agent import Agent, Tool


async def get_agent_tools(agent: Agent) -> list[dict]:
    """Get all tools configured for an agent."""
    if not agent.tools:
        return []

    tools = []
    for tool_id in agent.tools:
        tool = await Tool.get_or_none(id=tool_id)
        if tool and tool.is_active:
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

    display_names = {}
    for tool_id in agent.tools:
        tool = await Tool.get_or_none(id=tool_id)
        if tool and tool.is_active:
            # Use localized name if available
            if user_locale and tool.i18n_names and user_locale in tool.i18n_names:
                display_names[tool.name] = tool.i18n_names[user_locale]
            else:
                display_names[tool.name] = tool.name

    return display_names
