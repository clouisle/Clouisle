"""
Model utilities for chat.
"""

from app.models.agent import Agent
from app.models.model import TeamModel


async def get_model_identifier(agent: Agent) -> str | None:
    """Get model identifier from agent's model."""
    if not agent.model_id:
        return None

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if not team_model:
        return None

    return f"{team_model.model.provider}/{team_model.model.model_id}"


async def get_model_capabilities(agent: Agent) -> dict:
    """Get model capabilities including vision support."""
    if not agent.model_id:
        return {"supports_vision": False}

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if not team_model:
        return {"supports_vision": False}

    capabilities = team_model.model.capabilities or {}
    supports_vision = bool(capabilities.get("vision"))

    return {"supports_vision": supports_vision}
