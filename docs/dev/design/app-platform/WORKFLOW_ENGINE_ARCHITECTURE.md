# 工作流执行引擎架构设计

## 一、设计目标

1. **可扩展性** - 支持分布式部署，横向扩展
2. **可靠性** - 任务持久化、失败重试、断点恢复
3. **实时性** - 流式输出、实时状态更新
4. **可观测性** - 完整的执行日志、监控指标
5. **灵活性** - 易于添加新节点类型

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  API Layer                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Run API     │  │ Debug API   │  │ Webhook API │  │ WebSocket/SSE API   │ │
│  │ POST /run   │  │ POST /debug │  │ POST /hook  │  │ GET /stream         │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Orchestration Layer                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Workflow Orchestrator                          │    │
│  │  - 解析工作流定义                                                    │    │
│  │  - 构建执行计划（DAG 拓扑排序）                                       │    │
│  │  - 调度节点执行任务                                                  │    │
│  │  - 管理执行状态                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                        │                                     │
│                    ┌───────────────────┼───────────────────┐                │
│                    ▼                   ▼                   ▼                │
│  ┌─────────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   Sync Executor     │  │  Celery Tasks   │  │   State Manager         │  │
│  │ (调试/简单工作流)    │  │ (分布式执行)    │  │ (Redis 状态管理)         │  │
│  └─────────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Execution Layer                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      Node Executor Registry                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ LLM      │ │ Code     │ │ Condition│ │ Tool     │ │ Iteration│   │   │
│  │  │ Executor │ │ Executor │ │ Executor │ │ Executor │ │ Executor │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                        │                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      Execution Context                               │   │
│  │  - 变量存储（Redis Hash）                                            │   │
│  │  - 节点输出映射                                                      │   │
│  │  - 系统变量注入                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Infrastructure Layer                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │   PostgreSQL  │  │     Redis     │  │    Celery     │  │  LLM Manager │  │
│  │   (持久化)    │  │ (状态/缓存)   │  │  (任务队列)   │  │  (模型调用)   │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心组件设计

### 3.1 Workflow Orchestrator（编排器）

负责工作流的整体调度和协调。

```python
# backend/app/services/workflow/orchestrator.py

class WorkflowOrchestrator:
    """工作流编排器 - 负责解析和调度执行"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.executor_registry = NodeExecutorRegistry()
        
    async def run(
        self,
        workflow: Workflow,
        inputs: dict[str, Any],
        user: User | None = None,
        is_debug: bool = False,
        distributed: bool = True,
    ) -> WorkflowRun:
        """
        执行工作流
        
        Args:
            workflow: 工作流定义
            inputs: 输入参数
            user: 触发用户
            is_debug: 是否调试模式
            distributed: 是否使用分布式执行
        """
        # 1. 创建运行记录
        run = await self._create_run(workflow, inputs, user, is_debug)
        
        # 2. 解析工作流，构建执行计划
        execution_plan = self._build_execution_plan(workflow.definition)
        
        # 3. 初始化执行上下文
        context = await ExecutionContext.create(run.id, self.redis)
        await context.set_inputs(inputs)
        
        # 4. 选择执行模式
        if distributed and not is_debug:
            # 分布式模式：提交到 Celery
            await self._dispatch_distributed(run, execution_plan, context)
        else:
            # 同步模式：本地执行（调试或简单工作流）
            await self._execute_sync(run, execution_plan, context)
            
        return run
        
    def _build_execution_plan(self, definition: dict) -> ExecutionPlan:
        """
        构建执行计划
        
        1. 解析节点和边
        2. 构建 DAG
        3. 拓扑排序确定执行顺序
        4. 识别并行执行的机会
        """
        nodes = definition['nodes']
        edges = definition['edges']
        
        # 构建邻接表
        graph = self._build_graph(nodes, edges)
        
        # 拓扑排序 + 层级划分（同层可并行）
        levels = self._topological_sort_with_levels(graph)
        
        return ExecutionPlan(
            nodes={n['id']: n for n in nodes},
            edges=edges,
            levels=levels,
            graph=graph,
        )
```

