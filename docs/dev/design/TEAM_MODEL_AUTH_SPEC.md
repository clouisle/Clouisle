# 团队模型授权设计规范

## 1. 概述

在企业中台场景中，模型资源需要按团队进行授权和配额管理，而不是让所有团队直接使用后台配置的全部模型。

### 1.1 设计目标

- **资源隔离**：不同团队只能使用被授权的模型
- **配额管控**：可设置团队的模型使用配额（Token 数量/调用次数）
- **灵活授权**：支持按模型类型、单个模型等多种授权方式
- **用量追踪**：记录团队的模型使用情况

### 1.2 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      管理后台 (Superuser)                            │
│  ┌─────────────────┐    授权/配额    ┌─────────────────┐            │
│  │   Model (全局)   │ ─────────────> │   TeamModel     │            │
│  │   配置各种模型    │               │   授权+配额表    │            │
│  └─────────────────┘                 └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      企业中台 (Team)                                 │
│  ┌─────────────────┐                 ┌─────────────────┐            │
│  │   Team A        │ ──可使用──>     │   Model A       │            │
│  │   Team B        │ ──可使用──>     │   Model A, B    │            │
│  │   Team C        │ ──可使用──>     │   Model A, B, C │            │
│  └─────────────────┘                 └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据模型

### 2.1 TeamModel（团队模型授权表）

```python
class TeamModel(models.Model):
    """团队模型授权 - 定义团队可使用的模型及配额"""
    
    id = fields.UUIDField(pk=True)
    
    # 关联
    team: ForeignKeyRelation[Team] = fields.ForeignKeyField(
        "models.Team", related_name="model_authorizations", on_delete=CASCADE
    )
    model: ForeignKeyRelation[Model] = fields.ForeignKeyField(
        "models.Model", related_name="team_authorizations", on_delete=CASCADE
    )
    
    # 配额设置 (null = 无限制)
    daily_token_limit = fields.BigIntField(null=True, description="每日 Token 限额")
    monthly_token_limit = fields.BigIntField(null=True, description="每月 Token 限额")
    daily_request_limit = fields.IntField(null=True, description="每日请求次数限额")
    monthly_request_limit = fields.IntField(null=True, description="每月请求次数限额")
    
    # 当前用量
    daily_tokens_used = fields.BigIntField(default=0)
    monthly_tokens_used = fields.BigIntField(default=0)
    daily_requests_used = fields.IntField(default=0)
    monthly_requests_used = fields.IntField(default=0)
    
    # 用量重置时间
    daily_reset_at = fields.DatetimeField(null=True)
    monthly_reset_at = fields.DatetimeField(null=True)
    
    # 状态
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    priority = fields.IntField(default=0, description="优先级，用于同类型模型排序")
    
    # 时间戳
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "team_models"
        unique_together = (("team", "model"),)
```

### 2.2 TeamModelUsageLog（使用日志表，可选）

```python
class TeamModelUsageLog(models.Model):
    """团队模型使用日志 - 详细记录每次调用"""
    
    id = fields.UUIDField(pk=True)
    
    team: ForeignKeyRelation[Team]
    model: ForeignKeyRelation[Model]
    user: ForeignKeyRelation[User]
    
    # 调用信息
    input_tokens = fields.IntField(default=0)
    output_tokens = fields.IntField(default=0)
    total_tokens = fields.IntField(default=0)
    
    # 成本估算
    estimated_cost = fields.DecimalField(max_digits=10, decimal_places=6, null=True)
    
    # 请求上下文
    request_type = fields.CharField(max_length=50)  # chat, embedding, image, etc.
    request_id = fields.CharField(max_length=100, null=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "team_model_usage_logs"
        indexes = [
            ("team", "created_at"),
            ("model", "created_at"),
        ]
```

---

## 3. API 设计

### 3.1 管理端 API（Superuser）

```
# 团队模型授权管理
POST   /api/v1/admin/teams/{team_id}/models           # 为团队授权模型
GET    /api/v1/admin/teams/{team_id}/models           # 获取团队已授权模型
PUT    /api/v1/admin/teams/{team_id}/models/{model_id} # 更新授权配置
DELETE /api/v1/admin/teams/{team_id}/models/{model_id} # 撤销授权

# 批量操作
POST   /api/v1/admin/teams/{team_id}/models/batch     # 批量授权
DELETE /api/v1/admin/teams/{team_id}/models/batch     # 批量撤销

# 用量统计
GET    /api/v1/admin/teams/{team_id}/models/usage     # 团队模型用量统计
GET    /api/v1/admin/models/{model_id}/usage          # 单个模型全局用量
```

### 3.2 中台 API（Team Member）

```
# 团队可用模型
GET    /api/v1/teams/{team_id}/models                 # 获取团队可用模型列表
GET    /api/v1/teams/{team_id}/models/{type}          # 按类型筛选 (chat, embedding, etc.)
GET    /api/v1/teams/{team_id}/models/default/{type}  # 获取默认模型

# 用量查询
GET    /api/v1/teams/{team_id}/models/usage           # 当前用量
GET    /api/v1/teams/{team_id}/models/{model_id}/quota # 单个模型配额状态
```

