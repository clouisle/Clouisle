"""
Embed API endpoints for external website integration.
Provides agent/workflow chat via API Key authentication for iframe embedding.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Header,
    UploadFile,
    File as FastAPIFile,
)
from fastapi.responses import StreamingResponse

from app.api import deps
from app.api.deps import _authenticate_api_key
from app.models.agent import Agent, AgentStatus, Conversation
from app.models.api_key import APIKey
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStatus
from app.schemas.agent import ChatRequest, EmbedAgentInfo
from app.api.v1.endpoints.chat import build_message_round_payloads
from app.schemas.response import BusinessError, ResponseCode, success
from app.services.message_branching import get_visible_conversation_messages
from app.services.audit_log import AuditLogService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Auth Dependency ============


async def get_embed_auth(
    token: Optional[str] = Query(None, description="API Key"),
    authorization: Optional[str] = Header(None),
) -> tuple[User, APIKey]:
    """
    Authenticate embed requests via API Key only.
    Accepts API Key from query param `token` or Authorization header.
    """
    api_key_str: str | None = None

    # Try query param first
    if token and token.startswith("clou_"):
        api_key_str = token
    # Then try Authorization header
    elif authorization:
        if authorization.startswith("Bearer "):
            bearer_token = authorization[7:]
            if bearer_token.startswith("clou_"):
                api_key_str = bearer_token

    if not api_key_str:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="embed_api_key_required",
            status_code=401,
        )

    return await _authenticate_api_key(api_key_str)


# ============ Helpers ============


def _check_embed_enabled(target: Agent | Workflow) -> None:
    """Verify agent/workflow has embedding enabled."""
    embed_config = target.embed_config or {}
    if not embed_config.get("enabled", False):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="embed_not_enabled",
            status_code=403,
        )


def _parse_origin_host(value: str) -> tuple[str, int | None]:
    parsed = urlparse(value if "://" in value else f"//{value}")
    try:
        port = parsed.port
    except ValueError:
        return "", None
    if port is None and parsed.scheme == "https":
        port = 443
    elif port is None and parsed.scheme == "http":
        port = 80
    return (parsed.hostname or "").lower(), port


def _domain_matches(
    allowed_host: str,
    allowed_port: int | None,
    check_host: str,
    check_port: int | None,
) -> bool:
    if allowed_port is not None and allowed_port != check_port:
        return False
    if allowed_host.startswith("*."):
        base = allowed_host[2:]
        return check_host == base or check_host.endswith(f".{base}")
    return check_host == allowed_host


def _check_embed_domain(request: Request, target: Agent | Workflow) -> None:
    """Verify request origin is in allowed domains list (if configured)."""
    embed_config = target.embed_config or {}
    allowed_domains = embed_config.get("allowed_domains", [])
    if not allowed_domains:
        return  # No restriction

    source = request.headers.get("origin") or request.headers.get("referer") or ""
    check_host, check_port = _parse_origin_host(source)
    if not check_host:
        return  # No origin info, allow (could be direct access for testing)

    for domain in allowed_domains:
        allowed_host, allowed_port = _parse_origin_host(str(domain).strip().lower())
        if allowed_host and _domain_matches(
            allowed_host, allowed_port, check_host, check_port
        ):
            return

    raise BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="embed_domain_not_allowed",
        status_code=403,
    )


async def _get_embed_agent(agent_id: UUID, api_key: APIKey, request: Request) -> Agent:
    """Get agent with embed access checks."""
    # Check API key has access to this agent
    await deps.check_api_key_agent_access(api_key, agent_id)

    agent = (
        await Agent.filter(id=agent_id).prefetch_related("team", "created_by").first()
    )
    if not agent:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    # Must be published
    if agent.status != AgentStatus.PUBLISHED:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    _check_embed_enabled(agent)
    _check_embed_domain(request, agent)

    return agent


# ============ Agent Embed Endpoints ============


@router.get("/agents/{agent_id}/info")
async def get_embed_agent_info(
    agent_id: UUID,
    request: Request,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
):
    """Get agent info for embed page."""
    user, api_key = auth_result
    agent = await _get_embed_agent(agent_id, api_key, request)

    return success(
        data=EmbedAgentInfo(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            icon=agent.icon,
            avatar_url=agent.avatar_url,
            opening_message=agent.opening_message,
            suggested_questions=agent.suggested_questions or [],
            variables=agent.variables or [],
            enable_vision=agent.enable_vision,
            enable_file_upload=agent.enable_file_upload,
            file_upload_config=agent.file_upload_config or None,
            hide_tool_calls=agent.hide_tool_calls,
            embed_config=agent.embed_config or {},
        ),
    )


@router.post("/agents/{agent_id}/chat/stream")
async def embed_chat_stream(
    agent_id: UUID,
    chat_in: ChatRequest,
    request: Request,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
) -> StreamingResponse:
    """
    Chat with an agent via embed (streaming SSE).
    Reuses the same streaming logic as the main chat endpoint.
    """
    user, api_key = auth_result
    await _get_embed_agent(agent_id, api_key, request)

    # Delegate to the original chat_stream endpoint (it handles conversation creation)
    from app.api.v1.endpoints.chat import (
        chat_stream as _original_chat_stream,
    )

    return await _original_chat_stream(
        agent_id=agent_id,
        chat_in=chat_in,
        request=request,
        auth_result=(user, api_key),
    )


@router.get("/agents/{agent_id}/conversations/{conversation_id}/messages")
async def get_embed_conversation_messages(
    agent_id: UUID,
    conversation_id: UUID,
    request: Request,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
):
    """Get conversation messages for embed page."""
    user, api_key = auth_result
    agent = await _get_embed_agent(agent_id, api_key, request)

    conversation = await Conversation.filter(
        id=conversation_id,
        agent_id=agent.id,
        user=user,
    ).first()

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    messages = await get_visible_conversation_messages(conversation.id)

    return success(
        data=await build_message_round_payloads(messages),
    )


@router.post("/agents/{agent_id}/upload/file")
async def embed_upload_file(
    agent_id: UUID,
    request: Request,
    file: UploadFile = FastAPIFile(...),
    category: str = Query("documents"),
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
):
    """Upload a file for embed chat (document attachments)."""
    user, api_key = auth_result
    await _get_embed_agent(agent_id, api_key, request)

    # Delegate to the upload endpoint logic
    from app.api.v1.endpoints.upload import upload_file as _upload_file

    return await _upload_file(file=file, category=category, current_user=user)


# ============ Workflow Embed Helpers ============


async def _get_embed_workflow(
    workflow_id: UUID, api_key: APIKey, request: Request
) -> Workflow:
    """Get workflow with embed access checks."""
    await deps.check_api_key_workflow_access(api_key, workflow_id)

    workflow = (
        await Workflow.filter(id=workflow_id)
        .prefetch_related("team", "created_by")
        .first()
    )
    if not workflow:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    if workflow.status != WorkflowStatus.PUBLISHED:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    _check_embed_enabled(workflow)
    _check_embed_domain(request, workflow)

    return workflow


# ============ Workflow Embed Endpoints ============


@router.get("/workflows/{workflow_id}/info")
async def get_embed_workflow_info(
    workflow_id: UUID,
    request: Request,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
):
    """Get workflow info for embed page."""
    user, api_key = auth_result
    workflow = await _get_embed_workflow(workflow_id, api_key, request)

    return success(
        data={
            "id": str(workflow.id),
            "name": workflow.name,
            "description": workflow.description,
            "icon": workflow.icon,
            "variables": workflow.variables or [],
            "embed_config": workflow.embed_config or {},
        },
    )


@router.post("/workflows/{workflow_id}/run")
async def embed_run_workflow(
    workflow_id: UUID,
    request: Request,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
):
    """
    Run a workflow via embed.
    Returns run_id and stream_url for SSE streaming.
    """
    from app.models.workflow import RunStatus, WorkflowRun
    from app.tasks.workflow import run_workflow_task

    user, api_key = auth_result
    workflow = await _get_embed_workflow(workflow_id, api_key, request)

    body = await request.json()
    inputs = body.get("inputs", {})

    run = await WorkflowRun.create(
        workflow_id=workflow_id,
        trigger_type=workflow.trigger_type,
        triggered_by_id=user.id,
        is_debug=False,
        status=RunStatus.PENDING,
        inputs=inputs,
    )

    run_workflow_task.delay(
        run_id=str(run.id),
        workflow_id=str(workflow_id),
        inputs=inputs,
        user_id=str(user.id),
        team_id=str(workflow.team_id) if workflow.team_id else None,
    )

    await AuditLogService.log(
        user=user,
        action="run_workflow_embed",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="execute",
        status="success",
        request=request,
        api_key=api_key,
        metadata={
            "run_id": str(run.id),
            "source": "embed",
        },
    )

    return success(
        data={
            "run_id": str(run.id),
            "stream_url": f"/api/v1/workflows/runs/{run.id}/stream",
        },
    )


@router.get("/workflows/runs/{run_id}/stream")
async def embed_stream_workflow_run(
    run_id: UUID,
    from_sequence: int = 0,
    auth_result: tuple[User, APIKey] = Depends(get_embed_auth),
) -> StreamingResponse:
    """Stream workflow execution events via SSE for embed context."""
    from app.models.workflow import WorkflowRun
    from app.services.workflow.stream import stream_to_sse

    user, api_key = auth_result

    run = await WorkflowRun.filter(id=run_id).first()
    if not run or run.triggered_by_id != user.id:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    async def event_generator():
        async for event in stream_to_sse(str(run_id), from_sequence):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
