# 通用工具连接、执行审批与 MCP 协议补全设计文档

## Background & Goals

状态：已完成代码落地与定向全链路验证（不含浏览器与真实第三方线上个人服务交互）。

已确认的范围：
- MCP、HTTP 等工具共用个人／团队连接机制。
- MCP 补全 Tools、Resources、Resource Templates、Prompts、OAuth，以及 sampling、elicitation、roots 双向交互。
- 无交互入口使用个人连接时必须显式绑定并获得连接所有者授权。
- 工具执行统一审批，不允许各入口自行绕过。

成功标准：两名用户使用同一工具定义操作各自外部账号；后台任务只使用被显式授权的连接；审批绑定具体操作；MCP 协议能力有实际产品入口和错误处理；进程重启不造成身份漂移或盲目重复副作用。

### 当前代码证据

| 位置 | 已核对行为 | 需要改变的边界 |
|---|---|---|
| `backend/app/models/tool_config.py` | 按工具名、团队保存 JSON 凭证；团队为空表示全局 | 无个人所有者和授权委托 |
| `backend/app/models/tool.py` | 工具定义保存 MCP 配置和凭证 | 定义与秘密分离 |
| `backend/app/llm/tools/executors.py::execute_http_tool` | 接收 credentials，渲染 Headers、query、body；有集中 SSRF 校验 | 保留传输执行器，凭证改由统一解析器提供 |
| `backend/app/llm/tools/mcp_client.py` | stdio/SSE/Streamable HTTP；每次建立会话；list_tools 无应用层总超时；结果提取 text/data | 能力协商、分页、完整结果、会话和双向回调 |
| `backend/app/services/tool.py` | 内置、HTTP、数据库、MCP 分支各自取配置 | 统一执行上下文和策略入口 |
| `backend/app/services/agent.py::_execute_tool` | MCP 从 Agent 配置定位服务器后直接执行；已有 user_id 参数 | 所有执行路径采用一致连接及审批规则 |
| `backend/app/api/v1/endpoints/chat_helpers/tool_executor.py` | HTTP 直接使用 tool.credentials | 删除执行端的独立凭证选择 |
| `backend/app/models/agent_run.py` | 已有 WAITING、pending_tool_* 和持久化输入 | 复用运行等待状态，不能把网络会话当可序列化状态 |
| `backend/app/llm/tools/builtin/ask_user.py` | 返回 ToolInteractionRequest | 可复用交互呈现及等待原语；不能将普通回答当作审批 |
| `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/tool-node-config.tsx` | 前端传 mcp_config 获取内部工具 | 改传服务定义 ID 和授权连接引用，不向前端返回秘密 |

本文只断言以上已核对事实；其余新文件、接口、字段均为拟议设计。实施前继续核对 worker、工作流、渠道、API Key 和加密实现的具体接入点，不凭文件名推断契约。

## High-Level Design

### 三个独立问题

1. 访问权限：是否允许主体访问工具、资源和运行。
2. 连接授权：以哪个外部账号访问；允许哪些入口委托使用。
3. 执行审批：是否批准这一次具体操作。

任何一层通过都不能代替另一层。审批人不能借批准操作获得凭证或扩大连接权限。

执行顺序：校验主体和工具权限 → 解析操作及连接 → 解析最终业务参数 → 评估策略 → 必要时持久化等待 → 执行前重新校验权限、版本与授权 → 原子领取执行权 → 调用适配器 → 保存结果。

### 通用模型：只抽象连接与策略，不抽象所有工具协议

以下模型拟放入 `backend/app/models/tool_connection.py`、`tool_approval.py`，业务服务放入 `backend/app/services/tool_connections.py`、`tool_approvals.py`、`tool_execution.py`。

- **工具定义**：继续复用 Tool；保留 HTTP 请求模板、MCP 地址／传输、参数 schema。新增连接字段 schema、认证类型、允许的身份模式及操作策略；不包含秘密。
- **ToolConnection**：tool_id 或稳定内置工具键（二选一）、team_id、scope=user/team/site、owner_user_id、名称、加密配置、secret_version、status、created/updated_at。个人连接必须有所有者；非个人连接不能伪装成用户身份。允许同一用户为同一服务配置多个外部账号，默认连接另设唯一约束。
- **ConnectionGrant**：连接 ID、授予者、入口类型及入口 ID、允许操作、有效期、撤销时间和版本。个人后台连接只能由所有者明确授予；管理员不可代替用户授权。API Key、定时触发器、渠道及工作流使用各自稳定入口标识；复制入口不复制授权。
- **ToolExecution**：稳定执行 ID、运行及工具调用 ID、发起主体、有效执行身份、连接 ID/版本、工具定义版本、操作名、加密业务参数快照、参数摘要、策略版本、状态、结果引用。秘密不复制到参数、消息或任务载荷。
- **ApprovalRequest/Decision**：执行 ID、审批类型、脱敏展示、审批人约束、过期时间、状态及不可变决策记录。执行允许有多个审批关卡，所有要求均满足才可执行。
- **InteractionRequest**：运行 ID、执行 ID、kind、请求内容、受众、状态、到期时间；关联审批但不把 elicitation、ask_user 都建模为批准。