### 3.2 Execution Context（执行上下文）

分布式环境下的变量共享和状态管理。

```python
# backend/app/services/workflow/context.py

class ExecutionContext:
    """
    执行上下文 - 管理工作流执行期间的状态
    
    使用 Redis 存储，支持分布式访问：
    - workflow:run:{run_id}:variables  - 变量存储 (Hash)
    - workflow:run:{run_id}:outputs    - 节点输出 (Hash, JSON encoded)
    - workflow:run:{run_id}:status     - 运行状态 (String)
    - workflow:run:{run_id}:stream     - 流式输出通道 (Pub/Sub)
    """
    
    VARIABLES_KEY = "workflow:run:{run_id}:variables"
    OUTPUTS_KEY = "workflow:run:{run_id}:outputs"
    STATUS_KEY = "workflow:run:{run_id}:status"
    STREAM_KEY = "workflow:run:{run_id}:stream"
    
    def __init__(self, run_id: str, redis: Redis):
        self.run_id = run_id
        self.redis = redis
        
    @classmethod
    async def create(cls, run_id: str, redis: Redis) -> "ExecutionContext":
        """创建新的执行上下文"""
        ctx = cls(run_id, redis)
        await ctx._init_keys()
        return ctx
        
    @classmethod
    async def load(cls, run_id: str, redis: Redis) -> "ExecutionContext":
        """加载已有的执行上下文（用于分布式 worker）"""
        return cls(run_id, redis)
        
    # ========== 变量管理 ==========
    
    async def set_variable(self, name: str, value: Any):
        """设置全局变量"""
        key = self.VARIABLES_KEY.format(run_id=self.run_id)
        await self.redis.hset(key, name, json.dumps(value))
        
    async def get_variable(self, name: str) -> Any:
        """获取全局变量"""
        key = self.VARIABLES_KEY.format(run_id=self.run_id)
        value = await self.redis.hget(key, name)
        return json.loads(value) if value else None
        
    # ========== 节点输出管理 ==========
    
    async def set_node_outputs(self, node_id: str, outputs: dict[str, Any]):
        """保存节点输出"""
        key = self.OUTPUTS_KEY.format(run_id=self.run_id)
        await self.redis.hset(key, node_id, json.dumps(outputs))
        
    async def get_node_outputs(self, node_id: str) -> dict[str, Any] | None:
        """获取节点输出"""
        key = self.OUTPUTS_KEY.format(run_id=self.run_id)
        value = await self.redis.hget(key, node_id)
        return json.loads(value) if value else None
        
    async def resolve_variable_ref(self, ref: str) -> Any:
        """
        解析变量引用
        
        格式: {{node_id.variable_name}} 或 {{sys.xxx}}
        """
        import re
        
        # 处理多个变量引用
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace_var(match):
            var_path = match.group(1)
            parts = var_path.split('.', 1)
            
            if len(parts) == 2:
                source, var_name = parts
                if source == 'sys':
                    return self._get_system_variable(var_name)
                else:
                    outputs = await self.get_node_outputs(source)
                    return outputs.get(var_name) if outputs else None
            return match.group(0)
            
        # 如果整个字符串就是一个变量引用，返回原始值
        if re.fullmatch(pattern, ref):
            var_path = ref[2:-2]
            parts = var_path.split('.', 1)
            if len(parts) == 2:
                source, var_name = parts
                if source == 'sys':
                    return self._get_system_variable(var_name)
                outputs = await self.get_node_outputs(source)
                return outputs.get(var_name) if outputs else None
                
        # 否则进行字符串替换
        result = ref
        for match in re.finditer(pattern, ref):
            var_path = match.group(1)
            parts = var_path.split('.', 1)
            if len(parts) == 2:
                source, var_name = parts
                if source == 'sys':
                    value = self._get_system_variable(var_name)
                else:
                    outputs = await self.get_node_outputs(source)
                    value = outputs.get(var_name) if outputs else ''
                result = result.replace(match.group(0), str(value))
                
        return result
        
    # ========== 流式输出 ==========
    
    async def publish_stream(self, event: StreamEvent):
        """发布流式事件到 Redis Pub/Sub"""
        key = self.STREAM_KEY.format(run_id=self.run_id)
        await self.redis.publish(key, event.model_dump_json())
        
    async def subscribe_stream(self) -> AsyncIterator[StreamEvent]:
        """订阅流式事件"""
        key = self.STREAM_KEY.format(run_id=self.run_id)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(key)
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                yield StreamEvent.model_validate_json(message['data'])
                
    # ========== TTL 管理 ==========
    
    async def set_ttl(self, seconds: int = 86400):
        """设置上下文过期时间（默认24小时）"""
        for key_pattern in [self.VARIABLES_KEY, self.OUTPUTS_KEY, self.STATUS_KEY]:
            key = key_pattern.format(run_id=self.run_id)
            await self.redis.expire(key, seconds)
```

