from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.workflow.executor import ExecutionResult
from app.services.workflow.retry import RetryableExecutor, RetryPolicy


@pytest.mark.asyncio
async def test_failed_result_retries_then_returns_recovery(monkeypatch):
    executor = MagicMock(node_type="http_request")
    executor.execute = AsyncMock(
        side_effect=[
            ExecutionResult(error="upstream unavailable"),
            ExecutionResult(outputs={"status": 200}),
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.workflow.retry.asyncio.sleep", sleep)
    retryable = RetryableExecutor(
        executor, RetryPolicy(max_retries=1, base_delay=0.25, jitter=False)
    )

    result = await retryable.execute({}, MagicMock(), MagicMock())

    assert result.outputs == {"status": 200}
    assert retryable.attempts == 2
    assert retryable.last_error == "upstream unavailable"
    sleep.assert_awaited_once_with(0.25)


@pytest.mark.asyncio
async def test_terminal_failed_result_is_returned_without_extra_delay(monkeypatch):
    failure = ExecutionResult(error="bad gateway")
    executor = MagicMock(node_type="http_request")
    executor.execute = AsyncMock(return_value=failure)
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.workflow.retry.asyncio.sleep", sleep)
    retryable = RetryableExecutor(executor, RetryPolicy(max_retries=0))

    assert await retryable.execute({}, MagicMock(), MagicMock()) is failure
    assert retryable.attempts == 1
    assert retryable.last_error is None
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_result_exhaustion_returns_final_failure(monkeypatch):
    final_failure = ExecutionResult(error="still unavailable")
    executor = MagicMock(node_type="tool")
    executor.execute = AsyncMock(
        side_effect=[ExecutionResult(error="temporary failure"), final_failure]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.workflow.retry.asyncio.sleep", sleep)
    retryable = RetryableExecutor(
        executor, RetryPolicy(max_retries=1, base_delay=0.5, jitter=False)
    )

    assert await retryable.execute({}, MagicMock(), MagicMock()) is final_failure
    assert retryable.attempts == 2
    assert retryable.last_error == "temporary failure"
    sleep.assert_awaited_once_with(0.5)
