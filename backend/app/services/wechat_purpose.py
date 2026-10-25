"""Owner-authorized configuration for one mutually exclusive WeChat use."""

from uuid import UUID

from app.models.agent import Agent, AgentStatus
from app.models.agent_run import AgentRunStatus
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import WeChatKnowledgeReceipt
from app.schemas.response import BusinessError
from app.services.wechat_connection import collection_error

TERMINAL_RUNS = [
    AgentRunStatus.COMPLETED,
    AgentRunStatus.STOPPED,
    AgentRunStatus.FAILED,
    AgentRunStatus.INTERRUPTED,
]


async def authorized_agent(agent_id: UUID | None, user) -> Agent:
    from app.api.v1.endpoints.chat import check_agent_chat_access

    if not agent_id:
        raise collection_error("agent_not_found", 404)
    if not user.is_active or getattr(user, "approval_status", "approved") != "approved":
        raise collection_error("inactive_user", 403)
    agent = await check_agent_chat_access(agent_id, user)
    if agent.status != AgentStatus.PUBLISHED or not agent.team or agent.team.is_deleted:
        raise collection_error("agent_access_denied", 403)
    return agent


async def available_agents(user) -> list[Agent]:
    """Stable numbering shared by personal settings and WeChat commands."""
    output = []
    async for candidate in (
        Agent.filter(status=AgentStatus.PUBLISHED).only("id").order_by("name", "id")
    ):
        try:
            output.append(await authorized_agent(candidate.id, user))
        except BusinessError:
            continue
    return output


async def check_switch_idle(
    binding_id: UUID, *, exclude_receipt_id: UUID | None = None
) -> None:
    active = (
        await WeChatAgentSession.filter(binding_id=binding_id)
        .exclude(active_run__status__in=TERMINAL_RUNS)
        .exclude(active_run_id=None)
        .exists()
    )
    pending = WeChatAgentReceipt.filter(
        binding_id=binding_id, status__in=["pending", "submitted"]
    )
    if exclude_receipt_id is not None:
        pending = pending.exclude(id=exclude_receipt_id)
    queued = await pending.exists()
    collecting = await WeChatKnowledgeReceipt.filter(
        binding_id=binding_id, status__in=["pending", "processing"]
    ).exists()
    delivering = await IntegrationDelivery.filter(
        provider_type="wechat",
        chat_id=str(binding_id),
        status__in=["pending", "sending"],
    ).exists()
    if active or queued or collecting or delivering:
        raise collection_error("wechat_purpose_busy", 409)


def resolve_variables(agent: Agent, values: dict) -> dict:
    definitions = agent.variables or []
    allowed = {entry["name"] for entry in definitions}
    if set(values) - allowed:
        raise collection_error("wechat_agent_variables_invalid")
    result = {}
    for entry in definitions:
        name = entry["name"]
        value = (
            entry.get("default")
            if entry.get("hidden")
            else values.get(name, entry.get("default"))
        )
        if entry.get("required") and (value is None or value == ""):
            raise collection_error("wechat_agent_variables_invalid")
        if value is None:
            continue
        kind = entry.get("type", "text")
        if value == "" and not entry.get("required"):
            continue
        if kind == "number":
            if isinstance(value, bool):
                raise collection_error("wechat_agent_variables_invalid")
            try:
                number = float(value)
            except (ValueError, TypeError):
                raise collection_error("wechat_agent_variables_invalid") from None
            import math

            if (
                not math.isfinite(number)
                or (entry.get("min") is not None and number < entry["min"])
                or (entry.get("max") is not None and number > entry["max"])
            ):
                raise collection_error("wechat_agent_variables_invalid")
        elif kind == "checkbox":
            if not isinstance(value, (str, bool)) or value not in (
                True,
                False,
                "true",
                "false",
                "",
            ):
                raise collection_error("wechat_agent_variables_invalid")
            value = "true" if value is True or value == "true" else "false"
        elif not isinstance(value, str):
            raise collection_error("wechat_agent_variables_invalid")
        if (
            isinstance(value, str)
            and entry.get("maxLength")
            and len(value) > entry["maxLength"]
        ):
            raise collection_error("wechat_agent_variables_invalid")
        if entry.get("options") and value not in entry["options"]:
            raise collection_error("wechat_agent_variables_invalid")
        result[name] = value
    return result
