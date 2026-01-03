"""
Workflow benchmark tools.

Provides load testing and performance benchmarking capabilities:
- Concurrent workflow execution
- Performance measurement
- Bottleneck identification
- Resource utilization tracking
"""

import asyncio
import logging
import time
import statistics
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from enum import Enum

logger = logging.getLogger(__name__)


class BenchmarkStatus(str, Enum):
    """Benchmark run status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BenchmarkConfig:
    """Benchmark configuration."""

    # Concurrency settings
    concurrent_users: int = 10
    requests_per_user: int = 10
    ramp_up_seconds: float = 5.0  # Time to ramp up to full concurrency

    # Duration settings
    duration_seconds: float | None = None  # If set, run for this duration
    max_requests: int | None = None  # If set, stop after this many requests

    # Rate limiting
    requests_per_second: float | None = None  # If set, limit request rate

    # Timeout
    request_timeout: float = 60.0

    # Warmup
    warmup_requests: int = 5

    def to_dict(self) -> dict:
        return {
            "concurrent_users": self.concurrent_users,
            "requests_per_user": self.requests_per_user,
            "ramp_up_seconds": self.ramp_up_seconds,
            "duration_seconds": self.duration_seconds,
            "max_requests": self.max_requests,
            "requests_per_second": self.requests_per_second,
            "request_timeout": self.request_timeout,
            "warmup_requests": self.warmup_requests,
        }


@dataclass
class RequestResult:
    """Result of a single benchmark request."""

    request_id: str
    success: bool
    duration_ms: float
    start_time: datetime
    end_time: datetime
    error: str | None = None
    response_size: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "error": self.error,
            "response_size": self.response_size,
            "metadata": self.metadata,
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark result."""

    benchmark_id: str
    status: BenchmarkStatus
    config: BenchmarkConfig

    # Timing
    start_time: datetime
    end_time: datetime | None = None
    total_duration_seconds: float = 0

    # Request stats
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency stats (ms)
    min_latency: float = 0
    max_latency: float = 0
    mean_latency: float = 0
    median_latency: float = 0
    p90_latency: float = 0
    p95_latency: float = 0
    p99_latency: float = 0
    stddev_latency: float = 0

    # Throughput
    requests_per_second: float = 0
    bytes_per_second: float = 0

    # Error breakdown
    errors: dict = field(default_factory=dict)

    # Raw results
    results: list[RequestResult] = field(default_factory=list)

    def to_dict(self, include_raw: bool = False) -> dict:
        data = {
            "benchmark_id": self.benchmark_id,
            "status": self.status.value,
            "config": self.config.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration_seconds": self.total_duration_seconds,
            "requests": {
                "total": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": self.successful_requests / max(self.total_requests, 1),
            },
            "latency_ms": {
                "min": self.min_latency,
                "max": self.max_latency,
                "mean": self.mean_latency,
                "median": self.median_latency,
                "p90": self.p90_latency,
                "p95": self.p95_latency,
                "p99": self.p99_latency,
                "stddev": self.stddev_latency,
            },
            "throughput": {
                "requests_per_second": self.requests_per_second,
                "bytes_per_second": self.bytes_per_second,
            },
            "errors": self.errors,
        }

        if include_raw:
            data["raw_results"] = [r.to_dict() for r in self.results]

        return data

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        success_rate = self.successful_requests / max(self.total_requests, 1) * 100
        lines = [
            f"=== Benchmark Results: {self.benchmark_id} ===",
            f"Status: {self.status.value}",
            f"Duration: {self.total_duration_seconds:.2f}s",
            "",
            "Requests:",
            f"  Total: {self.total_requests}",
            f"  Successful: {self.successful_requests} ({success_rate:.1f}%)",
            f"  Failed: {self.failed_requests}",
            "",
            "Latency (ms):",
            f"  Min: {self.min_latency:.2f}",
            f"  Max: {self.max_latency:.2f}",
            f"  Mean: {self.mean_latency:.2f}",
            f"  Median: {self.median_latency:.2f}",
            f"  P90: {self.p90_latency:.2f}",
            f"  P95: {self.p95_latency:.2f}",
            f"  P99: {self.p99_latency:.2f}",
            "",
            "Throughput:",
            f"  {self.requests_per_second:.2f} req/s",
        ]

        if self.errors:
            lines.extend([
                "",
                "Errors:",
            ])
            for error, count in self.errors.items():
                lines.append(f"  {error}: {count}")

        return "\n".join(lines)


