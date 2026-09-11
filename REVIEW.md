# Code Review Guidelines (REVIEW.md)

本文件作为 Clouisle 项目的代码审查（Code Review）准入与评估标准。所有提交的 Pull Request 均须对照本清单进行逐项核验。

---

## 一、代码审查核心准则清单 (Checklist)

### 1. 权限与多租户隔离 (Permissions & Tenant Boundaries)
- [ ] **前后端双重防护 (Defense-in-Depth)**：前端 UI 隐藏或禁用操作（如 `<PermissionGuard>`）必须与后端接口强鉴权依赖（如 `require_kb_update`, `check_team_access`）严格对齐，绝不假设前端隐藏即安全。
- [ ] **水平越权防护 (IDOR Prevention)**：对路径或参数中传入的资源 ID（如 `kb_id`, `tool_id`, `doc_id`），必须校验其归属当前团队或存在有效的跨团队共享授权记录。
- [ ] **只读权限降级**：非拥有者团队（共享接收方）访问共享资产时，必须被强制降级为只读模式，破坏性操作（上传、删除、重置参数、编辑分块等）必须拦截。

### 2. 高并发与大数据量吞吐 (High-Volume & Concurrency)
- [ ] **URL 长度与请求头限制 (防 HTTP 431/414)**：严禁在 URL Query 中传递数组（如 `?docs=${ids.join(',')}`）。海量 ID 必须使用 `sessionStorage` 暂存或由后端生成一次性 `batch_id`。
- [ ] **事务级状态隔离 (Batch ID Isolation)**：分布式临时状态、计数器或缓存 Key 严禁绑定在宏观复用维度（如 `user_id`, `kb_id`），必须以单次操作凭据 `batch_id = uuid4()` 为主键，彻底杜绝多用户并发交叉与多标签页覆盖。
- [ ] **内存原子收敛 (Zero DB-hammering)**：异步任务批次收敛必须使用 Redis 单线程原子命令（`DECR` / `INCR`），严禁让并发 Worker 在循环或任务末尾通过全量数据库 `SELECT count(*)` 判定结束。
- [ ] **全路径闭环防死锁 (Exception Exit Convergence)**：计数或锁逻辑必须覆盖所有分支（成功、业务失败、维度不匹配、未捕获异常）。所有临时 Redis Key 必须强制设置 TTL（如 `EX=7200`）。

### 3. 前端交互降噪与客户端性能 (Client UX & Throttling)
- [ ] **请求并发池化**：前端面对大量数据处理时，禁止使用无限制的 `Promise.all`（必须限制在 5~10 的并发池），防止打满浏览器 HTTP 连接通道导致页面假死。
- [ ] **Toast 消息降噪**：大批量循环操作禁止在每个子项完成时弹出独立 Toast，必须采用单一 `toast.loading` 原地刷新动态百分比，结束时原地替换为统计摘要。
- [ ] **响应式与移动端自适应**：
  - 严禁滥用 `100vh`，移动端全屏布局必须采用 `h-svh` 或 `min-h-0 flex-1`，避免移动端浏览器地址栏遮挡底部按钮；
  - 核心操作必须保证触控热区至少达到 44x44px；
  - 严禁纯依赖鼠标 `:hover` 才能触发核心操作（移动端无悬停状态）；
  - 数据表格在移动端必须支持横向平滑滚动或降级为卡片（Card）视图。

### 4. 外部服务、依赖与开源许可证合规 (Dependencies & Licensing)
- [ ] **传染型许可证绝对红线 (Copyleft Prohibition)**：严禁直接或间接引入 **GPL v2/v3**, **AGPL v3** 等强传染型协议依赖。
- [ ] **间接依赖穿透检查**：新引入任何 npm / pip 依赖必须通过 `python scripts/check_licenses.py` 及 `bun run license:check` 门禁。如有多重授权等特殊情况，必须在 `license-policy.yml` 中显式登记备案并获得审批。
- [ ] **依赖膨胀克制**：短小功能（<=30行原生代码可实现）严禁引入第三方依赖；严禁引入年久失修或单人维护的不可控供应链依赖。
- [ ] **外部服务故障假设 (Assume Failure)**：调用模型 API（OpenAI/Claude 等）、OCR、SMTP、外部对象存储时，必须设置严格的超时阈值（Timeout）、指数退避重试及熔断降级逻辑，防止进程永久挂起或费用失控。

### 5. 全链路国际化 (Internationalization / i18n)
- [ ] **零硬编码文本**：前端所有界面文字、错误提示、表单占位符及后端邮件/通知内容，必须 100% 抽取至中英双语字典（`en` / `zh`）。
- [ ] **命名空间一致性**：`useTranslations('scope')` 调用的键必须在对应作用域 JSON 文件中存在，严禁跨作用域凭空调用导致线上 `MISSING_MESSAGE` 错误。
- [ ] **校验工具通过**：每次提交前必须执行 `bun run i18n:lint`，保证双语键位 100% 对齐。

### 6. 错误可观测性与全局策略对齐 (Observability & Policy Matrix)
- [ ] **混合状态联合判定 (Union-Gate)**：对于“既有成功又有失败”的批次任务，必须优先暴露失败告警，并对齐站点设置中的各类通知开关，避免异常被系统设置静默吞没。
- [ ] **用户友好的错误转换**：后端必须在日志中保留完整堆栈与上下文，前端禁止直接展示原生堆栈或未处理的 `500 Internal Server Error`。
- [ ] **全量审计日志 (Audit Logging)**：资源创建、破坏性更新、删除、权限变更等操作，必须调用 `AuditLogService.log` 记录操作人、IP、User-Agent、资源 ID 及结构化变更快照（before/after diff）。

---

## 二、测试质量与覆盖率门禁 (Test & Coverage Gates)

PR 合并前必须通过严格的覆盖率门禁，严禁为了“刷覆盖率”而编写无断言的伪测试：

### 1. 后端测试门禁 (Backend Gates)
- **行覆盖率 (Line Coverage)**：$\ge 95.00\%$
- **分支覆盖率 (Branch Coverage)**：$\ge 95.00\%$
- **门禁执行命令**：
  ```bash
  cd backend
  uv run pytest --cov=app --cov-report=json
  uv run python scripts/check_coverage.py
  ```
- **测试原则**：
  - 核心分支（成功、校验拦截、业务异常、第三方超时降级）必须全覆盖；
  - 严禁过度依赖 Mock 掩盖真实的函数参数签名错误（如 `task_kwargs` 透传缺失）。

### 2. 前端测试门禁 (Frontend Gates)
- **类型检查 (Type Check)**：零 TypeScript 报错
  ```bash
  cd frontend
  bun x tsc --noEmit
  ```
- **多语言校验 (i18n Lint)**：双语键位零缺失
  ```bash
  cd frontend
  bun run i18n:lint
  ```
- **单元测试执行**：
  ```bash
  cd frontend
  bun test --isolate
  ```
- **测试原则**：
  - 涉及交互状态流转、异步加载、错误重试与权限守卫的组件必须有对应的测试用例（`.test.tsx`）；
  - 测试用例必须校验真实 DOM 渲染输出与受控状态，杜绝无边界假设。
