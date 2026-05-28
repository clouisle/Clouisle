# 后端实施详细指南

## 目录
1. [数据库查询实现](#数据库查询实现)
2. [API 端点实现](#api-端点实现)
3. [服务层实现](#服务层实现)
4. [性能优化](#性能优化)

---

## 1. 数据库查询实现

### 1.1 基础索引创建

```sql
-- 为 Message 表添加性能索引
CREATE INDEX IF NOT EXISTS idx_message_created_at_agent 
ON messages(created_at DESC, conversation_id) 
WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_message_duration_status 
ON messages(duration_ms, round_status, created_at DESC) 
WHERE is_active = true AND is_round_canonical = true;

-- 为 Conversation 表添加索引
CREATE INDEX IF NOT EXISTS idx_conversation_agent_created 
ON conversations(agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_created_at 
ON conversations(created_at DESC);
```

### 1.2 核心聚合查询

#### 1.2.1 概览指标查询

```python
# backend/app/services/observability/queries.py

from datetime import datetime, timedelta
from typing import Dict, Any
from tortoise import Tortoise
from tortoise.expressions import Q, F
from tortoise.functions import Count, Avg
from app.models.agent import Message, Conversation, MessageRoundStatus

async def get_overview_metrics(
    start_time: datetime,
    end_time: datetime,
    team_id: str | None = None
) -> Dict[str, Any]:
    """获取概览指标"""
    
    # 构建基础查询条件
    base_filter = Q(
        created_at__gte=start_time,
        created_at__lte=end_time,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    if team_id:
        base_filter &= Q(conversation__agent__team_id=team_id)
    
    # 总请求数
    total_requests = await Message.filter(base_filter).count()
    
    # 成功请求数
    success_count = await Message.filter(
        base_filter,
        round_status=MessageRoundStatus.COMPLETED
    ).count()
    
    # 超时请求数
    timeout_count = await Message.filter(
        base_filter,
        round_status__in=[
            MessageRoundStatus.ERROR,
            MessageRoundStatus.MANUALLY_STOPPED
        ]
    ).count()
    
    # 计算环比（与前一周期对比）
    period_duration = end_time - start_time
    prev_start = start_time - period_duration
    prev_end = start_time
    
    prev_filter = Q(
        created_at__gte=prev_start,
        created_at__lte=prev_end,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    if team_id:
        prev_filter &= Q(conversation__agent__team_id=team_id)
    
    prev_total = await Message.filter(prev_filter).count()
    
    # 计算增长率
    growth_rate = 0.0
    if prev_total > 0:
        growth_rate = ((total_requests - prev_total) / prev_total) * 100
    
    # 响应时间（需要原始数据计算分位数）
    durations = await Message.filter(
        base_filter,
        duration_ms__isnull=False
    ).values_list('duration_ms', flat=True)
    
    p50 = calculate_percentile(durations, 50) if durations else 0
    
    # 超时率
    timeout_rate = (timeout_count / total_requests * 100) if total_requests > 0 else 0
    
    return {
        "total_requests": total_requests,
        "total_requests_growth": round(growth_rate, 2),
        "success_count": success_count,
        "timeout_count": timeout_count,
        "timeout_rate": round(timeout_rate, 2),
        "avg_response_time_p50": p50,
    }


def calculate_percentile(values: list[int], percentile: int) -> int:
    """计算分位数"""
    if not values:
        return 0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    return sorted_values[min(index, len(sorted_values) - 1)]
```

#### 1.2.2 Agent 性能查询

```python
async def get_agent_performance(
    start_time: datetime,
    end_time: datetime,
    agent_ids: list[str] | None = None,
    team_id: str | None = None,
    sort_by: str = "request_count",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取 Agent 性能数据"""
    
    # 构建查询
    base_filter = Q(
        created_at__gte=start_time,
        created_at__lte=end_time,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    if team_id:
        base_filter &= Q(conversation__agent__team_id=team_id)
    
    if agent_ids:
        base_filter &= Q(conversation__agent_id__in=agent_ids)
    
    # 按 Agent 分组统计
    messages = await Message.filter(base_filter).prefetch_related(
        'conversation__agent',
        'conversation__agent__team'
    ).all()
    
    # 按 Agent 聚合
    agent_stats = {}
    for msg in messages:
        agent_id = str(msg.conversation.agent.id)
        if agent_id not in agent_stats:
            agent_stats[agent_id] = {
                "agent_id": agent_id,
                "agent_name": msg.conversation.agent.name,
                "team_name": msg.conversation.agent.team.name if msg.conversation.agent.team else "N/A",
                "durations": [],
                "request_count": 0,
                "success_count": 0,
                "timeout_count": 0,
                "total_tokens": 0,
            }
        
        stats = agent_stats[agent_id]
        stats["request_count"] += 1
        
        if msg.round_status == MessageRoundStatus.COMPLETED:
            stats["success_count"] += 1
        elif msg.round_status in [MessageRoundStatus.ERROR, MessageRoundStatus.MANUALLY_STOPPED]:
            stats["timeout_count"] += 1
        
        if msg.duration_ms:
            stats["durations"].append(msg.duration_ms)
        
        if msg.token_usage:
            stats["total_tokens"] += msg.token_usage.get("prompt", 0) + msg.token_usage.get("completion", 0)
    
    # 计算分位数和派生指标
    result_data = []
    for agent_id, stats in agent_stats.items():
        durations = stats["durations"]
        result_data.append({
            "agent_id": stats["agent_id"],
            "agent_name": stats["agent_name"],
            "team_name": stats["team_name"],
            "request_count": stats["request_count"],
            "p50": calculate_percentile(durations, 50),
            "p90": calculate_percentile(durations, 90),
            "p95": calculate_percentile(durations, 95),
            "p99": calculate_percentile(durations, 99),
            "timeout_count": stats["timeout_count"],
            "timeout_rate": round(stats["timeout_count"] / stats["request_count"] * 100, 2) if stats["request_count"] > 0 else 0,
            "success_count": stats["success_count"],
            "success_rate": round(stats["success_count"] / stats["request_count"] * 100, 2) if stats["request_count"] > 0 else 0,
            "avg_tokens": round(stats["total_tokens"] / stats["request_count"], 0) if stats["request_count"] > 0 else 0,
        })
    
    # 排序
    sort_key_map = {
        "request_count": "request_count",
        "p50": "p50",
        "p90": "p90",
        "p95": "p95",
        "timeout_rate": "timeout_rate",
    }
    sort_key = sort_key_map.get(sort_by, "request_count")
    result_data.sort(key=lambda x: x[sort_key], reverse=(sort_order == "desc"))
    
    # 分页
    total = len(result_data)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_data = result_data[start_idx:end_idx]
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": paginated_data
    }
```

#### 1.2.3 时间序列查询

```python
async def get_request_trend(
    start_time: datetime,
    end_time: datetime,
    granularity: str = "hour",  # hour | day
    team_id: str | None = None
) -> Dict[str, Any]:
    """获取请求量趋势"""
    
    # 根据粒度确定时间分组
    if granularity == "hour":
        time_format = "%Y-%m-%d %H:00:00"
        delta = timedelta(hours=1)
    else:  # day
        time_format = "%Y-%m-%d 00:00:00"
        delta = timedelta(days=1)
    
    base_filter = Q(
        created_at__gte=start_time,
        created_at__lte=end_time,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    if team_id:
        base_filter &= Q(conversation__agent__team_id=team_id)
    
    messages = await Message.filter(base_filter).values_list('created_at', flat=True)
    
    # 按时间分组
    time_buckets = {}
    current = start_time
    while current <= end_time:
        bucket_key = current.strftime(time_format)
        time_buckets[bucket_key] = 0
        current += delta
    
    for created_at in messages:
        bucket_key = created_at.strftime(time_format)
        if bucket_key in time_buckets:
            time_buckets[bucket_key] += 1
    
    # 转换为列表
    data = [
        {"timestamp": key, "count": value}
        for key, value in sorted(time_buckets.items())
    ]
    
    return {"data": data}
```

#### 1.2.4 超时事件查询

```python
async def get_timeout_events(
    start_time: datetime,
    end_time: datetime,
    timeout_type: str | None = None,  # idle | global
    agent_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取超时事件列表
    
    注意：timeout_type 需要从日志系统获取，这里简化为从 round_status 推断
    """
    
    base_filter = Q(
        created_at__gte=start_time,
        created_at__lte=end_time,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final",
        round_status__in=[MessageRoundStatus.ERROR, MessageRoundStatus.MANUALLY_STOPPED]
    )
    
    if agent_ids:
        base_filter &= Q(conversation__agent_id__in=agent_ids)
    
    # 查询超时消息
    total = await Message.filter(base_filter).count()
    
    messages = await Message.filter(base_filter).prefetch_related(
        'conversation__agent',
        'conversation__agent__model__model'
    ).order_by('-created_at').offset((page - 1) * page_size).limit(page_size)
    
    data = []
    for msg in messages:
        agent = msg.conversation.agent
        model_name = "N/A"
        if agent.model and agent.model.model:
            model_name = f"{agent.model.model.provider}/{agent.model.model.model_id}"
        
        # 简化：根据 duration 推断超时类型
        # 实际应该从日志系统查询
        timeout_type_inferred = "idle" if msg.duration_ms and msg.duration_ms < 3600000 else "global"
        
        data.append({
            "timestamp": msg.created_at.isoformat(),
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "timeout_type": timeout_type_inferred,
            "timeout_threshold": 180 if timeout_type_inferred == "idle" else 3600,
            "actual_duration": msg.duration_ms // 1000 if msg.duration_ms else 0,
            "model_name": model_name,
            "conversation_id": str(msg.conversation_id),
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": data
    }
```

---

## 2. API 端点实现

### 2.1 路由结构

```python
# backend/app/api/v1/admin/endpoints/observability.py

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from app.api import deps
from app.models.user import User
from app.schemas.response import Response, success
from app.services.observability import queries

router = APIRouter()


def parse_time_range(
    time_range: Literal["today", "week", "month", "custom"],
    start_time: datetime | None = None,
    end_time: datetime | None = None
) -> tuple[datetime, datetime]:
    """解析时间范围"""
    now = datetime.utcnow()
    
    if time_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif time_range == "week":
        start = now - timedelta(days=7)
        end = now
    elif time_range == "month":
        start = now - timedelta(days=30)
        end = now
    elif time_range == "custom":
        if not start_time or not end_time:
            raise ValueError("start_time and end_time required for custom range")
        start = start_time
        end = end_time
    else:
        raise ValueError(f"Invalid time_range: {time_range}")
    
    return start, end
```

### 2.2 概览端点

```python
@router.get("/overview")
async def get_overview(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取概览指标"""
    
    start, end = parse_time_range(time_range, start_time, end_time)
    
    metrics = await queries.get_overview_metrics(start, end)
    
    return success(data=metrics)
```

### 2.3 Agent 性能端点

```python
@router.get("/agents")
async def get_agent_performance(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    agent_ids: str | None = Query(None, description="Comma-separated UUIDs"),
    sort_by: Literal["request_count", "p50", "p90", "p95", "timeout_rate"] = Query("request_count"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取 Agent 性能数据"""
    
    start, end = parse_time_range(time_range, start_time, end_time)
    
    agent_id_list = None
    if agent_ids:
        agent_id_list = [aid.strip() for aid in agent_ids.split(",")]
    
    result = await queries.get_agent_performance(
        start, end,
        agent_ids=agent_id_list,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size
    )
    
    return success(data=result)
```

### 2.4 趋势端点

```python
@router.get("/request-trend")
async def get_request_trend(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    granularity: Literal["hour", "day"] = Query("hour"),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取请求量趋势"""
    
    start, end = parse_time_range(time_range, start_time, end_time)
    
    result = await queries.get_request_trend(start, end, granularity)
    
    return success(data=result)


@router.get("/response-time-trend")
async def get_response_time_trend(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    granularity: Literal["hour", "day"] = Query("hour"),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取响应时间趋势"""
    
    start, end = parse_time_range(time_range, start_time, end_time)
    
    # 类似 request_trend，但返回分位数
    result = await queries.get_response_time_trend(start, end, granularity)
    
    return success(data=result)
```

### 2.5 超时事件端点

```python
@router.get("/timeouts")
async def get_timeout_events(
    time_range: Literal["today", "week", "month", "custom"] = Query("today"),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    timeout_type: Literal["idle", "global"] | None = Query(None),
    agent_ids: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_superuser),
) -> Response:
    """获取超时事件列表"""
    
    start, end = parse_time_range(time_range, start_time, end_time)
    
    agent_id_list = None
    if agent_ids:
        agent_id_list = [aid.strip() for aid in agent_ids.split(",")]
    
    result = await queries.get_timeout_events(
        start, end,
        timeout_type=timeout_type,
        agent_ids=agent_id_list,
        page=page,
        page_size=page_size
    )
    
    return success(data=result)
```

### 2.6 注册路由

```python
# backend/app/api/v1/admin/api.py

from fastapi import APIRouter
from app.api.v1.admin.endpoints import observability

api_router = APIRouter()

# ... 其他路由

api_router.include_router(
    observability.router,
    prefix="/observability",
    tags=["admin-observability"]
)
```

---

## 3. 服务层实现

### 3.1 缓存策略

```python
# backend/app/services/observability/cache.py

from functools import wraps
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any, Callable
from app.core.redis import redis_client

def cache_observability_query(ttl_seconds: int = 300):
    """缓存可观测性查询结果"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # 生成缓存键
            cache_key_data = {
                "func": func.__name__,
                "args": str(args),
                "kwargs": str(sorted(kwargs.items()))
            }
            cache_key_str = json.dumps(cache_key_data, sort_keys=True)
            cache_key = f"obs:{hashlib.md5(cache_key_str.encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # 执行查询
            result = await func(*args, **kwargs)
            
            # 写入缓存
            await redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(result, default=str)
            )
            
            return result
        
        return wrapper
    return decorator
```

### 3.2 应用缓存

```python
# 在 queries.py 中应用缓存

from app.services.observability.cache import cache_observability_query

@cache_observability_query(ttl_seconds=300)  # 5 分钟缓存
async def get_overview_metrics(
    start_time: datetime,
    end_time: datetime,
    team_id: str | None = None
) -> Dict[str, Any]:
    # ... 原有实现
    pass
```

---

## 4. 性能优化

### 4.1 数据库连接池配置

```python
# backend/app/core/config.py

class Settings(BaseSettings):
    # ... 其他配置
    
    # 数据库连接池（针对可观测性查询）
    DB_POOL_MIN_SIZE: int = 5
    DB_POOL_MAX_SIZE: int = 20
    DB_POOL_MAX_QUERIES: int = 50000
    DB_POOL_MAX_INACTIVE_CONNECTION_LIFETIME: float = 300.0
```

### 4.2 查询优化建议

1. **使用物化视图**（PostgreSQL 9.3+）

```sql
-- 创建每小时聚合的物化视图
CREATE MATERIALIZED VIEW observability_hourly_stats AS
SELECT 
    date_trunc('hour', m.created_at) as hour,
    c.agent_id,
    COUNT(*) as request_count,
    COUNT(*) FILTER (WHERE m.round_status = 'completed') as success_count,
    COUNT(*) FILTER (WHERE m.round_status IN ('error', 'manually_stopped')) as timeout_count,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY m.duration_ms) as p50,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY m.duration_ms) as p90,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY m.duration_ms) as p95,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY m.duration_ms) as p99
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE m.is_active = true 
  AND m.is_round_canonical = true 
  AND m.round_role = 'assistant_final'
GROUP BY hour, c.agent_id;

-- 创建索引
CREATE INDEX idx_obs_hourly_hour_agent ON observability_hourly_stats(hour, agent_id);

-- 定时刷新（通过 Celery 任务）
REFRESH MATERIALIZED VIEW CONCURRENTLY observability_hourly_stats;
```

2. **Celery 定时任务**

```python
# backend/app/tasks/observability.py

from celery import shared_task
from app.core.db import get_db_connection

@shared_task
def refresh_observability_materialized_view():
    """刷新可观测性物化视图"""
    conn = get_db_connection()
    conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY observability_hourly_stats")
    conn.close()


# backend/app/core/celery_app.py

from celery.schedules import crontab

app.conf.beat_schedule = {
    # ... 其他任务
    'refresh-observability-stats': {
        'task': 'app.tasks.observability.refresh_observability_materialized_view',
        'schedule': crontab(minute='*/15'),  # 每 15 分钟刷新
    },
}
```

### 4.3 分页优化

```python
# 使用游标分页代替 offset/limit（大数据量时更高效）

async def get_agent_performance_cursor(
    start_time: datetime,
    end_time: datetime,
    cursor: str | None = None,
    page_size: int = 20
) -> Dict[str, Any]:
    """使用游标分页的 Agent 性能查询"""
    
    base_filter = Q(
        created_at__gte=start_time,
        created_at__lte=end_time,
        is_active=True,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    if cursor:
        # 解码游标（这里简化为 agent_id）
        base_filter &= Q(conversation__agent_id__gt=cursor)
    
    # ... 查询逻辑
    
    # 返回下一个游标
    next_cursor = result_data[-1]["agent_id"] if result_data else None
    
    return {
        "data": result_data,
        "next_cursor": next_cursor,
        "has_more": len(result_data) == page_size
    }
```

---

## 5. 测试

### 5.1 单元测试示例

```python
# backend/tests/services/test_observability_queries.py

import pytest
from datetime import datetime, timedelta
from app.services.observability import queries
from app.models.agent import Message, Conversation, Agent, MessageRoundStatus

@pytest.mark.asyncio
async def test_get_overview_metrics(db):
    """测试概览指标查询"""
    
    # 准备测试数据
    agent = await Agent.create(name="Test Agent", team_id=...)
    conversation = await Conversation.create(agent=agent, user_id=...)
    
    # 创建成功消息
    await Message.create(
        conversation=conversation,
        role="assistant",
        content="test",
        round_status=MessageRoundStatus.COMPLETED,
        duration_ms=1000,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    # 创建超时消息
    await Message.create(
        conversation=conversation,
        role="assistant",
        content="test",
        round_status=MessageRoundStatus.ERROR,
        duration_ms=5000,
        is_round_canonical=True,
        round_role="assistant_final"
    )
    
    # 执行查询
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)
    
    result = await queries.get_overview_metrics(start_time, end_time)
    
    # 断言
    assert result["total_requests"] == 2
    assert result["success_count"] == 1
    assert result["timeout_count"] == 1
    assert result["timeout_rate"] == 50.0
```

### 5.2 API 集成测试

```python
# backend/tests/api/test_observability_api.py

import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_get_overview_endpoint(client: AsyncClient, superuser_token_headers):
    """测试概览端点"""
    
    response = await client.get(
        "/api/v1/admin/observability/overview?time_range=today",
        headers=superuser_token_headers
    )
    
    assert response.status_code == 200
    data = response.json()["data"]
    assert "total_requests" in data
    assert "timeout_rate" in data
    assert "avg_response_time_p50" in data
```

---

## 6. 部署检查清单

- [ ] 数据库索引已创建
- [ ] 物化视图已创建（如果使用）
- [ ] Celery 定时任务已配置
- [ ] Redis 缓存已启用
- [ ] API 权限检查已实施
- [ ] 单元测试已通过
- [ ] 集成测试已通过
- [ ] 性能测试已完成（查询响应时间 < 2s）
- [ ] 文档已更新

---

**下一步**: 查看 [02-frontend-implementation.md](./02-frontend-implementation.md) 了解前端实施细节。
