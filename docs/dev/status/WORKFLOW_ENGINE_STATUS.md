# Workflow Engine Implementation Progress

## Phase 1, 2, 3, 4 & 5 Complete ✅

### Core Components Created

```
backend/app/services/workflow/
├── __init__.py           # Package exports
├── errors.py             # Error classes (11 types)
├── context.py            # ExecutionContext (Redis state management)
├── executor.py           # NodeExecutor base class + Registry
├── plan.py               # ExecutionPlan (DAG parsing, topological sort)
├── stream.py             # StreamManager (SSE streaming)
├── orchestrator.py       # WorkflowOrchestrator (main entry point)
├── tasks.py              # Celery distributed tasks ✨
├── retry.py              # Retry mechanism & circuit breaker ✨
├── cache.py              # Caching layer ✨ (Phase 4)
├── metrics.py            # Metrics collection ✨ (Phase 4)
├── profiler.py           # Performance profiling ✨ (Phase 4)
├── versioning.py         # Version control ✨ (Phase 5)
├── debugger.py           # Advanced debugging ✨ (Phase 5)
├── templates.py          # Workflow templates ✨ (Phase 5)
├── benchmark.py          # Load testing tools ✨ (Phase 5)
└── executors/
    ├── __init__.py       # Auto-imports all executors
    ├── start.py          # user_input, trigger nodes
    ├── answer.py         # answer (output) node
    ├── llm.py            # LLM node
    ├── condition.py      # condition, question_classifier nodes
    ├── code.py           # code node (sandboxed Python)
    ├── template.py       # template node
    ├── variable.py       # variable_assignment, variable_aggregator, parameter_extractor
    ├── iteration.py      # iteration, loop nodes
    ├── tool.py           # tool, agent, http_request nodes
    ├── subworkflow.py    # sub_workflow, file_to_url nodes
    └── knowledge.py      # knowledge_retrieval, document_extractor nodes
```

### API Endpoints Added

**Workflow Execution:**
- `POST /api/v1/workflows/{id}/run` - Run published workflow
- `POST /api/v1/workflows/{id}/debug` - Debug workflow (draft)
- `GET /api/v1/workflows/runs/{id}/stream` - SSE event stream
- `POST /api/v1/workflows/runs/{id}/cancel` - Cancel running workflow

**Monitoring (Phase 4):**
- `GET /api/v1/workflows/metrics/dashboard` - Dashboard summary
- `GET /api/v1/workflows/metrics/workflows/{id}` - Workflow metrics
- `GET /api/v1/workflows/metrics/nodes` - Node type metrics
- `GET /api/v1/workflows/metrics/running` - Running workflows
- `GET /api/v1/workflows/metrics/cache` - Cache statistics

**Version Control (Phase 5):**
- `POST /api/v1/workflow-versions` - Create new version
- `GET /api/v1/workflow-versions/{workflow_id}/history` - Version history
- `GET /api/v1/workflow-versions/{workflow_id}/version/{version_id}` - Get version
- `POST /api/v1/workflow-versions/{workflow_id}/version/{version_id}/publish` - Publish
- `POST /api/v1/workflow-versions/{workflow_id}/version/{version_id}/archive` - Archive
- `GET /api/v1/workflow-versions/{workflow_id}/diff` - Version diff
- `POST /api/v1/workflow-versions/{workflow_id}/rollback` - Rollback
- `POST /api/v1/workflow-versions/{workflow_id}/fork` - Fork workflow

**Templates (Phase 5):**
- `GET /api/v1/workflow-templates` - List templates
- `GET /api/v1/workflow-templates/featured` - Featured templates
- `GET /api/v1/workflow-templates/search` - Search templates
- `GET /api/v1/workflow-templates/categories` - Template categories
- `GET /api/v1/workflow-templates/{id}` - Get template
- `POST /api/v1/workflow-templates` - Create template
- `POST /api/v1/workflow-templates/{id}/instantiate` - Instantiate template
- `POST /api/v1/workflow-templates/{id}/rate` - Rate template
- `DELETE /api/v1/workflow-templates/{id}` - Delete template

### All Node Types Implemented (17/17) ✅

| Node Type | File | Description |
|-----------|------|-------------|
| user_input | start.py | Start node with input variables |
| trigger | start.py | Scheduled/webhook trigger |
| answer | answer.py | Output node |
| llm | llm.py | LLM inference with streaming |
| condition | condition.py | Conditional branching |
| question_classifier | condition.py | LLM-based classification |
| code | code.py | Sandboxed Python execution |
| template | template.py | Text templating |
| variable_assignment | variable.py | Variable assignment |
| variable_aggregator | variable.py | Combine variables |
| parameter_extractor | variable.py | LLM-based extraction |
| iteration | iteration.py | Array iteration |
| loop | iteration.py | While loop |
| tool | tool.py | Tool execution |
| agent | tool.py | Agent invocation |
| http_request | tool.py | HTTP API calls |
| sub_workflow | subworkflow.py | Nested workflow execution |
| file_to_url | subworkflow.py | File URL conversion |
| knowledge_retrieval | knowledge.py | Knowledge base search |
| document_extractor | knowledge.py | Document content extraction |