数据库约束必须保证主体与范围一致，跨团队引用不可仅依赖前端筛选。复用现有可靠加密设施；若不足，先完成带 key_id 的信封加密及轮换，不允许 JSON 明文落盘。密钥必须由部署注入，不硬编码。

### 连接解析规则

#### 身份模式的配置契约

工具定义声明 `identity_policy=none|team_only|personal_only|selectable`；站点托管工具使用独立的受保护站点配置，不允许普通工具编辑者切换为个人覆盖。

| 模式 | 入口可选择的连接 | 示例 |
|---|---|---|
| none | 不接受连接 ID，不注入外部账号秘密 | 无认证本地计算 |
| team_only | 当前团队获准的共享连接 | 团队工单服务账号 |
| personal_only | 当前用户连接；后台为所有者显式委托的个人连接 | 滴答清单、个人邮箱 |
| selectable | 入口必须明确选择 personal 或 team，再按对应规则解析 | 同时支持个人和服务账号的系统 |

`selectable` 不定义自动回退顺序。Agent 工具项、工作流工具节点、API Key 及定时入口保存 `connection_mode`；团队模式保存明确连接引用，个人交互模式在运行时使用调用者选择／默认连接，个人后台模式保存显式连接与 grant 引用。定义收紧允许范围后，旧入口绑定在执行前验证并拒绝不兼容配置。

工具的 private/team 可见性与上述身份模式独立：团队可见的工具可以要求每个人授权自己的账号。MCP 的身份模式设在服务器定义，内部操作继承当前会话连接，不在同一会话内切换账号；若操作需要另一账号，必须另建执行及会话并重新授权。


| 场景 | 连接选择 | 缺失／失效 |
|---|---|---|
| 登录用户交互，current_user 模式 | 当前用户显式选择或其默认连接 | 返回 connection_required，不回退 |
| 显式 shared 模式 | 入口配置的团队／站点连接，检查使用权限 | 拒绝，不尝试个人连接 |
| API Key、定时、渠道等非交互入口 | 显式绑定连接；个人连接还需有效 ConnectionGrant | 拒绝，不采用工具创建者身份 |
| 子工作流、嵌套 Agent、sampling | 继承受限执行上下文；不可自行提升身份 | 无明确上下文则拒绝 |

个人连接按团队隔离；相同外部服务在不同团队分别授权，避免通过跨团队共享工具继承个人数据。跨团队共享只共享工具定义；目标团队创建自己的连接。团队连接如需跨团队使用必须另行显式授权，本设计默认不允许。

调用上下文由后端建立：actor、effective principal、team、entrypoint、run、connection binding、delegation grant、interaction capabilities；不接受模型参数覆盖这些字段。重试和恢复固定连接 ID，不重新挑选“当前默认账号”。授权撤销在后续调用及恢复前生效，已发送的外部请求不能保证追回。

HTTP 支持 API Key、Bearer、Basic、OAuth2 及已有凭证模板字段；连接秘密只允许注入定义声明的字段，业务参数不能覆盖凭证。数据库连接的用户名／密码等可使用同一机制。代码工具仅对显式声明的环境变量提供连接值，并继续受 sandbox 边界约束；不得自动向任意代码注入所有凭证。站点搜索引擎仍保持站点管理，不能被个人连接覆盖。

### 统一审批策略

