"""
Agent statistics and monitoring API endpoints.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.functions import Avg

from app.api import deps
from app.models.agent import Agent, Conversation, Message, MessageRole
from app.models.user import User
from app.schemas.response import success, ResponseCode, BusinessError
from app.core.timezone import now, to_local, to_utc

router = APIRouter()


@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: UUID,
    period: str = Query("7d", description="Time period: 24h, 7d, 30d, all"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get agent statistics overview.
    """
    agent = await Agent.filter(id=agent_id).first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    # Calculate time range
    now_local = now()
    if period == "24h":
        start_time = now_local - timedelta(hours=24)
    elif period == "7d":
        start_time = now_local - timedelta(days=7)
    elif period == "30d":
        start_time = now_local - timedelta(days=30)
    else:
        start_time = None

    # Build base query
    conv_query = Conversation.filter(agent_id=agent_id)
    msg_query = Message.filter(conversation__agent_id=agent_id)

    if start_time:
        conv_query = conv_query.filter(created_at__gte=start_time)
        msg_query = msg_query.filter(created_at__gte=start_time)

    # Get conversation count
    total_conversations = await conv_query.count()

    # Get message counts by role
    user_messages = await msg_query.filter(role=MessageRole.USER).count()
    assistant_messages = await msg_query.filter(role=MessageRole.ASSISTANT).count()
    tool_messages = await msg_query.filter(role=MessageRole.TOOL).count()
    total_messages = user_messages + assistant_messages + tool_messages

    # Get token usage - calculate manually from JSON field
    prompt_tokens = 0
    completion_tokens = 0
    messages_with_tokens = await msg_query.filter(
        role=MessageRole.ASSISTANT, token_usage__isnull=False
    ).values("token_usage")

    for msg in messages_with_tokens:
        if msg["token_usage"]:
            prompt_tokens += msg["token_usage"].get("prompt", 0) or 0
            completion_tokens += msg["token_usage"].get("completion", 0) or 0

    # Get average response time
    avg_duration = (
        await msg_query.filter(role=MessageRole.ASSISTANT, duration_ms__isnull=False)
        .annotate(avg_duration=Avg("duration_ms"))
        .values("avg_duration")
    )

    avg_response_time = (
        avg_duration[0]["avg_duration"]
        if avg_duration and avg_duration[0]["avg_duration"]
        else 0
    )

    # Get unique users - use a fresh query to avoid ORDER BY conflict with DISTINCT
    user_query = Conversation.filter(agent_id=agent_id)
    if start_time:
        user_query = user_query.filter(created_at__gte=start_time)
    unique_users = await user_query.values_list("user_id", flat=True)
    active_users = len(set(unique_users))

    # Get actual tool call count (not just message count)
    messages_with_tools = await msg_query.filter(
        role=MessageRole.ASSISTANT, tool_calls__isnull=False
    ).values("tool_calls")

    tool_call_count = 0
    for msg in messages_with_tools:
        if msg["tool_calls"] and isinstance(msg["tool_calls"], list):
            tool_call_count += len(msg["tool_calls"])

    # Get error count (messages with error in content or tool errors)
    # This is a simplified approach - in production you might want a separate error table

    return success(
        data={
            "period": period,
            "overview": {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "tool_messages": tool_messages,
                "active_users": active_users,
            },
            "tokens": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "performance": {
                "avg_response_time_ms": round(avg_response_time, 2)
                if avg_response_time
                else 0,
            },
            "tools": {
                "tool_call_count": tool_call_count,
            },
        }
    )


