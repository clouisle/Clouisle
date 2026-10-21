# 集成与 SSO 配置指南

在 **站点设置 → 集成**（`/site-settings/integrations`）统一管理登录身份源、邮件、Webhook、飞书与微信。它们使用同一 Integration 模型，但功能与权限并不混用。内置集成各自打开独立页面（`/site-settings/integrations/email`、`/webhook`、`/feishu`、`/wechat`）；登录身份源仍在列表页以弹窗配置。

## 支持范围

| 类型 | 静态能力 | 管理权限域 |
|---|---|---|
| `oauth2`、`oidc`、`saml2`、`cas` | `user_login` | login |
| `email`、`webhook` | `notification` | settings |
| `feishu` | `directory_sync`、`user_login`、`notification`、`agent_chat` | settings（共享应用凭据、接收方式、通讯录与通知）；login（登录开关）；个人设置（回复智能体） |
| `wechat` | `agent_chat`、`knowledge_collection` | settings（平台功能可用性）；个人设置（各用户授权与连接用途） |

能力由后端注册表静态声明。飞书与微信仅提供**功能开关，不增加集成总开关**；按需启用功能，修改一项不会自动授予其他功能。飞书仍是单实例应用，在 **站点设置 → 集成 → 飞书** 配置。

飞书通讯录同步仍是手动、单向操作。通知仍是独立能力。Agent 对话是另一项显式能力，私聊文本会进入 Clouisle 的 durable AgentRun 执行路径；不会在飞书内部另建 Agent 运行时。

每位用户在 **个人设置 → 飞书** 或通过 `/use` 自行选择回复智能体，候选项仅包括其绑定的 Clouisle 账号有权访问的已发布 Agent。选择按集成和用户隔离，会话仍按聊天、用户和 Agent 隔离；切换只影响后续消息。不处理群聊和媒体。

## 配置飞书 Agent 对话

飞书 Agent 对话复用现有飞书应用集成和 Clouisle durable AgentRun 运行时，是一项显式的 `agent_chat` 能力；开启后不会扩大用户的 Agent 访问权限。

1. 在飞书开发者后台开启机器人能力，授予 `im:message.p2p_msg:readonly`（获取用户发给机器人的单聊消息）、`im:message:send_as_bot`（以应用身份发消息）和 `contact:user.base:readonly`（查询用户基本信息），并订阅 `im.message.receive_v1`（接收消息）事件。发布应用版本，并完成所需的管理员审批，使权限生效。接收群聊 @ 消息的权限不能代替接收私聊消息的权限。
2. 在 **站点设置 → 集成 → 飞书 → 智能体对话** 中选择 **HTTP 回调** 或 **长连接（WebSocket）**，并保存。已有配置默认保持回调模式；飞书开放平台的 **事件与回调** 中也要选择相同的接收方式。
3. 用户通过飞书通讯录同步或飞书登录绑定账号后，在 **个人设置 → 飞书** 中选择回复智能体；不再由管理员配置全局 Agent 名单。
4. 在“集成配置”中启用 `agent_chat` 功能。运行现有 API、Celery Beat 和消费 `agent` 队列的 worker，无需新增服务或接收命令。

“智能体对话”页签始终显示飞书应用必需配置清单，未开启能力或未配置凭据时也可查看。这是配置指引，不代表系统已自动检测飞书权限是否开通。

每位用户在 **个人设置 → 飞书** 中先保存回复智能体，再打开 **启用智能体对话**。该开关立即保存且仅影响本人。关闭后保留选择与历史，暂停新消息接入、待处理消息和未发送回复；已开始的任务仍可能完成。后台共享功能开关也必须开启。

个人设置只显示一项配置提示，依次优先检查通道可用性、账号绑定、所选智能体可用性和选择配置。暂停与切换的详细规则在默认折叠的“使用说明”中查看。

升级时，已有用户保留其最近所选会话的 Agent；未使用过的用户需要自行选择。旧全局名单和会话选择标记会被移除。API 与 worker 必须部署匹配版本，并在 schema 切换后同步重启 worker。

### 长连接：本地或无公网入口的环境