### 3.3 Node Executor（节点执行器）

每种节点类型的执行逻辑。

```python
# backend/app/services/workflow/executor.py

from abc import ABC, abstractmethod
from typing import Any

class NodeExecutor(ABC):
    """节点执行器基类"""
    
    # 节点类型标识
    node_type: str = ""
    
    @abstractmethod
    async def execute(
        self,
        node: dict,
        context: ExecutionContext,
        run: WorkflowRun,
    ) -> ExecutionResult:
        """
        执行节点
        
        Args:
            node: 节点定义 {id, type, data, position}
            context: 执行上下文
            run: 工作流运行记录
            
        Returns:
            ExecutionResult 包含:
            - outputs: 输出变量字典
            - next_handles: 激活的输出句柄列表（用于分支节点）
            - stream_events: 流式事件列表（可选）
        """
        pass
        
    async def resolve_inputs(
        self,
        config: dict,
        context: ExecutionContext,
        input_mappings: list[dict],
    ) -> dict[str, Any]:
        """解析输入变量映射"""
        inputs = {}
        for mapping in input_mappings:
            name = mapping['name']
            source = mapping.get('source', 'variable')
            
            if source == 'variable':
                ref = mapping.get('variableRef', '')
                inputs[name] = await context.resolve_variable_ref(ref)
            else:  # constant
                inputs[name] = mapping.get('constantValue', '')
                
        return inputs


class ExecutionResult:
    """节点执行结果"""
    outputs: dict[str, Any]           # 输出变量
    next_handles: list[str] | None    # 激活的输出句柄（分支节点用）
    stream_events: list[StreamEvent]  # 流式事件
    error: str | None                 # 错误信息


# 节点执行器注册表
class NodeExecutorRegistry:
    """节点执行器注册表"""
    
    _executors: dict[str, type[NodeExecutor]] = {}
    
    @classmethod
    def register(cls, node_type: str):
        """装饰器：注册节点执行器"""
        def decorator(executor_cls: type[NodeExecutor]):
            cls._executors[node_type] = executor_cls
            return executor_cls
        return decorator
        
    @classmethod
    def get(cls, node_type: str) -> NodeExecutor:
        """获取节点执行器实例"""
        executor_cls = cls._executors.get(node_type)
        if not executor_cls:
            raise ValueError(f"Unknown node type: {node_type}")
        return executor_cls()
```

### 3.4 Celery Tasks（分布式任务）

使用 Celery 实现分布式节点执行。

