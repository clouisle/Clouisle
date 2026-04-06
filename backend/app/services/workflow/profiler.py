"""
Workflow execution profiler.

Provides detailed profiling for workflow execution, including
node-level timing, bottleneck detection, and optimization suggestions.
"""

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NodeProfile:
    """Profile data for a single node execution."""

    node_id: str
    node_type: str
    node_label: str = ""

    # Timing (ms)
    start_time: float = 0
    end_time: float = 0
    duration_ms: int = 0
    wait_time_ms: int = 0  # Time waiting for upstream

    # Execution details
    success: bool = True
    retries: int = 0
    error: str | None = None

    # Resource usage
    memory_mb: float = 0
    tokens_used: int = 0  # For LLM nodes
    cache_hit: bool = False

    # Input/Output sizes
    input_size_bytes: int = 0
    output_size_bytes: int = 0


@dataclass
class StageProfile:
    """Profile data for an execution stage."""

    stage_index: int
    node_ids: list[str] = field(default_factory=list)

    # Timing
    start_time: float = 0
    end_time: float = 0
    duration_ms: int = 0

    # Parallelism
    parallel_nodes: int = 0
    sequential_bottleneck: str | None = None


@dataclass
class WorkflowProfile:
    """Complete profile for a workflow execution."""

    run_id: str
    workflow_id: str
    workflow_name: str = ""

    # Overall timing
    start_time: datetime | None = None
    end_time: datetime | None = None
    total_duration_ms: int = 0

    # Breakdown
    node_profiles: dict[str, NodeProfile] = field(default_factory=dict)
    stage_profiles: list[StageProfile] = field(default_factory=list)

    # Summary
    total_nodes: int = 0
    successful_nodes: int = 0
    failed_nodes: int = 0
    skipped_nodes: int = 0
    cached_nodes: int = 0

    # Performance metrics
    slowest_node_id: str | None = None
    slowest_node_ms: int = 0
    total_wait_time_ms: int = 0
    parallel_efficiency: float = 0.0

    # Resource usage
    total_tokens: int = 0
    total_retries: int = 0
    cache_hit_rate: float = 0.0

    # Bottlenecks detected
    bottlenecks: list[dict] = field(default_factory=list)

    # Optimization suggestions
    suggestions: list[str] = field(default_factory=list)


