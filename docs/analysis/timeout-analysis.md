# AI 流式生成对话超时时间分析报告

## 问题概述

本文档详细分析 Clouisle 项目中 AI 流式对话的超时实现策略，评估当前方案是否为最优解，并记录已落地的分阶段修复。

## 当前超时实现架构

### 1. 超时配置层级

当前系统实现了**三层超时机制**：

#### 1.1 全局配置层 (`backend/app/core/config.py`)

```python
# Streaming timeouts (seconds)
STREAM_GLOBAL_TIMEOUT: int = 3600  # 60 minutes - 整个对话的最大时长
STREAM_HEARTBEAT_INTERVAL: int = 15  # 15 seconds - 心跳间隔
STREAM_IDLE_TIMEOUT: int = 180  # max seconds between model stream chunks - 模型流空闲超时

# LLM HTTP client timeouts (seconds)
STREAM_HTTP_CONNECT_TIMEOUT: int = 10
STREAM_HTTP_READ_TIMEOUT: int = 200
STREAM_HTTP_REASONING_READ_TIMEOUT: int = 300
STREAM_HTTP_WRITE_TIMEOUT: int = 10
STREAM_GLOBAL_TIMEOUT_WITH_TOOLS: int = 5400  # 90 minutes

# Tool execution timeouts (seconds)
STREAM_TOOL_TIMEOUT_HTTP: int = 30   # HTTP 工具超时
STREAM_TOOL_TIMEOUT_CODE: int = 60   # 代码执行超时
STREAM_TOOL_TIMEOUT_MCP: int = 60    # MCP 工具超时
STREAM_TOOL_TIMEOUT_DOWNLOAD: int = 60  # 下载超时
```

#### 1.2 Agent 配置层 (`get_streaming_config`)

Agent 可以通过 `streaming_config` 字段覆盖全局配置：

```python
def get_streaming_config(agent: Agent) -> dict:
    """Get streaming configuration from agent or use defaults."""
    config = agent.streaming_config or {}
    
    return {
        "global_timeout": config.get("global_timeout", settings.STREAM_GLOBAL_TIMEOUT),
        "heartbeat_interval": config.get("heartbeat_interval", settings.STREAM_HEARTBEAT_INTERVAL),
        "idle_timeout": config.get("idle_timeout", settings.STREAM_IDLE_TIMEOUT),
        "tool_timeouts": {...}
    }
```

#### 1.3 模型适配器层 (`BaseChatAdapter.http_timeout`)

每个模型适配器可以配置自己的 HTTP 客户端超时：

```python
@property
def http_timeout(self) -> httpx.Timeout:
    """HTTP 客户端超时配置"""
    connect_timeout = self.get_effective_param("connect_timeout")
    read_timeout = self.get_effective_param("read_timeout")
    write_timeout = self.get_effective_param("write_timeout")
    legacy_timeout = self.get_effective_param("timeout")
    return httpx.Timeout(
        connect=float(connect_timeout) if connect_timeout is not None else settings.STREAM_HTTP_CONNECT_TIMEOUT,
        read=float(read_timeout or legacy_timeout) if read_timeout is not None or legacy_timeout is not None else settings.STREAM_HTTP_READ_TIMEOUT,
        write=float(write_timeout) if write_timeout is not None else settings.STREAM_HTTP_WRITE_TIMEOUT,
        pool=None,
    )
```

### 2. 超时实现机制

#### 2.1 全局超时 (Global Timeout)

**位置**: `backend/app/api/v1/endpoints/chat.py:1563`

```python
async with asyncio.timeout(global_timeout):  # 默认 1800 秒
    # 整个流式对话逻辑
```

**作用**: 
- 限制整个对话的最大时长（包括多轮工具调用）
- 超时后触发 `TimeoutError`，保存部分内容并返回错误

**问题**:
- ✅ 能防止无限挂起
- ⚠️ 30 分钟对于复杂任务可能不够（多轮工具调用、大量代码执行）
- ⚠️ 超时后用户体验较差，只能看到错误消息

#### 2.2 空闲超时 (Idle Timeout)

**位置**: `backend/app/api/v1/endpoints/chat_helpers/stream_utils.py:39`

```python
async def iter_with_idle_timeout(
    iterable: AsyncIterable[T],
    timeout_seconds: float,  # 默认 90 秒
    activity_predicate: Callable[[T], bool] | None = None,
) -> AsyncIterator[T]:
    iterator = iterable.__aiter__()
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StreamIdleTimeoutError
        try:
            item = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        except TimeoutError as e:
            raise StreamIdleTimeoutError from e
        # 如果有活动（activity_predicate 返回 True），重置 deadline
        if activity_predicate is None or activity_predicate(item):
            deadline = time.monotonic() + timeout_seconds
        yield item
```

