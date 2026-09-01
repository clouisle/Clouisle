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
        ("InsufficientQuotaError", ResponseCode.MODEL_QUOTA_EXCEEDED, 429),
        ("provider_error", ResponseCode.UNKNOWN_ERROR, 500),
    ],
)
async def test_chat_maps_worker_failure_to_business_error(
    monkeypatch, error_code, expected_code, expected_status
):
    """The non-stream adapter maps durable worker failure metadata."""
    agent_id = uuid4()
    user_id = uuid4()
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
            agent_id,
            ChatRequest(message="hello"),
            (SimpleNamespace(id=user_id, is_active=True), None),
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.NON_STREAM
    wait.assert_awaited_once_with(started["data"].run_id)
