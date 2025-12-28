"""
Conversation management API endpoints for admin dashboard.
Provides administrative access to all conversations across the system.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q
from tortoise.functions import Count

from app.api import deps
from app.models.user import User
from app.models.agent import Agent, Conversation, Message
from app.schemas.agent import (
    ConversationListOut,
    ConversationOut,
    ConversationWithMessages,
    MessageOut,
)
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    PageData,
    success,
)


router = APIRouter()


# ============ Admin Conversation Management ============


@router.get("", response_model=Response[PageData[ConversationListOut]])
async def list_all_conversations(
    team_id: UUID | None = Query(None, description="Filter by team"),
    agent_id: UUID | None = Query(None, description="Filter by agent"),
    user_id: UUID | None = Query(None, description="Filter by user"),
    search: str | None = Query(None, description="Search in title"),
    untitled_only: bool = Query(False, description="Show only untitled conversations"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    List all conversations (admin endpoint).
    
    Returns conversations across all users, filterable by team and agent.
    Requires appropriate permissions (to be enforced by permission system).
    """
    query = Conversation.all()

    # Apply filters
    if team_id:
        # Get all agents for this team, then filter conversations
        agent_ids = await Agent.filter(team_id=team_id).values_list("id", flat=True)
        query = query.filter(agent_id__in=agent_ids)
    
    if agent_id:
        query = query.filter(agent_id=agent_id)
    
    if user_id:
        query = query.filter(user_id=user_id)
    
    if untitled_only:
        # Filter conversations with null or empty title
        query = query.filter(Q(title__isnull=True) | Q(title=""))
    elif search:
        query = query.filter(title__icontains=search)

    # Get total count
    total = await query.count()

    # Paginate
    skip = (page - 1) * page_size
    conversations = await query.select_related(
        "agent", "user"
    ).order_by("-updated_at").offset(skip).limit(page_size)

    # Build response with additional info
    conv_list = []
    for conv in conversations:
        conv_data = {
            "id": str(conv.id),
            "agent_id": str(conv.agent_id),
            "agent_name": conv.agent.name if conv.agent else None,
            "agent_icon": conv.agent.icon if conv.agent else None,
            "title": conv.title,
            "message_count": conv.message_count,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            # Extra fields for admin view
            "user_id": str(conv.user_id) if conv.user_id else None,
            "user_name": conv.user.username if conv.user else None,
        }
        conv_list.append(conv_data)

    return success(
        data={
            "items": conv_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/stats", response_model=Response[dict])
async def get_conversation_stats(
    team_id: UUID | None = Query(None, description="Filter by team"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get conversation statistics for admin dashboard.
    """
    query = Conversation.all()
    
    if team_id:
        agent_ids = await Agent.filter(team_id=team_id).values_list("id", flat=True)
        query = query.filter(agent_id__in=agent_ids)

    total_conversations = await query.count()
    
    # Get total messages
    message_query = Message.all()
    if team_id:
        conv_ids = await query.values_list("id", flat=True)
        message_query = message_query.filter(conversation_id__in=conv_ids)
    total_messages = await message_query.count()

    # Get conversations by agent (top 10)
    if team_id:
        agent_stats = (
            await Conversation.filter(agent_id__in=agent_ids)
            .annotate(count=Count("id"))
            .group_by("agent_id")
            .order_by("-count")
            .limit(10)
            .values("agent_id", "count")
        )
    else:
        agent_stats = (
            await Conversation.all()
            .annotate(count=Count("id"))
            .group_by("agent_id")
            .order_by("-count")
            .limit(10)
            .values("agent_id", "count")
        )

    # Get agent names for stats
    agent_ids_list = [s["agent_id"] for s in agent_stats]
    agents = await Agent.filter(id__in=agent_ids_list).values("id", "name", "icon")
    agent_map = {str(a["id"]): a for a in agents}

    conversations_by_agent = [
        {
            "agent_id": str(s["agent_id"]),
            "agent_name": agent_map.get(str(s["agent_id"]), {}).get("name", "Unknown"),
            "agent_icon": agent_map.get(str(s["agent_id"]), {}).get("icon"),
            "count": s["count"],
        }
        for s in agent_stats
    ]

    return success(
        data={
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "conversations_by_agent": conversations_by_agent,
        }
    )


@router.get("/{conversation_id}", response_model=Response[ConversationWithMessages])
async def get_conversation_detail(
    conversation_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get conversation detail with messages (admin endpoint).
    
    Returns full conversation data including all messages.
    """
    conversation = (
        await Conversation.filter(id=conversation_id)
        .prefetch_related("agent", "user")
        .first()
    )

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Get only active messages
    messages = await Message.filter(
        conversation_id=conversation.id,
        is_active=True,
    ).order_by("created_at")

    # Batch calculate version counts
    root_ids = set()
    for m in messages:
        root_id = m.parent_id if m.parent_id else m.id
        root_ids.add(root_id)

    version_counts: dict[str, int] = {}
    if root_ids:
        child_counts = (
            await Message.filter(parent_id__in=list(root_ids))
            .annotate(count=Count("id"))
            .group_by("parent_id")
            .values("parent_id", "count")
        )
        for item in child_counts:
            version_counts[str(item["parent_id"])] = item["count"] + 1
        for root_id in root_ids:
            if str(root_id) not in version_counts:
                version_counts[str(root_id)] = 1

    # Build message outputs
    messages_out = []
    for m in messages:
        msg_data = MessageOut.model_validate(m).model_dump()
        root_id = m.parent_id if m.parent_id else m.id
        msg_data["version_count"] = version_counts.get(str(root_id), 1)
        messages_out.append(msg_data)

    # Build response
    conv_data = ConversationOut.model_validate(conversation).model_dump()
    conv_data["agent_name"] = conversation.agent.name if conversation.agent else None
    conv_data["agent_icon"] = conversation.agent.icon if conversation.agent else None
    conv_data["messages"] = messages_out
    # Extra admin fields
    conv_data["user_id"] = str(conversation.user_id)
    conv_data["user_name"] = conversation.user.username if conversation.user else None

    return success(data=conv_data)


@router.delete("/{conversation_id}", response_model=Response[dict])
async def delete_conversation_admin(
    conversation_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete a conversation (admin endpoint).
    
    Admins can delete any conversation regardless of owner.
    """
    conversation = await Conversation.filter(id=conversation_id).first()

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Update agent stats
    from tortoise.expressions import F
    await Agent.filter(id=conversation.agent_id).update(
        conversation_count=F("conversation_count") - 1,
        message_count=F("message_count") - conversation.message_count,
    )

    # Delete conversation (cascades to messages)
    await conversation.delete()

    return success(data={"id": str(conversation_id)}, msg_key="conversation_deleted")


@router.delete("", response_model=Response[dict])
async def batch_delete_conversations(
    ids: list[UUID] = Query(..., description="Conversation IDs to delete"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Batch delete conversations (admin endpoint).
    """
    from tortoise.expressions import F

    # Get conversations to delete
    conversations = await Conversation.filter(id__in=ids)
    
    if not conversations:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Update agent stats for each conversation
    for conv in conversations:
        await Agent.filter(id=conv.agent_id).update(
            conversation_count=F("conversation_count") - 1,
            message_count=F("message_count") - conv.message_count,
        )

    # Delete conversations
    deleted_count = await Conversation.filter(id__in=ids).delete()

    return success(
        data={
            "deleted_count": deleted_count,
            "ids": [str(id) for id in ids],
        },
        msg_key="conversations_deleted",
    )
