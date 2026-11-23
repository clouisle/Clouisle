# MCP 协议覆盖矩阵

本文档是 MCP 客户端能力的唯一权威清单：Clouisle 只作为 **MCP 客户端**消费外部
MCP 服务器，不对外暴露 MCP 服务端。协议实现集中在
`backend/app/llm/tools/mcp_client.py`，身份与凭据在
`backend/app/services/tool_connections.py`。

## 运行时基线

- SDK：`mcp>=2.2.0`（当前锁 `2.3.0`），协议最高版本 `2026-07-28`。
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
| `ping` | 未实现 | — | 见 #499 |
| `logging/setLevel` + `notifications/message` | 未实现 | — | 见 #499；新协议已弃用该能力 |
| `tools/list` / `tools/call` | 支持 | `enumerate_tools` / `execute_tool` | 含 `outputSchema`、`structuredContent`、`_meta`、annotations |
| `resources/list` · `templates/list` · `read` | 支持 | `enumerate_resources` / `enumerate_resource_templates` / `read_resource` | URI 校验拒绝未展开的 RFC 6570 模板 |
| `prompts/list` · `prompts/get` | 支持 | `enumerate_prompts` / `get_prompt` | 返回值按不可信内容处理，需预览后使用 |
| `completion/complete` | 支持 | `complete` | prompt 与 resource_template 两种引用 |
| 分页 | 支持 | `_enumerate` / `_fetch_page` | `max_pages` / `max_items` + `truncated` 元数据 |
| 内容块 | 支持 | `_content_block` | text / image / audio / resource_link / resource；未知类型原样透传 |
| `sampling/createMessage`（服务器主动） | 支持（已弃用方向） | `_CallbackGuard.sampling` + `mcp_interactions` | 不自动应答，落库转人工审批；可限制 `max_tokens`、禁止工具调用 |
| `elicitation/create`（服务器主动） | 支持（已弃用方向） | `_CallbackGuard.elicitation` | form 与 url 两种模式；敏感字段直接 decline |
| `roots/list` | 支持（已弃用方向） | `_CallbackGuard.list_roots` | 只返回显式配置的白名单 root |
| MRTR（`input_required` 回填） | 支持 | `parse_input_responses` + `*_round_trip_kwargs` | 见下文「多轮往返」 |
| `resources/subscribe`（≤2025-11-25） | 支持 | `mcp_subscriptions.open_subscription` | 会话内订阅 + 退出时 best-effort 退订 |
| `subscriptions/listen`（2026-07-28） | 支持 | 同文件 `_pump_listen` | 一次请求声明过滤器，事件流入同一 SSE 契约 |
| `tasks/*`（长任务） | 未实现 | — | SDK 无客户端实现；见 #500 |
| 进度通知（服务器→客户端） | 未实现 | — | 见 #497 |
| 取消（`notifications/cancelled`） | 未实现 | — | 见 #497；当前超时即关会话 |
| `x-mcp-header` 参数镜像 | 未实现 | — | 见 #498 |
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
  `connection_id`（否则默认连接在两段之间变化，会把 A 账号的答案交给 B 账号的会话）；
  `identity_policy=none` 的工具没有可漂移的身份，不强制要求。
- **审批绑定**：`request_state` 与 `input_responses` 进入 `parameters`，自动进入
  `build_parameter_snapshot` 摘要；已批准的请求不能被换成另一组答案。不续跑时
  这两个字段不写入 `parameters`，因此升级前 parked 的执行仍可恢复。
- **失败要响**：SDK 不支持回填时抛错，而不是丢掉答案重发（那样会无限循环在同一个
  问题上）。

## 资源订阅的双路径

会话协商结果决定用哪一种，两者都向 SSE 端点输出同一份事件契约
（`opened` / `update` / `closed`）：

| 协商结果 | 机制 |
|---|---|
| 版本 ≥ `2026-07-28` | `subscriptions/listen(resource_subscriptions=(uri,))`，后台任务把 `ResourceUpdated` 转进队列。**即使服务器仍上报旧的 `resources.subscribe` 标志也走这里**（该版本已移除该方法） |
| 旧版本且服务器声明 `resources.subscribe` | `subscribe_resource(uri)`，退出时 `unsubscribe_resource` |
| 两者都不满足 | 409 `mcp_capability_unavailable`，不伪造订阅 |

两条路径都按**精确 URI** 过滤，所以 SSE 契约与协商版本无关。

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
| 进度回传与显式取消 | #497 | 长调用无进度；中断后服务器继续算 |
| `x-mcp-header` 参数镜像 | #498 | 带 header 参数的工具少头 |
| logging + ping | #499 | 服务器日志不可见；长连接静默断开 |
| `tasks/*` | #500 | 长任务只能同步等超时 |

## 维护约定

- 升级 `mcp` SDK 后，按本表逐行核对：新增能力要么实现，要么在「缺口登记」里留 issue。
- 变更协议行为时同步更新 `backend/tests/llm/test_mcp_client*.py`、
  `test_mcp_input_required_roundtrip.py` 与 `backend/tests/services/test_mcp_subscriptions_listen.py`。
- 能力缺失一律 fail closed，不允许「降级成看起来成功了」。
