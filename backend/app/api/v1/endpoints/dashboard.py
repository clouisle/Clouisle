"""
Dashboard statistics API endpoints for admin.
Provides system-wide statistics and metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.core.timezone import now, to_local, to_utc
from app.models.user import User, Team
from app.models.agent import Agent, Conversation, Message
from app.models.workflow import Workflow, WorkflowRun
from app.models.knowledge_base import KnowledgeBase
from app.models.model import Model
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
    now_local = now()
    today_start = datetime.combine(now_local.date(), datetime.min.time()).replace(tzinfo=now_local.tzinfo)
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
    now_local = now()

    # Determine time range
    if period == "7d":
        start_time = now_local - timedelta(days=7)
        num_points = 7
    else:  # Default to 30d
        start_time = now_local - timedelta(days=30)
        num_points = 30

    start_time_utc = to_utc(start_time)

    # Get all data in the period
    users = await User.filter(created_at__gte=start_time_utc).values("created_at")
    conversations = await Conversation.filter(created_at__gte=start_time_utc).values("created_at", "user_id")
    messages = await Message.filter(created_at__gte=start_time_utc).values("created_at", "token_usage")

    # Build time series data
    data_points = []
    for i in range(num_points):
        point_date = (now_local - timedelta(days=num_points - i - 1)).date()
        point_start = datetime.combine(point_date, datetime.min.time()).replace(tzinfo=now_local.tzinfo)
        point_end = point_start + timedelta(days=1)

        # New users
        new_users = sum(
            1
            for u in users
            if point_start <= to_local(u["created_at"]) < point_end
        )

        # Active users (users who created conversations)
        active_user_ids = set(
            c["user_id"] for c in conversations
            if point_start <= to_local(c["created_at"]) < point_end and c["user_id"]
        )
        active_users = len(active_user_ids)

        # New conversations
        new_conversations = sum(
            1
            for c in conversations
            if point_start <= to_local(c["created_at"]) < point_end
        )

        # Messages and tokens
        msgs_in_period = [
            m for m in messages
            if point_start <= to_local(m["created_at"]) < point_end
        ]
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


@router.get("/stats/agents/top", response_model=Response[list[dict]])
async def get_top_agents(
    limit: int = Query(10, ge=1, le=50, description="Number of top agents to return"),
    metric: str = Query("conversation_count", description="Metric to sort by: conversation_count, message_count, total_tokens"),
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get top agents by usage metrics (superuser only).

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

    # Build query
    query = Agent.all().prefetch_related("team")

    # Apply time range filter if not "all"
    if time_range != "all":
        now_local = now()
        if time_range == "7d":
            start_time = now_local - timedelta(days=7)
        elif time_range == "90d":
            start_time = now_local - timedelta(days=90)
        else:  # Default to 30d
            start_time = now_local - timedelta(days=30)

        start_time_utc = to_utc(start_time)
        # Note: For cumulative fields, we can't filter by time range directly
        # We'll use all-time data for now

    # Get agents sorted by metric
    agents = await query.order_by(f"-{metric}").limit(limit)

    # Build response
    result = []
    for agent in agents:
        value = getattr(agent, metric, 0)
        result.append({
            "agent_id": str(agent.id),
            "name": agent.name,
            "icon": agent.icon,
            "value": value,
            "team_name": agent.team.name if agent.team else "Unknown",
        })

    return success(data=result)


@router.get("/stats/teams/token-usage", response_model=Response[list[dict]])
async def get_team_token_usage(
    limit: int = Query(10, ge=1, le=50, description="Number of top teams to return"),
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get top teams by token usage (superuser only).

    Returns:
    - team_id: Team UUID
    - name: Team name
    - total_tokens: Total tokens consumed
    - conversations: Total conversations
    - messages: Total messages
    """
    # Build query
    query = Team.filter(is_deleted=False)

    # Get teams sorted by total_tokens
    teams = await query.order_by("-total_tokens").limit(limit)

    # Build response
    result = []
    for team in teams:
        result.append({
            "team_id": str(team.id),
            "name": team.name,
            "total_tokens": team.total_tokens,
            "conversations": team.total_conversations,
            "messages": team.total_messages,
        })

    return success(data=result)


