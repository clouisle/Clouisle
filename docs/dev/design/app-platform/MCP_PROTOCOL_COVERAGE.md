# MCP 协议覆盖矩阵

本文档是 MCP 客户端能力的唯一权威清单：Clouisle 只作为 **MCP 客户端**消费外部
MCP 服务器，不对外暴露 MCP 服务端。协议实现集中在
`backend/app/llm/tools/mcp_client.py`，身份与凭据在
`backend/app/services/tool_connections.py`。

## 运行时基线

- SDK：`mcp>=2.2.0`（当前锁 `2.3.0`），协议最高版本 `2026-07-28`。任务相关模型自
  `2.3.0` 才有；`2.2` 上 `TASKS_SDK_READY` 为假，任务能力自动关闭。
- 版本不写死：握手优先 `server/discover`，回退 `initialize`；能力一律从协商结果读取。
- SDK 版本差异（`params=` 分页、`allow_input_required`、`input_responses`）用
  `inspect.signature` 探测，不在运行时猜测。
- 服务器没有声明的能力一律 fail closed（`McpCapabilityUnavailable` → 409），
  绝不伪造成功。

## 覆盖矩阵

| 协议面 | 状态 | 实现位置 | 说明 |
|---|---|---|---|
| `stdio` / `sse` / Streamable HTTP | 支持 | `McpClient._transport` | 未支持的传输显式报配置错误 |
| 握手与版本协商 | 支持 | `_negotiate` / `_read_negotiated` | `2026-07-28` 与旧的 `initialize` 都覆盖 |
| `ping` | 支持（订阅会话） | `mcp_subscriptions._ping_session` | 按 TTL 预算的一半发放；失败即标记 `connection_lost` |
| `logging/setLevel` + `notifications/message` | 支持（可选开启） | `_CallbackGuard.server_log` / `_request_server_log_level` | 仅在 `mcp_config.server_log_level` 开启；`2026-07-28` 走每请求 `_meta` |
| `tools/list` / `tools/call` | 支持 | `enumerate_tools` / `execute_tool` | 含 `outputSchema`、`structuredContent`、`_meta`、annotations |
| `resources/list` · `templates/list` · `read` | 支持 | `enumerate_resources` / `enumerate_resource_templates` / `read_resource` | URI 校验拒绝未展开的 RFC 6570 模板 |
| `prompts/list` · `prompts/get` | 支持 | `enumerate_prompts` / `get_prompt` | 返回值按不可信内容处理，需预览后使用 |
| `completion/complete` | 支持 | `complete` | prompt 与 resource_template 两种引用 |
| 分页 | 支持 | `_enumerate` / `_fetch_page` | `max_pages` / `max_items` + `truncated` 元数据 |
| 内容块 | 支持 | `_content_block` | text / image / audio / resource_link / resource；未知类型原样透传 |
| `sampling/createMessage`（服务器主动） | 支持（已弃用方向） | `_CallbackGuard.sampling` + `mcp_interactions` | 不自动应答，落库转人工审批；可限制 `max_tokens`、禁止工具调用 |
| `elicitation/create`（服务器主动） | 支持（已弃用方向） | `_CallbackGuard.elicitation` | form 与 url 两种模式；敏感字段直接 decline |
| `roots/list` | 支持（已弃用方向） | `_CallbackGuard.list_roots` | 只返回 `file://` root；仅当 `roots_allowlist` 非空时才只返回白名单内的 root（默认空表放行所有 `file://`） |
| MRTR（`input_required` 回填） | 支持 | `parse_input_responses` + `*_round_trip_kwargs` | 见下文「多轮往返」 |
| `resources/subscribe`（≤2025-11-25） | 支持 | `mcp_subscriptions.open_subscription` | 会话内订阅 + 退出时 best-effort 退订 |
| `subscriptions/listen`（2026-07-28） | 支持 | 同文件 `_pump_listen` | 一次请求声明过滤器，事件流入同一 SSE 契约 |
| `tasks/*`（长任务） | 支持（可选，默认关） | `mcp_tasks.py` | 客户端手写循环；见下文「客户端任务」与 #500 |
| 进度通知（服务器→客户端） | 支持 | `execute_tool(progress=...)` + `_ProgressReporter` | 见下文「进度与取消」 |
| 取消（`notifications/cancelled`） | 支持 | `_cancel_in_flight` + `execute_tool` | 见下文「进度与取消」 |
| `x-mcp-header` 参数镜像 | 已实现（协议版本 `2026-07-28` 及以上） | `execute_tool`（同会话 list 后镜像 `Mcp-Param-*`） | 更早版本不镜像；发现列表在目标工具前被截断时 fail closed |
| 服务端角色（对外提供 MCP） | 明确不做 | — | 本项目只做客户端 |

