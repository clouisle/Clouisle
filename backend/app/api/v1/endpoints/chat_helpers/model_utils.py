"""Model utilities for chat."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.agent import Agent
from app.models.model import Model, TeamModel
from app.schemas.response import BusinessError, ResponseCode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatModelResolution:
    """Resolved chat model metadata shared by context preparation and calls."""

    model: Model
    team_model: TeamModel
    model_id: str
    tokenizer_model_id: str
    provider: str
    context_length: int | None
    max_output_tokens: int | None
    supports_vision: bool


async def resolve_agent_chat_model(agent: Agent) -> ChatModelResolution:
    """Resolve one authorized chat model for budgeting and LLM calls.

    ``model_id`` in the returned resolution is the database UUID of the
    selected ``Model``.  ``tokenizer_model_id`` is the provider's model name
    and is used only for token encoding selection.
    """
    from app.api.v1.endpoints.chat import get_agent_chat_model
    from app.llm import model_manager

    team_model = await get_agent_chat_model(agent)
    if team_model is None:
        if getattr(agent, "model_id", None):
            raise BusinessError(
                code=ResponseCode.MODEL_NOT_FOUND,
                msg_key="model_not_found",
            )
        model, team_model = await model_manager.resolve_team_chat_model(
            team_id=str(agent.team_id),
            model_id=None,
        )
    else:
        if not getattr(team_model, "is_enabled", True):
            raise BusinessError(
                code=ResponseCode.MODEL_DISABLED,
                msg_key="model_disabled",
            )
        model = team_model.model
        if not getattr(model, "is_enabled", True):
            raise BusinessError(
                code=ResponseCode.MODEL_DISABLED,
                msg_key="model_disabled",
            )

    capabilities = model.capabilities or {}
    return ChatModelResolution(
        model=model,
        team_model=team_model,
        model_id=str(model.id),
        tokenizer_model_id=model.model_id,
        provider=model.provider,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
        supports_vision=bool(capabilities.get("vision")),
    )


async def get_model_identifier(agent: Agent) -> str | None:
    """Get the database UUID of the agent's bound model, if any."""
    if not getattr(agent, "model_id", None):
        return None

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if not team_model or not getattr(team_model, "model", None):
        return None

    return str(team_model.model.id)


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