```python
# backend/app/tasks/workflow.py

from celery import shared_task, chain, group, chord
from app.core.celery import celery_app

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def execute_node_task(
    self,
    run_id: str,
    node_id: str,
    node_type: str,
    node_data: dict,
) -> dict:
    """
    执行单个节点的 Celery 任务
    
    特点:
    - bind=True: 可以访问 self.retry()
    - acks_late=True: 任务完成后才确认，保证可靠性
    - 支持自动重试
    """
    import asyncio
    from app.services.workflow.context import ExecutionContext
    from app.services.workflow.executor import NodeExecutorRegistry
    from app.core.redis import get_redis
    
    async def _execute():
        redis = await get_redis()
        context = await ExecutionContext.load(run_id, redis)
        
        # 获取执行器
        executor = NodeExecutorRegistry.get(node_type)
        
        # 创建节点执行记录
        node_execution = await NodeExecution.create(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            node_name=node_data.get('label', ''),
            status=NodeStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        
        try:
            # 执行节点
            result = await executor.execute(
                node={'id': node_id, 'type': node_type, 'data': node_data},
                context=context,
                run=await WorkflowRun.get(id=run_id),
            )
            
            # 保存输出到上下文
            await context.set_node_outputs(node_id, result.outputs)
            
            # 更新执行记录
            node_execution.status = NodeStatus.SUCCESS
            node_execution.outputs = result.outputs
            node_execution.finished_at = datetime.utcnow()
            await node_execution.save()
            
            return {
                'node_id': node_id,
                'status': 'success',
                'outputs': result.outputs,
                'next_handles': result.next_handles,
            }
            
        except Exception as e:
            # 更新执行记录为失败
            node_execution.status = NodeStatus.FAILED
            node_execution.error_message = str(e)
            node_execution.finished_at = datetime.utcnow()
            await node_execution.save()
            
            # 重试或抛出异常
            raise self.retry(exc=e)
            
    return asyncio.run(_execute())


@celery_app.task
def execute_workflow_level(
    run_id: str,
    level_nodes: list[dict],
    previous_results: list[dict] | None = None,
) -> list[dict]:
    """
    执行工作流的一个层级（同层节点可并行）
    
    使用 Celery 的 chord 实现：
    - 同层节点并行执行
    - 全部完成后执行下一层
    """
    # 过滤掉不需要执行的节点（基于前一层的分支结果）
    nodes_to_execute = filter_nodes_by_branch_results(
        level_nodes, previous_results
    )
    
    # 创建并行任务组
    tasks = [
        execute_node_task.s(
            run_id=run_id,
            node_id=node['id'],
            node_type=node['type'],
            node_data=node['data'],
        )
        for node in nodes_to_execute
    ]
    
    # 使用 group 并行执行
    job = group(tasks)
    result = job.apply_async()
    
    # 等待所有任务完成
    return result.get()


@celery_app.task
def orchestrate_workflow(run_id: str, execution_plan: dict):
    """
    工作流编排任务 - 按层级调度执行
    
    使用 chain 串联各层级的执行
    """
    levels = execution_plan['levels']
    
    # 构建执行链
    task_chain = chain(
        execute_workflow_level.s(run_id, levels[0]),
        *[
            execute_workflow_level.s(run_id, level)
            for level in levels[1:]
        ]
    )
    
    # 启动执行链
    task_chain.apply_async()
```

### 3.5 Stream Manager（流式输出管理）

支持 SSE 实时推送执行状态和 LLM 输出。