保存 **长连接（WebSocket）** 接收方式。它复用已保存的 App ID 和 App Secret，无需公网回调地址、Verification Token 或 Encrypt Key。在飞书开放平台中选择使用长连接接收事件，并订阅 `im.message.receive_v1`。

消费 `agent` 队列的现有 Celery worker 自动托管接收进程。智能体对话开启、保存长连接方式并配置应用凭据后启动，不依赖全局智能体名单。关闭功能或切回 HTTP 回调会停止接收；修改凭据会重建连接。多个 worker 通过 Redis 过期所有权选主并接管故障；子进程在失去所有权或父进程退出后停止。

智能体对话页显示已保存配置的接收状态：等待 worker、连接中、已连接、重连中、未配置、已关闭或异常。SDK 处理心跳与重连，终止性故障由 worker 退避重启。API、worker 和 Beat 仍需运行，并使用相同数据库、Redis 和 `SECRET_KEY`。本地调试建议使用独立飞书应用，避免与线上争用事件。

“已连接”仅表示 WebSocket 连接成功，不代表消息权限或事件订阅已就绪。如果机器人不回复且没有收件记录，先检查已发布版本是否获得 `im:message.p2p_msg:readonly` 权限，以及 `im.message.receive_v1` 是否使用长连接方式订阅。配置生效后重新发送一条私聊消息；不能假定之前未接收的消息会自动补推。

### HTTP 回调：有公网入口的环境

保存 **HTTP 回调** 接收方式，配置相同的 Verification Token 和 Encrypt Key，并在飞书加密事件推送设置中登记 `https://<backend-host>/api/v1/integrations/feishu/callback`。飞书必须能访问该地址。密钥加密保存且不会通过设置 API 返回。选择长连接时，回调地址会拒绝请求；切回回调方式后自动停止托管接收进程。

### 机器人命令

用户只能通过私聊纯文本使用机器人。`/agents` 查看自己可访问的已发布 Agent，`/use <序号>` 与个人设置共用选择；`/new` 在当前运行结束后新建对话，`/status` 查看状态，`/stop` 停止所选 Agent 的当前运行，`/help` 查看命令。所选 Agent 等待 `ask_user` 回答时，普通文本恢复原运行。

回调 API 详见[飞书 Agent 对话 API](../../api-reference/endpoints/feishu-agent.md)。该地址只供飞书事件回调使用，不是公开应用 API。

## 配置微信功能

进入 **站点设置 → 集成 → 微信 iLink**，按需启用 `agent_chat`、`knowledge_collection` 或两者。收件轮询和处理复用现有 worker 与 Beat，无需新增接收服务或命令。新安装默认关闭两项功能；首次升级根据现有已授权且正在使用的个人连接保留对应功能，之后不覆盖管理员选择。

各用户仍在个人设置中独立扫码授权，并为每个连接选择一个用途。关闭平台功能会暂停对应新收件、执行与回复，不删除个人凭据、历史或待处理记录；已开始的操作仍可能完成，重新开启后继续处理待办。暂停轮询期间的消息能否恢复取决于微信上游保留策略，详见[微信 iLink](../../user-guide/knowledge-base/wechat-collection_zh-CN.md)。

个人微信 iLink 将扫码授权与刷新放在标题栏，连接卡片紧凑展示状态，用途摘要与操作同行；配置表单宽屏双列、窄屏单列。悬浮或聚焦页面标题旁的帮助图标查看使用说明，图片／视频识别模型字段旁的帮助图标显示模型说明。设置页不再展示智能体运行和采集记录，连接卡片仍显示当前任务状态并提供停止操作；后台记录保留。


- `admin:integrations:login:read/update`：查看或管理登录集成，以及 **站点设置 → 安全** 中的全局 SSO 策略。
- `admin:integrations:settings:read/update`：查看或管理邮件、Webhook、飞书与微信的功能设置、凭据、测试、通讯录同步及 Agent 对话配置。
- 任一域的 read 权限可进入集成页面和读取类型目录；实例列表按授权域过滤，编辑控件分别授权。后端权限检查为最终依据。
- 通用 `PUT /api/v1/admin/integrations/{id}` 的更新授权按字段判定：`enabled_capabilities` 与 `is_enabled` 计入所涉及能力所属的域（`user_login` → login，飞书 `directory_sync`、`notification` 和 `agent_chat` → settings）；内置集成的 `config`、`credentials` 计入 settings；只要集成的类型支持登录，`button_text`、`display_name`、`icon_url`、`login_config`、`attribute_mapping` 计入 login。飞书 Agent 对话专用配置 API 使用 settings 域；现有登录开关仍单独受 login 域控制。
- `admin:settings:read/update` 继续管理其他站点设置，不替代集成权限。