@router.get("/{agent_id}/stats/trends")
async def get_agent_trends(
    agent_id: UUID,
    period: str = Query("7d", description="Time period: 24h, 7d, 30d"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get agent statistics trends for charting.
    """
    agent = await Agent.filter(id=agent_id).first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    now_local = now()

    # Determine granularity and range based on period
    if period == "24h":
        start_time = now_local - timedelta(hours=24)
        granularity = "hour"
        num_points = 24
    elif period == "7d":
        start_time = now_local - timedelta(days=7)
        granularity = "day"
        num_points = 7
    else:  # 30d
        start_time = now_local - timedelta(days=30)
        granularity = "day"
        num_points = 30

    start_time_utc = to_utc(start_time)

    # Get all conversations and messages in the period
    conversations = await Conversation.filter(
        agent_id=agent_id, created_at__gte=start_time_utc
    ).values("id", "created_at")

    messages = await Message.filter(
        conversation__agent_id=agent_id,
        created_at__gte=start_time_utc,
        role=MessageRole.ASSISTANT,
    ).values("created_at", "token_usage", "duration_ms")

    # Build time series data
    if granularity == "hour":
        # Group by hour
        data_points = []
        for i in range(num_points):
            point_start = now_local - timedelta(hours=num_points - i)
            point_end = now_local - timedelta(hours=num_points - i - 1)

            conv_count = sum(
                1
                for c in conversations
                if point_start <= to_local(c["created_at"]) < point_end
            )

            msgs_in_period = [
                m
                for m in messages
                if point_start <= to_local(m["created_at"]) < point_end
            ]
            msg_count = len(msgs_in_period)

            tokens = sum(
                (m["token_usage"].get("prompt", 0) or 0)
                + (m["token_usage"].get("completion", 0) or 0)
                for m in msgs_in_period
                if m["token_usage"]
            )

            durations = [m["duration_ms"] for m in msgs_in_period if m["duration_ms"]]
            avg_duration = sum(durations) / len(durations) if durations else 0

            data_points.append(
                {
                    "timestamp": point_start.isoformat(),
                    "label": point_start.strftime("%H:00"),
                    "conversations": conv_count,
                    "messages": msg_count,
                    "tokens": tokens,
                    "avg_response_time_ms": round(avg_duration, 2),
                }
            )
    else:
        # Group by day
        data_points = []
        for i in range(num_points):
            point_date = (now_local - timedelta(days=num_points - i - 1)).date()
            point_start = datetime.combine(point_date, datetime.min.time()).replace(
                tzinfo=now_local.tzinfo
            )
            point_end = point_start + timedelta(days=1)

            conv_count = sum(
                1
                for c in conversations
                if point_start <= to_local(c["created_at"]) < point_end
            )

            msgs_in_period = [
                m
                for m in messages
                if point_start <= to_local(m["created_at"]) < point_end
            ]
            msg_count = len(msgs_in_period)

            tokens = sum(
                (m["token_usage"].get("prompt", 0) or 0)
                + (m["token_usage"].get("completion", 0) or 0)
                for m in msgs_in_period
                if m["token_usage"]
            )

            durations = [m["duration_ms"] for m in msgs_in_period if m["duration_ms"]]
            avg_duration = sum(durations) / len(durations) if durations else 0

            data_points.append(
                {
                    "timestamp": point_start.isoformat(),
                    "label": point_date.strftime("%m/%d"),
                    "conversations": conv_count,
                    "messages": msg_count,
                    "tokens": tokens,
                    "avg_response_time_ms": round(avg_duration, 2),
                }
            )

    return success(
        data={
            "period": period,
            "granularity": granularity,
            "data": data_points,
        }
    )


@router.get("/{agent_id}/stats/tool-usage")
async def get_agent_tool_usage(
    agent_id: UUID,
    period: str = Query("7d", description="Time period: 24h, 7d, 30d, all"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get tool usage statistics for the agent.
    """
    agent = await Agent.filter(id=agent_id).first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    now_local = now()
    if period == "24h":
        start_time = now_local - timedelta(hours=24)
    elif period == "7d":
        start_time = now_local - timedelta(days=7)
    elif period == "30d":
        start_time = now_local - timedelta(days=30)
    else:
        start_time = None

    # Query messages with tool calls
    query = Message.filter(
        conversation__agent_id=agent_id,
        role=MessageRole.ASSISTANT,
        tool_calls__isnull=False,
    )
    if start_time:
        query = query.filter(created_at__gte=start_time)

    messages = await query.values("tool_calls")

    # Aggregate tool usage
    tool_stats: dict[str, int] = {}
    for msg in messages:
        if msg["tool_calls"]:
            for tool_call in msg["tool_calls"]:
                # Handle different possible structures
                tool_name = None
                if isinstance(tool_call, dict):
                    # Standard format: { function: { name: "xxx" } }
                    if "function" in tool_call and isinstance(
                        tool_call["function"], dict
                    ):
                        tool_name = tool_call["function"].get("name")
                    # Alternative format: { name: "xxx" }
                    elif "name" in tool_call:
                        tool_name = tool_call.get("name")

                if tool_name:
                    tool_stats[tool_name] = tool_stats.get(tool_name, 0) + 1

    # Sort by count descending
    tool_items: list[dict[str, int | str]] = [
        {"name": k, "count": v} for k, v in tool_stats.items()
    ]
    sorted_tools = sorted(
        tool_items,
        key=lambda x: int(x["count"]),
        reverse=True,
    )

    return success(
        data={
            "period": period,
            "tools": sorted_tools,
            "total_calls": sum(t["count"] for t in sorted_tools),
        }
    )


@router.get("/{agent_id}/stats/recent-conversations")
async def get_recent_conversations(
    agent_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get recent conversations for the agent.
    """
    agent = await Agent.filter(id=agent_id).first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    conversations = (
        await Conversation.filter(agent_id=agent_id)
        .order_by("-updated_at")
        .limit(limit)
        .prefetch_related("user")
    )

    result = []
    for conv in conversations:
        result.append(
            {
                "id": str(conv.id),
                "title": conv.title,
                "user": {
                    "id": str(conv.user.id),
                    "username": conv.user.username,
                }
                if conv.user
                else None,
                "message_count": conv.message_count,
                "token_usage": conv.token_usage,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
            }
        )

    return success(data=result)
