# MCP 连接与审批

本指南面向配置已保存 MCP 服务器、并管理其调用身份与审批的团队管理员和运维人员，介绍连接、委托、OAuth、审批、资源、提示词以及实时资源订阅。字段级请求/响应说明见 [工具 API](../../api-reference/endpoints/tools.md#saved-mcp-server-protocol)。

## 已保存的服务器，而不是客户端凭据

已保存的 MCP 工具会把传输方式、URL/命令以及请求头/环境变量模板保存在工具定义中。Agent、工作流或工具面板使用该服务器时，后端会为当前身份解析连接，并且只注入工具声明的字段。调用方只选择**使用哪个身份**，绝不会提交 `mcp_config`、请求头或凭据值。响应和运行事件都不包含秘密值或渲染后的服务器配置。

原始的 `POST /tools/mcp/list-tools` 及管理端同类接口仅用于未保存定义的临时诊断，并计划从已保存工具对话框中移除。任何已经保存的配置都应使用已保存服务器接口（`/tools/{tool_id}/mcp/...`）。

## 身份类型

每个工具声明一种身份策略：

| 策略 | 含义 |
|------|------|
| `none` | 不需要外部身份；不接受连接 |
| `team_only` | 使用团队范围连接 |
| `personal_only` | 使用当前操作者的个人连接 |
| `selectable` | 每次请求必须选择 `personal` 或 `team` |

连接范围：

| 范围 | 所有者 | 说明 |
|------|--------|------|
| `user` | 个人用户 | 按团队隔离；仅所有者可交互使用 |
| `team` | 团队 | 共享账号；需要团队成员身份 |
| `site` | 站点管理员 | 全局账号；工具编辑者不能覆盖 |

需要身份但没有可用连接时，执行会明确失败（`tool_connection_required`、`tool_connection_inactive`），绝不会回退到团队或全局明文凭据。只有在调用方未指定连接且入口可交互时，才会使用标记为默认的连接。

## 连接账号

1. 打开工具的连接管理，选择范围（`personal` 或 `team`；`site` 仅管理员可用）。
2. 只填写工具声明的字段。值只写、加密存储；接口只返回字段名、可选的账号标签和秘密版本号。
3. 选择是否为该范围与服务的默认连接。
4. 通过 `config_set` / `config_remove` 轮换或删除秘密；携带 `expected_secret_version` 可避免覆盖并发修改。

撤销连接是终态操作，并会同时撤销其授权。需要更换外部账号时请新建连接；审批绑定连接版本，旧审批不会自动迁移。

## MCP OAuth

如果服务器定义启用了 `mcp_config.oauth`，连接必须先完成授权：

1. `POST /tool-connections/{id}/oauth/start` 返回授权 URL 和一次性 state。需要客户端密钥时，密钥只写且要求工具写权限。
2. 浏览器完成提供方流程后回到精确允许的前端路径，回调完成代码交换。
3. `GET /tool-connections/{id}/oauth` 显示授权状态、scope 和过期时间，不返回令牌。
4. 断开连接会清除本地令牌并尽力撤销远端授权；远端失败会明确报告，但不会阻止本地撤销。

流程使用 PKCE S256、一次性 state、精确回调匹配、最小 scope 和 refresh 轮换。发现与令牌端点受集中 SSRF 策略约束，且必须使用 HTTPS。`invalid_grant` 会把连接标记为 `reauth_required`，需要重新发起授权。符合规范的提供方应可工作，但本平台不声明与任何特定第三方提供方已验证互通。

## 委托个人连接

后台或非交互入口（Agent 运行、工作流、API Key、定时任务、渠道、嵌入）无法询问用户。个人连接的所有者可以显式授权某个入口：

- 入口类型：`agent`、`workflow`、`api_key`、`schedule`、`channel`、`embed`。
- `allowed_operations` 使用精确操作键，例如 `tool:query_orders`、`read:resource`、`prompt:summarize`、`list:tools` 或 `*`。
- 授权可设置过期时间，可随连接或单独撤销。

管理员不能委托他人的个人账号，团队或站点连接也不能使用个人授权。入口所有者或连接身份变化后，需要重新授权并重新审批。

## 使用服务器能力

已保存的 MCP 服务器可以提供：

- **工具**：带参数调用；结果保留内容块、结构化内容和错误状态。
- **资源**：按 URI 列出与读取。资源文本和链接属于不可信上下文；后端不会自动下载链接。
- **资源模板**：单独列出；展开 URI 后读取。
- **提示词（Prompts）**：列出并按参数渲染。消息需要预览，不会自动成为系统指令。
- **补全**：在同一身份与审批边界下补全提示词或模板参数。
- **订阅**：为单个 URI 流式接收资源变更通知。

列表结果有上限，会报告 `truncated`/`truncation_reason`，并提供可续传的 `next_cursor`（页内截断除外）。元数据发现默认允许，即使工具的操作默认是拒绝或需要审批；显式的 `list:<kind>` 覆盖会被遵守，站点/团队/入口策略层仍然生效。页大小和游标属于审批绑定的一部分：审批通过后不能更改分页范围。

## 审批

策略由站点、团队、入口层与工具自身策略组合。`deny` 优先，审批要求取并集，低层不能放宽高层。审批关卡可以面向：

- 调用者（仅交互入口；调用者必须是团队成员），
- 指定用户，
- 团队角色（仅显式允许时才能自批）。

需要审批时，接口返回可查询的待处理引用而不是结果。在审批待办中批准或拒绝后，携带 `execution_id` 重放同一请求。参数、身份、分页范围、连接版本或工具定义的任何变化都会使请求失效。决策是幂等的，且不会修改已绑定参数。拒绝、过期、撤销和运行停止都是终态，绝不会变成批准。

**结果未知不会自动重试。** 如果外部副作用可能已经发生但结果未知（崩溃、连接丢失），执行会标记为 `outcome_unknown`。请核对外部系统并重新发起请求；平台不会静默重放调用。

服务器发起的 sampling 与 elicitation 同样等待人工处理：只有显式受众可以接受/拒绝，表单内容会按 schema 校验且不得收集凭据，URL elicitation 只允许配置的主机，会话丢失会把交互标记为 `connection_lost`，且不会重放外层调用。

## 资源订阅

使用 `GET /tools/{tool_id}/mcp/resources/subscribe?team_id=…&uri=…`，并设置 `Accept: text/event-stream`。审批先执行：审批前返回普通 JSON 待处理信封，审批后携带 `execution_id` 重放才会打开流。

- 事件：`subscription_opened`、`resource_updated`、`subscription_closed`。
- 关闭原因：`client_disconnected`、`ttl_expired`、`connection_lost`、`capability_unavailable`。
- 订阅仅在当前请求内有效。没有后台监听或持久订阅：断开或进程重启即结束，更新不会重放。
- 最多排队 100 条更新；客户端过慢时丢弃最旧更新。
- 生命周期受 `MCP_SUBSCRIPTION_TTL_SECONDS` 限制（默认 300 秒，最大 3600 秒）。

## 限制与运维

| 配置 | 默认 | 范围 | 用途 |
|------|------|------|------|
| `MCP_SUBSCRIPTION_TTL_SECONDS` | 300 | 10–3600 | 实时订阅最长存活时间 |
| `MCP_INTERACTION_TTL_SECONDS` | 300 | 10–900 | sampling/elicitation 最长等待时间，以及 MCP 回调窗口上限 |

协议预算对调用方固定：连接 10 秒，元数据列表/能力 20 秒，资源读取与提示词获取 30 秒。工具调用至少 60 秒，并随服务器配置的 `mcp_config.callback_timeout_seconds`（默认 120 秒，受交互 TTL 约束）增长。内容默认限制为单块 1,000,000 字节、总计 4,000,000 字节。

## 故障排查

| 现象 / 代码 | 含义 |
|-------------|------|
| `403 tool_access_denied` | 无消费团队访问权，或私有工具不可共享 |
| `403 tool_connection_required` | 工具需要身份，但没有解析到可用/默认连接 |
| `409 tool_connection_inactive` | 连接或授权已撤销/失效 |
| `409 tool_connection_grant_required` | 非交互入口缺少委托授权 |
| `409 mcp_capability_unavailable` | 服务器未声明所需能力 |
| `504 mcp_request_timeout` | 协议预算超时 |
| `413 mcp_content_too_large` | 资源/提示词/结果超出内容预算 |
| `409 tool_execution_not_ready` | 待处理执行被拒绝、过期或已完成 |
| `6504 tool_approval_not_authorized` | 调用者不在关卡受众中（调用者关卡要求团队成员） |
| `409 6510` | 审批策略格式错误，需要管理员修复 |
| `6434 tool_oauth_reauth_required` | OAuth 令牌已不可用，需重新授权 |

## 相关文档

- [工具 API](../../api-reference/endpoints/tools.md#saved-mcp-server-protocol) - 精确路由、DTO 与信封
- [工具指南](TOOLS_zh-CN.md) - 工具类型与配置
- [工具管理](tool-management.md) - 管理员操作
