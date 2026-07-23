import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.tasks.session_memory import extract_session_memory_task


CONVERSATION_ID = "11111111-1111-1111-1111-111111111111"
MESSAGE_ID = "22222222-2222-2222-2222-222222222222"


@pytest.mark.parametrize("service_result", [{"memory": "likes tea"}, {}])
def test_extract_session_memory_task_returns_service_result(service_result):
    loop = asyncio.new_event_loop()
    service = AsyncMock(return_value=service_result)

    try:
        with (
            patch("asyncio.get_event_loop", return_value=loop),
            patch(
                "app.tasks.session_memory.extract_session_memory_for_message",
                service,
            ),
        ):
            result = extract_session_memory_task.run(CONVERSATION_ID, MESSAGE_ID)
    finally:
        loop.close()

    assert result == service_result
    service.assert_awaited_once_with(
        conversation_id=UUID(CONVERSATION_ID),
        source_message_id=UUID(MESSAGE_ID),
    )


def test_extract_session_memory_task_logs_and_reraises_failure():
    loop = asyncio.new_event_loop()
    service = AsyncMock(side_effect=RuntimeError("boom"))

    try:
        with (
            patch("asyncio.get_event_loop", return_value=loop),
            patch(
                "app.tasks.session_memory.extract_session_memory_for_message",
                service,
            ),
            patch("app.tasks.session_memory.logger.exception") as log_exception,
            pytest.raises(RuntimeError, match="boom"),
        ):
            extract_session_memory_task.run(CONVERSATION_ID, MESSAGE_ID)
    finally:
        loop.close()

    log_exception.assert_called_once_with(
        "Session memory extraction task failed for conversation %s message %s: %s",
        CONVERSATION_ID,
        MESSAGE_ID,
        service.side_effect,
    )


def test_extract_session_memory_task_creates_loop_when_none_exists():
    loop = asyncio.new_event_loop()
    service = AsyncMock(return_value={})

    try:
        with (
            patch("asyncio.get_event_loop", side_effect=RuntimeError),
            patch("asyncio.new_event_loop", return_value=loop) as new_event_loop,
            patch("asyncio.set_event_loop") as set_event_loop,
            patch(
                "app.tasks.session_memory.extract_session_memory_for_message",
                service,
            ),
        ):
            result = extract_session_memory_task.run(CONVERSATION_ID, MESSAGE_ID)
    finally:
        loop.close()

    assert result == {}
    new_event_loop.assert_called_once_with()
    set_event_loop.assert_called_once_with(loop)