**作用**:
- 监控模型流的活跃度
- 如果连续 90 秒没有有效输出（token、reasoning、tool_calls），触发超时
- 每次有活动时重置计时器

**活动判断逻辑** (`_is_model_stream_activity`):
```python
def _is_model_stream_activity(chunk: ChatStreamChunk) -> bool:
    delta = chunk.delta
    return bool(
        delta.content
        or delta.reasoning_content
        or delta.tool_calls
        or delta.stream_activity
        or chunk.finish_reason
    )
```

**问题**:
- ✅ 能检测模型卡死或网络中断
- ⚠️ **90 秒可能过短**：某些模型在思考复杂问题时可能长时间不输出
- ⚠️ 与全局超时存在重叠，可能导致混淆

#### 2.3 HTTP 客户端超时 (Model API Timeout)

**位置**: `backend/app/llm/adapters/chat/openai_adapter.py`

```python
client = AsyncOpenAI(
    api_key=self.api_key,
    base_url=self.base_url,
    timeout=self.timeout,  # 默认 60 秒
)
```

**作用**:
- 限制单次 HTTP 请求的超时时间
- 由 OpenAI SDK 内部的 httpx 客户端处理

**问题**:
- ⚠️ **60 秒对于流式调用可能不合适**：流式调用是长连接，不应该有固定的总超时
- ⚠️ 这个超时应该是**连接超时**或**读取超时**，而不是总超时
- ⚠️ 与空闲超时功能重叠

#### 2.4 心跳机制 (Heartbeat)

**位置**: `backend/app/api/v1/endpoints/chat.py:1701-1728`

```python
(should_continue, new_last_event_time) = await send_heartbeat_if_needed(
    last_event_time, heartbeat_interval, request
)
if not should_continue:
    # 客户端断开，保存当前状态并退出
    assistant_msg.is_manually_stopped = True
    await assistant_msg.save()
    return
```

**作用**:
- 每 15 秒检查客户端是否断开
- 如果断开，立即停止生成，保存部分内容

**问题**:
- ✅ 能及时检测客户端断开，节省资源
- ✅ 实现合理

## 问题分析

### 问题 1: 超时层级混乱，职责不清

当前有 **4 个不同的超时**：
1. **全局超时** (1800s) - 整个对话
2. **空闲超时** (90s) - 模型流活跃度
3. **HTTP 客户端超时** (60s) - 单次 API 请求
4. **工具超时** (30-60s) - 工具执行

**问题**:
- HTTP 客户端超时 (60s) < 空闲超时 (90s)，可能导致在空闲超时触发前就被 HTTP 超时中断
- 空闲超时和 HTTP 客户端超时功能重叠
- 用户和开发者难以理解哪个超时会先触发

### 问题 2: 空闲超时 90 秒可能过短

**场景**:
- 某些模型（如 o1、o3）在处理复杂问题时，可能长时间处于"思考"状态而不输出 token
- 如果模型 API 本身没有返回 `stream_activity` 心跳，90 秒后会被误判为超时

**建议**:
- 将空闲超时提高到 **180-300 秒**
- 或者根据模型类型动态调整（推理模型更长，普通模型更短）

### 问题 3: HTTP 客户端超时配置不当

**当前问题**:
```python
client = AsyncOpenAI(
    timeout=self.timeout,  # 60 秒
)
```

OpenAI SDK 的 `timeout` 参数实际上是 `httpx.Timeout` 对象，支持细粒度配置：
- `connect`: 连接超时
- `read`: 读取超时（两次数据之间的间隔）
- `write`: 写入超时
- `pool`: 连接池超时

**当前实现的问题**:
- 使用单一的 60 秒作为所有超时，不够灵活
- 对于流式调用，应该使用**读取超时**而不是总超时

**正确的配置应该是**:
```python
import httpx

client = AsyncOpenAI(
    timeout=httpx.Timeout(
        connect=10.0,      # 连接超时 10 秒
        read=90.0,         # 读取超时 90 秒（与空闲超时一致）
        write=10.0,        # 写入超时 10 秒
        pool=None,         # 连接池不超时
    )
)
```

### 问题 4: 全局超时 30 分钟可能不够

**场景**:
- 复杂的多轮工具调用任务（如代码生成、测试、调试）
- 大量文件处理
- 长时间运行的代码执行

