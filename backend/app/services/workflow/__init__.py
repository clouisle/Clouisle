"""
Workflow execution engine.

This package provides the core components for executing visual workflows:
- WorkflowOrchestrator: Main entry point for running workflows
- ExecutionContext: Manages state during workflow execution
- NodeExecutor: Base class for node type implementations
"""

from .orchestrator import WorkflowOrchestrator
from .context import ExecutionContext
from .executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from .plan import ExecutionPlan, NodeDependency, ExecutionStage
from .stream import StreamManager, StreamEvent, StreamEventType
from .retry import RetryPolicy, RetryableExecutor, CircuitBreaker, with_retry
from .cache import WorkflowCache, CacheConfig, get_workflow_cache
from .metrics import MetricsCollector, WorkflowMetrics, NodeMetrics, get_metrics_collector
from .profiler import ExecutionProfiler, WorkflowProfile, NodeProfile
from .versioning import WorkflowVersionManager, WorkflowVersion, VersionDiff, get_version_manager
from .debugger import WorkflowDebugger, DebugSession, DebugFrame, Breakpoint, get_debugger
from .templates import TemplateManager, WorkflowTemplate, TemplateVariable, get_template_manager
from .benchmark import WorkflowBenchmark, BenchmarkConfig, BenchmarkResult, get_benchmark
from .errors import (
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
    NodeExecutionError,
    VariableNotFoundError,
    NodeTypeNotFoundError,
    ExecutionTimeoutError,
    ExecutionCancelledError,
    CyclicDependencyError,
    MaxDepthExceededError,
)

# Import executors to register them
from . import executors

__all__ = [
    # Orchestrator
    "WorkflowOrchestrator",
    # Context
    "ExecutionContext",
    # Executor
    "NodeExecutor",
    "NodeExecutorRegistry",
    "ExecutionResult",
    # Plan
    "ExecutionPlan",
    "NodeDependency",
    "ExecutionStage",
    # Stream
    "StreamManager",
    "StreamEvent",
    "StreamEventType",
    # Retry
    "RetryPolicy",
    "RetryableExecutor",
    "CircuitBreaker",
    "with_retry",
    # Cache
    "WorkflowCache",
    "CacheConfig",
    "get_workflow_cache",
    # Metrics
    "MetricsCollector",
    "WorkflowMetrics",
    "NodeMetrics",
    "get_metrics_collector",
    # Profiler
    "ExecutionProfiler",
    "WorkflowProfile",
    "NodeProfile",
    # Versioning
    "WorkflowVersionManager",
    "WorkflowVersion",
    "VersionDiff",
    "get_version_manager",
    # Debugger
    "WorkflowDebugger",
    "DebugSession",
    "DebugFrame",
    "Breakpoint",
    "get_debugger",
    # Templates
    "TemplateManager",
    "WorkflowTemplate",
    "TemplateVariable",
    "get_template_manager",
    # Benchmark
    "WorkflowBenchmark",
    "BenchmarkConfig",
    "BenchmarkResult",
    "get_benchmark",
    # Errors
    "WorkflowError",
    "WorkflowNotFoundError",
    "WorkflowNotPublishedError",
    "WorkflowValidationError",
    "NodeExecutionError",
    "VariableNotFoundError",
    "NodeTypeNotFoundError",
    "ExecutionTimeoutError",
    "ExecutionCancelledError",
    "CyclicDependencyError",
    "MaxDepthExceededError",
]
