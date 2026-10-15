# 集成与 SSO 配置指南

在 **站点设置 → 集成**（`/site-settings/integrations`）统一管理登录身份源、邮件、Webhook 和飞书通讯录。它们使用同一 Integration 模型，但功能与权限并不混用。

## 支持范围

| 类型 | 静态能力 | 管理权限域 |
|---|---|---|
| `oauth2`、`oidc`、`saml2`、`cas` | `user_login` | login |
| `email`、`webhook` | `notification` | settings |
| `feishu` | `directory_sync`、`user_login`、`notification` | settings（app_id、app_secret、部门范围、通讯录同步、通知能力）与 login（登录开关、按钮文案、登录的启用/停用） |

能力由后端注册表静态声明，不能通过配置添加尚未实现的功能。邮件、Webhook 和飞书为单实例集成，使用专用表单配置。飞书通知会向通过通讯录同步绑定的用户发送私聊；不提供 Agent 消息。

飞书是由同一套飞书应用凭据（app_id、app_secret）构成的单个集成，同时声明 `directory_sync`、`user_login` 和 `notification`。启用飞书集成本身不会授予登录能力，网页登录需要在同一集成上显式开启；关闭集成会同时停用通讯录同步、登录与通知，但保留登录选项。飞书仍是手动、单向通讯录同步，详见[系统设置](system-settings.md)。

## 权限

- `admin:integrations:login:read/update`：查看或管理登录集成，以及 **站点设置 → 安全** 中的全局 SSO 策略。
- `admin:integrations:settings:read/update`：查看或管理邮件、Webhook、飞书的配置、凭据、测试和同步。
- 任一域的 read 权限可进入集成页面和读取类型目录；实例列表按授权域过滤，编辑控件分别授权。后端权限检查为最终依据。
- 通用 `PUT /api/v1/admin/integrations/{id}` 的更新授权按字段判定：`enabled_capabilities` 与 `is_enabled` 计入所涉及能力所属的域（`user_login` → login，`directory_sync` → settings）；内置集成的 `config`、`credentials` 计入 settings；只要集成的类型支持登录，`button_text`、`display_name`、`icon_url`、`login_config`、`attribute_mapping` 计入 login。飞书既是内置集成又支持登录，因此同一张卡片上的不同字段可能分别要求不同的域。
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
3. 在 **站点设置 → 集成 → 飞书** 卡片的“能力”区域打开 **飞书登录** 开关，并按需填写按钮文案。两个能力开关（通讯录同步与飞书登录）一起通过通用 `PUT /api/v1/admin/integrations/{id}` 以 `enabled_capabilities` 保存：打开该卡片需要 settings 域 read 权限，修改登录开关需要 `admin:integrations:login:update`，因此启用它的角色需同时具备两个域（超级管理员始终可以）。
4. 如果尚未配置应用凭据，在同一张卡片上填写。凭据与通讯录同步共用，密钥留空表示保留原值。保持集成处于启用状态。

只有在全局 SSO 已启用、集成已启用、且 `user_login` 位于其已启用能力中时，登录页才会展示飞书登录按钮。未开启该选项时，飞书只提供通讯录同步，不出现登录按钮。关闭集成会同时停用两项能力，但保留该选项。

登录身份以资料中的 `union_id` 作为外部身份 `provider_user_id` 存储；缺少 `union_id` 时回退为 `open_id`，因此在同一开发者账号内更换应用不会导致已绑定账号失效。

通讯录中没有任何邮箱的飞书账号，会使用与目录同步相同的确定性占位邮箱 `feishu-<sha256(user_id)>@accounts.clouisle.example`，使登录与同步汇聚到同一个本地账号而不是各建一个。推导该地址需要飞书 `user_id`，因此需要 `contact:user.employee_id:readonly`；缺少该 scope 时这类账号没有 `user_id`，其首次登录会被拒绝，而不会创建占位身份。

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
- 飞书部门浏览或同步提示集成未启用：先保存 App ID 和 App Secret，再启用飞书集成并在卡片中打开 **通讯录同步** 开关。部门区域仅在集成已启用且通讯录同步已保存开启时显示，否则接口会返回同样的提示。
- 凭据无法解密：恢复匹配的 `SECRET_KEY`，或通过对应表单重新保存凭据。
- 无法解除唯一身份连接：无密码账号必须先建立另一种可用认证方式。
