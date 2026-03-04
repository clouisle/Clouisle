"""
Model utilities for chat.
"""

from app.models.agent import Agent, Model


async def get_model_identifier(agent: Agent) -> str | None:
    """Get model identifier from agent's model."""
    if not agent.model_id:
        return None

    model = await Model.get_or_none(id=agent.model_id)
    if not model:
        return None

    return model.model_identifier


async def get_model_capabilities(agent: Agent) -> dict:
    """Get model capabilities including vision support."""
    if not agent.model_id:
        return {"supports_vision": False}

    model = await Model.get_or_none(id=agent.model_id)
    if not model:
        return {"supports_vision": False}

    # Check if model supports vision (e.g., gpt-4-vision, claude-3-opus, etc.)
    supports_vision = any(
        keyword in model.model_identifier.lower()
        for keyword in ["vision", "claude-3", "gpt-4o", "gemini-pro-vision"]
    )

    return {"supports_vision": supports_vision}