@router.get("/stats/models/distribution", response_model=Response[list[dict]])
async def get_models_distribution(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get model usage distribution (superuser only).

    Returns:
    - model: Model identifier
    - count: Number of messages using this model
    - percentage: Percentage of total usage
    """
    # Calculate time range
    now_local = now()
    if time_range == "7d":
        start_time = now_local - timedelta(days=7)
    elif time_range == "90d":
        start_time = now_local - timedelta(days=90)
    elif time_range == "all":
        start_time = None
    else:  # Default to 30d
        start_time = now_local - timedelta(days=30)

    # Build query
    if start_time:
        start_time_utc = to_utc(start_time)
        messages_query = Message.filter(
            created_at__gte=start_time_utc,
            model_used__isnull=False
        )
    else:
        messages_query = Message.filter(model_used__isnull=False)

    # Get all messages with model_used
    messages = await messages_query.values("model_used")

    # Count model usage
    model_counts: dict[str, int] = {}
    total_count = 0
    for msg in messages:
        model = msg["model_used"]
        if model:
            model_counts[model] = model_counts.get(model, 0) + 1
            total_count += 1

    # Build response with percentages
    result = []
    for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_count * 100) if total_count > 0 else 0
        result.append({
            "model": model,
            "count": count,
            "percentage": round(percentage, 2),
        })

    return success(data=result)


@router.get("/stats/workflows/summary", response_model=Response[dict])
async def get_workflow_summary(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get workflow statistics summary (superuser only).

    Returns:
    - total_runs: Total workflow runs
    - success_rate: Overall success rate
    - avg_duration_ms: Average execution duration
    - trigger_type_distribution: Distribution by trigger type
    - status_distribution: Distribution by status
    - top_workflows: Top workflows by run count
    """
    # Calculate time range
    now_local = now()
    if time_range == "7d":
        start_time = now_local - timedelta(days=7)
    elif time_range == "90d":
        start_time = now_local - timedelta(days=90)
    elif time_range == "all":
        start_time = None
    else:  # Default to 30d
        start_time = now_local - timedelta(days=30)

    # Build query
    if start_time:
        start_time_utc = to_utc(start_time)
        runs_query = WorkflowRun.filter(created_at__gte=start_time_utc)
    else:
        runs_query = WorkflowRun.all()

    # Get all runs
    runs = await runs_query.all()

    # Calculate statistics
    total_runs = len(runs)
    success_count = sum(1 for r in runs if r.status == "success")
    success_rate = (success_count / total_runs * 100) if total_runs > 0 else 0

    # Average duration
    durations = [r.total_duration_ms for r in runs if r.total_duration_ms]
    avg_duration_ms = sum(durations) // len(durations) if durations else 0

    # Trigger type distribution
    trigger_types = {}
    for run in runs:
        trigger_type = run.trigger_type
        trigger_types[trigger_type] = trigger_types.get(trigger_type, 0) + 1

    # Status distribution
    statuses = {}
    for run in runs:
        status = run.status
        statuses[status] = statuses.get(status, 0) + 1

    # Top workflows
    workflow_stats = {}
    for run in runs:
        wf_id = str(run.workflow_id) if run.workflow_id else "unknown"
        if wf_id not in workflow_stats:
            workflow_stats[wf_id] = {"run_count": 0, "success_count": 0}
        workflow_stats[wf_id]["run_count"] += 1
        if run.status == "success":
            workflow_stats[wf_id]["success_count"] += 1

    # Get workflow details for top 10
    top_workflow_ids = sorted(workflow_stats.items(), key=lambda x: x[1]["run_count"], reverse=True)[:10]
    top_workflows = []
    for wf_id, stats in top_workflow_ids:
        if wf_id != "unknown":
            workflow = await Workflow.filter(id=wf_id).first()
            if workflow:
                success_rate_wf = (stats["success_count"] / stats["run_count"] * 100) if stats["run_count"] > 0 else 0
                top_workflows.append({
                    "workflow_id": wf_id,
                    "name": workflow.name,
                    "run_count": stats["run_count"],
                    "success_rate": round(success_rate_wf, 2),
                })

    return success(data={
        "total_runs": total_runs,
        "success_rate": round(success_rate, 2),
        "avg_duration_ms": avg_duration_ms,
        "trigger_type_distribution": [{"type": k, "count": v} for k, v in trigger_types.items()],
        "status_distribution": [{"status": k, "count": v} for k, v in statuses.items()],
        "top_workflows": top_workflows,
    })