class WorkflowBenchmark:
    """
    Workflow load testing and benchmarking tool.

    Provides:
    - Concurrent workflow execution testing
    - Performance metrics collection
    - Bottleneck identification
    - Resource utilization tracking

    Example:
        benchmark = WorkflowBenchmark()

        # Define workflow executor
        async def run_workflow(inputs):
            return await orchestrator.run(workflow_id, inputs)

        # Configure benchmark
        config = BenchmarkConfig(
            concurrent_users=10,
            requests_per_user=100,
            ramp_up_seconds=10,
        )

        # Run benchmark
        result = await benchmark.run(
            name="my_workflow_test",
            executor=run_workflow,
            inputs_generator=lambda: {"query": "test"},
            config=config,
        )

        # Print results
        print(result.to_summary())
    """

    def __init__(self):
        self._running_benchmarks: dict[str, BenchmarkResult] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def run(
        self,
        name: str,
        executor: Callable[[dict], Awaitable[Any]],
        inputs_generator: Callable[[], dict],
        config: BenchmarkConfig | None = None,
    ) -> BenchmarkResult:
        """
        Run a benchmark.

        Args:
            name: Benchmark name for identification
            executor: Async function to execute for each request
            inputs_generator: Function that generates input for each request
            config: Benchmark configuration

        Returns:
            BenchmarkResult with detailed metrics
        """
        config = config or BenchmarkConfig()
        benchmark_id = f"{name}_{uuid4().hex[:8]}"

        result = BenchmarkResult(
            benchmark_id=benchmark_id,
            status=BenchmarkStatus.RUNNING,
            config=config,
            start_time=datetime.utcnow(),
        )

        self._running_benchmarks[benchmark_id] = result
        self._cancel_events[benchmark_id] = asyncio.Event()

        try:
            # Warmup
            if config.warmup_requests > 0:
                logger.info(f"Running {config.warmup_requests} warmup requests...")
                for _ in range(config.warmup_requests):
                    try:
                        await executor(inputs_generator())
                    except Exception:
                        pass

            # Run benchmark
            logger.info(f"Starting benchmark: {benchmark_id}")
            logger.info(f"Config: {config.concurrent_users} users, {config.requests_per_user} req/user")

            all_results = await self._run_concurrent(
                benchmark_id=benchmark_id,
                executor=executor,
                inputs_generator=inputs_generator,
                config=config,
            )

            # Calculate statistics
            result.results = all_results
            result.end_time = datetime.utcnow()
            result.total_duration_seconds = (result.end_time - result.start_time).total_seconds()

            self._calculate_stats(result)

            result.status = BenchmarkStatus.COMPLETED
            logger.info(f"Benchmark completed: {benchmark_id}")

        except asyncio.CancelledError:
            result.status = BenchmarkStatus.CANCELLED
            result.end_time = datetime.utcnow()
            logger.info(f"Benchmark cancelled: {benchmark_id}")
        except Exception as e:
            result.status = BenchmarkStatus.FAILED
            result.end_time = datetime.utcnow()
            result.errors["benchmark_error"] = str(e)
            logger.error(f"Benchmark failed: {benchmark_id} - {e}")
        finally:
            self._running_benchmarks.pop(benchmark_id, None)
            self._cancel_events.pop(benchmark_id, None)

        return result

    async def _run_concurrent(
        self,
        benchmark_id: str,
        executor: Callable[[dict], Awaitable[Any]],
        inputs_generator: Callable[[], dict],
        config: BenchmarkConfig,
    ) -> list[RequestResult]:
        """Run concurrent requests."""
        results: list[RequestResult] = []
        results_lock = asyncio.Lock()
        cancel_event = self._cancel_events[benchmark_id]

        # Calculate total requests
        total_requests = config.concurrent_users * config.requests_per_user
        if config.max_requests:
            total_requests = min(total_requests, config.max_requests)

        request_count = 0
        request_count_lock = asyncio.Lock()

        # Rate limiter
        rate_limiter: asyncio.Semaphore | None = None
        if config.requests_per_second:
            rate_limiter = asyncio.Semaphore(int(config.requests_per_second))

        async def rate_limit_refill():
            """Refill rate limiter tokens."""
            if not rate_limiter:
                return
            while not cancel_event.is_set():
                await asyncio.sleep(1.0)
                # Release tokens up to the limit
                for _ in range(int(config.requests_per_second or 0)):
                    try:
                        rate_limiter.release()
                    except ValueError:
                        break

        async def user_worker(user_id: int, delay: float):
            """Simulate a single user."""
            nonlocal request_count

            # Ramp-up delay
            if delay > 0:
                await asyncio.sleep(delay)

            for i in range(config.requests_per_user):
                if cancel_event.is_set():
                    break

                # Check max requests
                async with request_count_lock:
                    if config.max_requests and request_count >= config.max_requests:
                        break
                    request_count += 1
                    current_request = request_count

                # Rate limiting
                if rate_limiter:
                    await rate_limiter.acquire()

                # Execute request
                result = await self._execute_request(
                    request_id=f"{benchmark_id}_u{user_id}_r{i}",
                    executor=executor,
                    inputs=inputs_generator(),
                    timeout=config.request_timeout,
                )

                async with results_lock:
                    results.append(result)

                # Progress logging
                if current_request % 100 == 0:
                    logger.info(f"Progress: {current_request}/{total_requests} requests")

        # Create user tasks with ramp-up delay
        tasks = []
        for user_id in range(config.concurrent_users):
            delay = (user_id / config.concurrent_users) * config.ramp_up_seconds
            task = asyncio.create_task(user_worker(user_id, delay))
            tasks.append(task)

        # Start rate limiter refill task
        if rate_limiter:
            refill_task = asyncio.create_task(rate_limit_refill())
            tasks.append(refill_task)

        # Handle duration-based stopping
        if config.duration_seconds:
            async def duration_stopper():
                await asyncio.sleep(config.duration_seconds)
                cancel_event.set()

            tasks.append(asyncio.create_task(duration_stopper()))

        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def _execute_request(
        self,
        request_id: str,
        executor: Callable[[dict], Awaitable[Any]],
        inputs: dict,
        timeout: float,
    ) -> RequestResult:
        """Execute a single request and measure it."""
        start_time = datetime.utcnow()
        start_ns = time.perf_counter_ns()

        try:
            result = await asyncio.wait_for(executor(inputs), timeout=timeout)
            end_ns = time.perf_counter_ns()
            duration_ms = (end_ns - start_ns) / 1_000_000

            # Try to get response size
            response_size = 0
            if isinstance(result, (str, bytes)):
                response_size = len(result)
            elif isinstance(result, dict):
                import json
                response_size = len(json.dumps(result))

            return RequestResult(
                request_id=request_id,
                success=True,
                duration_ms=duration_ms,
                start_time=start_time,
                end_time=datetime.utcnow(),
                response_size=response_size,
            )
        except asyncio.TimeoutError:
            end_ns = time.perf_counter_ns()
            return RequestResult(
                request_id=request_id,
                success=False,
                duration_ms=(end_ns - start_ns) / 1_000_000,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error="timeout",
            )
        except Exception as e:
            end_ns = time.perf_counter_ns()
            return RequestResult(
                request_id=request_id,
                success=False,
                duration_ms=(end_ns - start_ns) / 1_000_000,
                start_time=start_time,
                end_time=datetime.utcnow(),
                error=str(e),
            )

    def _calculate_stats(self, result: BenchmarkResult) -> None:
        """Calculate statistics from raw results."""
        if not result.results:
            return

        result.total_requests = len(result.results)
        result.successful_requests = sum(1 for r in result.results if r.success)
        result.failed_requests = result.total_requests - result.successful_requests

        # Latency calculations (only for successful requests)
        successful_latencies = [r.duration_ms for r in result.results if r.success]
        if successful_latencies:
            successful_latencies.sort()

            result.min_latency = min(successful_latencies)
            result.max_latency = max(successful_latencies)
            result.mean_latency = statistics.mean(successful_latencies)
            result.median_latency = statistics.median(successful_latencies)
            result.stddev_latency = statistics.stdev(successful_latencies) if len(successful_latencies) > 1 else 0

            # Percentiles
            n = len(successful_latencies)
            result.p90_latency = successful_latencies[int(n * 0.90)] if n > 0 else 0
            result.p95_latency = successful_latencies[int(n * 0.95)] if n > 0 else 0
            result.p99_latency = successful_latencies[int(n * 0.99)] if n > 0 else 0

        # Throughput
        if result.total_duration_seconds > 0:
            result.requests_per_second = result.successful_requests / result.total_duration_seconds
            total_bytes = sum(r.response_size for r in result.results if r.success)
            result.bytes_per_second = total_bytes / result.total_duration_seconds

        # Error breakdown
        for r in result.results:
            if not r.success and r.error:
                error_key = r.error[:50]  # Truncate long errors
                result.errors[error_key] = result.errors.get(error_key, 0) + 1

    async def cancel(self, benchmark_id: str) -> bool:
        """Cancel a running benchmark."""
        event = self._cancel_events.get(benchmark_id)
        if event:
            event.set()
            return True
        return False

    def get_running(self) -> list[str]:
        """Get IDs of running benchmarks."""
        return list(self._running_benchmarks.keys())

    def get_status(self, benchmark_id: str) -> dict | None:
        """Get status of a running benchmark."""
        result = self._running_benchmarks.get(benchmark_id)
        if result:
            return {
                "benchmark_id": benchmark_id,
                "status": result.status.value,
                "requests_completed": len(result.results),
                "successful": sum(1 for r in result.results if r.success),
                "failed": sum(1 for r in result.results if not r.success),
                "elapsed_seconds": (datetime.utcnow() - result.start_time).total_seconds(),
            }
        return None