---

## 4. 业务逻辑

### 4.1 授权检查流程

```python
async def check_model_authorization(team_id: UUID, model_id: UUID) -> TeamModel:
    """检查团队是否有权使用指定模型"""
    
    auth = await TeamModel.filter(
        team_id=team_id,
        model_id=model_id,
        is_enabled=True
    ).first()
    
    if not auth:
        raise ModelNotAuthorizedError(f"Team {team_id} is not authorized to use model {model_id}")
    
    return auth
```

### 4.2 配额检查与扣减

```python
async def check_and_consume_quota(
    team_id: UUID, 
    model_id: UUID, 
    tokens: int
) -> bool:
    """检查配额并扣减"""
    
    auth = await check_model_authorization(team_id, model_id)
    
    # 检查每日配额
    if auth.daily_token_limit:
        if auth.daily_tokens_used + tokens > auth.daily_token_limit:
            raise QuotaExceededError("Daily token limit exceeded")
    
    # 检查每月配额
    if auth.monthly_token_limit:
        if auth.monthly_tokens_used + tokens > auth.monthly_token_limit:
            raise QuotaExceededError("Monthly token limit exceeded")
    
    # 扣减配额
    auth.daily_tokens_used += tokens
    auth.monthly_tokens_used += tokens
    await auth.save()
    
    return True
```

### 4.3 配额重置（定时任务）

```python
# 每日凌晨重置
async def reset_daily_quota():
    await TeamModel.all().update(
        daily_tokens_used=0,
        daily_requests_used=0,
        daily_reset_at=datetime.utcnow()
    )

# 每月1日重置
async def reset_monthly_quota():
    await TeamModel.all().update(
        monthly_tokens_used=0,
        monthly_requests_used=0,
        monthly_reset_at=datetime.utcnow()
    )
```

---

## 5. 获取团队可用模型

### 5.1 基本查询

```python
async def get_team_available_models(
    team_id: UUID,
    model_type: ModelType | None = None
) -> list[Model]:
    """获取团队可用的模型列表"""
    
    query = TeamModel.filter(
        team_id=team_id,
        is_enabled=True,
        model__is_enabled=True  # 全局模型也必须启用
    )
    
    if model_type:
        query = query.filter(model__model_type=model_type)
    
    authorizations = await query.prefetch_related("model").order_by("-priority")
    
    return [auth.model for auth in authorizations]
```

### 5.2 获取默认模型

```python
async def get_team_default_model(
    team_id: UUID,
    model_type: ModelType
) -> Model | None:
    """获取团队某类型的默认模型（优先级最高的）"""
    
    auth = await TeamModel.filter(
        team_id=team_id,
        is_enabled=True,
        model__model_type=model_type,
        model__is_enabled=True
    ).prefetch_related("model").order_by("-priority").first()
    
    return auth.model if auth else None
```

---

## 6. 前端集成

### 6.1 中台模型选择器

中台在选择模型时，只显示团队被授权的模型：

```typescript
// 获取团队可用的 Chat 模型
const { data: models } = await api.get(`/teams/${teamId}/models?type=chat`)

// 模型选择下拉
<Select>
  {models.map(model => (
    <SelectItem key={model.id} value={model.id}>
      {model.name}
      {model.quota && (
        <span className="text-muted">
          {model.quota.daily_tokens_used} / {model.quota.daily_token_limit}
        </span>
      )}
    </SelectItem>
  ))}
</Select>
```

### 6.2 管理后台授权界面

```
┌─────────────────────────────────────────────────────────────┐
│  团队模型授权 - Team Alpha                                    │
├─────────────────────────────────────────────────────────────┤
│  ☑ GPT-4o           每日: 100K tokens    每月: 1M tokens    │
│  ☑ GPT-4o-mini      每日: 无限制         每月: 无限制       │
│  ☑ Claude 3.5       每日: 50K tokens     每月: 500K tokens  │
│  ☐ DeepSeek V3      (未授权)                                │
│  ☑ text-embedding   每日: 无限制         每月: 无限制       │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 实现优先级

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P0** | TeamModel 数据模型 | 待实现 |
| **P0** | 团队可用模型查询 API | 待实现 |
| **P0** | 管理端授权 API | 待实现 |
| **P1** | 配额检查与扣减 | 待实现 |
| **P1** | 用量日志记录 | 待实现 |
| **P2** | 配额重置定时任务 | 待实现 |
| **P2** | 用量统计与报表 | 待实现 |

---

## 8. 迁移策略

对于现有系统，可以提供两种迁移方式：

1. **自动授权**：将所有现有模型自动授权给所有团队（配额无限制）
2. **手动授权**：管理员手动配置各团队的模型授权

```python
# 迁移脚本：为所有团队授权所有模型
async def migrate_team_model_auth():
    teams = await Team.all()
    models = await Model.filter(is_enabled=True)
    
    for team in teams:
        for model in models:
            await TeamModel.get_or_create(
                team=team,
                model=model,
                defaults={"is_enabled": True}
            )
```
