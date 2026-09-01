from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.models.agent_run import AgentRunMode, AgentRunStatus
from app.schemas.agent import ChatRequest, RunStartOut
from app.schemas.response import BusinessError, ResponseCode


def _started() -> dict:
    return {
        "data": RunStartOut(
            run_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            status="queued",
            stream_url="/agents/run/chat/runs/run/stream",
        )
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_code", "expected_status"),
    [
        ("model_quota_exceeded", ResponseCode.MODEL_QUOTA_EXCEEDED, 429),
        ("provider_error", ResponseCode.UNKNOWN_ERROR, 500),
    ],
)
async def test_chat_maps_worker_failures_to_business_error(
    monkeypatch, error_code, expected_code, expected_status
):
    """Non-stream chat adapts durable worker terminal status to API errors."""
    started = _started()
    run = SimpleNamespace(
        id=started["data"].run_id,
        status=AgentRunStatus.FAILED,
        error_code=error_code,
        canonical_message_id=None,
    )
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    monkeypatch.setattr(chat_endpoint, "_enqueue_durable_chat_run", enqueue)
    monkeypatch.setattr(chat_endpoint, "_wait_for_agent_run", wait)

    with pytest.raises(BusinessError) as exc_info:
        await chat_endpoint.chat(
            uuid4(),
            ChatRequest(message="hello"),
            (SimpleNamespace(id=uuid4(), is_active=True), None),
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.NON_STREAM
    wait.assert_awaited_once_with(started["data"].run_id)


@pytest.mark.asyncio
async def test_chat_inactive_user_exits_before_api_key_access(monkeypatch):
    """Inactive users are rejected before durable-run setup or access checks."""
    api_key_check = AsyncMock()
    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", api_key_check)
    inactive = SimpleNamespace(id=uuid4(), is_active=False)

    with pytest.raises(BusinessError) as exc_info:
        await chat_endpoint.chat(
            uuid4(), ChatRequest(message="hello"), (inactive, None)
        )

    assert exc_info.value.code == ResponseCode.INACTIVE_USER
    assert api_key_check.await_count == 0