## 配置 GitHub 登录

1. 确保外部可访问 Clouisle，配置正确的 `FRONTEND_URL`，并保留可用的管理员登录方式。
2. 在 **站点设置 → 安全** 配置全局 SSO 策略：SSO 总开关、密码登录、自动创建用户、审批和邮箱匹配。原有 `sso_*` 键与认证行为保持不变。
3. 在 GitHub 的 **Settings → Developer settings → OAuth Apps** 创建 OAuth 应用，将回调填写为 `https://your-domain.com/api/v1/sso/callback/github`。
4. 创建名称为 `github` 的 `oauth2` 登录集成，启用 `user_login`，填写显示名称、按钮文本、图标及该集成自己的 `login_config`（注册、审批、默认角色）。
5. 非敏感配置填写 client ID、授权 URL、token URL、userinfo URL 和 `read:user user:email` scopes。独立的 `attribute_mapping` 字段使用 `{"email":"email","username":"login","avatar_url":"avatar_url"}`。
6. 在凭据字段填写 client secret（API 为 `credentials.client_secret`），不要放入 `config`。保存并测试配置后，用独立浏览器会话完成实际登录；配置测试不代表完整登录已通过。

**原有登录与回调地址不变：** `/api/v1/sso/login/{name}`、`/api/v1/sso/callback/{name}`；前端结果页仍为 `/sso-callback`。回调使用外部可达的后端域名；若前端代理 `/api/*`，则使用前端公开域名。`API_BASE_URL` 是内部服务地址，不决定回调域名。集成名称是已登记的 URL 标识，请保持稳定。

OAuth2/OIDC、SAML2 和 CAS 保留原协议配置。SAML ACS 地址仍使用上述 callback 地址。属性映射支持 `profile.name` 等点路径和 `$.emails[0].value` 等 JSONPath，多个匹配时取第一个值。

登录集成的 `allow_signup`、`require_approval`、`default_role_id` 位于 `login_config`，不再是顶层字段。注册、审批与邮箱匹配规则不变。关闭密码登录仍要求至少一个超级管理员已绑定身份连接。

## 配置飞书登录

飞书网页登录是飞书集成上的一项可选能力，与通讯录同步共用同一套 app_id、app_secret，无需再创建一个身份源。

1. 在飞书开发者后台把卡片中显示的 **重定向地址**（`https://<backend-host>/api/v1/sso/callback/<integration-name>`，例如 `…/api/v1/sso/callback/feishu`）加入应用的重定向 URL 白名单；该地址在飞书卡片中直接可见并可一键复制。`<backend-host>` 是外部可达的后端（或代理）域名，与所有身份源的回调域名一致。
2. 为应用授予登录所需 scope：`contact:user.base:readonly contact:user.email:readonly`。身份来自登录用户资料本身，无需 scope；邮箱字段需要 `contact:user.email:readonly`。
3. 在 **站点设置 → 集成 → 飞书** 页面的“能力”区域打开 **飞书登录** 开关，并按需填写按钮文案。两个能力开关（通讯录同步与飞书登录）一起通过通用 `PUT /api/v1/admin/integrations/{id}` 以 `enabled_capabilities` 保存：打开该卡片需要 settings 域 read 权限，修改登录开关需要 `admin:integrations:login:update`，因此启用它的角色需同时具备两个域（超级管理员始终可以）。
4. 如果尚未配置应用凭据，在同一页面填写。凭据与通讯录同步共用，密钥留空表示保留原值。

只有全局 SSO 已启用且 `user_login` 功能已开启时，登录页才展示飞书登录按钮。关闭“飞书登录”仅停用该功能，不影响其他已启用功能；页面不提供集成总开关。

