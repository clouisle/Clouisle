"""
Agent statistics and monitoring API endpoints.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.api.v1.endpoints.agents import check_agent_access
from app.api.v1.endpoints.chat import get_tool_display_names
from app.core.config import settings
from app.core.i18n import resolve_language
from app.models.agent import Conversation
from app.models.user import User
from app.schemas.response import success
from app.services import stats_sql
from app.core.timezone import now, to_utc

router = APIRouter()


def _resolve_tool_display_name(name: str, display_names: dict[str, str]) -> str:
    """Resolve one observed tool name to a human-readable label.

    Exact keys cover builtin, memory, asset, custom and skill tools. MCP tools
    are only known by their server prefix when enumeration is disabled, so a
    prefix match renders "<server>/<tool>" without contacting the server.
    Unknown names — for example a tool the agent no longer has configured —
    fall back to the raw identifier rather than disappearing.
    """
    if name in display_names:
        return display_names[name]
    for key, label in display_names.items():
        if key.endswith("_") and name.startswith(key):
            return f"{label}{name[len(key) :]}"
    return name


@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: UUID,
    period: str = Query("7d", description="Time period: 24h, 7d, 30d, all"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get agent statistics overview.
    """
    await check_agent_access(agent_id, current_user)

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

    # Both helpers aggregate in the database; the previous implementation ran
    # six counts and pulled every token_usage / tool_calls JSON payload plus
    # every user_id into Python. The five aggregations are independent, so they
    # run concurrently rather than as five sequential round trips.
    (
        conversations,
        messages,
        health,
        latency,
        interventions,
    ) = await asyncio.gather(
        stats_sql.agent_conversation_overview(agent_id, start_time),
        stats_sql.agent_message_overview(agent_id, start_time),
        stats_sql.agent_run_health(agent_id, start_time),
        stats_sql.agent_latency_percentiles(agent_id, start_time),
        stats_sql.agent_intervention_counts(agent_id, start_time),
    )

    total_conversations = conversations["total_conversations"]
    active_users = conversations["active_users"]
    user_messages = messages["user_messages"]
    assistant_messages = messages["assistant_messages"]
    tool_messages = messages["tool_messages"]
    total_messages = user_messages + assistant_messages + tool_messages
    prompt_tokens = messages["prompt_tokens"]
    completion_tokens = messages["completion_tokens"]
    avg_response_time = messages["avg_duration"]
    tool_call_count = messages["tool_call_count"]

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
                "first_token_ms": {
                    "p50": round(latency["p50"], 2),
                    "p95": round(latency["p95"], 2),
                    "avg": round(latency["avg"], 2),
                    "samples": latency["samples"],
                },
            },
            "tools": {
                "tool_call_count": tool_call_count,
            },
            "health": health,
            "interventions": interventions,
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
    await check_agent_access(agent_id, current_user)

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

    # Bucket in the database on local-time boundaries. The previous loop
    # rescanned every loaded row once per point (O(points x rows)).
    buckets = await stats_sql.agent_trend_buckets(
        agent_id, start_time_utc, granularity, settings.TIMEZONE
    )

    data_points = []
    for i in range(num_points):
        if granularity == "hour":
            point_start = now_local.replace(
                minute=0, second=0, microsecond=0
            ) - timedelta(hours=num_points - 1 - i)
            label = point_start.strftime("%H:00")
        else:
            point_date = (now_local - timedelta(days=num_points - i - 1)).date()
            point_start = datetime.combine(point_date, datetime.min.time()).replace(
                tzinfo=now_local.tzinfo
            )
            label = point_date.strftime("%m/%d")

        bucket = buckets.get(point_start.replace(tzinfo=None), {})
        data_points.append(
            {
                "timestamp": point_start.isoformat(),
                "label": label,
                "conversations": bucket.get("conversations", 0),
                "messages": bucket.get("messages", 0),
                "tokens": bucket.get("tokens", 0),
                "avg_response_time_ms": round(bucket.get("avg_duration", 0), 2),
                # None on an unmeasured bucket so the latency line breaks
                # rather than dipping to zero.
                "first_token_p50_ms": bucket.get("ttft_p50"),
                "first_token_p95_ms": bucket.get("ttft_p95"),
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
    agent = await check_agent_access(agent_id, current_user)

    now_local = now()
    if period == "24h":
        start_time = now_local - timedelta(hours=24)
    elif period == "7d":
        start_time = now_local - timedelta(days=7)
    elif period == "30d":
        start_time = now_local - timedelta(days=30)
    else:
        start_time = None

    # Aggregate tool names in the database, preserving the two accepted
    # payload shapes and the count-descending ordering.
    rows = await stats_sql.agent_tool_usage(agent_id, start_time)

    # Raw tool names are internal identifiers ("web_search"); the chat UI
    # renders localized labels, so resolve the same mapping here to stay
    # consistent. MCP enumeration is disabled because it performs an untimed
    # network call that must not run on a statistics request.
    locale = await resolve_language(getattr(current_user, "locale", None))
    display_names = await get_tool_display_names(
        agent, locale, enumerate_mcp_tools=False
    )

    sorted_tools: list[dict[str, int | str]] = [
        {
            "name": row["name"],
            "display_name": _resolve_tool_display_name(row["name"], display_names),
            "count": int(row["count"]),
        }
        for row in rows
    ]

    return success(
        data={
            "period": period,
            "tools": sorted_tools,
            "total_calls": sum(int(t["count"]) for t in sorted_tools),
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
    await check_agent_access(agent_id, current_user)

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