## Next Steps (Phase 6+)

1. **Production hardening** - Connection pooling, graceful shutdown
2. **Multi-tenancy optimization** - Resource isolation per team
3. **Workflow analytics dashboard** - Visual metrics display
4. **A/B testing for workflows** - Traffic splitting between versions

## Unit Tests ✅

```
backend/tests/services/workflow/
├── __init__.py
├── test_executor.py       # NodeExecutor, Registry tests
├── test_context.py        # ExecutionContext tests
├── test_plan.py           # ExecutionPlan tests
├── test_retry.py          # RetryPolicy, CircuitBreaker tests
├── test_executors.py      # Individual executor tests
└── test_orchestrator.py   # WorkflowOrchestrator tests
```

Run tests with:
```bash
cd backend
pytest tests/services/workflow/ -v
```

## Phase 3 Features

### Celery Distributed Tasks

```python
from app.services.workflow.tasks import execute_workflow_task

# Async workflow execution
task = execute_workflow_task.delay(
    workflow_id=str(workflow_id),
    inputs={"query": "Hello"},
    user_id=str(user_id),
)

# Get result
result = task.get(timeout=300)
```

**Task Types:**
- `execute_workflow_task` - Main async workflow execution
- `execute_node_task` - Single node execution with retry
- `execute_stage_task` - Parallel stage execution using Celery groups
- `cancel_workflow_task` - Cancel running workflow
- `cleanup_workflow_task` - Clean up workflow state after completion
- `check_scheduled_workflows` - Cron trigger checking (beat task)
- `cleanup_old_runs` - Old run cleanup (daily beat task)

### Retry Mechanism

```python
from app.services.workflow.retry import RetryPolicy, RetryableExecutor

# Custom retry policy
policy = RetryPolicy(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
)

# Wrap executor with retry
executor = NodeExecutorRegistry.get("llm")
retryable = RetryableExecutor(executor, policy)
result = await retryable.execute(node, context, run)
```

**Default Policies per Node Type:**
| Node Type | Max Retries | Base Delay | Reason |
|-----------|-------------|------------|--------|
| llm | 3 | 1.0s | Transient API errors |
| http_request | 3 | 1.0s | Network issues |
| tool | 2 | 0.5s | External service failures |
| agent | 2 | 1.0s | Agent API errors |
| knowledge_retrieval | 2 | 0.5s | Vector DB issues |
| code | 0 | - | Deterministic, no retry |
| condition | 0 | - | Deterministic, no retry |
| template | 0 | - | Deterministic, no retry |

### Circuit Breaker

```python
from app.services.workflow.retry import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_requests=3,
)

if await breaker.can_execute():
    try:
        result = await some_operation()
        await breaker.record_success()
    except Exception as e:
        await breaker.record_failure()
        raise
else:
    raise Exception("Circuit breaker is open")
```

**States:**
- `closed` - Normal operation
- `open` - Too many failures, reject requests
- `half_open` - Testing recovery with limited requests

### Iteration/Loop State Machine

The orchestrator now handles iteration and loop nodes with a state machine:

1. Execute iteration/loop node to get first item or check condition
2. If not complete, execute body nodes (downstream nodes)
3. Re-execute iteration/loop node
4. Repeat until complete

This allows for proper loop execution within the DAG-based execution model.

## Phase 4 Features

### Caching Layer

```python
from app.services.workflow.cache import WorkflowCache, get_workflow_cache

cache = get_workflow_cache()

# Cache workflow definition
await cache.set_workflow(workflow_id, definition)
cached = await cache.get_workflow(workflow_id)

# Cache execution plan
await cache.set_plan(workflow_id, definition, plan)
cached_plan = await cache.get_plan(workflow_id, definition)

# Cache LLM responses (for identical prompts)
await cache.set_llm_response(model, messages, response)
cached_response = await cache.get_llm_response(model, messages)

# Get cache statistics
stats = await cache.get_stats()
```

**Cache Types:**
| Cache Type | TTL | Description |
|------------|-----|-------------|
| workflow_definition | 5 min | Workflow JSON definition |
| execution_plan | 5 min | Parsed DAG execution plan |
| node_result | 1 min | Deterministic node outputs |
| llm_response | 1 hour | LLM responses for identical prompts |
| tool_result | 5 min | External tool results |

