"""
Conversation management API endpoints for admin dashboard.
Provides administrative access to all conversations across the system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q
from tortoise.functions import Count

from app.api import deps
from app.core.timezone import now, to_local, to_utc
from app.models.user import User, Team, TeamMember
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


# ============ Helper Functions ============


async def check_team_access(team_id: UUID, user: User) -> Team:
    """Check if user has access to the team."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return team

    membership = await TeamMember.filter(team=team, user=user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=403,
        )

    return team


async def get_user_team_agent_ids(user: User, team_id: UUID | None = None) -> list[UUID]:
    """Get agent IDs that the user has access to."""
    if team_id:
        # Verify access to specific team
        await check_team_access(team_id, user)
        agent_ids = await Agent.filter(team_id=team_id).values_list("id", flat=True)
    elif user.is_superuser:
        # Superuser can access all agents
        agent_ids = await Agent.all().values_list("id", flat=True)
    else:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=user).values_list("team_id", flat=True)
        agent_ids = await Agent.filter(team_id__in=memberships).values_list("id", flat=True)

    return list(agent_ids)


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
    Returns stats for teams the user has access to.
    """
    # Get agent IDs user has access to
    agent_ids = await get_user_team_agent_ids(current_user, team_id)

    if not agent_ids:
        # User has no access to any agents
        return success(
            data={
                "total_conversations": 0,
                "total_messages": 0,
                "conversations_by_agent": [],
            }
        )

    # Get conversations for accessible agents
    query = Conversation.filter(agent_id__in=agent_ids)
    total_conversations = await query.count()

    # Get total messages
    conv_ids = await query.values_list("id", flat=True)
    message_query = Message.filter(conversation_id__in=conv_ids)
    total_messages = await message_query.count()

    # Get conversations by agent (top 10)
    agent_stats = (
        await Conversation.filter(agent_id__in=agent_ids)
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


@router.get("/stats/trends", response_model=Response[dict])
async def get_conversation_trends(
    team_id: UUID | None = Query(None, description="Filter by team"),
    period: str = Query("7d", description="Time period: 7d, 30d"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get conversation and message trends for dashboard charts.
    Returns daily statistics for teams the user has access to.
    """
    now_local = now()

    # Determine time range
    if period == "30d":
        start_time = now_local - timedelta(days=30)
        num_points = 30
    else:  # Default to 7d
        start_time = now_local - timedelta(days=7)
        num_points = 7

    start_time_utc = to_utc(start_time)

    # Get agent IDs user has access to
    agent_ids = await get_user_team_agent_ids(current_user, team_id)

    if not agent_ids:
        # User has no access to any agents, return empty data
        data_points = []
        for i in range(num_points):
            point_date = (now_local - timedelta(days=num_points - i - 1)).date()
            label = point_date.strftime("%m/%d")
            data_points.append({
                "date": label,
                "conversations": 0,
                "messages": 0,
                "tokens": 0,
            })
        return success(data={
            "period": period,
            "data": data_points,
        })

    # Get all conversations in the period for accessible agents
    conv_query = Conversation.filter(
        created_at__gte=start_time_utc,
        agent_id__in=agent_ids
    )
    conversations = await conv_query.values("id", "created_at")

    # Get all messages in the period for accessible agents
    msg_query = Message.filter(
        created_at__gte=start_time_utc,
        conversation__agent_id__in=agent_ids
    )
    messages = await msg_query.values("created_at", "token_usage", "role")

    # Build time series data grouped by day
    data_points = []
    for i in range(num_points):
        point_date = (now_local - timedelta(days=num_points - i - 1)).date()
        point_start = datetime.combine(point_date, datetime.min.time()).replace(tzinfo=now_local.tzinfo)
        point_end = point_start + timedelta(days=1)

        # Count conversations created in this day
        conv_count = sum(
            1
            for c in conversations
            if point_start <= to_local(c["created_at"]) < point_end
        )

        # Count messages and tokens in this day
        msgs_in_period = [
            m for m in messages
            if point_start <= to_local(m["created_at"]) < point_end
        ]
        msg_count = len(msgs_in_period)

        # Calculate total tokens
        tokens = 0
        for m in msgs_in_period:
            if m["token_usage"]:
                tokens += (m["token_usage"].get("prompt", 0) or 0)
                tokens += (m["token_usage"].get("completion", 0) or 0)

        # Format label based on locale (use simple format for now)
        label = point_date.strftime("%m/%d")

        data_points.append({
            "date": label,
            "conversations": conv_count,
            "messages": msg_count,
            "tokens": tokens,
        })

    return success(data={
        "period": period,
        "data": data_points,
    })


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