- 决策：allow、deny、require_approval。使用结构化配置，不引入通用脚本／表达式语言。
- 层级：站点安全底线、团队强制策略、工具操作策略、入口附加限制；deny 优先，所有审批要求取并集，低层不能放宽上层强制要求。工具内的操作覆盖只替换本工具默认值，不覆盖站点／团队强制策略。
- 支持调用者确认、指定用户、指定团队角色；角色审批默认不允许发起者自批。团队审批不替代个人连接所有者的委托授权。
- MCP 注解仅供展示和策略配置参考，不能自动把服务端标注 readOnly 的操作免审批。HTTP GET 也不天然可信。
- 审批绑定 tool_id、operation、definition_version、连接 ID/版本、有效主体、最终参数摘要及有效期。参数、身份或定义变更使审批失效；密钥刷新可延续同一账号身份，账号／权限范围变化必须提升绑定版本并重新审批。
- 审批 UI 展示对象、范围、副作用、执行账号标签和脱敏参数；用户可以拒绝，不能在审批接口悄悄修改参数。修改参数生成新执行请求。
- 秘密、认证 Headers、OAuth code、完整敏感结果不进入展示、审计或 SSE。敏感业务参数加密保存，审批人仅按权限查看必要内容。
- 数据库原子状态变更保证一个决策生效、执行权只领取一次。外部服务无幂等能力时不声称 exactly-once：发送后进程崩溃进入 outcome_unknown，不自动重试；提供人工核对和新执行请求。
- 请求状态：pending → approved/rejected/expired/cancelled；执行状态另为 awaiting_approval → ready → executing → succeeded/failed/outcome_unknown。拒绝、过期、撤销、停止运行均不可恢复成批准。
- 所有执行入口（含工具测试、管理员测试和直接调用）走统一边界；模型不能通过别名、自定义 HTTP 或嵌套工具绕过目标工具策略。平台不能识别任意代码／HTTP 的真实业务语义，故未知能力采用保守策略，不承诺语义级防绕过。

#### 普通工具与 MCP 的审批配置契约

普通 HTTP、数据库、代码及内置工具按稳定工具键设置默认策略；MCP 服务器定义设置默认策略，并按原始内部工具名保存显式操作覆盖。MCP 发现缓存和模型调用别名不得作为策略主键。

工具级策略包含 `default_decision=allow|deny|require_approval`、审批关卡及 `operation_overrides`。每个覆盖项是同结构的完整策略，只有管理员显式配置才生效。服务默认“需审批”时，可明确配置查询免审批、删除需审批；若团队强制所有操作审批，则查询覆盖也不能免除。服务默认“禁止”只表示未列入允许清单的操作禁止；要禁止整个服务应使用上层强制 deny 或停用服务。

未配置默认值的新工具一律要求审批；MCP 新发现的内部工具继承服务器默认值，默认值缺失则要求审批。缺少有效审批人／调用者交互受众时返回 policy_configuration_required，不隐式放行。迁移旧配置也必须生成显式策略；无法确定审批受众或历史策略时停用相关执行并要求管理员确认，不能推断曾经直连就是永久免审批。

Resource 读取、Prompt 获取及 sampling 等使用区分操作类型的策略键，不与同名 MCP tool 混淆。用户预览／提交模板或 elicitation 表单不等于批准外部副作用。sampling 的模型预算和授权检查独立于外层工具是否免审批。

界面配置落点：工具编辑页显示身份模式与默认审批规则；MCP 内部工具表提供逐操作覆盖和“继承默认”状态；Agent／工作流绑定页显示选定身份模式及有效策略摘要。服务端计算最终策略及来源，前端不得自行合并策略或信任请求携带的“已批准”标记。

验收组合：personal_only 滴答清单查询 allow／删除调用者确认；team_only 工单查询 allow／关闭指定角色审批；selectable 工具两种身份各执行一次且不得回退；新发现操作继承默认；团队强制审批无法被内部工具 allow 覆盖；后台授权个人连接不自动批准发送邮件。


### API 与界面契约（拟议）

- `/tools/{id}/connections`：列出有权使用的连接元数据、创建连接；更新／删除按 connection_id 授权。响应只返回字段是否已设置及账号标签，不返回秘密；空值、保留与删除必须有明确区别。
- `/tool-connections/{id}/grants`：所有者为具体入口授予／撤销权限；更换入口所有者后重新授权。
- `/tool-connections/{id}/oauth/start` 和受校验 callback：登录态绑定的一次性流程。
- `/tool-approvals`：按受众分页展示待办；`/{id}/decision` 接受批准／拒绝与幂等请求 ID，不接受客户端指定审批人或执行参数。
- `/tools/{id}/mcp/{tools,resources,resource-templates,prompts}`：使用连接引用和分页游标；读取资源、获取模板和调用工具走统一权限、策略与限额。
- `/run-interactions/{id}/response`：受众校验、schema 校验、幂等提交及过期处理。不能把有运行查看权视为有审批权。
- 非流式调用遇到等待时返回可查询的执行／交互引用，不保持 HTTP 请求无限等待。SSE 只投递脱敏事件，重连按持久化序列恢复。