### Metrics Collection

```python
from app.services.workflow.metrics import MetricsCollector, get_metrics_collector

metrics = get_metrics_collector()

# Get workflow metrics
wf_metrics = await metrics.get_workflow_metrics(
    workflow_id,
    time_range_minutes=60,
)
print(f"Success rate: {1 - wf_metrics.error_rate:.2%}")
print(f"P95 latency: {wf_metrics.p95_duration_ms}ms")

# Get node type metrics
node_metrics = await metrics.get_node_metrics("llm")
print(f"Avg duration: {node_metrics.avg_duration_ms}ms")

# Get dashboard summary
summary = await metrics.get_dashboard_summary()
```

**Metrics Collected:**
- Execution counts (total, success, failed, cancelled)
- Duration percentiles (p50, p95, p99)
- Throughput (runs/minute)
- Error rates and types
- Node execution statistics
- Retry counts

### Performance Profiler

```python
from app.services.workflow.profiler import ExecutionProfiler

# Enable profiling in orchestrator
orchestrator = WorkflowOrchestrator(enable_profiling=True)
run_id = await orchestrator.run(...)

# Or use profiler directly
profiler = ExecutionProfiler(run_id, workflow_id)
profiler.start()

with profiler.node(node_id, "llm") as np:
    result = await executor.execute(...)
    np.tokens_used = 150
    np.cache_hit = False

profile = profiler.finish()
print(f"Slowest node: {profile.slowest_node_id}")
print(f"Bottlenecks: {profile.bottlenecks}")
print(f"Suggestions: {profile.suggestions}")
```

**Profiler Features:**
- Node-level timing breakdown
- Bottleneck detection
- Parallel efficiency calculation
- Cache hit rate tracking
- Optimization suggestions

## Phase 5 Features

### Version Control System

```python
from app.services.workflow.versioning import get_version_manager

manager = get_version_manager()

# Create a new version
version = await manager.create_version(
    workflow_id="wf_123",
    nodes=[...],
    edges=[...],
    description="Added new error handling",
    created_by="user_id",
)

# Get version history
history = await manager.get_history(workflow_id, limit=20)

# Publish a version
await manager.publish_version(workflow_id, version.version_id)

# Compare versions
diff = await manager.diff(workflow_id, v1_id, v2_id)
print(f"Nodes added: {diff.nodes_added}")
print(f"Nodes removed: {diff.nodes_removed}")

# Rollback to previous version
result = await manager.rollback(
    workflow_id,
    target_version_id,
    created_by="user_id",
    create_backup=True,
)

# Fork workflow
new_version = await manager.fork(
    source_workflow_id="wf_123",
    source_version_id=version.version_id,
    new_workflow_id="wf_456",
    created_by="user_id",
)
```

**Version Features:**
- Semantic versioning (major.minor.patch)
- Content hash for change detection
- Status management (draft, published, archived, deprecated)
- Full diff generation (nodes, edges, config)
- Rollback with optional backup
- Workflow forking

### Advanced Debugger

```python
from app.services.workflow.debugger import get_debugger, BreakpointType

debugger = get_debugger()

# Create debug session
session = await debugger.create_session(run_id, workflow_id)

# Add breakpoints
await debugger.add_breakpoint(
    session.session_id,
    node_id="llm_1",
    breakpoint_type=BreakpointType.NODE,
)

# Add conditional breakpoint
await debugger.add_breakpoint(
    session.session_id,
    condition="error_count > 3",
    breakpoint_type=BreakpointType.CONDITION,
)

# When paused, inspect variables
variables = await debugger.get_variables(session.session_id)

# Evaluate expression
result = await debugger.evaluate_expression(
    session.session_id,
    "len(results)",
)

# Time-travel debugging
await debugger.goto_frame(session.session_id, frame_index=5)
await debugger.step_back(session.session_id)
await debugger.step_forward(session.session_id)

# Get execution path
path = await debugger.get_execution_path(session.session_id)

# Resume execution
await debugger.resume(session.session_id, action=DebugAction.CONTINUE)
```

**Debugger Features:**
- Breakpoint management (node, conditional, error, output)
- Step-by-step execution control
- Variable inspection at any frame
- Watch expressions
- Time-travel debugging (navigate history)
- Execution path visualization
- Call stack tracking

### Workflow Templates