class ExecutionProfiler:
    """
    Profiler for workflow execution.

    Tracks detailed timing and resource usage for each node,
    identifies bottlenecks, and generates optimization suggestions.

    Example:
        profiler = ExecutionProfiler(run_id, workflow_id)

        # Start profiling
        profiler.start()

        # Profile node execution
        with profiler.node(node_id, node_type) as np:
            result = await executor.execute(...)
            np.success = result.success
            np.tokens_used = result.token_count

        # Finish profiling
        profile = profiler.finish()
    """

    def __init__(
        self,
        run_id: str,
        workflow_id: str,
        workflow_name: str = "",
    ):
        """Initialize profiler."""
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name

        self._profile = WorkflowProfile(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
        )
        self._stage_index = 0
        self._current_stage: StageProfile | None = None
        self._node_start_times: dict[str, float] = {}

    def start(self) -> None:
        """Start profiling."""
        self._profile.start_time = datetime.utcnow()
        self._start_time = time.time()

    def finish(self) -> WorkflowProfile:
        """Finish profiling and generate report."""
        self._profile.end_time = datetime.utcnow()
        self._profile.total_duration_ms = int((time.time() - self._start_time) * 1000)

        # Calculate summary metrics
        self._calculate_summary()

        # Detect bottlenecks
        self._detect_bottlenecks()

        # Generate suggestions
        self._generate_suggestions()

        return self._profile

    def start_stage(self, node_ids: list[str]) -> None:
        """Start profiling a new stage."""
        self._current_stage = StageProfile(
            stage_index=self._stage_index,
            node_ids=node_ids,
            start_time=time.time(),
            parallel_nodes=len(node_ids),
        )
        self._stage_index += 1

    def end_stage(self) -> None:
        """End current stage profiling."""
        if self._current_stage:
            self._current_stage.end_time = time.time()
            self._current_stage.duration_ms = int(
                (self._current_stage.end_time - self._current_stage.start_time) * 1000
            )
            self._profile.stage_profiles.append(self._current_stage)
            self._current_stage = None

    def node(
        self,
        node_id: str,
        node_type: str,
        node_label: str = "",
    ) -> "NodeProfileContext":
        """Create a node profiling context."""
        return NodeProfileContext(self, node_id, node_type, node_label)

    def record_node_start(
        self,
        node_id: str,
        node_type: str,
        node_label: str = "",
    ) -> NodeProfile:
        """Record node execution start."""
        profile = NodeProfile(
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            start_time=time.time(),
        )
        self._node_start_times[node_id] = profile.start_time
        self._profile.node_profiles[node_id] = profile
        return profile

    def record_node_end(
        self,
        node_id: str,
        success: bool = True,
        error: str | None = None,
        retries: int = 0,
        tokens_used: int = 0,
        cache_hit: bool = False,
        output_size: int = 0,
    ) -> None:
        """Record node execution end."""
        if node_id not in self._profile.node_profiles:
            return

        profile = self._profile.node_profiles[node_id]
        profile.end_time = time.time()
        profile.duration_ms = int((profile.end_time - profile.start_time) * 1000)
        profile.success = success
        profile.error = error
        profile.retries = retries
        profile.tokens_used = tokens_used
        profile.cache_hit = cache_hit
        profile.output_size_bytes = output_size

        # Calculate wait time (time between upstream completion and this start)
        # This is simplified - real implementation would track dependencies

    def record_skip(self, node_id: str, reason: str = "") -> None:
        """Record that a node was skipped."""
        self._profile.skipped_nodes += 1

    def _calculate_summary(self) -> None:
        """Calculate summary metrics from node profiles."""
        profile = self._profile

        profile.total_nodes = len(profile.node_profiles)

        for node_id, np in profile.node_profiles.items():
            if np.success:
                profile.successful_nodes += 1
            else:
                profile.failed_nodes += 1

            if np.cache_hit:
                profile.cached_nodes += 1

            profile.total_tokens += np.tokens_used
            profile.total_retries += np.retries
            profile.total_wait_time_ms += np.wait_time_ms

            # Track slowest node
            if np.duration_ms > profile.slowest_node_ms:
                profile.slowest_node_ms = np.duration_ms
                profile.slowest_node_id = node_id

        # Calculate cache hit rate
        if profile.total_nodes > 0:
            profile.cache_hit_rate = profile.cached_nodes / profile.total_nodes

        # Calculate parallel efficiency
        # (sum of node times) / (total time * max parallelism)
        total_node_time = sum(np.duration_ms for np in profile.node_profiles.values())
        max_parallelism = max(
            (sp.parallel_nodes for sp in profile.stage_profiles),
            default=1,
        )
        if profile.total_duration_ms > 0 and max_parallelism > 0:
            profile.parallel_efficiency = total_node_time / (
                profile.total_duration_ms * max_parallelism
            )

    def _detect_bottlenecks(self) -> None:
        """Detect performance bottlenecks."""
        profile = self._profile
        bottlenecks = []

        # 1. Slow nodes (>1s or >50% of total time)
        for node_id, np in profile.node_profiles.items():
            if np.duration_ms > 1000:
                bottlenecks.append(
                    {
                        "type": "slow_node",
                        "node_id": node_id,
                        "node_type": np.node_type,
                        "duration_ms": np.duration_ms,
                        "severity": "high" if np.duration_ms > 5000 else "medium",
                    }
                )
            elif (
                profile.total_duration_ms > 0
                and np.duration_ms / profile.total_duration_ms > 0.5
            ):
                bottlenecks.append(
                    {
                        "type": "dominant_node",
                        "node_id": node_id,
                        "node_type": np.node_type,
                        "percentage": np.duration_ms / profile.total_duration_ms * 100,
                        "severity": "medium",
                    }
                )

        # 2. High retry count
        for node_id, np in profile.node_profiles.items():
            if np.retries > 2:
                bottlenecks.append(
                    {
                        "type": "high_retries",
                        "node_id": node_id,
                        "node_type": np.node_type,
                        "retries": np.retries,
                        "severity": "medium",
                    }
                )

        # 3. Sequential bottlenecks (stages with single node taking most time)
        for sp in profile.stage_profiles:
            if (
                sp.parallel_nodes == 1
                and sp.duration_ms > profile.total_duration_ms * 0.3
            ):
                stage_node_id = sp.node_ids[0] if sp.node_ids else None
                if stage_node_id:
                    bottlenecks.append(
                        {
                            "type": "sequential_bottleneck",
                            "stage_index": sp.stage_index,
                            "node_id": stage_node_id,
                            "duration_ms": sp.duration_ms,
                            "severity": "low",
                        }
                    )

        # 4. Low cache hit rate for cacheable nodes
        cacheable_types = {"code", "template", "condition", "variable_assignment"}
        cacheable_nodes = [
            np
            for np in profile.node_profiles.values()
            if np.node_type in cacheable_types
        ]
        if cacheable_nodes:
            cache_hits = sum(1 for np in cacheable_nodes if np.cache_hit)
            if len(cacheable_nodes) > 5 and cache_hits / len(cacheable_nodes) < 0.3:
                bottlenecks.append(
                    {
                        "type": "low_cache_rate",
                        "cacheable_nodes": len(cacheable_nodes),
                        "cache_hits": cache_hits,
                        "severity": "low",
                    }
                )

        profile.bottlenecks = bottlenecks

    def _generate_suggestions(self) -> None:
        """Generate optimization suggestions based on profile."""
        profile = self._profile
        suggestions = []

        # Based on bottlenecks
        for bottleneck in profile.bottlenecks:
            if bottleneck["type"] == "slow_node":
                node_type = bottleneck["node_type"]
                if node_type == "llm":
                    suggestions.append(
                        f"Consider using a faster LLM model for node {bottleneck['node_id']} "
                        f"or reducing prompt length."
                    )
                elif node_type == "http_request":
                    suggestions.append(
                        f"HTTP request node {bottleneck['node_id']} is slow. "
                        f"Consider adding caching or using a faster endpoint."
                    )
                elif node_type == "code":
                    suggestions.append(
                        f"Code node {bottleneck['node_id']} is slow. "
                        f"Consider optimizing the code or moving heavy computation."
                    )

            elif bottleneck["type"] == "high_retries":
                suggestions.append(
                    f"Node {bottleneck['node_id']} has high retry count ({bottleneck['retries']}). "
                    f"Check for transient errors or service issues."
                )

            elif bottleneck["type"] == "sequential_bottleneck":
                suggestions.append(
                    f"Stage {bottleneck['stage_index']} is a sequential bottleneck. "
                    f"Consider parallelizing with other nodes if possible."
                )

            elif bottleneck["type"] == "low_cache_rate":
                suggestions.append(
                    "Cache hit rate is low for deterministic nodes. "
                    "Ensure caching is properly configured."
                )

        # General suggestions based on profile
        if profile.total_tokens > 10000:
            suggestions.append(
                f"High token usage ({profile.total_tokens}). "
                "Consider optimizing prompts or using summarization."
            )

        if profile.parallel_efficiency < 0.5 and len(profile.stage_profiles) > 3:
            suggestions.append(
                "Low parallel efficiency. Consider restructuring workflow "
                "to enable more parallel execution."
            )

        if profile.total_retries > profile.total_nodes * 0.2:
            suggestions.append(
                "High overall retry rate. Check external service health "
                "and consider adding circuit breakers."
            )

        profile.suggestions = suggestions

    def to_dict(self) -> dict:
        """Convert profile to dictionary for serialization."""
        profile = self._profile
        return {
            "run_id": profile.run_id,
            "workflow_id": profile.workflow_id,
            "workflow_name": profile.workflow_name,
            "start_time": profile.start_time.isoformat()
            if profile.start_time
            else None,
            "end_time": profile.end_time.isoformat() if profile.end_time else None,
            "total_duration_ms": profile.total_duration_ms,
            "summary": {
                "total_nodes": profile.total_nodes,
                "successful_nodes": profile.successful_nodes,
                "failed_nodes": profile.failed_nodes,
                "skipped_nodes": profile.skipped_nodes,
                "cached_nodes": profile.cached_nodes,
                "total_tokens": profile.total_tokens,
                "total_retries": profile.total_retries,
                "cache_hit_rate": profile.cache_hit_rate,
                "parallel_efficiency": profile.parallel_efficiency,
            },
            "slowest_node": {
                "node_id": profile.slowest_node_id,
                "duration_ms": profile.slowest_node_ms,
            }
            if profile.slowest_node_id
            else None,
            "nodes": {
                node_id: {
                    "node_type": np.node_type,
                    "node_label": np.node_label,
                    "duration_ms": np.duration_ms,
                    "success": np.success,
                    "retries": np.retries,
                    "cache_hit": np.cache_hit,
                    "tokens_used": np.tokens_used,
                }
                for node_id, np in profile.node_profiles.items()
            },
            "stages": [
                {
                    "index": sp.stage_index,
                    "node_ids": sp.node_ids,
                    "duration_ms": sp.duration_ms,
                    "parallel_nodes": sp.parallel_nodes,
                }
                for sp in profile.stage_profiles
            ],
            "bottlenecks": profile.bottlenecks,
            "suggestions": profile.suggestions,
        }


