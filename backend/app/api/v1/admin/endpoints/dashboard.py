"""
Dashboard statistics API endpoints for admin.
Provides system-wide statistics and metrics.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from tortoise import Tortoise
from tortoise.functions import Count, Sum, Avg

from app.api.deps import PermissionChecker
from app.core.i18n import t
from app.core.timezone import now, to_local, to_utc
from app.models.user import User, Team
from app.models.agent import Agent, Conversation, Message
from app.models.model import TeamModel
from app.models.workflow import Workflow, WorkflowRun
from app.models.knowledge_base import KnowledgeBase
from app.schemas.response import Response, success

router = APIRouter()


def _time_bounds(
    time_range: str, start_time: str | None, end_time: str | None
) -> tuple[datetime | None, datetime | None]:
    """Resolve inclusive UTC bounds without discarding timestamp precision."""
    if time_range == "custom":
        if not start_time or not end_time:
            raise HTTPException(422, "Custom ranges require start_time and end_time")
        bounds = []
        for value in (start_time, end_time):
            fraction = re.search(r"[.,](\d+)", value)
            if fraction and len(fraction.group(1)) > 6:
                raise HTTPException(
                    422, "Timestamps support at most six fractional digits"
                )
            try:
                bound = datetime.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(422, "Invalid ISO timestamp") from exc
            if bound.tzinfo is None or bound.utcoffset() is None:
                raise HTTPException(422, "Timestamps must include a timezone")
            bounds.append(to_utc(bound))
        if bounds[0] >= bounds[1]:
            raise HTTPException(422, "start_time must precede end_time")
        return bounds[0], bounds[1]
    if start_time is not None or end_time is not None:
        raise HTTPException(422, "Explicit bounds require a custom range")
    if time_range == "all":
        return None, None
    days = {"7d": 7, "30d": 30, "90d": 90}.get(time_range, 30)
    end = now()
    return to_utc(end - timedelta(days=days)), to_utc(end)


async def _bounded_usage(
    owner: str, start_time: datetime, end_time: datetime
) -> dict[str, dict[str, int]]:
    """Aggregate event history separately to avoid multiplying joined rows."""
    if owner == "agent":
        owner_id = "c.agent_id"
        owner_join = ""
    elif owner == "team":
        owner_id = "a.team_id"
        owner_join = "JOIN agents a ON a.id = c.agent_id"
    else:
        raise ValueError("Unsupported usage owner")
    rows = await Tortoise.get_connection("default").execute_query_dict(
        f"""
        SELECT owner_id,
               SUM(conversation_count) AS conversation_count,
               SUM(message_count) AS message_count,
               SUM(total_tokens) AS total_tokens
        FROM (
            SELECT {owner_id} AS owner_id, COUNT(*) AS conversation_count,
                   0 AS message_count, 0 AS total_tokens
            FROM conversations c {owner_join}
            WHERE c.created_at >= $1 AND c.created_at <= $2
              AND {owner_id} IS NOT NULL
            GROUP BY {owner_id}
            UNION ALL
            SELECT {owner_id} AS owner_id, 0 AS conversation_count,
                   COUNT(*) AS message_count,
                   COALESCE(SUM(
                       CASE WHEN jsonb_typeof(m.token_usage -> 'prompt') = 'number'
                            THEN (m.token_usage ->> 'prompt')::bigint ELSE 0 END
                       + CASE WHEN jsonb_typeof(m.token_usage -> 'completion') = 'number'
                              THEN (m.token_usage ->> 'completion')::bigint ELSE 0 END
                   ), 0) AS total_tokens
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            {owner_join}
            WHERE m.created_at >= $1 AND m.created_at <= $2
              AND {owner_id} IS NOT NULL
            GROUP BY {owner_id}
        ) usage
        GROUP BY owner_id
        """,
        [start_time, end_time],
    )
    return {
        str(row["owner_id"]): {
            key: int(row[key] or 0)
            for key in ("conversation_count", "message_count", "total_tokens")
        }
        for row in rows
    }


@router.get("/stats", response_model=Response[dict])
async def get_dashboard_stats(
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    """
    Get system-wide dashboard statistics (requires dashboard:access permission).

    Returns:
    - Total users, teams, agents, workflows, knowledge bases
    - Total conversations, messages, tokens
    - Daily/Weekly/Monthly active users
    - Growth trends
    """
    now_local = now()
    today_start = datetime.combine(now_local.date(), datetime.min.time()).replace(
        tzinfo=now_local.tzinfo
    )
    week_start = now_local - timedelta(days=7)
    month_start = now_local - timedelta(days=30)

    # Basic counts
    total_users = await User.all().count()
    total_teams = await Team.all().count()
    total_agents = await Agent.all().count()
    total_workflows = await Workflow.all().count()
    total_knowledge_bases = await KnowledgeBase.all().count()
    total_conversations = await Conversation.all().count()
    total_messages = await Message.all().count()

    # Token usage - use pre-aggregated values from Team model
    token_result = (
        await Team.filter(is_deleted=False)
        .annotate(tokens_sum=Sum("total_tokens"))
        .values("tokens_sum")
    )
    total_tokens = token_result[0]["tokens_sum"] or 0 if token_result else 0

    # Active users (based on conversation activity)
    # DAU - Daily Active Users
    dau_user_ids = await Conversation.filter(created_at__gte=today_start).values_list(
        "user_id", flat=True
    )
    dau = len(set(dau_user_ids))

    # WAU - Weekly Active Users
    wau_user_ids = await Conversation.filter(created_at__gte=week_start).values_list(
        "user_id", flat=True
    )
    wau = len(set(wau_user_ids))

    # MAU - Monthly Active Users
    mau_user_ids = await Conversation.filter(created_at__gte=month_start).values_list(
        "user_id", flat=True
    )
    mau = len(set(mau_user_ids))

    # User growth (last 30 days)
    new_users_30d = await User.filter(created_at__gte=month_start).count()

    # Conversation growth (last 30 days)
    new_conversations_30d = await Conversation.filter(
        created_at__gte=month_start
    ).count()

    return success(
        data={
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
            },
        }
    )


@router.get("/stats/trends", response_model=Response[dict])
async def get_dashboard_trends(
    period: str = Query("30d", description="Time period: 7d, 30d, 90d, all, custom"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
) -> Any:
    """
    Get system-wide trends for dashboard charts (requires dashboard:access permission).

    Returns daily statistics for:
    - New users
    - Active users
    - New conversations
    - Messages
    - Token usage
    """
    start, end = _time_bounds(period, start_time, end_time)
    now_local = now()
    if period != "custom" and start is not None:
        days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
        first_date = now_local.date() - timedelta(days=days - 1)
        start = to_utc(
            datetime.combine(first_date, datetime.min.time(), now_local.tzinfo)
        )
    end = end or to_utc(now_local)
    filters = {"created_at__lte": end}
    if start is not None:
        filters["created_at__gte"] = start
    users = await User.filter(**filters).values("created_at")
    conversations = await Conversation.filter(**filters).values("created_at", "user_id")
    messages = await Message.filter(**filters).values("created_at", "token_usage")

    # Bucket each event once, retaining the configured server-day labels.
    buckets: dict[date, dict[str, Any]] = {}
    for kind, records in (
        ("new_users", users),
        ("new_conversations", conversations),
        ("messages", messages),
    ):
        for record in records:
            timestamp = record["created_at"]
            if (start is not None and timestamp < start) or timestamp > end:
                continue
            day = to_local(timestamp).date()
            bucket = buckets.setdefault(
                day,
                {
                    "new_users": 0,
                    "new_conversations": 0,
                    "messages": 0,
                    "tokens": 0,
                    "user_ids": set(),
                },
            )
            bucket[kind] += 1
            if kind == "new_conversations" and record["user_id"]:
                bucket["user_ids"].add(record["user_id"])
            elif kind == "messages":
                usage = record["token_usage"] or {}
                bucket["tokens"] += (usage.get("prompt", 0) or 0) + (
                    usage.get("completion", 0) or 0
                )

    first_date = (
        to_local(start).date() if start is not None else min(buckets, default=None)
    )
    last_date = to_local(end).date()
    data_points = []
    while first_date is not None and first_date <= last_date:
        bucket = buckets.get(first_date, {})
        data_points.append(
            {
                "date": first_date.strftime("%m/%d"),
                "new_users": bucket.get("new_users", 0),
                "active_users": len(bucket.get("user_ids", ())),
                "new_conversations": bucket.get("new_conversations", 0),
                "messages": bucket.get("messages", 0),
                "tokens": bucket.get("tokens", 0),
            }
        )
        first_date += timedelta(days=1)

    return success(
        data={
            "period": period,
            "data": data_points,
        }
    )


@router.get("/stats/agents/top", response_model=Response[list[dict]])
async def get_top_agents(
    limit: int = Query(10, ge=1, le=50, description="Number of top agents to return"),
    metric: str = Query(
        "conversation_count",
        description="Metric to sort by: conversation_count, message_count, total_tokens",
    ),
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all, custom"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
) -> Any:
    """
    Get top agents by usage metrics (requires dashboard:access permission).

    Returns:
    - agent_id: Agent UUID
    - name: Agent name
    - icon: Agent icon
    - value: Metric value
    - team_name: Team name
    """
    # Validate metric parameter
    valid_metrics = ["conversation_count", "message_count", "total_tokens"]
    if metric not in valid_metrics:
        metric = "conversation_count"

    start, end = _time_bounds(time_range, start_time, end_time)
    query = Agent.all().prefetch_related("team")
    usage = None
    if start is not None and end is not None:
        usage = await _bounded_usage("agent", start, end)
        agents = sorted(
            await query,
            key=lambda agent: usage.get(str(agent.id), {}).get(metric, 0),
            reverse=True,
        )[:limit]
    else:
        agents = await query.order_by(f"-{metric}").limit(limit)

    # Build response
    result = []
    for agent in agents:
        value = (
            usage.get(str(agent.id), {}).get(metric, 0)
            if usage is not None
            else getattr(agent, metric, 0)
        )
        result.append(
            {
                "agent_id": str(agent.id),
                "name": agent.name,
                "icon": agent.icon,
                "value": value,
                "team_name": agent.team.name if agent.team else t("unknown"),
            }
        )

    return success(data=result)


@router.get("/stats/teams/token-usage", response_model=Response[list[dict]])
async def get_team_token_usage(
    limit: int = Query(10, ge=1, le=50, description="Number of top teams to return"),
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all, custom"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
) -> Any:
    """
    Get top teams by token usage (requires dashboard:access permission).

    Returns:
    - team_id: Team UUID
    - name: Team name
    - total_tokens: Total tokens consumed
    - conversations: Total conversations
    - messages: Total messages
    """
    start, end = _time_bounds(time_range, start_time, end_time)
    query = Team.filter(is_deleted=False)
    usage = None
    if start is not None and end is not None:
        usage = await _bounded_usage("team", start, end)
        teams = sorted(
            await query,
            key=lambda team: usage.get(str(team.id), {}).get("total_tokens", 0),
            reverse=True,
        )[:limit]
    else:
        teams = await query.order_by("-total_tokens").limit(limit)

    # Build response
    result = []
    for team in teams:
        team_usage = usage.get(str(team.id), {}) if usage is not None else None
        result.append(
            {
                "team_id": str(team.id),
                "name": team.name,
                "total_tokens": (
                    team_usage.get("total_tokens", 0)
                    if team_usage is not None
                    else team.total_tokens
                ),
                "conversations": (
                    team_usage.get("conversation_count", 0)
                    if team_usage is not None
                    else team.total_conversations
                ),
                "messages": (
                    team_usage.get("message_count", 0)
                    if team_usage is not None
                    else team.total_messages
                ),
            }
        )

    return success(data=result)


@router.get("/stats/models/distribution", response_model=Response[list[dict]])
async def get_models_distribution(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all, custom"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
) -> Any:
    """
    Get model usage distribution (requires dashboard:access permission).

    Returns:
    - model: Model identifier
    - count: Number of tracked model requests
    - percentage: Percentage of total usage
    """
    start, end = _time_bounds(time_range, start_time, end_time)
    now_local = now()
    if time_range not in {"7d", "30d", "90d", "all", "custom"}:
        time_range = "30d"
    filters: dict[str, Any] = {"model_used__isnull": False}
    if start is not None:
        filters.update(created_at__gte=start, created_at__lte=end)
    messages_query = Message.filter(**filters)

    # Messages provide exact historical attribution for agent conversations.
    message_stats = (
        await messages_query.annotate(count=Count("id"))
        .group_by("model_used")
        .values("model_used", "count")
    )
    counts_by_model = {
        str(item["model_used"]): int(item["count"]) for item in message_stats
    }

    # Daily/monthly counters cover only the current day/month. Use them for
    # the matching short windows, while longer ranges rely on event history.
    tracked_counts: dict[str, int] = {}
    if time_range in {"7d", "30d"}:
        if time_range == "7d":
            usage_field = "daily_requests_used"
            reset_field = "daily_reset_at"
            counter_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            usage_field = "monthly_requests_used"
            reset_field = "monthly_reset_at"
            counter_start = now_local.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

        usage_filters: dict[str, Any] = {
            f"{usage_field}__gt": 0,
            f"{reset_field}__gte": to_utc(counter_start),
        }
        team_models = await TeamModel.filter(**usage_filters).prefetch_related("model")
        for team_model in team_models:
            model_id = team_model.model.model_id
            tracked_counts[model_id] = tracked_counts.get(model_id, 0) + int(
                getattr(team_model, usage_field)
            )

        for model_id, tracked_count in tracked_counts.items():
            counts_by_model[model_id] = max(
                counts_by_model.get(model_id, 0), tracked_count
            )

    model_stats = [
        {"model_used": model_id, "count": count}
        for model_id, count in counts_by_model.items()
    ]

    # Calculate total and build response
    total_count = sum(item["count"] for item in model_stats)
    result = []
    for item in sorted(model_stats, key=lambda x: x["count"], reverse=True):
        model = item["model_used"]
        count = item["count"]
        percentage = (count / total_count * 100) if total_count > 0 else 0
        result.append(
            {
                "model": model,
                "count": count,
                "percentage": round(percentage, 2),
            }
        )

    return success(data=result)


@router.get("/stats/workflows/summary", response_model=Response[dict])
async def get_workflow_summary(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all, custom"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
) -> Any:
    """
    Get workflow statistics summary (requires dashboard:access permission).

    Returns:
    - total_runs: Total workflow runs
    - success_rate: Overall success rate
    - avg_duration_ms: Average execution duration
    - trigger_type_distribution: Distribution by trigger type
    - status_distribution: Distribution by status
    - top_workflows: Top workflows by run count
    """
    start, end = _time_bounds(time_range, start_time, end_time)
    if start is not None:
        runs_query = WorkflowRun.filter(created_at__gte=start, created_at__lte=end)
    else:
        runs_query = WorkflowRun.all()

    # Use database-level aggregation for basic stats
    total_runs = await runs_query.count()
    success_count = await runs_query.filter(status="success").count()
    success_rate = (success_count / total_runs * 100) if total_runs > 0 else 0

    # Average duration using database aggregation
    avg_result = (
        await runs_query.filter(total_duration_ms__isnull=False)
        .annotate(avg_dur=Avg("total_duration_ms"))
        .values("avg_dur")
    )
    avg_duration_ms = int(avg_result[0]["avg_dur"] or 0) if avg_result else 0

    # Trigger type distribution using GROUP BY
    trigger_stats = (
        await runs_query.annotate(count=Count("id"))
        .group_by("trigger_type")
        .values("trigger_type", "count")
    )

    # Status distribution using GROUP BY
    status_stats = (
        await runs_query.annotate(count=Count("id"))
        .group_by("status")
        .values("status", "count")
    )

    # Top workflows using GROUP BY
    workflow_run_stats = (
        await runs_query.filter(workflow_id__isnull=False)
        .annotate(run_count=Count("id"))
        .group_by("workflow_id")
        .order_by("-run_count")
        .limit(10)
        .values("workflow_id", "run_count")
    )

    # Get workflow details and success counts for top workflows
    top_workflows = []
    if workflow_run_stats:
        workflow_ids = [stat["workflow_id"] for stat in workflow_run_stats]

        # Fetch all workflows in one query
        workflows = await Workflow.filter(id__in=workflow_ids).all()
        workflow_map = {wf.id: wf for wf in workflows}

        # Fetch success counts for all workflows in one query
        success_counts = (
            await runs_query.filter(workflow_id__in=workflow_ids, status="success")
            .annotate(success_count=Count("id"))
            .group_by("workflow_id")
            .values("workflow_id", "success_count")
        )
        success_map = {
            item["workflow_id"]: item["success_count"] for item in success_counts
        }

        for stat in workflow_run_stats:
            wf_id = stat["workflow_id"]
            run_count = stat["run_count"]
            workflow = workflow_map.get(wf_id)
            if workflow:
                wf_success_count = success_map.get(wf_id, 0)
                success_rate_wf = (
                    (wf_success_count / run_count * 100) if run_count > 0 else 0
                )
                top_workflows.append(
                    {
                        "workflow_id": str(wf_id),
                        "name": workflow.name,
                        "run_count": run_count,
                        "success_rate": round(success_rate_wf, 2),
                    }
                )

    return success(
        data={
            "total_runs": total_runs,
            "success_rate": round(success_rate, 2),
            "avg_duration_ms": avg_duration_ms,
            "trigger_type_distribution": [
                {"type": item["trigger_type"], "count": item["count"]}
                for item in trigger_stats
            ],
            "status_distribution": [
                {"status": item["status"], "count": item["count"]}
                for item in status_stats
            ],
            "top_workflows": top_workflows,
        }
    )
