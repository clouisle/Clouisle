"""
Tests for the retry mechanism.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

from app.services.workflow.retry import (
    RetryPolicy,
    with_retry,
    retryable,
    RetryableExecutor,
    CircuitBreaker,
    CircuitState,
    get_retry_policy,
    DEFAULT_POLICIES,
)
from app.services.workflow.executor import NodeExecutor, ExecutionResult


class TestRetryPolicy:
    """Tests for RetryPolicy configuration."""

    def test_default_policy(self):
        """Test default retry policy values."""
        policy = RetryPolicy()

        assert policy.max_retries == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 30.0
        assert policy.exponential_base == 2.0
        assert policy.jitter is True
        assert policy.retryable_errors is None

    def test_custom_policy(self):
        """Test custom retry policy values."""
        policy = RetryPolicy(
            max_retries=5,
            base_delay=0.5,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False,
            retryable_errors=[TimeoutError, ConnectionError],
        )

        assert policy.max_retries == 5
        assert policy.base_delay == 0.5
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 3.0
        assert policy.jitter is False
        assert TimeoutError in policy.retryable_errors

    def test_get_delay_exponential(self):
        """Test exponential delay calculation."""
        policy = RetryPolicy(
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )

        assert policy.get_delay(0) == 1.0  # 1 * 2^0 = 1
        assert policy.get_delay(1) == 2.0  # 1 * 2^1 = 2
        assert policy.get_delay(2) == 4.0  # 1 * 2^2 = 4
        assert policy.get_delay(3) == 8.0  # 1 * 2^3 = 8

    def test_get_delay_max_cap(self):
        """Test delay is capped at max_delay."""
        policy = RetryPolicy(
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False,
        )

        # After a few retries, delay should be capped
        assert policy.get_delay(10) == 5.0

    def test_get_delay_with_jitter(self):
        """Test delay with jitter varies."""
        policy = RetryPolicy(
            base_delay=1.0,
            exponential_base=2.0,
            jitter=True,
        )

        # With jitter, delays should vary
        delays = [policy.get_delay(1) for _ in range(10)]
        # Not all delays should be exactly the same
        assert len(set(delays)) > 1

    def test_should_retry_no_errors(self):
        """Test should_retry with no specific error types."""
        policy = RetryPolicy()

        assert policy.should_retry(Exception("test")) is True
        assert policy.should_retry(ValueError("test")) is True
        assert policy.should_retry(TimeoutError("test")) is True

    def test_should_retry_specific_errors(self):
        """Test should_retry with specific error types."""
        policy = RetryPolicy(
            retryable_errors=[TimeoutError, ConnectionError],
        )

        assert policy.should_retry(TimeoutError("test")) is True
        assert policy.should_retry(ConnectionError("test")) is True
        assert policy.should_retry(ValueError("test")) is False


class TestWithRetry:
    """Tests for the with_retry function."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Test successful function doesn't retry."""
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        policy = RetryPolicy(max_retries=3)
        result = await with_retry(success_func, policy)

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """Test function retries then succeeds."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("temporary failure")
            return "success"

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        result = await with_retry(flaky_func, policy)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test function fails after max retries."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("always fails")

        policy = RetryPolicy(max_retries=3, base_delay=0.01)

        with pytest.raises(TimeoutError, match="always fails"):
            await with_retry(always_fail, policy)

        assert call_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        """Test non-retryable error doesn't retry."""
        call_count = 0

        async def fail_with_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("non-retryable")

        policy = RetryPolicy(
            max_retries=3,
            retryable_errors=[TimeoutError],
        )

        with pytest.raises(ValueError, match="non-retryable"):
            await with_retry(fail_with_value_error, policy)

        assert call_count == 1  # No retries


