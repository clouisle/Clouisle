from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import QuotaExceededError
from app.schemas.agent import ChatRequest


@pytest.mark.anyio
async def test_stream_outer_setup_exception_propagates_before_subscribing(monkeypatch):
    """Streaming chat raises enqueue/setup failures instead of emitting SSE.

    The durable-run entry point enqueues before subscribing; a setup failure
    therefore surfaces as an exception from chat_stream, never as an error
    event from a subscribed stream.
    """
    start_run = AsyncMock(side_effect=QuotaExceededError(quota_type="daily"))
    monkeypatch.setattr(chat, "start_chat_run", start_run)

    with pytest.raises(QuotaExceededError):
        await chat.chat_stream(
            uuid4(),
            ChatRequest(message="hello"),
            SimpleNamespace(),
            (SimpleNamespace(id=uuid4()), None),
        )

    start_run.assert_awaited_once()
