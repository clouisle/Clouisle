"""Current-user Feishu routing, shared by settings and authenticated intake."""

from uuid import UUID

from tortoise.expressions import Q

from app.models.agent import Agent, AgentStatus, AgentVisibility
from app.models.feishu_agent import FeishuAgentPreference
from app.models.feishu_user import FeishuUser
from app.models.integration import Integration
from app.models.user import TeamMember, User
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.response import BusinessError
from app.services.integration_features import active_features


def channel_available(integration: Integration | None) -> bool:
    return bool(
        integration
        and "agent_chat" in active_features(integration)
        and integration.config.get("app_id")
        and integration.credentials.get("app_secret")
    )


async def linked_user(integration: Integration, user: User) -> bool:
    return (
        await FeishuUser.filter(user_id=user.id).exists()
        or await UserSSOConnection.filter(
            integration_id=integration.id, user_id=user.id
        ).exists()
    )


async def available_agents(user: User) -> list[Agent]:
    from app.services.feishu_agent_runtime import _authorized_agent

    query = Agent.filter(status=AgentStatus.PUBLISHED, team__is_deleted=False)
    if not user.is_superuser:
        memberships = await TeamMember.filter(user_id=user.id).values_list(
            "team_id", flat=True
        )
        query = query.filter(
            Q(visibility=AgentVisibility.PRIVATE, created_by_id=user.id)
            | Q(
                team_id__in=memberships,
                visibility__in=[AgentVisibility.TEAM, AgentVisibility.PUBLIC],
            )
            | Q(
                team_id__in=memberships,
                visibility=AgentVisibility.PRIVATE,
                created_by_id__isnull=True,
            )
        )
    agents = []
    async for candidate in query.only("id").order_by("name", "id"):
        try:
            agents.append(await _authorized_agent(candidate.id, user))
        except BusinessError:
            continue
    return agents


async def set_preference(
    integration: Integration, user: User, agent_id: UUID | None, *, db=None
) -> None:
    """Caller holds the user routing lock; existing receipts are never changed."""
    preference, _ = await FeishuAgentPreference.get_or_create(
        integration_id=integration.id, user_id=user.id, using_db=db
    )
    preference.agent_id = agent_id
    await preference.save(using_db=db, update_fields=["agent_id", "updated_at"])


async def personal_enabled(integration_id: UUID, user_id: UUID) -> bool:
    return await FeishuAgentPreference.filter(
        integration_id=integration_id, user_id=user_id, is_enabled=True
    ).exists()


async def preference_summary(integration: Integration | None, user: User) -> dict:
    from app.services.feishu_agent_runtime import _authorized_agent

    linked = bool(integration and await linked_user(integration, user))
    preference = (
        await FeishuAgentPreference.get_or_none(
            integration_id=integration.id, user_id=user.id
        )
        if integration
        else None
    )
    agent_id = preference.agent_id if preference else None
    agent = None
    if agent_id and linked:
        try:
            agent = await _authorized_agent(agent_id, user)
        except BusinessError:
            pass
    return {
        "enabled": channel_available(integration),
        "is_enabled": bool(preference and preference.is_enabled),
        "linked": linked,
        "agent_id": str(agent_id) if agent_id else None,
        "agent_name": agent.name if agent else None,
        "agent_available": agent is not None,
    }