```python
# backend/app/services/workflow/stream.py

from enum import Enum
from pydantic import BaseModel
from typing import Any

class StreamEventType(str, Enum):
    """流式事件类型"""
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    NODE_START = "node_start"
    NODE_OUTPUT = "node_output"      # LLM 输出 chunk
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    VARIABLE_UPDATE = "variable_update"


class StreamEvent(BaseModel):
    """流式事件"""
    type: StreamEventType
    run_id: str
    node_id: str | None = None
    node_type: str | None = None
    data: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StreamManager:
    """流式输出管理器"""
    
    def __init__(self, context: ExecutionContext):
        self.context = context
        
    async def emit_node_start(self, node_id: str, node_type: str):
        """发送节点开始事件"""
        await self.context.publish_stream(StreamEvent(
            type=StreamEventType.NODE_START,
            run_id=self.context.run_id,
            node_id=node_id,
            node_type=node_type,
        ))
        
    async def emit_node_output(self, node_id: str, chunk: str):
        """发送节点输出块（LLM 流式输出）"""
        await self.context.publish_stream(StreamEvent(
            type=StreamEventType.NODE_OUTPUT,
            run_id=self.context.run_id,
            node_id=node_id,
            data={'chunk': chunk},
        ))
        
    async def emit_node_end(self, node_id: str, outputs: dict):
        """发送节点完成事件"""
        await self.context.publish_stream(StreamEvent(
            type=StreamEventType.NODE_END,
            run_id=self.context.run_id,
            node_id=node_id,
            data={'outputs': outputs},
        ))
        
    async def emit_workflow_end(self, status: str, outputs: dict):
        """发送工作流完成事件"""
        await self.context.publish_stream(StreamEvent(
            type=StreamEventType.WORKFLOW_END,
            run_id=self.context.run_id,
            data={'status': status, 'outputs': outputs},
        ))
```

---

## 四、执行模式

### 4.1 同步执行（调试模式）

适用于：调试运行、简单工作流、需要断点的场景。

```python
async def _execute_sync(
    self,
    run: WorkflowRun,
    plan: ExecutionPlan,
    context: ExecutionContext,
):
    """同步执行 - 单进程顺序执行所有节点"""
    stream = StreamManager(context)
    
    for level in plan.levels:
        for node_id in level:
            node = plan.nodes[node_id]
            
            # 检查是否应该执行（分支条件）
            if not self._should_execute(node_id, context):
                continue
                
            # 发送开始事件
            await stream.emit_node_start(node_id, node['type'])
            
            # 执行节点
            executor = self.executor_registry.get(node['type'])
            result = await executor.execute(node, context, run)
            
            # 保存输出
            await context.set_node_outputs(node_id, result.outputs)
            
            # 发送完成事件
            await stream.emit_node_end(node_id, result.outputs)
            
            # 处理分支结果
            if result.next_handles:
                await context.set_active_branches(node_id, result.next_handles)
```

### 4.2 分布式执行

适用于：生产环境、长时间运行、需要横向扩展。

```python
async def _dispatch_distributed(
    self,
    run: WorkflowRun,
    plan: ExecutionPlan,
    context: ExecutionContext,
):
    """分布式执行 - 提交到 Celery 队列"""
    
    # 将执行计划序列化
    plan_dict = plan.to_dict()
    
    # 提交编排任务
    orchestrate_workflow.delay(
        run_id=str(run.id),
        execution_plan=plan_dict,
    )
    
    # 更新运行状态为进行中
    run.status = RunStatus.RUNNING
    run.started_at = datetime.utcnow()
    await run.save()
```

### 4.3 执行模式选择策略

```python
def _should_use_distributed(
    self,
    workflow: Workflow,
    is_debug: bool,
) -> bool:
    """决定是否使用分布式执行"""
    
    # 调试模式强制同步
    if is_debug:
        return False
        
    # 节点数量少于阈值，同步执行更快
    node_count = len(workflow.definition.get('nodes', []))
    if node_count < 5:
        return False
        
    # 包含需要长时间执行的节点类型
    long_running_types = {'llm', 'code', 'tool', 'sub_workflow'}
    has_long_running = any(
        n['type'] in long_running_types
        for n in workflow.definition.get('nodes', [])
    )
    
    return has_long_running
```

---

## 五、队列设计

### 5.1 Celery 队列配置

```python
# 队列配置
celery_app.conf.task_routes = {
    # 工作流编排任务 - 高优先级队列
    "app.tasks.workflow.orchestrate_workflow": {"queue": "workflow_orchestrate"},
    
    # 节点执行任务 - 按节点类型分队列
    "app.tasks.workflow.execute_node_task": {"queue": "workflow_nodes"},
    
    # LLM 节点单独队列（耗时长）
    "app.tasks.workflow.execute_llm_node": {"queue": "workflow_llm"},
    
    # 代码执行节点单独队列（需要沙箱）
    "app.tasks.workflow.execute_code_node": {"queue": "workflow_code"},
}

# 队列优先级
celery_app.conf.task_default_priority = 5
celery_app.conf.task_queue_max_priority = 10
```