界面：工具配置页展示身份模式、连接字段和逐操作审批策略；个人“我的连接”管理账号和后台授权；聊天与工作流显示缺授权、待审批、服务端提问和结果；统一审批待办支持指定审批人，不依赖聊天窗口在线。API Key／定时配置页明确显示外部执行账号和委托范围。平台端与管理端复用安全 DTO 和交互组件，管理员不可读取他人个人秘密。

## MCP 协议设计

### 能力与版本

以实施时官方稳定规范和实际 Python SDK 支持矩阵为准，锁定并记录版本；本文不假设所有服务支持同一版本。initialize 保存协商版本与 capabilities，仅声明真正实现且当前入口允许的客户端能力。服务端无某能力时界面禁用，不伪造成功。

| 能力 | 实现要求与产品语义 |
|---|---|
| Tools | 分页列表、inputSchema/outputSchema、annotations、调用；新工具或 schema 变化重新校验策略 |
| Resources | 列表与读取、MIME 与文本／blob、URI 原样交给 MCP 服务；作为带来源且不可信的上下文 |
| Resource Templates | 独立列表及 URI 模板参数表单；不是假设列表枚举所有资源 |
| Prompts | 列表、参数、get_prompt 返回角色消息；用户预览后应用，不自动提升为系统指令 |
| Completion | 为支持 completion 的 prompt／资源模板提供参数补全，复用限额和连接权限 |
| Notifications | 正确处理工具／资源／模板列表变更、进度与日志；通知触发按身份隔离的缓存失效 |
| Resource subscriptions | 按服务端能力订阅／取消订阅与更新通知；只在活跃会话有效，不承诺永久后台监听 |
| Structured/multimodal results | 保留 content、structuredContent、isError 与资源链接、MIME、注解；转换模型不支持的内容时明确呈现限制，不静默丢失 |
| Cancellation/timeouts | 连接、发现、读取、调用和整体运行均有预算；取消传播到协议层，不能宣称撤销已发生的副作用 |
| Sampling | 服务端请求模型生成；使用 Clouisle 已授权模型和额度，预览上下文并独立批准，限制 token、递归深度、并发及可调用工具 |
| Elicitation | 支持协商版本的 form／URL 模式，校验 schema，分别返回 accept/decline/cancel；不通过表单收集密码／Token；URL 模式仅外部受验证授权页面 |
| Roots | 仅返回显式配置且当前连接获准的 roots；roots 是协作范围声明，不是沙箱安全边界，不暴露宿主机路径 |

分页限制最大页数、总条目和重复游标；超限返回明确截断信息。内容限制单项字节数、总字节数和模型上下文预算；资源链接不能由后端直接任意下载，读取经 MCP 或集中 SSRF 校验及资源权限边界。

### 会话与持久化等待的关键限制

MCP JSON-RPC 请求和 stdio 进程不是可持久化 continuation。不能把 socket 或 request_id 存到 PostgreSQL 就宣称重启可恢复。

采用独立 MCP 会话执行进程，由显式部署的执行角色持有活动会话；API、Agent worker 和 workflow worker 提交持久化执行请求。实现阶段评估复用现有 worker 部署角色，不在 API 内创建无管理守护进程。会话按连接 ID、身份、凭证绑定版本和运行隔离，有容量、空闲／最长存活和退出清理。初期只在同一运行内复用，不跨用户共享会话。

审批尽量在发起 MCP 调用前完成，运行可安全停放。调用内的 sampling／elicitation 通过持久化 InteractionRequest 和通知投递，活动会话等待有界响应，不阻塞普通 API worker。执行进程故障或服务端断线时：交互记录保留，但原 RPC 标记 connection_lost；不能重新执行外层有副作用工具来补回调。具备协议级恢复能力时按协商契约恢复，否则进入失败／结果未知，由用户重新发起。UI 必须显示这一限制。

不具备交互渠道的入口只声明可兑现能力：可将交互交付给已绑定的负责人及审批待办；无受众或超过期限则拒绝／取消，绝不隐式批准。roots 按入口限制；sampling 继承原执行身份且不能获取额外连接。

### OAuth 与网络安全

MCP OAuth 采用协商规范要求的发现与授权流程；HTTP 工具采用配置化 OAuth2 提供方。复用状态存储与令牌加密服务，但不将二者的发现规则混为一谈。