class LatencyHistogram:
    """Latency histogram for detailed distribution analysis."""

    def __init__(self, buckets: list[float] | None = None):
        """
        Initialize histogram with latency buckets (in ms).

        Default buckets: 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000
        """
        self.buckets = buckets or [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        self.counts = {b: 0 for b in self.buckets}
        self.counts[float("inf")] = 0
        self.total = 0
        self.sum = 0.0

    def observe(self, latency_ms: float) -> None:
        """Record a latency observation."""
        self.total += 1
        self.sum += latency_ms

        for bucket in self.buckets:
            if latency_ms <= bucket:
                self.counts[bucket] += 1
                return
        self.counts[float("inf")] += 1

    def get_distribution(self) -> dict:
        """Get latency distribution."""
        distribution = {}
        prev_count = 0

        for bucket in self.buckets:
            count = self.counts[bucket]
            distribution[f"<={bucket}ms"] = count - prev_count
            prev_count = count

        distribution[f">{self.buckets[-1]}ms"] = self.counts[float("inf")]
        return distribution

    def get_percentile(self, p: float) -> float:
        """Estimate percentile from histogram."""
        if self.total == 0:
            return 0

        target = self.total * p
        cumulative = 0

        for bucket in self.buckets:
            cumulative = self.counts[bucket]
            if cumulative >= target:
                return bucket

        return self.buckets[-1]


# Convenience functions

async def run_quick_benchmark(
    executor: Callable[[dict], Awaitable[Any]],
    inputs: dict,
    iterations: int = 100,
) -> dict:
    """
    Run a quick benchmark with default settings.

    Returns basic statistics.
    """
    benchmark = WorkflowBenchmark()

    config = BenchmarkConfig(
        concurrent_users=1,
        requests_per_user=iterations,
        warmup_requests=5,
    )

    result = await benchmark.run(
        name="quick_test",
        executor=executor,
        inputs_generator=lambda: inputs,
        config=config,
    )

    return {
        "iterations": result.total_requests,
        "success_rate": result.successful_requests / max(result.total_requests, 1),
        "mean_latency_ms": result.mean_latency,
        "p95_latency_ms": result.p95_latency,
        "requests_per_second": result.requests_per_second,
    }


async def compare_benchmarks(
    executors: dict[str, Callable[[dict], Awaitable[Any]]],
    inputs_generator: Callable[[], dict],
    config: BenchmarkConfig | None = None,
) -> dict[str, BenchmarkResult]:
    """
    Compare multiple implementations.

    Args:
        executors: Dict of name -> executor function
        inputs_generator: Function to generate inputs
        config: Benchmark configuration

    Returns:
        Dict of name -> BenchmarkResult
    """
    results = {}
    benchmark = WorkflowBenchmark()

    for name, executor in executors.items():
        logger.info(f"Running benchmark for: {name}")
        result = await benchmark.run(
            name=name,
            executor=executor,
            inputs_generator=inputs_generator,
            config=config,
        )
        results[name] = result

    # Print comparison
    print("\n=== Benchmark Comparison ===\n")
    print(f"{'Name':<20} {'RPS':>10} {'Mean':>10} {'P95':>10} {'Success':>10}")
    print("-" * 62)
    for name, result in results.items():
        success_rate = result.successful_requests / max(result.total_requests, 1) * 100
        print(f"{name:<20} {result.requests_per_second:>10.2f} {result.mean_latency:>10.2f} {result.p95_latency:>10.2f} {success_rate:>9.1f}%")

    return results


# Global benchmark instance
_benchmark: WorkflowBenchmark | None = None


def get_benchmark() -> WorkflowBenchmark:
    """Get global benchmark instance."""
    global _benchmark
    if _benchmark is None:
        _benchmark = WorkflowBenchmark()
    return _benchmark
