"""
Dashboard statistics API endpoints for admin.
Provides system-wide statistics and metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.core.timezone import now_utc
from app.models.user import User, Team
from app.models.agent import Agent, Conversation, Message
from app.models.workflow import Workflow
from app.models.knowledge_base import KnowledgeBase
from app.schemas.response import Response, success

router = APIRouter()


@router.get("/stats", response_model=Response[dict])
async def get_dashboard_stats(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get system-wide dashboard statistics (superuser only).

    Returns:
    - Total users, teams, agents, workflows, knowledge bases
    - Total conversations, messages, tokens
    - Daily/Weekly/Monthly active users
    - Growth trends
    """
    now = now_utc()
    today_start = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=now.tzinfo)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Basic counts
    total_users = await User.all().count()
    total_teams = await Team.all().count()
    total_agents = await Agent.all().count()
    total_workflows = await Workflow.all().count()
    total_knowledge_bases = await KnowledgeBase.all().count()
    total_conversations = await Conversation.all().count()
    total_messages = await Message.all().count()

    # Token usage
    messages_with_tokens = await Message.filter(
        token_usage__isnull=False
    ).values("token_usage")

    total_tokens = 0
    for msg in messages_with_tokens:
        if msg["token_usage"]:
            total_tokens += (msg["token_usage"].get("prompt", 0) or 0)
            total_tokens += (msg["token_usage"].get("completion", 0) or 0)

    # Active users (based on conversation activity)
    # DAU - Daily Active Users
    dau_user_ids = await Conversation.filter(
        created_at__gte=today_start
    ).values_list("user_id", flat=True)
    dau = len(set(dau_user_ids))

    # WAU - Weekly Active Users
    wau_user_ids = await Conversation.filter(
        created_at__gte=week_start
    ).values_list("user_id", flat=True)
    wau = len(set(wau_user_ids))

    # MAU - Monthly Active Users
    mau_user_ids = await Conversation.filter(
        created_at__gte=month_start
    ).values_list("user_id", flat=True)
    mau = len(set(mau_user_ids))

    # User growth (last 30 days)
    new_users_30d = await User.filter(created_at__gte=month_start).count()

    # Conversation growth (last 30 days)
    new_conversations_30d = await Conversation.filter(created_at__gte=month_start).count()

    return success(data={
        "overview": {
            "total_users": total_users,
            "total_teams": total_teams,
            "total_agents": total_agents,
            "total_workflows": total_workflows,
            "total_knowledge_bases": total_knowledge_bases,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
        },
        "active_users": {
            "dau": dau,
            "wau": wau,
            "mau": mau,
        },
        "growth": {
            "new_users_30d": new_users_30d,
            "new_conversations_30d": new_conversations_30d,
        }
    })


@router.get("/stats/trends", response_model=Response[dict])
async def get_dashboard_trends(
    period: str = Query("30d", description="Time period: 7d, 30d"),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get system-wide trends for dashboard charts (superuser only).

    Returns daily statistics for:
    - New users
    - Active users
    - New conversations
    - Messages
    - Token usage
    """
    now = now_utc()

    # Determine time range
    if period == "7d":
        start_time = now - timedelta(days=7)
        num_points = 7
    else:  # Default to 30d
        start_time = now - timedelta(days=30)
        num_points = 30

    # Get all data in the period
    users = await User.filter(created_at__gte=start_time).values("created_at")
    conversations = await Conversation.filter(created_at__gte=start_time).values("created_at", "user_id")
    messages = await Message.filter(created_at__gte=start_time).values("created_at", "token_usage")

    # Build time series data
    data_points = []
    for i in range(num_points):
        point_date = (now - timedelta(days=num_points - i - 1)).date()
        point_start = datetime.combine(point_date, datetime.min.time()).replace(tzinfo=now.tzinfo)
        point_end = point_start + timedelta(days=1)

        # New users
        new_users = sum(1 for u in users if point_start <= u["created_at"] < point_end)

        # Active users (users who created conversations)
        active_user_ids = set(
            c["user_id"] for c in conversations
            if point_start <= c["created_at"] < point_end and c["user_id"]
        )
        active_users = len(active_user_ids)

        # New conversations
        new_conversations = sum(1 for c in conversations if point_start <= c["created_at"] < point_end)

        # Messages and tokens
        msgs_in_period = [m for m in messages if point_start <= m["created_at"] < point_end]
        msg_count = len(msgs_in_period)

        tokens = 0
        for m in msgs_in_period:
            if m["token_usage"]:
                tokens += (m["token_usage"].get("prompt", 0) or 0)
                tokens += (m["token_usage"].get("completion", 0) or 0)

        label = point_date.strftime("%m/%d")

        data_points.append({
            "date": label,
            "new_users": new_users,
            "active_users": active_users,
            "new_conversations": new_conversations,
            "messages": msg_count,
            "tokens": tokens,
        })

    return success(data={
        "period": period,
        "data": data_points,
    })
