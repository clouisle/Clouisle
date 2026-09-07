"""Conversation-scoped authorization shared by conversations and assets."""

from __future__ import annotations

from uuid import UUID

from app.models.agent import Conversation
from app.models.user import TeamMember, User
from app.schemas.response import BusinessError, ResponseCode


def has_global_conversation_access(user: User) -> bool:
    if user.is_superuser:
        return True
    return any(
        permission.code in ("admin:dashboard:access", "*")
        for role in user.roles
        for permission in role.permissions
    )


async def has_conversation_team_admin_access(user: User, team_id: UUID | None) -> bool:
    if has_global_conversation_access(user):
        return True
    if team_id is None:
        return False
    membership = await TeamMember.filter(team_id=team_id, user=user).first()
    return bool(membership and membership.role in ("owner", "admin"))


async def can_access_conversation(conversation: Conversation, user: User) -> bool:
    if conversation.user_id == user.id:
        return True
    agent = getattr(conversation, "agent", None)
    team_id = getattr(agent, "team_id", None) if agent is not None else None
    return await has_conversation_team_admin_access(user, team_id)


async def get_authorized_conversation(
    conversation_id: UUID, user: User
) -> Conversation:
    conversation = (
        await Conversation.filter(id=conversation_id).prefetch_related("agent").first()
    )
    if conversation is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )
    if not await can_access_conversation(conversation, user):
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )
    return conversation