class TestRetryableDecorator:
    """Tests for the @retryable decorator."""

    @pytest.mark.asyncio
    async def test_decorator_success(self):
        """Test decorator with successful function."""
        call_count = 0

        @retryable(max_retries=3)
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await success_func()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_decorator_retry(self):
        """Test decorator retries on failure."""
        call_count = 0

        @retryable(max_retries=3, base_delay=0.01)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("temporary")
            return "success"

        result = await flaky_func()

        assert result == "success"
        assert call_count == 2


class TestRetryableExecutor:
    """Tests for RetryableExecutor wrapper."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor."""
        executor = MagicMock(spec=NodeExecutor)
        executor.node_type = "test"
        return executor

    @pytest.mark.asyncio
    async def test_success_no_retry(self, mock_executor):
        """Test successful execution doesn't retry."""
        mock_executor.execute = AsyncMock(
            return_value=ExecutionResult(success=True, outputs={"result": "ok"})
        )

        policy = RetryPolicy(max_retries=3)
        retryable_exec = RetryableExecutor(mock_executor, policy)

        result = await retryable_exec.execute(
            node={"id": "test"},
            context=MagicMock(),
            run=MagicMock(),
        )

        assert result.success is True
        assert mock_executor.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_exception(self, mock_executor):
        """Test executor retries on exception."""
        call_count = 0

        async def flaky_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("temporary")
            return ExecutionResult(success=True, outputs={})

        mock_executor.execute = flaky_execute

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        retryable_exec = RetryableExecutor(mock_executor, policy)

        result = await retryable_exec.execute(
            node={"id": "test"},
            context=MagicMock(),
            run=MagicMock(),
        )

        assert result.success is True
        assert call_count == 3


class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    @pytest.fixture
    def breaker(self):
        """Create a test circuit breaker."""
        return CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=0.1,
            half_open_requests=2,
        )

    @pytest.mark.asyncio
    async def test_initial_state_closed(self, breaker):
        """Test initial state is closed."""
        assert breaker.state == CircuitState.CLOSED
        assert await breaker.can_execute() is True

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self, breaker):
        """Test circuit opens after failure threshold."""
        for _ in range(3):
            await breaker.record_failure()

        assert breaker.state == CircuitState.OPEN
        assert await breaker.can_execute() is False

    @pytest.mark.asyncio
    async def test_success_resets_failures(self, breaker):
        """Test success resets failure count."""
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker._failure_count == 2

        await breaker.record_success()
        assert breaker._failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, breaker):
        """Test circuit goes to half-open after timeout."""
        # Open the circuit
        for _ in range(3):
            await breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should be half-open now
        assert await breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self, breaker):
        """Test enough successes in half-open closes circuit."""
        # Open and wait
        for _ in range(3):
            await breaker.record_failure()
        await asyncio.sleep(0.15)

        # Record successes in half-open
        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, breaker):
        """Test failure in half-open reopens circuit."""
        # Open and wait
        for _ in range(3):
            await breaker.record_failure()
        await asyncio.sleep(0.15)

        # Failure in half-open
        await breaker.record_failure()

        assert breaker.state == CircuitState.OPEN


class TestDefaultPolicies:
    """Tests for default retry policies."""

    def test_llm_policy(self):
        """Test LLM nodes have retry policy."""
        policy = get_retry_policy("llm")
        assert policy.max_retries == 3

    def test_http_policy(self):
        """Test HTTP nodes have retry policy."""
        policy = get_retry_policy("http_request")
        assert policy.max_retries == 3

    def test_code_no_retry(self):
        """Test code nodes have no retry (deterministic)."""
        policy = get_retry_policy("code")
        assert policy.max_retries == 0

    def test_condition_no_retry(self):
        """Test condition nodes have no retry (deterministic)."""
        policy = get_retry_policy("condition")
        assert policy.max_retries == 0

    def test_unknown_default(self):
        """Test unknown node types get default policy."""
        policy = get_retry_policy("unknown_type")
        assert policy.max_retries == 0  # Default is no retry for safety