登录身份以资料中的 `union_id` 作为外部身份 `provider_user_id` 存储；缺少 `union_id` 时回退为 `open_id`，因此在同一开发者账号内更换应用不会导致已绑定账号失效。

通讯录中没有任何邮箱的飞书账号，会使用与目录同步相同的确定性占位邮箱 `feishu-<sha256(user_id)>@accounts.clouisle.example`，使登录与同步汇聚到同一个本地账号而不是各建一个。推导该地址需要飞书 `user_id`，因此需要 `contact:user.employee_id:readonly`；缺少该 scope 时这类账号没有 `user_id`，其首次登录会被拒绝，而不会创建占位身份。

### 将飞书绑定到已有账号

先登录已有 Clouisle 账号，再进入头像菜单 → **个人资料 → 账户安全 → 关联账号**，点击 **绑定飞书**。在同一浏览器标签页完成飞书授权并确认绑定。此流程保留当前账号、密码、邮箱、权限和登录状态，不创建新账号，也不依赖邮箱匹配。

管理员需在 **站点设置 → 安全** 启用全局 SSO，并在 **站点设置 → 集成 → 飞书** 启用 **飞书登录**，用户才会看到可绑定的飞书入口。绑定复用已登记的登录回调地址，无需在飞书另加重定向地址。如果飞书身份已属于其他账号，系统拒绝重新分配，请联系管理员处理已有通讯录或账号绑定。

即使飞书资料未返回通讯录 `user_id`，已验证邮箱属于其他本地账号时也会拒绝绑定。这是身份归属冲突检查，不会按邮箱自动匹配或合并账号。

通过 **账户安全 → 关联账号 → 绑定飞书** 关联的用户会被通讯录同步排除，对应飞书成员计入“跳过”：不重复创建账号、不覆盖本地资料，也不新增部门团队成员关系。已有成员关系、飞书登录及机器人绑定保留，普通通讯录托管用户继续正常同步。后续飞书登录或能力开关变化不会取消此排除。升级时会依据保留的成功 `link_sso` 审计记录识别此前的手动绑定；审计历史已被删除的记录无法可靠追溯分类。

相关接口均需登录：`GET /api/v1/sso/links/integrations`、`POST /api/v1/sso/links?provider_name=<name>`（返回授权地址和短期会话 ID）、`POST /api/v1/sso/links/complete`（请求体为 `{"session_id":"..."}`）。飞书回调只暂存已验证身份，最终绑定需由原发起账号确认并消费会话；浏览器也会核对本标签页保存的待绑定会话。


## 同步飞书知识库

系统超级管理员进入 **站点设置 → 集成 → 飞书**（`/site-settings/integrations/feishu`）。页面分为 **集成配置**、**通讯录同步**、**消息通知** 和 **飞书知识库同步** 四个标签。普通集成管理权限不会授予知识库同步标签或其 API。在 **集成配置** 中配置飞书应用，并统一设置通讯录、登录和通知能力，通过同一个按钮保存；在 **通讯录同步** 中管理部门范围和手动同步；在 **消息通知** 中检查连接并发送测试消息。

1. 保存并启用现有飞书集成。知识库同步复用应用凭据和租户访问令牌，不使用当前登录用户的令牌。
2. 按需授予 Wiki 空间/节点读取、Docx 文档块读取、电子表格读取、多维表格数据表/字段/记录读取、文档导出及云盘文件/素材下载权限。文件元数据使用 `drive:drive.metadata:readonly`（或更广的云盘权限）；素材下载需要 `docs:document.media:download` 或对应文档/表格/多维表格权限。同时让应用获得目标空间和文档的资源访问权限，仅开通 scope 不够。
3. 在目标团队中创建知识库。未显式选择 Embedding 模型时，同步与普通文档处理一样使用系统默认 Embedding 模型；该默认模型需要存在且已启用。在同步页添加同步源，选择飞书知识空间、已有目标知识库和同步间隔（1–43,200 分钟）。
4. 启用自动同步或点击“立即同步”。自动调度需要运行 Celery Beat，并有 worker 消费 `knowledge` 队列。通过同步源查看状态、最近同步时间、结果计数、错误及转换警告。