**建议**:
- 提高到 **60 分钟 (3600s)**
- 或者允许 Agent 级别配置更长的超时

### 问题 5: 超时错误处理不够友好

**当前实现**:
```python
except StreamIdleTimeoutError:
    logger.warning("Stream idle timeout (%ss) for conversation %s", idle_timeout, conversation.id)
    await persist_partial_round_error(...)
    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
```

**问题**:
- 用户只能看到"超时"错误，不知道是哪种超时
- 没有提供重试或恢复的选项
- 部分内容虽然保存了，但用户体验不佳

## 最优解建议

### 方案 1: 简化超时层级（推荐）

**目标**: 减少超时层级，明确职责

#### 1.1 保留的超时

1. **全局超时** (Global Timeout)
   - 默认值: **3600 秒 (60 分钟)**
   - 作用: 防止整个对话无限挂起
   - 可配置: Agent 级别可覆盖

2. **读取超时** (Read Timeout)
   - 默认值: **180 秒 (3 分钟)**
   - 作用: 检测模型 API 连接中断或卡死
   - 位置: HTTP 客户端层
   - 配置方式:
     ```python
     timeout=httpx.Timeout(
         connect=10.0,
         read=180.0,  # 读取超时
         write=10.0,
     )
     ```

3. **工具超时** (Tool Timeout)
   - 保持现有配置 (30-60s)
   - 作用: 限制单个工具执行时间

#### 1.2 移除的超时

- **移除空闲超时** (`iter_with_idle_timeout`)
  - 理由: 功能与 HTTP 读取超时重叠
  - 替代: 依赖 HTTP 客户端的读取超时

#### 1.3 配置示例

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    # Streaming timeouts (seconds)
    STREAM_GLOBAL_TIMEOUT: int = 3600  # 60 minutes (提高)
    STREAM_HEARTBEAT_INTERVAL: int = 15  # 15 seconds
    
    # HTTP client timeouts (seconds)
    STREAM_HTTP_CONNECT_TIMEOUT: int = 10  # 连接超时
    STREAM_HTTP_READ_TIMEOUT: int = 180    # 读取超时（新增）
    STREAM_HTTP_WRITE_TIMEOUT: int = 10    # 写入超时
    
    # Tool execution timeouts (seconds)
    STREAM_TOOL_TIMEOUT_HTTP: int = 30
    STREAM_TOOL_TIMEOUT_CODE: int = 60
    STREAM_TOOL_TIMEOUT_MCP: int = 60
    STREAM_TOOL_TIMEOUT_DOWNLOAD: int = 60
```

```python
# backend/app/llm/adapters/chat/base.py
@property
def http_timeout(self) -> httpx.Timeout:
    """HTTP 客户端超时配置"""
    from app.core.config import settings
    
    return httpx.Timeout(
        connect=settings.STREAM_HTTP_CONNECT_TIMEOUT,
        read=settings.STREAM_HTTP_READ_TIMEOUT,
        write=settings.STREAM_HTTP_WRITE_TIMEOUT,
        pool=None,
    )
```

```python
# backend/app/llm/adapters/chat/openai_adapter.py
client = AsyncOpenAI(
    api_key=self.api_key,
    base_url=self.base_url,
    timeout=self.http_timeout,  # 使用细粒度超时配置
)
```

### 方案 2: 保留空闲超时但优化（备选）

如果需要保留空闲超时（用于更精细的控制），建议：

1. **提高空闲超时到 180 秒**
2. **HTTP 读取超时设置为 200 秒**（略高于空闲超时）
3. **明确优先级**: 空闲超时 < HTTP 读取超时 < 全局超时

### 方案 3: 动态超时（高级）

根据不同场景动态调整超时：

```python
def get_dynamic_timeout(agent: Agent, has_tools: bool) -> dict:
    """根据 Agent 配置动态计算超时"""
    base_timeout = 3600  # 基础 60 分钟
    
    # 如果启用了工具，增加超时
    if has_tools:
        base_timeout += 1800  # 额外 30 分钟
    
    # 如果是推理模型（o1/o3），增加读取超时
    read_timeout = 180
    if agent.model_id and ("o1" in agent.model_id or "o3" in agent.model_id):
        read_timeout = 300  # 5 分钟
    
    return {
        "global_timeout": base_timeout,
        "read_timeout": read_timeout,
    }