## 多轮往返（MRTR）

协议 `2026-07-28` 把交互式请求改成「调用中途返回 `input_required` → 客户端补齐 →
重试同一请求」。三条路径都支持：

1. `tools/call`、`resources/read`、`prompts/get` 都允许服务器返回 `input_required`；
2. 返回体带上 `input_required.method`、`requests`（按请求 key）和 `request_state`；
3. 调用方按 key 回答，每一项必须声明所回答的 `method`：

```json
{
  "request_state": "opaque-from-server",
  "input_responses": {
    "q1": { "method": "elicitation/create", "result": { "action": "accept" } }
  }
}
```

设计约束：

- **不靠形状猜类型**：`method` 显式声明要校验的结果模型
  （`ElicitResult` / `ListRootsResult` / `CreateMessageResult`），否则一次 elicitation
  的答案可能被塞进 sampling 的槽位。
- **身份不漂移**：工具如果是靠外部账号执行的，带 `input_responses` 必须显式给
  `connection_id`；而且**首段调用与每一次续跑都必须给同一个** `connection_id`——只在
  续跑时指定是不够的，首段若落到默认连接 A、续跑显式给 B，绑定照样会变。无
  `execution_id` 的续跑没有可比对的已存绑定，因此这条约束由调用方保证；
  `identity_policy=none` 的工具没有可漂移的身份，不强制要求。
- **审批绑定**：`request_state` 与 `input_responses` 进入 `parameters`，自动进入
  `build_parameter_snapshot` 摘要；已批准的请求不能被换成另一组答案。不续跑时
  这两个字段不写入 `parameters`，因此升级前 parked 的执行仍可恢复。
- **失败要响**：SDK 不支持回填时抛错，而不是丢掉答案重发（那样会无限循环在同一个
  问题上）。

## 进度与取消

两条行为都局限在适配层与 Agent 运行事件流，`POST /mcp/tools/call` 的 HTTP 契约
不变。

**进度（服务器→客户端）**

- `McpClient.execute_tool(progress=...)` / `execute_mcp_tool(progress=...)` 接一个
  `Callable[[McpToolProgress], Awaitable[None]]`。给了 sink 才把 `progress_callback`
  传给 `session.call_tool`：SDK 因此带上 `progressToken`，并把 `notifications/progress`
  路由回来。不给 sink 时请求与以前逐字节一致（不传 `progress_callback`）。
- **节流**（`_ProgressReporter`，每调用一个实例）：首个 tick 立即放行，之后每个
  `PROGRESS_MIN_INTERVAL_SECONDS`（0.5s）最多一个，`progress >= total` 的完成 tick
  永远放行，完全重复的 tick 丢弃。服务器按秒刷也无所谓，事件流不会被打爆。
- sink 抛异常只记日志，绝不改变工具结果。
- 落点：Agent 运行时把 sink 放进 `RuntimeToolIdentity.progress`（仅当该运行有
  formatter，即真有观众时才放），`execute_agent_stored_tool` 转到 `ToolCallContext.progress`，
  `ToolExecutor` 再交给适配器。loop 用与 `tool_call`/`tool_result` 同一个 formatter
  发 `tool_progress` 事件（`AgentRunStream` → SSE）。chat 面板消费该事件并显示
  百分比；工作流面板当前不展示进度。非流式路径、以及 MCP 工具测试端点没有 sink，
  行为不变。

**取消**

- 超时与中断（任务被 cancel）都先对在飞请求发 `notifications/cancelled`，再让会话
  关闭。锁定的 SDK 2.x 在放弃请求时已会代发这条通知（dispatcher 的
  `cancel_on_abandon`）；适配层的显式发送是不依赖那个默认值的兵底：SDK 没自行
  发送时由这里补上，已代发时（pending 已清空）不会重复发。