class NodeProfileContext:
    """Context manager for node profiling."""

    def __init__(
        self,
        profiler: ExecutionProfiler,
        node_id: str,
        node_type: str,
        node_label: str,
    ):
        self.profiler = profiler
        self.node_id = node_id
        self.node_type = node_type
        self.node_label = node_label

        # Results to be set by user
        self.success = True
        self.error: str | None = None
        self.retries = 0
        self.tokens_used = 0
        self.cache_hit = False
        self.output_size = 0

    def __enter__(self):
        self.profiler.record_node_start(
            self.node_id,
            self.node_type,
            self.node_label,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.success = False
            self.error = str(exc_val)

        self.profiler.record_node_end(
            self.node_id,
            success=self.success,
            error=self.error,
            retries=self.retries,
            tokens_used=self.tokens_used,
            cache_hit=self.cache_hit,
            output_size=self.output_size,
        )
        return False  # Don't suppress exceptions

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


def compare_profiles(
    profile1: WorkflowProfile,
    profile2: WorkflowProfile,
) -> dict:
    """
    Compare two workflow profiles.

    Useful for A/B testing or comparing before/after optimization.

    Returns:
        Dictionary with comparison results
    """
    return {
        "duration_change_ms": profile2.total_duration_ms - profile1.total_duration_ms,
        "duration_change_pct": (
            (profile2.total_duration_ms - profile1.total_duration_ms)
            / profile1.total_duration_ms
            * 100
            if profile1.total_duration_ms > 0
            else 0
        ),
        "token_change": profile2.total_tokens - profile1.total_tokens,
        "retry_change": profile2.total_retries - profile1.total_retries,
        "cache_hit_rate_change": profile2.cache_hit_rate - profile1.cache_hit_rate,
        "efficiency_change": profile2.parallel_efficiency
        - profile1.parallel_efficiency,
        "profile1": {
            "run_id": profile1.run_id,
            "total_duration_ms": profile1.total_duration_ms,
            "total_tokens": profile1.total_tokens,
        },
        "profile2": {
            "run_id": profile2.run_id,
            "total_duration_ms": profile2.total_duration_ms,
            "total_tokens": profile2.total_tokens,
        },
    }