### 5.2 Worker 配置建议

```bash
# 通用节点 worker
celery -A app.core.celery worker -Q workflow_nodes -c 4

# LLM 专用 worker（并发低，因为是 IO 密集）
celery -A app.core.celery worker -Q workflow_llm -c 10

# 代码执行 worker（需要沙箱隔离）
celery -A app.core.celery worker -Q workflow_code -c 2

# 编排 worker
celery -A app.core.celery worker -Q workflow_orchestrate -c 2
```

---

## 六、状态管理

### 6.1 Redis Key 设计

```
# 运行状态
workflow:run:{run_id}:status           # String: pending|running|success|failed
workflow:run:{run_id}:variables        # Hash: 全局变量
workflow:run:{run_id}:outputs          # Hash: 节点输出 (node_id -> JSON)
workflow:run:{run_id}:active_branches  # Hash: 激活的分支 (node_id -> handles[])

# 流式输出
workflow:run:{run_id}:stream           # Pub/Sub channel

# 调试模式
workflow:run:{run_id}:breakpoints      # Set: 断点节点 ID
workflow:run:{run_id}:paused_at        # String: 暂停在哪个节点

# 分布式锁
workflow:run:{run_id}:lock:{node_id}   # String: 节点执行锁

# TTL: 所有 key 默认 24 小时过期
```

### 6.2 状态机

```
                    ┌─────────┐
                    │ PENDING │
                    └────┬────┘
                         │ start
                         ▼
    ┌────────────────────────────────────────┐
    │                RUNNING                  │
    │  ┌──────────────────────────────────┐  │
    │  │         Node Execution           │  │
    │  │  PENDING → RUNNING → SUCCESS     │  │
    │  │                   ↘ FAILED       │  │
    │  │                   ↘ SKIPPED      │  │
    │  └──────────────────────────────────┘  │
    └────────────┬───────────────┬───────────┘
                 │               │
         success │               │ error
                 ▼               ▼
           ┌─────────┐     ┌─────────┐
           │ SUCCESS │     │ FAILED  │
           └─────────┘     └─────────┘
                 ↑               ↑
                 │               │
                 └───┬───────────┘
                     │ cancel
               ┌─────────┐
               │CANCELLED│
               └─────────┘
```

---

## 七、错误处理

### 7.1 重试策略

```python
class RetryPolicy:
    """重试策略配置"""
    
    # 默认重试配置
    DEFAULT = {
        'max_retries': 3,
        'retry_delay': 5,           # 秒
        'retry_backoff': True,      # 指数退避
        'retry_backoff_max': 60,    # 最大延迟
    }
    
    # 按节点类型的特殊配置
    BY_NODE_TYPE = {
        'llm': {
            'max_retries': 2,
            'retry_delay': 10,
            'retry_on': [RateLimitError, ProviderError],
        },
        'code': {
            'max_retries': 0,       # 代码错误不重试
        },
        'tool': {
            'max_retries': 3,
            'retry_delay': 5,
        },
    }
```

### 7.2 错误传播

```python
class ErrorHandling:
    """错误处理策略"""
    
    @staticmethod
    async def handle_node_error(
        node: dict,
        error: Exception,
        context: ExecutionContext,
        run: WorkflowRun,
    ) -> ErrorAction:
        """处理节点执行错误"""
        
        config = node['data'].get('errorHandling', {})
        error_type = config.get('type', 'none')
        
        if error_type == 'none':
            # 不处理，终止工作流
            return ErrorAction.ABORT
            
        elif error_type == 'default_value':
            # 使用默认值继续
            default = config.get('defaultValue', '')
            await context.set_node_outputs(node['id'], {'output': default})
            return ErrorAction.CONTINUE
            
        elif error_type == 'error_branch':
            # 走错误分支
            return ErrorAction.ERROR_BRANCH
```