- request id 由 SDK 内部生成且无公开访问器，所以 `_in_flight_request_id` 只能从 SDK
  自己跟踪的表（mcp 2.x 的 dispatcher `_pending`，1.x 的 `_response_streams`）探；
  取不到或待定集合不唯一时不发——向服务器发一个它没见过的 id 只是噪声。
- 全程 fail safe：发送被 shield + 超时（`CANCEL_NOTIFY_TIMEOUT_SECONDS`）包住，
  会话已死、写入失败、SDK 没有 `CancelledNotification` 都只记 debug 日志；原始超时/
  中断错误原样上抛。

## 客户端任务（`tasks/*`）

长耗时工具（批量建索引、长视频生成）不再必然阻塞到超时：服务器可以把一次
`tools/call` 变成任务，客户端轮询取结果。实现集中在新模块
`backend/app/llm/tools/mcp_tasks.py`，`mcp_client.py` 只有三个接入点：
`McpClient.__init__` 解析策略、`_open` 选择会话类型、`execute_tool` 调用
`call_tool_with_tasks`。

覆盖的协议面：`tools/call` 带 `params.task` 创建任务、`tasks/get` 轮询、
`tasks/result` 取结果、`tasks/cancel` 取消。**不实现** `tasks/list`：一次调用的任务生命
周期全在同一个 `execute_tool` 内完成，不靠枚举任务清单恢复或管理，因此能力声明只写
`cancel`（声明未实现的能力会让服务器据此采取我们处理不了的行为）。这是产品决定，
不是待补缺口；代价仅仅是客户端进程在轮询中途死亡时，服务器侧任务会留到它自己的
`ttl` 过期才回收。

### 开启方式

必须同时满足两个开关，缺一不可（声明能力会改变服务器对**每一次**调用的行为，
不能盲目打开）：

| 开关 | 位置 | 默认 |
|---|---|---|
| `MCP_TASKS_ENABLED` | `backend/app/core/config.py`（平台级） | `false` |
| `enable_tasks` | 工具的 `mcp_config`（每服务器） | `false` |

开启后该服务器还会有三个边界值，写入 `mcp_config` 即生效（越界会被再次钳制）：
`tasks_timeout_seconds`（默认 120，1–3600）、`tasks_poll_interval_seconds`（默认 1，
0.1–30）、`tasks_max_polls`（默认 60，1–600）。实际生效的截止时间是
`min(tasks_timeout_seconds, 调用方本次预算 - 2s)`：工具的 MCP 超时（默认 60s）通常比
任务截止时间短，不比它小的话，外层超时会先杀掉轮询协程，服务器侧任务就没人取消了。
运营者打开开关后能看到的变化：该服务器的会话在握手时会声明
`capabilities.tasks = {cancel: {}}`，工具调用先发 task-augmented 请求，若服务器建了
任务则按上面的边界轮询到终态；服务器不支持时行为与今天完全一致（同步执行）。

### 为什么是手写的

`mcp` 2.3.0 只提供了任务**模型**（`Task`、`CreateTaskResult`、`GetTaskRequest`、
`CancelTaskRequest`、`ClientTasksCapability` …），没有客户端 API，而且挡住了三条
常规路径：

1. `ClientSession` 没有任何任务方法；
2. `ClientSession._build_capabilities` 把客户端能力写死，不提供扩展钩子，所以
   `tasks` 只能通过子类覆写该方法声明（`_TaskCapableSession`）；
3. `tools/call` 的结果在 SDK 内按 `(method, version)` 表校验为 `CallToolResult`，
   一个 `CreateTaskResult` 会在读到之前就被拒——所以**创建**请求走
   `session._dispatcher.send_raw_request(...)`，而 `tasks/get|result|cancel` 走
   `session.send_request(...)`（这三个方法不在校验表里，未知方法被跳过）。

上面第 2、3 点是本次实现仅有的两处私有 API 依赖，`mcp_tasks.TASKS_SDK_READY` 在导入
时探测它们（还有任务模型是否存在），缺失就整体退回同步路径而不是崩溃。**SDK 补上
客户端任务 API 后，应优先删掉这两处私有面依赖**，只保留策略解析与边界。

### 失败安全

每一步都有兜底，外部服务一律不假设健康：

