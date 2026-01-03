"""
Workflow metrics and monitoring.

Provides comprehensive metrics collection for workflow execution,
including latency, throughput, error rates, and resource utilization.
"""

import time
import logging
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import asyncio
import json

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricConfig:
    """Metrics configuration."""

    # Redis key prefix
    prefix: str = "wf:metrics:"

    # Retention periods (seconds)
    realtime_retention: int = 300  # 5 minutes for real-time metrics
    hourly_retention: int = 86400  # 24 hours for hourly aggregates
    daily_retention: int = 604800  # 7 days for daily aggregates

    # Histogram buckets for latency (ms)
    latency_buckets: tuple = (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

    # Enable detailed node metrics
    enable_node_metrics: bool = True


METRICS_CONFIG = MetricConfig()


@dataclass
class WorkflowMetrics:
    """Aggregated workflow metrics."""

    # Execution counts
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    cancelled_runs: int = 0

    # Timing metrics (ms)
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0

    # Throughput
    runs_per_minute: float = 0.0
    nodes_per_minute: float = 0.0

    # Error rates
    error_rate: float = 0.0
    errors_by_type: dict = field(default_factory=dict)

    # Resource usage
    avg_nodes_per_run: float = 0.0
    total_nodes_executed: int = 0

    # Time range
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass
class NodeMetrics:
    """Aggregated node metrics."""

    node_type: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0

    # Timing
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0

    # Retries
    total_retries: int = 0
    avg_retries: float = 0.0


class MetricsCollector:
    """
    Metrics collector for workflow execution.

    Collects and stores metrics in Redis for:
    - Workflow execution (latency, success rate, throughput)
    - Node execution (per-type metrics)
    - Error tracking
    - Resource utilization

    Example:
        collector = MetricsCollector()

        # Record workflow execution
        await collector.record_workflow_start(run_id, workflow_id)
        await collector.record_workflow_complete(run_id, duration_ms)

        # Record node execution
        await collector.record_node_execution(
            run_id=run_id,
            node_id=node_id,
            node_type="llm",
            duration_ms=150,
            success=True,
        )

        # Get metrics
        metrics = await collector.get_workflow_metrics(workflow_id)
    """

    def __init__(self, config: MetricConfig | None = None):
        """Initialize metrics collector."""
        self.config = config or METRICS_CONFIG
        self._redis = None

    async def _get_redis(self):
        """Get Redis connection."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    def _key(self, *parts: str) -> str:
        """Generate Redis key."""
        return f"{self.config.prefix}{':'.join(parts)}"

    # Workflow Metrics

    async def record_workflow_start(
        self,
        run_id: str,
        workflow_id: str,
    ) -> None:
        """Record workflow execution start."""
        try:
            redis = await self._get_redis()
            now = time.time()

            # Store start time
            await redis.hset(
                self._key("runs", run_id),
                mapping={
                    "workflow_id": workflow_id,
                    "start_time": str(now),
                    "status": "running",
                },
            )
            await redis.expire(
                self._key("runs", run_id),
                self.config.realtime_retention,
            )

            # Increment running count
            await redis.incr(self._key("workflow", workflow_id, "running"))

            # Record in time series (minute granularity)
            minute_key = self._key("ts", workflow_id, "starts", str(int(now // 60)))
            await redis.incr(minute_key)
            await redis.expire(minute_key, self.config.realtime_retention)

        except Exception as e:
            logger.warning(f"Metrics record error: {e}")

    async def record_workflow_complete(
        self,
        run_id: str,
        workflow_id: str,
        duration_ms: int,
        status: str = "success",
        node_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Record workflow execution completion."""
        try:
            redis = await self._get_redis()
            now = time.time()

            # Update run info
            await redis.hset(
                self._key("runs", run_id),
                mapping={
                    "end_time": str(now),
                    "duration_ms": str(duration_ms),
                    "status": status,
                    "node_count": str(node_count),
                    "error": error or "",
                },
            )

            # Decrement running count
            await redis.decr(self._key("workflow", workflow_id, "running"))

            # Increment status counter
            await redis.incr(self._key("workflow", workflow_id, status))

            # Record duration in histogram
            bucket = self._get_bucket(duration_ms)
            await redis.incr(
                self._key("workflow", workflow_id, "duration", str(bucket))
            )

            # Record in sorted set for percentile calculation
            await redis.zadd(
                self._key("workflow", workflow_id, "durations"),
                {run_id: duration_ms},
            )
            # Keep only recent runs
            await redis.zremrangebyrank(
                self._key("workflow", workflow_id, "durations"),
                0, -1001,  # Keep last 1000
            )

            # Record node count
            await redis.incrby(
                self._key("workflow", workflow_id, "nodes"),
                node_count,
            )

            # Record error type if failed
            if status == "failed" and error:
                error_type = self._extract_error_type(error)
                await redis.hincrby(
                    self._key("workflow", workflow_id, "errors"),
                    error_type,
                    1,
                )

            # Time series for completions
            minute_key = self._key("ts", workflow_id, status, str(int(now // 60)))
            await redis.incr(minute_key)
            await redis.expire(minute_key, self.config.realtime_retention)

        except Exception as e:
            logger.warning(f"Metrics record error: {e}")

    async def record_node_execution(
        self,
        run_id: str,
        node_id: str,
        node_type: str,
        duration_ms: int,
        success: bool = True,
        retries: int = 0,
        error: str | None = None,
    ) -> None:
        """Record node execution metrics."""
        if not self.config.enable_node_metrics:
            return

        try:
            redis = await self._get_redis()

            # Increment execution count
            status = "success" if success else "failed"
            await redis.incr(self._key("node", node_type, status))

            # Record duration
            bucket = self._get_bucket(duration_ms)
            await redis.incr(self._key("node", node_type, "duration", str(bucket)))

            # Record in sorted set for percentiles
            await redis.zadd(
                self._key("node", node_type, "durations"),
                {f"{run_id}:{node_id}": duration_ms},
            )
            await redis.zremrangebyrank(
                self._key("node", node_type, "durations"),
                0, -1001,
            )

            # Record retries
            if retries > 0:
                await redis.incrby(self._key("node", node_type, "retries"), retries)

            # Record error
            if not success and error:
                error_type = self._extract_error_type(error)
                await redis.hincrby(
                    self._key("node", node_type, "errors"),
                    error_type,
                    1,
                )

        except Exception as e:
            logger.warning(f"Node metrics record error: {e}")

    # Metrics Retrieval

    async def get_workflow_metrics(
        self,
        workflow_id: str,
        time_range_minutes: int = 60,
    ) -> WorkflowMetrics:
        """
        Get aggregated metrics for a workflow.

        Args:
            workflow_id: Workflow UUID
            time_range_minutes: Time range for metrics

        Returns:
            Aggregated workflow metrics
        """
        metrics = WorkflowMetrics()

        try:
            redis = await self._get_redis()

            # Get status counts
            metrics.successful_runs = int(
                await redis.get(self._key("workflow", workflow_id, "success")) or 0
            )
            metrics.failed_runs = int(
                await redis.get(self._key("workflow", workflow_id, "failed")) or 0
            )
            metrics.cancelled_runs = int(
                await redis.get(self._key("workflow", workflow_id, "cancelled")) or 0
            )
            metrics.total_runs = (
                metrics.successful_runs +
                metrics.failed_runs +
                metrics.cancelled_runs
            )

            # Calculate error rate
            if metrics.total_runs > 0:
                metrics.error_rate = metrics.failed_runs / metrics.total_runs

            # Get duration percentiles
            durations = await redis.zrange(
                self._key("workflow", workflow_id, "durations"),
                0, -1,
                withscores=True,
            )
            if durations:
                duration_values = [d[1] for d in durations]
                duration_values.sort()

                metrics.min_duration_ms = min(duration_values)
                metrics.max_duration_ms = max(duration_values)
                metrics.avg_duration_ms = sum(duration_values) / len(duration_values)
                metrics.p50_duration_ms = self._percentile(duration_values, 50)
                metrics.p95_duration_ms = self._percentile(duration_values, 95)
                metrics.p99_duration_ms = self._percentile(duration_values, 99)

            # Get node count
            metrics.total_nodes_executed = int(
                await redis.get(self._key("workflow", workflow_id, "nodes")) or 0
            )
            if metrics.total_runs > 0:
                metrics.avg_nodes_per_run = (
                    metrics.total_nodes_executed / metrics.total_runs
                )

            # Get error breakdown
            errors = await redis.hgetall(
                self._key("workflow", workflow_id, "errors")
            )
            metrics.errors_by_type = {k: int(v) for k, v in errors.items()}

            # Calculate throughput (runs per minute)
            now = time.time()
            start_minute = int((now - time_range_minutes * 60) // 60)
            end_minute = int(now // 60)

            total_in_range = 0
            for minute in range(start_minute, end_minute + 1):
                for status in ["success", "failed", "cancelled"]:
                    count = await redis.get(
                        self._key("ts", workflow_id, status, str(minute))
                    )
                    total_in_range += int(count or 0)

            if time_range_minutes > 0:
                metrics.runs_per_minute = total_in_range / time_range_minutes

            metrics.start_time = datetime.utcnow() - timedelta(minutes=time_range_minutes)
            metrics.end_time = datetime.utcnow()

        except Exception as e:
            logger.warning(f"Get metrics error: {e}")

        return metrics

    async def get_node_metrics(
        self,
        node_type: str,
    ) -> NodeMetrics:
        """Get aggregated metrics for a node type."""
        metrics = NodeMetrics(node_type=node_type)

        try:
            redis = await self._get_redis()

            # Get counts
            metrics.successful_executions = int(
                await redis.get(self._key("node", node_type, "success")) or 0
            )
            metrics.failed_executions = int(
                await redis.get(self._key("node", node_type, "failed")) or 0
            )
            metrics.total_executions = (
                metrics.successful_executions + metrics.failed_executions
            )

            # Get duration percentiles
            durations = await redis.zrange(
                self._key("node", node_type, "durations"),
                0, -1,
                withscores=True,
            )
            if durations:
                duration_values = [d[1] for d in durations]
                duration_values.sort()

                metrics.min_duration_ms = min(duration_values)
                metrics.max_duration_ms = max(duration_values)
                metrics.avg_duration_ms = sum(duration_values) / len(duration_values)
                metrics.p50_duration_ms = self._percentile(duration_values, 50)
                metrics.p95_duration_ms = self._percentile(duration_values, 95)

            # Get retries
            metrics.total_retries = int(
                await redis.get(self._key("node", node_type, "retries")) or 0
            )
            if metrics.total_executions > 0:
                metrics.avg_retries = metrics.total_retries / metrics.total_executions

        except Exception as e:
            logger.warning(f"Get node metrics error: {e}")

        return metrics

    async def get_all_node_metrics(self) -> dict[str, NodeMetrics]:
        """Get metrics for all node types."""
        node_types = [
            "user_input", "trigger", "answer", "llm", "condition",
            "question_classifier", "code", "template", "variable_assignment",
            "variable_aggregator", "parameter_extractor", "iteration", "loop",
            "tool", "agent", "http_request", "sub_workflow", "file_to_url",
            "knowledge_retrieval", "document_extractor",
        ]

        results = {}
        for node_type in node_types:
            metrics = await self.get_node_metrics(node_type)
            if metrics.total_executions > 0:
                results[node_type] = metrics

        return results

    async def get_running_workflows(self) -> list[dict]:
        """Get list of currently running workflows."""
        try:
            redis = await self._get_redis()

            # Find all running runs
            pattern = self._key("runs", "*")
            keys = await redis.keys(pattern)

            running = []
            for key in keys:
                data = await redis.hgetall(key)
                if data.get("status") == "running":
                    run_id = key.split(":")[-1]
                    running.append({
                        "run_id": run_id,
                        "workflow_id": data.get("workflow_id"),
                        "start_time": float(data.get("start_time", 0)),
                        "duration_s": time.time() - float(data.get("start_time", 0)),
                    })

            return sorted(running, key=lambda x: x["start_time"])

        except Exception as e:
            logger.warning(f"Get running workflows error: {e}")
            return []

    async def get_dashboard_summary(self) -> dict:
        """Get summary metrics for dashboard."""
        try:
            redis = await self._get_redis()

            # Get global counts
            success_keys = await redis.keys(self._key("workflow", "*", "success"))
            failed_keys = await redis.keys(self._key("workflow", "*", "failed"))

            total_success = 0
            total_failed = 0

            for key in success_keys:
                total_success += int(await redis.get(key) or 0)
            for key in failed_keys:
                total_failed += int(await redis.get(key) or 0)

            total_runs = total_success + total_failed

            # Get running count
            running_workflows = await self.get_running_workflows()

            return {
                "total_runs": total_runs,
                "successful_runs": total_success,
                "failed_runs": total_failed,
                "success_rate": total_success / total_runs if total_runs > 0 else 0,
                "currently_running": len(running_workflows),
                "running_workflows": running_workflows[:10],  # Top 10
            }

        except Exception as e:
            logger.warning(f"Get dashboard summary error: {e}")
            return {}

    # Helper methods

    def _get_bucket(self, value: float) -> int:
        """Get histogram bucket for a value."""
        for bucket in self.config.latency_buckets:
            if value <= bucket:
                return bucket
        return int(self.config.latency_buckets[-1])

    def _percentile(self, values: list[float], percentile: int) -> float:
        """Calculate percentile from sorted values."""
        if not values:
            return 0.0
        index = int(len(values) * percentile / 100)
        index = min(index, len(values) - 1)
        return values[index]

    def _extract_error_type(self, error: str) -> str:
        """Extract error type from error message."""
        # Simple extraction - get first word or error class
        if ":" in error:
            return error.split(":")[0].strip()
        return error.split()[0] if error else "UnknownError"


class Timer:
    """
    Context manager for timing code execution.

    Example:
        async with Timer() as t:
            await some_operation()
        print(f"Duration: {t.duration_ms}ms")
    """

    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: int = 0

    async def __aenter__(self):
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        return False


# Global metrics instance
_metrics_instance: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