要求 PKCE、一次性 state、登录用户及连接绑定、精确 callback、授权服务器／resource 绑定、最小 scope、撤销和 refresh rotation。跨进程刷新用数据库锁／版本比较保证单次刷新，invalid_grant 标记 reauth_required。授权发现、重定向、Token 端点与 MCP SSE 回传地址均受集中 SSRF 和网络策略控制，拒绝跨源泄漏认证 Headers。外部 URL 不能由模型改变授权服务器。

stdio 等于在服务端执行程序：仅允许管理员审核的命令与参数模板，个人仅配置被声明的凭证字段；不得开放任意 command／env。继承环境最小化，不继承部署秘密。运行身份、文件系统和网络隔离必须使用真实进程／容器控制，roots 不提供这种隔离。

## Implementation Plan

所有阶段已在当前分支分段完成并附带自动化回归验证。

### Stage 1: 连接模型、秘密存储与迁移
- **Files modified**：`backend/app/models/tool.py`、`tool_config.py`；新增 `tool_connection.py`；数据库迁移入口在实施前核对；复用已核对的加密设施。
- **Specific logic**：建立连接及授权模型、范围约束和密钥版本；清点 HTTP/MCP/数据库配置中的秘密并迁移；旧共享凭证仅迁移为相同范围共享连接，绝不推断个人归属；歧义及重复配置停迁并报告元数据。
- **Validation**：真实 PostgreSQL 上演练备份、幂等迁移、空团队约束、密钥轮换、跨用户拒绝；对比迁移前后外部账号不变。敏感字段不得再从工具详情返回。

### Stage 2: 统一身份解析与所有执行入口切换
- **Files modified**：`backend/app/services/tool.py`、`agent.py`、`backend/app/api/v1/endpoints/chat_tools.py`、`chat_helpers/tool_executor.py`、平台／管理 tools endpoints；worker、workflow、embed、channel 具体文件通过引用清单确认。
- **Specific logic**：实现统一执行上下文和 resolver；HTTP/MCP/内置/数据库使用解析结果；传播 API Key／定时／渠道主体及 grants；嵌套执行继承受限身份；前端不再上传已有服务的秘密配置。
- **Validation**：A/B 用户操作不同账号；切默认账号不影响已停放请求；撤销 grants／退出团队后恢复拒绝；所有测试执行入口同样受限。枚举每个传输执行器的引用，逐项标记迁移或纯内部调用。

### Stage 3: 统一审批与持久化恢复
- **Files modified**：新增 approval/execution 模型与服务；`backend/app/models/agent_run.py`、Agent worker、workflow orchestrator、运行 API 与审计服务的实际接入点。
- **Specific logic**：确定性策略、审批受众、脱敏、超时、状态机、执行权领取、结果未知；复用已有运行 WAITING 与交互原语，不复用 ask_user 的答案语义。
- **Validation**：拒绝／过期／重复批准／参数变更／撤销凭证／两个 worker 竞争／发送后崩溃；HTTP、MCP、工具测试和后台入口均不能绕过。

### Stage 4: MCP 常用协议、OAuth 与会话执行
- **Files modified**：`backend/app/llm/tools/mcp_client.py`、工具 schemas/endpoints；新增受管理 MCP 会话执行模块及部署角色；部署清单具体路径实施前核对。
- **Specific logic**：协商、Tools/Resources/Templates/Prompts/Completion、分页、结果保持、通知、订阅、超时取消；OAuth、安全网络访问与身份隔离会话。
- **Validation**：真实 stdio/SSE/Streamable HTTP 测试服务验证；分页循环、无能力、超大内容、结构化／图片／资源结果、OAuth 拒绝与并发刷新、会话串号及关闭清理。

### Stage 5: 双向交互与统一交互界面
- **Files modified**：MCP 会话回调、交互服务、运行事件；`frontend/hooks/use-chat.ts`、聊天／工作流呈现组件；新增连接管理、审批待办与交互组件。
- **Specific logic**：sampling/form 与 URL elicitation/roots；同一交互基础设施、不同语义与授权；模型预算、受众、深度限制；个人连接与入口授权、工具策略编辑。
- **Validation**：嵌套 sampling 不能提权；用户拒绝与断线；URL 授权不泄密；roots 不返回宿主路径；刷新页面恢复待办；会话执行进程被杀后明确失败而不重放工具。浏览器和服务验证需获得用户明确许可。

