"""
Retry mechanism for node execution.

Provides configurable retry policies for failed node executions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TypeVar
from functools import wraps
import asyncio
import logging
import random

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """
    Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delays
        retryable_errors: List of exception types to retry
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_errors: tuple = field(default_factory=lambda: (Exception,))

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt."""
        delay = min(
            self.base_delay * (self.exponential_base**attempt),
            self.max_delay,
        )

        if self.jitter:
            # Add up to 25% jitter
            delay *= 1 + random.uniform(-0.25, 0.25)

        return delay


# Default policies for different node types
DEFAULT_POLICIES = {
    "llm": RetryPolicy(max_retries=3, base_delay=2.0),
    "http_request": RetryPolicy(max_retries=3, base_delay=1.0),
    "tool": RetryPolicy(max_retries=2, base_delay=1.0),
    "agent": RetryPolicy(max_retries=2, base_delay=2.0),
    "knowledge_retrieval": RetryPolicy(max_retries=2, base_delay=1.0),
    "sub_workflow": RetryPolicy(max_retries=1, base_delay=5.0),
    # Code/template nodes don't retry by default (deterministic)
    "code": RetryPolicy(max_retries=0),
    "template": RetryPolicy(max_retries=0),
    "condition": RetryPolicy(max_retries=0),
}


def get_retry_policy(node_type: str) -> RetryPolicy:
    """Get retry policy for a node type."""
    return DEFAULT_POLICIES.get(node_type, RetryPolicy(max_retries=1))


async def with_retry(
    func: Callable[..., Awaitable[T]],
    policy: RetryPolicy,
    *args,
    **kwargs,
) -> T:
    """
    Execute a function with retry logic.

    Args:
        func: Async function to execute
        policy: Retry policy to use
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    last_exception = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await func(*args, **kwargs)

        except policy.retryable_errors as e:
            last_exception = e

            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                logger.warning(
                    f"Retry attempt {attempt + 1}/{policy.max_retries} "
                    f"after {delay:.2f}s. Error: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {policy.max_retries} retries exhausted. Error: {e}")

    raise last_exception


def retryable(policy: RetryPolicy | None = None):
    """
    Decorator to make an async function retryable.

    Usage:
        @retryable(RetryPolicy(max_retries=3))
        async def my_function():
            ...
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            retry_policy = policy or RetryPolicy()
            return await with_retry(func, retry_policy, *args, **kwargs)

        return wrapper

    return decorator


class RetryableExecutor:
    """
    Wrapper to execute node with retry logic.

    Example:
        executor = NodeExecutorRegistry.get("llm")
        retryable = RetryableExecutor(executor, policy)
        result = await retryable.execute(node, context, run)
    """

    def __init__(self, executor: Any, policy: RetryPolicy | None = None):
        """
        Initialize retryable executor.

        Args:
            executor: Node executor instance
            policy: Retry policy (uses default if not provided)
        """
        self.executor = executor
        self.policy = policy or get_retry_policy(executor.node_type)
        self.attempts = 0
        self.last_error: str | None = None

    async def execute(self, node: dict, context: Any, run: Any) -> Any:
        """Execute with retry logic."""
        from .executor import ExecutionResult

        self.attempts = 0
        self.last_error = None

        for attempt in range(self.policy.max_retries + 1):
            self.attempts = attempt + 1

            try:
                result = await self.executor.execute(node, context, run)

                # Check if result indicates an error that should be retried
                if not result.success and attempt < self.policy.max_retries:
                    self.last_error = result.error
                    delay = self.policy.get_delay(attempt)
                    logger.warning(
                        f"Node execution failed, retry {attempt + 1}/{self.policy.max_retries} "
                        f"after {delay:.2f}s. Error: {result.error}"
                    )
                    await asyncio.sleep(delay)
                    continue

                return result

            except Exception as e:
                self.last_error = str(e)

                if attempt < self.policy.max_retries:
                    delay = self.policy.get_delay(attempt)
                    logger.warning(
                        f"Node exception, retry {attempt + 1}/{self.policy.max_retries} "
                        f"after {delay:.2f}s. Error: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retries exhausted. Error: {e}")
                    return ExecutionResult(
                        error=f"Failed after {self.attempts} attempts: {str(e)}"
                    )

        return ExecutionResult(
            error=f"Failed after {self.attempts} attempts: {self.last_error}"
        )


class CircuitBreaker:
    """
    Circuit breaker pattern for node execution.

    Prevents repeated calls to failing services.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests fail immediately
    - HALF_OPEN: Testing if service recovered

    Example:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        if breaker.can_execute():
            try:
                result = await execute_node()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 1,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds before attempting recovery
            half_open_requests: Requests to allow in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = "closed"
        self._half_open_count = 0

    @property
    def state(self) -> str:
        """Get current state."""
        if self._state == "open":
            # Check if we should transition to half-open
            import time

            if (
                self._last_failure_time
                and time.time() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = "half_open"
                self._half_open_count = 0

        return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        state = self.state

        if state == "closed":
            return True
        elif state == "half_open":
            if self._half_open_count < self.half_open_requests:
                self._half_open_count += 1
                return True
            return False
        else:  # open
            return False

    def record_success(self) -> None:
        """Record successful execution."""
        if self._state == "half_open":
            # Service recovered, close the circuit
            self._state = "closed"
            self._failure_count = 0
            logger.info("Circuit breaker closed - service recovered")
        elif self._state == "closed":
            # Reset failure count on success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record failed execution."""
        import time

        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == "half_open":
            # Still failing, reopen
            self._state = "open"
            logger.warning("Circuit breaker reopened - service still failing")
        elif self._state == "closed" and self._failure_count >= self.failure_threshold:
            # Too many failures, open the circuit
            self._state = "open"
            logger.warning(f"Circuit breaker opened - {self._failure_count} failures")

    def reset(self) -> None:
        """Reset the circuit breaker."""
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_count = 0