---

## 八、监控与可观测性

### 8.1 指标采集

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# 运行计数
workflow_runs_total = Counter(
    'workflow_runs_total',
    'Total workflow runs',
    ['workflow_id', 'status', 'trigger_type']
)

# 运行耗时
workflow_duration_seconds = Histogram(
    'workflow_duration_seconds',
    'Workflow execution duration',
    ['workflow_id'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

# 节点执行计数
node_executions_total = Counter(
    'node_executions_total',
    'Total node executions',
    ['node_type', 'status']
)

# 当前运行中的工作流
workflow_runs_active = Gauge(
    'workflow_runs_active',
    'Currently running workflows'
)
```

### 8.2 日志规范

```python
import structlog

logger = structlog.get_logger()

# 工作流开始
logger.info(
    "workflow_started",
    run_id=run.id,
    workflow_id=workflow.id,
    trigger_type=trigger_type,
    inputs=inputs,
)

# 节点执行
logger.info(
    "node_executed",
    run_id=run.id,
    node_id=node_id,
    node_type=node_type,
    duration_ms=duration,
    status=status,
)

# 错误日志
logger.error(
    "node_failed",
    run_id=run.id,
    node_id=node_id,
    error=str(e),
    traceback=traceback.format_exc(),
)
```

---

## 九、API 设计

### 9.1 运行 API

```python
# POST /api/v1/workflows/{workflow_id}/run
@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: UUID,
    run_input: WorkflowRunInput,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    执行工作流
    
    Request Body:
    {
        "inputs": {"query": "hello"},
        "is_debug": false
    }
    
    Response:
    {
        "data": {
            "run_id": "xxx",
            "status": "pending"
        }
    }
    """
    pass

# POST /api/v1/workflows/{workflow_id}/run/stream
@router.post("/{workflow_id}/run/stream")
async def run_workflow_stream(
    workflow_id: UUID,
    run_input: WorkflowRunInput,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    流式执行工作流（SSE）
    
    Response: Server-Sent Events
    
    event: node_start
    data: {"node_id": "xxx", "node_type": "llm"}
    
    event: node_output
    data: {"node_id": "xxx", "chunk": "Hello"}
    
    event: node_end
    data: {"node_id": "xxx", "outputs": {...}}
    
    event: workflow_end
    data: {"status": "success", "outputs": {...}}
    """
    pass
```

### 9.2 调试 API

```python
# POST /api/v1/workflows/{workflow_id}/debug
@router.post("/{workflow_id}/debug")
async def debug_workflow(
    workflow_id: UUID,
    debug_input: WorkflowDebugInput,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    调试模式执行
    
    Request Body:
    {
        "inputs": {"query": "hello"},
        "breakpoints": ["node_1", "node_2"],
        "single_step": false
    }
    """
    pass

# POST /api/v1/workflows/runs/{run_id}/continue
@router.post("/runs/{run_id}/continue")
async def continue_debug(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
):
    """继续执行（从断点恢复）"""
    pass

# POST /api/v1/workflows/runs/{run_id}/step
@router.post("/runs/{run_id}/step")
async def step_debug(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
):
    """单步执行下一个节点"""
    pass

# POST /api/v1/workflows/runs/{run_id}/cancel
@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
):
    """取消执行"""
    pass
```

---

## 十、文件结构

```
backend/app/
├── services/
│   └── workflow/
│       ├── __init__.py
│       ├── orchestrator.py        # 工作流编排器
│       ├── context.py             # 执行上下文（Redis 状态管理）
│       ├── executor.py            # 节点执行器基类和注册表
│       ├── stream.py              # 流式输出管理
│       ├── plan.py                # 执行计划（DAG 解析）
│       ├── errors.py              # 错误定义
│       ├── executors/             # 各节点类型执行器
│       │   ├── __init__.py
│       │   ├── base.py            # 基类
│       │   ├── start.py           # user_input, trigger
│       │   ├── llm.py             # llm
│       │   ├── classifier.py      # question_classifier
│       │   ├── extractor.py       # parameter_extractor
│       │   ├── condition.py       # condition
│       │   ├── iteration.py       # iteration
│       │   ├── loop.py            # loop
│       │   ├── code.py            # code (sandbox)
│       │   ├── template.py        # template (Jinja2)
│       │   ├── tool.py            # tool
│       │   ├── agent.py           # agent
│       │   ├── sub_workflow.py    # sub_workflow
│       │   ├── variable.py        # aggregator, assignment
│       │   ├── file.py            # file_to_url
│       │   └── output.py          # answer
│       └── sandbox/               # 代码沙箱
│           ├── __init__.py
│           ├── python.py          # Python 沙箱
│           └── javascript.py      # JavaScript 沙箱
│
├── tasks/
│   └── workflow.py                # Celery 任务定义
│
├── api/v1/endpoints/
│   └── workflows.py               # 添加 run/debug API
│
└── schemas/
    └── workflow.py                # 添加运行相关的 schema
```

---

## 十一、实现阶段规划

### Phase 1: 基础框架（1-2 周）
- [ ] ExecutionContext 实现（Redis 状态管理）
- [ ] NodeExecutor 基类和注册表
- [ ] WorkflowOrchestrator 核心逻辑
- [ ] 同步执行模式
- [ ] 基础 API（/run, /runs/{id}）

### Phase 2: 核心节点（1-2 周）
- [ ] StartNodeExecutor (user_input, trigger)
- [ ] LLMNodeExecutor（集成现有 model_manager）
- [ ] ConditionNodeExecutor
- [ ] AnswerNodeExecutor
- [ ] 流式输出 SSE

### Phase 3: 分布式支持（1 周）
- [ ] Celery 任务定义
- [ ] 分布式执行模式
- [ ] 队列配置
- [ ] Worker 部署脚本

### Phase 4: 完整节点（2-3 周）
- [ ] CodeNodeExecutor（Python/JS 沙箱）
- [ ] ToolNodeExecutor
- [ ] TemplateNodeExecutor
- [ ] VariableAggregatorExecutor
- [ ] VariableAssignmentExecutor
- [ ] ParameterExtractorExecutor
- [ ] QuestionClassifierExecutor

### Phase 5: 高级功能（1-2 周）
- [ ] IterationNodeExecutor
- [ ] LoopNodeExecutor
- [ ] SubWorkflowNodeExecutor
- [ ] AgentNodeExecutor
- [ ] 调试模式（断点、单步）

### Phase 6: 触发器（1 周）
- [ ] Webhook 触发器
- [ ] Cron 定时任务（Celery Beat）
- [ ] 触发器管理 API

### Phase 7: 可观测性（1 周）
- [ ] Prometheus 指标
- [ ] 结构化日志
- [ ] 执行追踪

---

## 十二、技术选型说明

| 组件 | 选型 | 理由 |
|------|------|------|
| 任务队列 | Celery | 已在项目中使用，成熟稳定，支持任务编排 |
| 状态存储 | Redis | 高性能，支持 Pub/Sub，已集成 |
| 持久化 | PostgreSQL | 已使用 Tortoise ORM |
| 代码沙箱 | RestrictedPython / Docker | 安全执行用户代码 |
| 流式输出 | Redis Pub/Sub + SSE | 低延迟，支持分布式 |

---

## 十三、风险与挑战

1. **代码节点安全性** - 需要严格的沙箱隔离
2. **长时间运行的 LLM 调用** - 需要超时处理和取消机制
3. **分布式状态一致性** - 使用 Redis 分布式锁
4. **嵌套工作流深度** - 限制最大嵌套层级
5. **变量循环引用** - DAG 检测防止死循环