同步页显示知识空间名称，新同步结果会记录失败及警告节点的标题。点击节点名称可在新标签页打开飞书原文；没有标题的历史结果仍显示可点击的节点 ID。查看原文仍受飞书本身的用户访问权限限制。

不支持的来源类型或文件格式会跳过，不计为失败。其名称、原文链接、类型和原因单独显示在“已跳过（不支持）”（`last_result.skipped`），`unsupported` 保留数量统计。没有实际失败的同步会标记为成功并清除 `last_error`，即使跳过了不支持的文档；真实读取、转换或索引错误仍计为失败。

**权限边界：**这是将内容导入团队知识库，不会复制飞书用户 ACL。导入后的查看、检索、引用和分享均受本地团队及知识库权限控制；启用前必须确认目标访问范围。飞书撤权只有在后续同步检测到后才会反映到本地。

支持的来源类型：

| 来源 | 导入方式 |
|---|---|
| 新版文档 `docx` | 正文、标题、列表、代码、引用、待办、表格；鉴权下载图片，提取内嵌附件文本。日期提醒转换为文本，保留 UTC 事件时间、原始毫秒时间戳、创建者 ID、通知及全天标记，不会在本地创建通知任务。 |
| 旧版文档 `doc` | 导出为 DOCX，复用现有文档解析器 |
| 电子表格 `sheet` | 按明确行列范围分批读取所有网格工作表，保留显示值和源公式 |
| 多维表格 `bitable` | 读取所有可访问数据表、字段定义和分页记录；提取可解析附件文本及图片 |
| 云盘文件 `file` | 下载并解析 PDF、DOC/DOCX、TXT、MD/Markdown、HTML/HTM、CSV、XLS/XLSX、JSON、PPTX |
| 思维笔记 `mindnote` | 明确报告不支持：[飞书公开 API 明确不包含思维笔记](https://open.feishu.cn/document/server-docs/docs/docs-overview)。可先导出为支持的文件格式再导入。 |

这是内容入库，不是原界面的完整备份：电子表格浮动图片、图表和非网格资源不提取；保留公式，不在本地重新计算。不支持的块、图片/附件格式及提取缺口会报告警告。图片作为本地展示资源保存，不意味着已进行 OCR 文本检索。下载及生成内容受知识库上传大小上限约束；内容不完整或超限时保留旧版本。导出失败（包括部分块无权限的导出）不会替换旧版本。导入文档保持本地只读，不能编辑分块、删除或重新处理。

每次完整枚举知识空间后，才会移除已消失的文档。内容变更处理成功后替换索引并保留本地文档 ID；内容未变则不重复 Embedding。下载失败、扫描不完整或处理失败会保留旧版本。明确的权限拒绝会移除对应本地副本，临时错误或含义不明的错误不视为删除；权限恢复后可重新导入。停用同步源保留已导入文档；删除同步源会删除该源导入的文档及索引，不影响本地上传文档。

## 管理 API 与凭据

统一管理基地址为 `/api/v1/admin/integrations`：

- `GET /types`：静态类型与能力目录；`GET` 基地址：按权限过滤实例。
- `POST` 基地址、`PUT/DELETE /{id}`、`POST /{id}/test`：非单实例登录集成的创建、更新、删除与测试。
- `GET/PUT /login-settings`：全局登录设置，保留 SSOSettings 原有 wire keys。
- `GET/PUT /email`、`/webhook`，以及 `POST /email/test`、`/webhook/test`：通知集成配置与测试。
`GET/PUT /feishu/config`、`GET /feishu/departments`、`PUT /feishu/department-scope`、`POST /feishu/sync`：飞书配置和手动同步；`POST /feishu/connection-check` 通过获取 tenant token 验证应用凭据（不要求通讯录同步范围）；`GET /feishu/test-recipients` 列出最多 20 个已绑定飞书身份的启用本地用户；`POST /feishu/test-message` 向管理员明确选择的一名已绑定用户发送自定义测试消息，要求启用“通知”能力。飞书卡片提供连接检查和手动测试消息表单；测试消息不会群发，也不会创建通知记录。登录开关与按钮文案/图标通过通用 `PUT /{id}`（login 域）写入，`/feishu/*` 仍属 settings 域，只负责应用配置、目录、测试和同步。

公开登录列表改为 `GET /api/v1/sso/integrations`；旧 `/sso/providers` 无兼容别名。用户解除自己的身份连接仍使用 `DELETE /api/v1/sso/connections/{id}`。详见[SSO 与集成 API](../../api-reference/endpoints/sso.md)。

凭据使用 Fernet 加密存储，仅运行时解密。**管理响应不返回明文或密文凭据**，只返回 `credentials_configured` 字段名称与 `supported_capabilities`。空凭据值保留原密钥。脱敏 API 响应不是完整备份。

## 现有部署升级

**部署前备份数据库，并保留对应的后端 `SECRET_KEY`。** 切换前停止所有旧版 API 与 worker；完成迁移后，再启动使用同一新版本的 API 和 worker。**不支持新旧版本混用的滚动部署**：新旧表和列名不同，事务与 advisory lock 保护不意味着旧程序可以访问新 schema。

建表前执行幂等迁移：`sso_providers` 改名为 `integrations`，`protocol` 改为 `provider_type`，注册策略移入 `login_config`，增加 `user_login`，将配置中的敏感字段分离并加密。会话与身份连接的 `provider_id` 列改为 `integration_id`，原认证表名及外部身份字段 `provider_user_id` 保留。

**原集成 UUID、用户身份连接、外部身份 ID 和外键关系保留**，无需重新绑定账号或修改身份提供方回调。连接响应改用 `integration_id`、`integration_name`、`integration_display_name`、`integration_icon_url`；读取旧 `provider_*` 字段的客户端须同步更新。

邮件、Webhook 和飞书的旧 SiteSetting 配置仅导入一次，成功持久化后删除相应旧键；运行时不再回退读取旧配置。全局 `sso_*` 登录策略保留，分类改为 integration。

角色授权从 `admin:sso:read/update` 迁移为 `admin:integrations:login:read/update`。原 `admin:settings:read/update` 授权额外获得对应 settings 域集成权限，并保留其他站点设置权限；不会把登录域与内置配置域的权限混在一起。

权限授权只迁移一次，完成标记避免重启后恢复管理员刻意撤销的新权限。内置集成的通用 `PUT /{id}` 同样需要 settings 域 update 权限；单实例集成禁止删除。

**回滚必须同时恢复切换前数据库、匹配的应用版本和加密密钥。** 不要直接用旧程序访问新 schema、随意更换 `SECRET_KEY`，或尝试从脱敏响应恢复凭据。迁移失败时先解决启动错误，不要删除身份关系或手动创建重复集成。

## 排障

- 登录按钮缺失：检查全局开关、集成启用状态和 `user_login` 能力。飞书需要显式开启，因此集成已启用但 `enabled_capabilities` 不含 `user_login` 时不会显示按钮。
- 飞书回调被拒或未创建账号：确认应用已登记 `https://<backend-host>/api/v1/sso/callback/<integration-name>`，登录 scope 包含 `contact:user.email:readonly`；对于通讯录中没有邮箱的账号还需 `contact:user.employee_id:readonly`，否则没有可据以推导占位邮箱的 `user_id`，首次登录会被拒绝。
- 回调不匹配：检查名称、公开域名和代理头；不要登记新的 integrations callback 地址。
- 无配置或编辑控件：检查对应 login/settings 权限域。
- 飞书部门浏览或同步提示功能未启用：先保存 App ID 和 App Secret，再在“集成配置”中打开并保存 **通讯录同步** 功能。无需额外的集成总开关。
- 同步结果中的 `99991672` 会针对**失败的具体接口**列出缺少的 API scope（例如多维表格读取权限）。按提示在飞书开放平台 → 当前应用 → 权限管理申请对应权限，发布应用版本并完成管理员审批后重试；不同接口要求的权限不同。
- 凭据无法解密：恢复匹配的 `SECRET_KEY`，或通过对应表单重新保存凭据。
- 无法解除唯一身份连接：无密码账号必须先建立另一种可用认证方式。