```python
from app.services.workflow.templates import (
    get_template_manager,
    TemplateCategory,
    TemplateVisibility,
)

manager = get_template_manager()

# List templates
templates = await manager.list_templates(
    category=TemplateCategory.CUSTOMER_SERVICE,
    visibility=TemplateVisibility.PUBLIC,
)

# Search templates
results = await manager.search("customer support")

# Get featured templates
featured = await manager.get_featured(limit=10)

# Create template
template = await manager.create_template(
    name="Customer Support Bot",
    description="AI-powered customer support workflow",
    category=TemplateCategory.CUSTOMER_SERVICE,
    visibility=TemplateVisibility.PUBLIC,
    author_id=user_id,
    author_name="John Doe",
    nodes=[...],
    edges=[...],
    variables=[
        TemplateVariable(
            name="model_id",
            label="LLM Model",
            variable_type="model",
            required=True,
        ),
    ],
    tags=["support", "customer"],
    icon="💬",
)

# Instantiate template
workflow_def = await manager.instantiate(
    template_id=template.id,
    variables={"model_id": "gpt-4"},
    workflow_name="My Support Bot",
)

# Rate template
await manager.rate_template(template.id, user_id, rating=5)
```

**Built-in Templates:**
| Template | Category | Description |
|----------|----------|-------------|
| Simple Q&A Bot | General | Basic LLM question answering |
| RAG Knowledge Bot | Research | Knowledge base powered Q&A |
| Intent Router | Customer Service | Route by detected intent |
| Code Review Assistant | Code | Parallel multi-perspective review |

**Template Features:**
- Category-based organization
- Variable-based customization
- Rating and usage tracking
- Search and discovery
- Built-in templates for common patterns

### Load Testing & Benchmarking

```python
from app.services.workflow.benchmark import (
    WorkflowBenchmark,
    BenchmarkConfig,
    run_quick_benchmark,
    compare_benchmarks,
)

benchmark = WorkflowBenchmark()

# Quick benchmark
async def run_workflow(inputs):
    return await orchestrator.run(workflow_id, inputs)

result = await run_quick_benchmark(
    executor=run_workflow,
    inputs={"query": "test"},
    iterations=100,
)
print(f"Mean latency: {result['mean_latency_ms']}ms")
print(f"RPS: {result['requests_per_second']}")

# Full benchmark
config = BenchmarkConfig(
    concurrent_users=10,
    requests_per_user=100,
    ramp_up_seconds=10,
    requests_per_second=50,  # Rate limiting
    request_timeout=60,
)

result = await benchmark.run(
    name="load_test",
    executor=run_workflow,
    inputs_generator=lambda: {"query": f"test_{random.randint(1,100)}"},
    config=config,
)

print(result.to_summary())
# === Benchmark Results ===
# Duration: 120.5s
# Requests: Total 1000, Success 995 (99.5%)
# Latency: Mean 150ms, P95 320ms, P99 500ms
# Throughput: 8.3 req/s

# Compare implementations
results = await compare_benchmarks(
    executors={
        "v1": run_workflow_v1,
        "v2": run_workflow_v2,
    },
    inputs_generator=lambda: {"query": "test"},
    config=config,
)
```

**Benchmark Features:**
- Concurrent user simulation
- Configurable ramp-up period
- Rate limiting support
- Latency percentiles (p50, p90, p95, p99)
- Throughput measurement
- Error breakdown
- Implementation comparison

### Monitoring API Endpoints

New API endpoints for workflow monitoring:

```
GET /api/v1/workflows/metrics/dashboard
    - Dashboard summary with overall metrics

GET /api/v1/workflows/metrics/workflows/{workflow_id}
    - Detailed metrics for a specific workflow

GET /api/v1/workflows/metrics/nodes
    - Metrics for all node types

GET /api/v1/workflows/metrics/nodes/{node_type}
    - Metrics for a specific node type

GET /api/v1/workflows/metrics/running
    - List of currently running workflows

GET /api/v1/workflows/metrics/cache
    - Cache statistics

DELETE /api/v1/workflows/metrics/cache
    - Clear all workflow caches
```

## Usage Example

```python
from app.services.workflow import WorkflowOrchestrator

# Create orchestrator with all features enabled
orchestrator = WorkflowOrchestrator(
    timeout=300,
    enable_retry=True,
    enable_cache=True,
    enable_metrics=True,
    enable_profiling=True,  # Enable for debugging
)

# Run a workflow
run_id = await orchestrator.run(
    workflow_id=uuid,
    inputs={"query": "Hello world"},
    user_id=user_id,
    team_id=team_id,
)

# Stream events
from app.services.workflow.stream import stream_to_sse
async for event in stream_to_sse(run_id):
    print(event)
```

## Architecture Notes

- **Redis**: State management (variables, outputs, branches, cache, metrics)
- **Celery**: Distributed task execution
- **SSE**: Real-time streaming via Pub/Sub
- **DAG**: Topological sort for execution order
- **Branching**: Handle-based routing for condition nodes
- **Depth Tracking**: Max depth of 5 for nested workflows
- **Caching**: Multi-level caching (local + Redis)
- **Metrics**: Time-series metrics with percentile calculations