### Stage 6: 全链路验收与文档切换
- **Files modified**：沿用现有 backend/tests、frontend 测试布局；`docs/guide/` 工具使用／API／部署文档、双语索引与部署配置；本设计和实施索引。
- **Specific logic**：清除旧直接取凭证、前端秘密回传和绕审批分支；更新 locale JSON 及生成类型；明确兼容矩阵、迁移、密钥与会话执行角色运维。
- **Validation**：用两个测试账号完成个人任务增删、HTTP 个人身份、团队账号、后台显式委托、审批、资源／模板／双向交互；观察外部真实结果而不只检查 mocks；未经许可不启动服务或浏览器。

## Testing Strategy

- **Happy path**：同一工具不同用户不同账号；一个用户多连接；团队共享账号；个人显式委托后台；审批后执行；资源上下文与模板预览；三种 MCP 传输及双向交互。
- **Negative triggers**：伪造 connection_id／actor／审批者、越团队访问、授权缺失、策略收紧、审批过期、OAuth state 重放／refresh 竞争、恶意发现 URL、stdio 注入、未声明 capability、游标循环、资源超限、sampling 递归、敏感 elicitation、取消及结果未知。
- **Regression scope**：Agent 流式／非流式／恢复／重生成，工作流工具节点与嵌套执行，API Key/embed/渠道/定时入口，管理员和平台工具测试、工具共享、站点搜索、数据库工具、sandbox 边界和历史消息展示。
- 永久测试关注权限、状态转换、真实参数绑定和副作用次数，不测试源码字符串或仅转发。真实 smoke 用可清理测试账号／数据；不对用户个人账号执行破坏性实验。
- 设计阶段不运行程序、不声称协议兼容性验证完成；实施前形成稳定规范与 SDK 能力矩阵，并逐项验收以上协议表。

## Risks & Mitigation

| 风险 | 约束与缓解 |
|---|---|
| “通用”演变成插件框架 | 仅统一身份、连接、审批和结果信封；HTTP、数据库、MCP 各自保留适配器 |
| 个人账号被无意委托 | 默认无后台授权；绑定具体入口与操作；所有者可撤销；复制不继承 |
| 等待被误认为 RPC 可恢复 | 数据库等待与活动协议会话分开；故障明确终止／结果未知，不重放副作用 |
| 审批成为 UI 装饰 | 服务端唯一执行边界；管理员／测试入口没有旁路；执行前复核 |
| 内容和秘密泄露 | 加密、脱敏 DTO、按连接缓存隔离、来源标记、上下文预算及模型权限 |
| 协议版本和 SDK 差异 | 锁定稳定版本并维护能力矩阵；不实现的能力不声明 |
| OAuth 刷新改变身份 | 校验外部账号绑定；权限或账号变化提升版本并使审批失效 |
| 老版本进程继续直连 | 切换窗口暂停新调用，排空旧执行进程，完成迁移后部署统一入口，再恢复；不允许新旧执行器同时处理敏感调用 |

### Rollback plan

迁移前备份并记录配置数量和不可逆步骤；先演练可恢复性。遇到异常停止新调用、撤销活动会话、保留审计及审批数据。只在确认旧程序不会读取不兼容数据、不会恢复已发送操作且有受控秘密还原流程后回退程序；否则采用向前修复。禁止把加密秘密批量导出成明文“兼容配置”。删除旧字段安排在切换验证后独立迁移，不能在滚动部署期间先删除。

## 设计阶段验收记录

- 已确认：从仅设计转入完整实施；包含双向 MCP、后台显式连接绑定和统一执行审批。
- 已核对：当前凭证模型、HTTP/MCP 适配器、Agent 直接执行路径、AgentRun 等待字段、ask_user 交互原语与工作流 MCP 选择界面。
- 已执行：连接、审批、策略层、OAuth、协议、双向交互、工作流／Agent 审批恢复和前端组件的 SQLite／ASGI／Bun 隔离验证（后端 270 项、前端 93 项通过），以及内存传输真实 MCP 握手验证。受限于不启动应用服务与浏览器的约束，尚未执行真实浏览器及第三方线上个人服务（如滴答清单线上 OAuth）端到端测试。

### 实施中的执行边界说明

策略编辑对提交后重新读取策略的执行预检生效；已经通过预检的调用可能使用原先绑定且批准的策略完成。权限和策略检查不是对外部副作用的可撤回事务，已发送操作不能保证撤销。服务端反向交互和资源订阅只在活动会话中有效；进程故障不会重放外层工具。
