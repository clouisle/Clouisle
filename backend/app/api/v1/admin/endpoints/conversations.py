"""
Conversation management API endpoints for admin dashboard.
Provides administrative access to all conversations across the system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q, F
from tortoise.functions import Count
from tortoise.contrib.postgres.functions import TruncDate

from app.api import deps
from app.core.i18n import t
from app.core.timezone import now, to_utc
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


async def get_user_team_agent_ids(
    user: User, team_id: UUID | None = None
) -> list[UUID]:
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
        memberships = await TeamMember.filter(user=user).values_list(
            "team_id", flat=True
        )
        agent_ids = await Agent.filter(team_id__in=memberships).values_list(
            "id", flat=True
        )

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
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """
    List conversations.

    - Super Admin: Can see all conversations
    - Admin (has dashboard:access): Can see all conversations in their teams
    - Member/Viewer: Can only see their own conversations
    """
    # Check if user has dashboard:access permission (Admin level)
    has_dashboard_access = current_user.is_superuser
    if not has_dashboard_access:
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

    # Get agent IDs user has access to (team isolation for non-superusers)
    accessible_agent_ids = await get_user_team_agent_ids(current_user, team_id)

    if not accessible_agent_ids:
        # User has no access to any agents
        return success(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
        )

    # Start with accessible agents filter
    query = Conversation.filter(agent_id__in=accessible_agent_ids)

    # Member/Viewer can only see their own conversations
    if not has_dashboard_access:
        query = query.filter(user_id=current_user.id)

    # Apply additional filters
    if agent_id:
        # Verify agent is in accessible list
        if agent_id not in accessible_agent_ids:
            return success(
                data={
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                }
            )
        query = query.filter(agent_id=agent_id)

    # user_id filter only applies for admins (members already filtered to own)
    if user_id and has_dashboard_access:
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
    conversations = (
        await query.select_related("agent", "user")
        .order_by("-updated_at")
        .offset(skip)
        .limit(page_size)
    )

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
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """
    Get conversation statistics.

    - Super Admin/Admin: Stats for all conversations in accessible teams
    - Member/Viewer: Stats for their own conversations only
    """
    # Check if user has dashboard:access permission (Admin level)
    has_dashboard_access = current_user.is_superuser
    if not has_dashboard_access:
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

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

    # Member/Viewer can only see their own conversations
    if not has_dashboard_access:
        query = query.filter(user_id=current_user.id)

    total_conversations = await query.count()

    # Get total messages
    conv_ids = await query.values_list("id", flat=True)
    message_query = Message.filter(conversation_id__in=conv_ids)
    total_messages = await message_query.count()

    # Get conversations by agent (top 10) - also apply user filter for non-admins
    if has_dashboard_access:
        agent_stats_query = Conversation.filter(agent_id__in=agent_ids)
    else:
        agent_stats_query = Conversation.filter(
            agent_id__in=agent_ids, user_id=current_user.id
        )

    agent_stats = (
        await agent_stats_query.annotate(count=Count("id"))
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
            "agent_name": agent_map.get(str(s["agent_id"]), {}).get(
                "name", t("unknown")
            ),
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
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """
    Get conversation and message trends.

    - Super Admin/Admin: Trends for all conversations in accessible teams
    - Member/Viewer: Trends for their own conversations only
    """
    # Check if user has dashboard:access permission (Admin level)
    has_dashboard_access = current_user.is_superuser
    if not has_dashboard_access:
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

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
            data_points.append(
                {
                    "date": label,
                    "conversations": 0,
                    "messages": 0,
                    "tokens": 0,
                }
            )
        return success(
            data={
                "period": period,
                "data": data_points,
            }
        )

    # Get all conversations in the period for accessible agents
    conv_query = Conversation.filter(
        created_at__gte=start_time_utc, agent_id__in=agent_ids
    )
    # Member/Viewer can only see their own conversations
    if not has_dashboard_access:
        conv_query = conv_query.filter(user_id=current_user.id)

    # Use database-level aggregation for efficient trend calculation
    # Get all conversation IDs in scope
    all_conv_ids = await conv_query.values_list("id", flat=True)

    # Calculate date range
    start_date = (now_local - timedelta(days=num_points - 1)).date()
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(
        tzinfo=now_local.tzinfo
    )
    start_utc = to_utc(start_datetime)
    end_utc = to_utc(now_local)

    # Aggregate conversations by day
    conv_by_day = {}
    if all_conv_ids:
        conv_aggregates = (
            await Conversation.filter(
                id__in=list(all_conv_ids),
                created_at__gte=start_utc,
                created_at__lt=end_utc,
            )
            .annotate(day=TruncDate("created_at"))
            .group_by("day")
            .values("day", count=Count("id"))
        )

        for item in conv_aggregates:
            conv_by_day[item["day"]] = item["count"]

    # Aggregate messages by day
    msg_by_day = {}
    token_by_day = {}
    if all_conv_ids:
        msg_aggregates = (
            await Message.filter(
                conversation_id__in=list(all_conv_ids),
                created_at__gte=start_utc,
                created_at__lt=end_utc,
            )
            .annotate(day=TruncDate("created_at"))
            .group_by("day")
            .values("day", count=Count("id"))
        )

        for item in msg_aggregates:
            msg_by_day[item["day"]] = item["count"]

        # Calculate token usage by day
        token_messages = (
            await Message.filter(
                conversation_id__in=list(all_conv_ids),
                created_at__gte=start_utc,
                created_at__lt=end_utc,
                token_usage__isnull=False,
            )
            .annotate(day=TruncDate("created_at"))
            .group_by("day")
            .values("day", "token_usage")
        )

        for item in token_messages:
            day = item["day"]
            if day not in token_by_day:
                token_by_day[day] = 0
            if item["token_usage"]:
                token_by_day[day] += item["token_usage"].get("prompt", 0) or 0
                token_by_day[day] += item["token_usage"].get("completion", 0) or 0

    # Build time series data
    data_points = []
    for i in range(num_points):
        point_date = (now_local - timedelta(days=num_points - i - 1)).date()
        label = point_date.strftime("%m/%d")

        data_points.append(
            {
                "date": label,
                "conversations": conv_by_day.get(point_date, 0),
                "messages": msg_by_day.get(point_date, 0),
                "tokens": token_by_day.get(point_date, 0),
            }
        )

    return success(
        data={
            "period": period,
            "data": data_points,
        }
    )


@router.get("/{conversation_id}", response_model=Response[ConversationWithMessages])
async def get_conversation_detail(
    conversation_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """
    Get conversation detail with messages.

    - Super Admin/Admin: Can access any conversation in accessible teams
    - Member/Viewer: Can only access their own conversations
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

    # Check access permissions
    if not current_user.is_superuser:
        # Check if user has dashboard:access permission (Admin level)
        has_dashboard_access = False
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

        if has_dashboard_access:
            # Admin can access any conversation in their teams
            if conversation.agent_id:
                accessible_agent_ids = await get_user_team_agent_ids(current_user)
                if conversation.agent_id not in accessible_agent_ids:
                    raise BusinessError(
                        code=ResponseCode.PERMISSION_DENIED,
                        msg_key="not_team_member",
                        status_code=403,
                    )
        else:
            # Member/Viewer can only access their own conversations
            if conversation.user_id != current_user.id:
                raise BusinessError(
                    code=ResponseCode.PERMISSION_DENIED,
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
    current_user: User = Depends(deps.PermissionChecker("conversation:delete")),
) -> Any:
    """
    Delete a conversation.

    - Super Admin/Admin: Can delete any conversation in accessible teams
    - Member/Viewer: Can only delete their own conversations
    """
    conversation = await Conversation.filter(id=conversation_id).first()

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Check access permissions
    if not current_user.is_superuser:
        # Check if user has dashboard:access permission (Admin level)
        has_dashboard_access = False
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

        if has_dashboard_access:
            # Admin can delete any conversation in their teams
            if conversation.agent_id:
                accessible_agent_ids = await get_user_team_agent_ids(current_user)
                if conversation.agent_id not in accessible_agent_ids:
                    raise BusinessError(
                        code=ResponseCode.PERMISSION_DENIED,
                        msg_key="not_team_member",
                        status_code=403,
                    )
        else:
            # Member/Viewer can only delete their own conversations
            if conversation.user_id != current_user.id:
                raise BusinessError(
                    code=ResponseCode.PERMISSION_DENIED,
                    msg_key="conversation_not_found",
                    status_code=404,
                )

    # Update agent stats
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
    current_user: User = Depends(deps.PermissionChecker("conversation:delete")),
) -> Any:
    """
    Batch delete conversations.

    - Super Admin/Admin: Can delete any conversation in accessible teams
    - Member/Viewer: Can only delete their own conversations
    """
    # Get conversations to delete
    conversations = await Conversation.filter(id__in=ids)

    if not conversations:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Check access permissions
    if not current_user.is_superuser:
        # Check if user has dashboard:access permission (Admin level)
        has_dashboard_access = False
        for role in current_user.roles:
            for perm in role.permissions:
                if perm.code == "dashboard:access" or perm.code == "*":
                    has_dashboard_access = True
                    break
            if has_dashboard_access:
                break

        if has_dashboard_access:
            # Admin can delete any conversation in their teams
            accessible_agent_ids = await get_user_team_agent_ids(current_user)
            for conv in conversations:
                if conv.agent_id and conv.agent_id not in accessible_agent_ids:
                    raise BusinessError(
                        code=ResponseCode.PERMISSION_DENIED,
                        msg_key="not_team_member",
                        status_code=403,
                    )
        else:
            # Member/Viewer can only delete their own conversations
            for conv in conversations:
                if conv.user_id != current_user.id:
                    raise BusinessError(
                        code=ResponseCode.PERMISSION_DENIED,
                        msg_key="conversation_not_found",
                        status_code=404,
                    )

    # Update agent stats - group by agent_id to reduce queries
    from collections import defaultdict

    agent_updates = defaultdict(lambda: {"conv_count": 0, "msg_count": 0})

    for conv in conversations:
        if conv.agent_id:
            agent_updates[conv.agent_id]["conv_count"] += 1
            agent_updates[conv.agent_id]["msg_count"] += conv.message_count

    # Batch update agents
    for agent_id, updates in agent_updates.items():
        await Agent.filter(id=agent_id).update(
            conversation_count=F("conversation_count") - updates["conv_count"],
            message_count=F("message_count") - updates["msg_count"],
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