| 情况 | 行为 |
|---|---|
| `tasks` 未开启 / SDK 无任务模型或钩子 | 直接走同步路径，不声明任何能力 |
| 服务器用 JSON-RPC error 拒绝 task-augmented 请求（如 `-32601`） | 打警告并回退同步执行（此时尚未开始工作） |
| 服务器忽略 `params.task`、直接返回结果 | 原样返回该结果，不再重发 |
| 传输超时 / 连接错误 | 向上抛（可能已经产生副作用，绝不重放） |
| 截止时间或轮询次数用尽 | 先 `tasks/cancel`，再抛 `McpTimeout`（截止时间含调用方预算上限，见上） |
| 任务终态 `failed` / `cancelled` | 抛 `McpServerError`，带 `statusMessage` |
| 任务 `input_required` | 先取消（本适配器无法在任务循环里补答案），再抛 `McpServerError` |
| `tasks/get` 本身出错 | 向上抛；已创建的任务不会被重新执行 |

协议版本上只对 `2025-11-25` 声明 `tasks`（`tasks/*` 只在该版本定义；已核对 schema：
`2026-07-28` 的 `ClientCapabilities` 无 `tasks`、`CallToolRequestParams` 无 `task`，而
SDK 的 `initialize()` 正是用 `LATEST_HANDSHAKE_VERSION = 2025-11-25` 构建能力声明）。
服务器自报的 `pollInterval` 提示被忽略：那是未经校验的远端输入，边界只认配置。

> 任务模式下不转发进度：task-augmented 请求走原始 dispatcher，不经过
> `call_tool(progress_callback=...)`。这是当前已知的能力交集限制，不是遗漏。

## 资源订阅的双路径
## 进度与取消

两条行为都局限在适配层与 Agent 运行事件流，`POST /mcp/tools/call` 的 HTTP 契约
不变。

**进度（服务器→客户端）**

- `McpClient.execute_tool(progress=...)` / `execute_mcp_tool(progress=...)` 接一个
  `Callable[[McpToolProgress], Awaitable[None]]`。给了 sink 才把 `progress_callback`
  传给 `session.call_tool`：SDK 因此带上 `progressToken`，并把 `notifications/progress`
  路由回来。不给 sink 时请求与以前逐字节一致（不传 `progress_callback`）。
- **节流**（`_ProgressReporter`，每调用一个实例）：首个 tick 立即放行，之后每个
  `PROGRESS_MIN_INTERVAL_SECONDS`（0.5s）最多一个，`progress >= total` 的完成 tick
  永远放行，完全重复的 tick 丢弃。服务器按秒刷也无所谓，事件流不会被打爆。
- sink 抛异常只记日志，绝不改变工具结果。
- 落点：Agent 运行时把 sink 放进 `RuntimeToolIdentity.progress`（仅当该运行有
  formatter，即真有观众时才放），`execute_agent_stored_tool` 转到 `ToolCallContext.progress`，
  `ToolExecutor` 再交给适配器。loop 用与 `tool_call`/`tool_result` 同一个 formatter
  发 `tool_progress` 事件（`AgentRunStream` → SSE）。chat 面板消费该事件并显示
  百分比；工作流面板当前不展示进度。非流式路径、以及 MCP 工具测试端点没有 sink，
  行为不变。

**取消**

- 超时与中断（任务被 cancel）都先对在飞请求发 `notifications/cancelled`，再让会话
  关闭。锁定的 SDK 2.x 在放弃请求时已会代发这条通知（dispatcher 的
  `cancel_on_abandon`）；适配层的显式发送是不依赖那个默认值的兵底：SDK 没自行
  发送时由这里补上，已代发时（pending 已清空）不会重复发。
- request id 由 SDK 内部生成且无公开访问器，所以 `_in_flight_request_id` 只能从 SDK
  自己跟踪的表（mcp 2.x 的 dispatcher `_pending`，1.x 的 `_response_streams`）探；
  取不到或待定集合不唯一时不发——向服务器发一个它没见过的 id 只是噪声。
- 全程 fail safe：发送被 shield + 超时（`CANCEL_NOTIFY_TIMEOUT_SECONDS`）包住，
  会话已死、写入失败、SDK 没有 `CancelledNotification` 都只记 debug 日志；原始超时/
  中断错误原样上抛。
## 资源订阅的双路径

会话协商结果决定用哪一种，两者都向 SSE 端点输出同一份事件契约
（`subscription_opened` / `resource_updated` / `subscription_closed`）：