```

## 实施建议

### 优先级 P0（立即修复）

1. **修复 HTTP 客户端超时配置**
   - 将单一的 60 秒超时改为细粒度的 `httpx.Timeout`
   - 设置合理的读取超时（180 秒）

2. **提高全局超时到 60 分钟**
   - 避免复杂任务被过早中断

### 优先级 P1（短期优化）

3. **移除或优化空闲超时**
   - 方案 A: 移除 `iter_with_idle_timeout`，依赖 HTTP 读取超时
   - 方案 B: 提高空闲超时到 180 秒，并确保 HTTP 读取超时更高

4. **改进超时错误提示**
   - 区分不同类型的超时
   - 提供更友好的错误消息和重试建议

### 优先级 P2（长期优化）

5. **实现动态超时**
   - 根据模型类型、工具配置动态调整
   - 提供 Agent 级别的超时配置 UI

6. **添加超时监控和告警**
   - 记录超时事件到日志
   - 统计超时率，优化默认值

## 测试建议

### 测试场景

1. **正常流式对话**
   - 验证不会被误超时

2. **长时间思考的模型**
   - 使用 o1/o3 模型，验证不会在思考时超时

3. **多轮工具调用**
   - 验证复杂任务不会被全局超时中断

4. **网络中断模拟**
   - 验证读取超时能正确检测并处理

5. **客户端断开**
   - 验证心跳机制能及时检测并停止生成

### 测试方法

```python
# 模拟慢速模型响应
async def slow_model_stream():
    yield chunk1
    await asyncio.sleep(150)  # 模拟 150 秒无输出
    yield chunk2

# 验证超时行为
with pytest.raises(StreamIdleTimeoutError):
    async for chunk in iter_with_idle_timeout(slow_model_stream(), timeout_seconds=90):
        pass
```

## 总结

### 当前实现的问题

1. ❌ 超时层级过多，职责不清
2. ❌ HTTP 客户端超时配置不当（应使用细粒度配置）
3. ❌ 空闲超时 90 秒可能过短
4. ❌ 全局超时 30 分钟可能不够
5. ❌ 超时错误处理不够友好

### 推荐方案

**采用方案 2（保留空闲超时但优化，已落地）**:
- 全局超时: **3600 秒 (60 分钟)**
- 应用层空闲超时: **180 秒 (3 分钟)**
- HTTP 读取超时: **200 秒**，略高于应用层空闲超时，确保应用层能先给出可控错误
- HTTP 连接/写入超时: **10 秒**
- 保持工具超时不变

### 已完成阶段

1. ✅ **P0: HTTP 客户端超时配置**
   - `backend/app/llm/adapters/chat/base.py` 新增 `http_timeout`，使用 `httpx.Timeout` 区分 connect/read/write。
   - 所有 OpenAI-compatible/Anthropic/Ollama 等聊天适配器已从 `self.timeout` 切换到 `self.http_timeout`。
   - 旧的 `timeout` 模型参数继续作为 `read_timeout` 兼容入口。

2. ✅ **P0: 全局超时默认值**
   - `STREAM_GLOBAL_TIMEOUT` 从 1800 秒提高到 3600 秒。

3. ✅ **P1: 空闲超时默认值与优先级**
   - `STREAM_IDLE_TIMEOUT` 从 90 秒提高到 180 秒。
   - `STREAM_HTTP_READ_TIMEOUT` 设为 200 秒，避免 HTTP SDK 在应用层空闲超时前抢先失败。

### 后续可选阶段

1. ✅ **P2: 动态超时**
   - 推理模型或显式开启 thinking/reasoning 的模型默认使用 300 秒 HTTP read timeout。
   - 启用工具、记忆、图片生成或视频生成的 Agent 默认使用 5400 秒全局超时。
   - 显式配置的 `global_timeout`、`read_timeout` 或旧 `timeout` 仍优先。

2. ✅ **P2: 基础监控字段**
   - stream 与 regenerate 的 idle/global timeout 日志已补充 `timeout_type` 和 `timeout_seconds`，便于按类型统计。

3. **后续可选：前端错误提示细化**
   - SSE error payload 仍沿用统一 `stream_timeout_exceeded` 文案。
   - 如果要在 UI 明确区分“模型空闲超时”和“整轮任务超时”，可在 error payload 中新增 `timeout_type`。

4. **后续可选：指标面板**
   - 将日志中的 `timeout_type` 汇总到监控系统，按 provider/model/agent 统计超时率。

### 预期收益

1. ✅ 减少超时相关的误报
2. ✅ 提高复杂任务的成功率
3. ✅ 简化配置和维护
4. ✅ 更好的用户体验

---

**文档版本**: 1.0  
**创建时间**: 2026-05-28  
**作者**: Claude (Opus 4.7)  
**相关 Issue**: YUN-72