| 协商结果 | 机制 |
|---|---|
| 版本 ≥ `2026-07-28` | `subscriptions/listen(resource_subscriptions=(uri,))`，后台任务把 `ResourceUpdated` 转进队列。**即使服务器仍上报旧的 `resources.subscribe` 标志也走这里**（该版本已移除该方法） |
| 旧版本且服务器声明 `resources.subscribe` | `subscribe_resource(uri)`，退出时 `unsubscribe_resource` |
| 两者都不满足 | 409 `mcp_capability_unavailable`，不伪造订阅 |

两条路径都按**精确 URI** 过滤，所以 SSE 契约与协商版本无关。

### 保活 ping

订阅会话活几分钟且不做重连，所以会话自己发 `ping`：间隔 = TTL 预算 ×
`PING_INTERVAL_FRACTION`（当前 `0.5`，即 300s TTL → 150s 一次）。

- 服务器已经不响应时，`ping` 失败即把订阅标记为 `connection_lost` 并结束 SSE
  流，而不是等到 TTL 或读超时才被发现；
- 不新增后台保活层、不重连、不重放订阅：仍是一个请求一个会话。

## 服务器日志转发（可选）

默认关闭：不开 `mcp_config.server_log_level` 时不注册 logging 回调，也不向服务器
要任何日志级别，日志量与升级前一致。开启后（值为 MCP 级别名，如 `debug`）：

| 协商版本 | 取值方式 |
|---|---|
| < `2026-07-28` | 握手后调 `logging/setLevel`，且只在服务器声明 `logging` 能力时发送；失败只告警，不影响操作 |
| ≥ `2026-07-28` | 不调已弃用的 `logging/setLevel`（SEP-2577），改由每请求 `_meta` 的 `io.modelcontextprotocol/logLevel` 表达（`ClientSession(log_level=...)`，SDK 负责盖章） |

转发规则：

- `notifications/message` 进应用日志，级别按服务器声明的级别映射（`notice`→`INFO`，
  `alert`/`emergency`→`CRITICAL`），记录带 `mcp_server`（如 `tool:<uuid>`）与
  `mcp_server_log_level` 字段便于关联；
- **只在 `DEBUG` 上回显 `data`**（并截断到 2000 字符）：服务器日志正文不可信，可能
  携带用户内容或凭据，普通日志级别只记结构化元数据；
- 回调自身抛错只吞掉并告警，绝不弄死 SDK 读循环。

## 身份与用户级密钥箱

MCP 连接永远不带静态凭据，凭据来自 `ToolConnection`：

- **作用域**：`personal` 连接有且只有 owner，按团队隔离；`team` 连接不能冒充个人身份。
  管理员不能管理别人的个人连接。
- **声明与取值分离**：工具定义只能声明 `connection_fields`（字段名），值只存在于连接行；
  配置里用 `{{field}}` 占位，在 `build_mcp_config` 里渲染，渲染结果不落库、不回包。
- **加密**：连接 secrets 用 Fernet 加密存储，只有 `ResolvedConnection` 内部可见；
  写入受 `tool_secret_contract` 约束，定义落盘时携带明文 secret 会被拒绝。
- **每次调用重新校验**：`resolve_connection` 每次重新校验成员关系、owner、状态与
  `secret_version`，不缓存解析结果。
- **OAuth**：MCP 授权走 RFC 9728 protected-resource metadata + RFC 8414 AS metadata，
  支持 DCR、PKCE(S256)、RFC 8707 `resource` 指示器、refresh token 加锁轮换。
- **与协议面的关系**：MRTR 续跑、订阅、metadata 列表都走同一套
  `execute_stored_tool` 边界，因此审批、身份、审计行为一致。

## 缺口登记

| 缺口 | Issue | 影响 |
|---|---|---|
| SDK 原生任务 API | #500 | 客户端循环依赖两处 SDK 私有面（能力钩子、原始 dispatcher），SDK 补齐后应替换；`tasks/list` 不在范围内 |

## 维护约定

- 升级 `mcp` SDK 后，按本表逐行核对：新增能力要么实现，要么在「缺口登记」里留 issue。
- 变更协议行为时同步更新 `backend/tests/llm/test_mcp_client*.py`、
  `test_mcp_observability_issue499.py`、`test_mcp_input_required_roundtrip.py`、`test_mcp_tasks*.py` 与
  `backend/tests/services/test_mcp_subscriptions_listen.py`。
- 能力缺失一律 fail closed，不允许「降级成看起来成功了」。
