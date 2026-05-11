# Sandbox Runtime Migration Design Document

## Background & Goals

当前项目的代码工具、聊天自定义代码工具和 workflow code node 都依赖 `backend/app/llm/tools/sandbox.py` 中的 `CodeSandbox`。这套实现本质上是直接在业务容器中通过 `python -c` / `node -e` 拉起子进程执行代码片段，能力边界和安全边界都比较窄：

- 只支持 Python / JavaScript 代码片段
- `dependencies` 字段已进入 schema，但没有真正落地安装与缓存
- 无法承载长期运行的 skill / CLI / 自定义命令执行模型
- 与工具测试、聊天调用、workflow code node 的入口耦合较深
- 当前执行模型无法自然支持长期运行、单容器多任务的 sandbox worker

本次目标是在保留现有产品入口和已有简单代码执行体验的前提下，逐步迁移到一个长期运行的 sandbox runtime：

1. 支持 Python 模块安装、JS 模块安装、CLI 执行、自定义命令执行
2. 支持 skill 声明式定义，并编译为统一的执行任务
3. 支持长期运行、单容器多任务的 sandbox worker，并以 k8s Deployment 作为生产承载形态
4. 保持工具测试、聊天 custom code tool、workflow code node 三条链路兼容迁移
5. 通过策略层、调度层、workspace 隔离、进程组治理、环境缓存和观测能力，把当前 subprocess runner 升级为可运营 runtime
6. 在迁移完成前保留 legacy `CodeSandbox` 作为简单 snippet fallback，避免一次性切断现有功能

### Success criteria

- 后端形成统一的 `SandboxJob` / `SkillSpec` / `SandboxResult` 契约，而不是分散在 `execute_code(...)` 的 ad hoc 参数
- 生产执行主路径从 `backend/app/llm/tools/sandbox.py` 迁移到新的 sandbox gateway + long-running worker
- Python 包通过任务级 workspace + 可复用 venv cache 安装和执行
- JS 包通过任务级 workspace + 可复用 node env cache 安装和执行
- 工具页代码工具编辑/测试、聊天 custom code tool、workflow code node 都能接入新 runtime，并保留兼容回退路径
- k8s / Docker 部署增加独立 sandbox worker 运行入口和资源/安全配置
- 新 runtime 具备任务状态、日志、超时、取消、artifact 收集、缓存命中率等基础观测指标
- legacy subprocess runner 被明确降级为 snippet fallback，并有可执行的下线路径

## High-Level Design

### Architecture

迁移后的整体执行链路分为五层：

1. **Specification layer**
   - `SkillSpec`：技能模板，描述依赖、入口命令、输入输出、权限和资源策略
   - `SandboxJob`：统一执行任务，所有工具/skill/workflow/chat 最终都编译成这个结构

2. **Policy & compilation layer**
   - `SandboxPolicyEngine`：校验 runtime profile、依赖来源、命令形式、网络权限、artifact 白名单、资源上限
   - `SandboxCompiler`：把 skill / code tool / workflow code node / direct execute 请求编译成统一 `SandboxJob`

3. **Gateway & queue layer**
   - `SandboxGateway`：供 API、tool service、workflow executor 调用的统一入口
   - `SandboxTaskStore` / `SandboxResultStore`：存任务状态、结果和观测信息
   - `Celery` + Redis queue：将执行与 API 请求解耦，避免在 FastAPI 进程中直接执行长任务

4. **Execution layer**
   - 长期运行的 `sandbox-worker` 进程，部署成独立 Deployment
   - worker 内部的 `SandboxManager` 负责 slot 调度、workspace 准备、环境缓存、进程组执行、artifact 收集和清理
   - 第一阶段只做单 worker image 多任务；后续再按 runtime profile 拆镜像池

5. **Compatibility layer**
   - 工具测试 `/api/v1/tools/execute-code`
   - `ToolExecutor` 中的 custom code tool 执行
   - 聊天中的 custom code tool 执行
   - workflow code node 执行
   - 以上入口都先接入 gateway，legacy `CodeSandbox` 只作为 feature-gated fallback

### Runtime model

新 runtime 不再把“代码执行”视作唯一能力，而统一视作“任务执行”：

- snippet：执行一段 Python / JS 代码
- script：执行一个生成的脚本文件
- cli：执行 pip/npm 安装后的 CLI
- skill：执行声明式 skill 的 entrypoint

统一任务模型推荐包含：

- `job_id`
- `tenant_id`
- `source`（tool / chat / workflow / debug / skill）
- `python_packages`
- `js_packages`
- `command`
- `cwd`
- `env`
- `limits`
- `network`
- `artifacts`
- `input_files`
- `metadata`

### Long-running worker model

生产环境以单容器多任务 worker 运行，而不是每任务一 Pod / 容器：

- worker 进程长期驻留，持续消费任务
- 每个任务有独立 workspace：`/sandbox/jobs/<job_id>`
- 每个任务以新进程组执行，支持整组超时杀死
- Python / Node 依赖环境按 hash 缓存到 `/sandbox/cache/...`
- 安装阶段和执行阶段在同一 worker 内分离，但共享调度、日志和结果收集
- worker 使用 slot / admission control 控制并发，避免 install 阶段打爆 CPU、内存、磁盘和网络

### Proposed directory structure

为了避免 runtime、gateway、worker、前端配置和部署脚本散落在现有工具逻辑里，目录结构按“控制面 / 执行面 / 兼容层 / 部署层”拆分：

```text
backend/
  app/
    services/
      sandbox/
        __init__.py
        models.py              # SandboxJob / SandboxResult / SkillSpec
        policies.py            # policy engine
        compiler.py            # legacy config / skill -> SandboxJob
        gateway.py             # submit / await / cancel facade
        result_store.py        # task state / result persistence facade
        worker.py              # worker bootstrap
        manager.py             # long-running sandbox manager
        scheduler.py           # slot admission / install throttling
        workspace.py           # job workspace lifecycle
        process_launcher.py    # process group spawn / kill / output limit
        cache.py               # shared cache helpers
        python_env.py          # venv cache build / reuse
        node_env.py            # node env cache build / reuse
        artifacts.py           # artifact collect / manifest
        metrics.py             # runtime metrics / tracing hooks
        cleanup.py             # workspace/cache gc
        skills.py              # built-in skill helpers / registry adapter
    tasks/
      sandbox.py              # celery task entry for sandbox queue
    api/
      v1/
        endpoints/
          tools.py            # direct execute / tool test / config APIs
          chat.py             # chat custom code tool bridge
          chat_helpers/
            tool_executor.py  # chat tool execution bridge
    llm/
      tools/
        sandbox.py            # legacy snippet runner + gateway-compatible facade
    schemas/
      tool.py                 # tool/code runtime schema
    models/
      tool.py                 # persisted tool runtime config
    services/
      workflow/
        executors/
          code.py             # workflow code node bridge

deploy/
  dockerfiles/
    backend.Dockerfile
    sandbox-worker.Dockerfile
  k8s/
    clouisle.yaml            # add sandbox worker deployment/service config
  docker-compose.dev.yml     # local sandbox worker service
  docker-compose.yml         # production-like compose wiring

frontend/
  lib/
    api/
      tools.ts               # runtime config + test API types
  app/
    (platform)/app/tools/
      code/page.tsx          # code tool editor
      _components/
        tool-test-panel.tsx  # test execution panel
        tool-config-dialog.tsx
```

目录约束：

- `backend/app/services/sandbox/` 只承载 runtime 通用能力，不直接感知具体入口页面或业务场景
- `backend/app/llm/tools/sandbox.py` 只保留 legacy snippet fallback 和兼容 facade，不继续增长 worker 逻辑
- API / chat / workflow 只做编译与桥接，不各自实现环境安装、缓存和进程治理
- 部署文件只在 `deploy/` 收口，不把 worker 部署细节散到 backend 代码目录
- 前端只暴露配置和测试能力，不复制后端 policy 判断

### Compatibility strategy

为了避免一次性切换导致功能中断，本次迁移分三层兼容：

1. **数据结构兼容**
   - 历史 `code_config.dependencies` 仅作为读旧数据时的兼容输入，统一映射到 `python_packages` / `js_packages`
   - workflow code node 继续接受现有 `language + code + inputs + outputs` 结构
   - 工具编辑页继续保留 Python / JavaScript 双语言编辑体验

2. **执行入口兼容**
   - `execute_code(...)` 改造为 gateway facade，而不是直接 subprocess
   - 在 gateway 中根据配置选择新 runtime 或 legacy fallback

3. **部署兼容**
   - 现有 backend image 暂不移除 Node / uv 运行时
   - 新增 sandbox worker image / command
   - 本地开发先通过 compose / backend worker 复用基础依赖运行，生产再独立 Deployment 化

## Implementation Plan

### Stage 1: Runtime contracts, policies, and compatibility schema
- **Files modified**:
  - `backend/app/schemas/tool.py`
  - `backend/app/models/tool.py`
  - `frontend/lib/api/tools.ts`
  - `docs/dev/design/app-platform/TOOL_SYSTEM_SPEC.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `docs/plan/sandbox-runtime-migration.md`
- **Specific logic**:
  - 明确历史 `code_config.dependencies` 只作为读旧数据时的兼容输入，统一映射到 `python_packages` / `js_packages`
  - 新增后端 runtime 契约 schema，至少覆盖：
    - `SandboxJob`
    - `SandboxResult`
    - `SkillSpec`
    - `SandboxLimits`
    - `SandboxArtifactSpec`
  - 在 `Tool` / `CodeConfigSchema` 上设计兼容字段：
    - legacy `language` + `code`
    - 新 runtime 所需的 packages / command / skill 信息
  - 新增 policy engine 设计：
    - 只允许 argv 数组命令
    - Python / JS 依赖要求固定版本
    - artifact 必须白名单导出
  - 更新工具系统设计文档，明确 legacy snippet runner 与新 sandbox runtime 的职责边界
- **Validation**:
  - schema 变更后，现有 tool create/update payload 仍可通过校验
  - 前端 `CodeConfig` 类型编译通过，旧页面不必一次性重构
  - 设计文档与总计划索引同步更新

### Stage 2: Queue, gateway, and result transport
- **Files modified**:
  - `backend/app/core/celery.py`
  - `backend/app/tasks/__init__.py`
  - `backend/app/tasks/sandbox.py` (new)
  - `backend/app/services/sandbox/models.py` (new)
  - `backend/app/services/sandbox/gateway.py` (new)
  - `backend/app/services/sandbox/result_store.py` (new)
  - `backend/app/services/sandbox/policies.py` (new)
  - `main.py`
- **Specific logic**:
  - 新增 `SandboxGateway.submit(...) / await_result(...) / cancel(...)` 统一入口
  - 使用 Redis + Celery 为 sandbox 任务增加独立队列，例如 `sandbox`
  - 增加结果存储结构，记录：
    - 状态
    - stdout/stderr 摘要
    - exit code
    - execution metadata
    - artifact manifest
  - 为直接同步等待的 API 路径提供“提交任务并等待结果”的 gateway facade
  - 在 `main.py` 增加 sandbox worker 启动入口或独立 command 说明，避免与普通 celery worker 配置耦合不清
- **Validation**:
  - 可以提交一个 no-op sandbox job 并完成状态流转
  - API 进程无需直接执行本地 subprocess，也能拿到结果
  - sandbox 队列和现有 default/workflow 队列不互相污染

### Stage 3: Long-running worker, scheduler, and workspace/process isolation
- **Files modified**:
  - `backend/app/services/sandbox/worker.py` (new)
  - `backend/app/services/sandbox/manager.py` (new)
  - `backend/app/services/sandbox/scheduler.py` (new)
  - `backend/app/services/sandbox/workspace.py` (new)
  - `backend/app/services/sandbox/process_launcher.py` (new)
  - `deploy/dockerfiles/sandbox-worker.Dockerfile` (new)
  - `deploy/k8s/clouisle.yaml`
  - `deploy/docker-compose.dev.yml`
- **Specific logic**:
  - 实现长期运行的 `SandboxManager`：
    - 消费任务
    - admission control
    - slot 调度
    - 任务状态推进
  - 实现 workspace 生命周期：
    - `/sandbox/jobs/<job_id>/input|output|tmp|logs`
    - `umask 077`
    - 任务结束清理
  - 实现进程组执行与取消：
    - 新进程组启动
    - timeout 后 `SIGTERM -> SIGKILL`
    - stdout/stderr 大小限制
  - 为 worker 单独增加镜像和命令入口，生产上作为 Deployment 部署
  - 在 k8s manifest 中加入 sandbox worker Deployment、资源限制、security context 和 volume mount
- **Validation**:
  - 同一 worker 进程可以顺序执行多个任务且 workspace 不串扰
  - 任务超时会结束整个进程组而不是只杀父进程
  - k8s / compose 能启动 worker 进程并消费 sandbox 队列

### Stage 4: Python environment cache and CLI execution
- **Files modified**:
  - `backend/app/services/sandbox/python_env.py` (new)
  - `backend/app/services/sandbox/cache.py` (new)
  - `backend/app/services/sandbox/manager.py`
  - `deploy/dockerfiles/sandbox-worker.Dockerfile`
- **Specific logic**:
  - 新增 Python 环境缓存层：
    - 基于 Python version + package list + index config + runtime profile 生成 hash
    - 首次构建 venv
    - 后续任务复用只读 venv cache
  - 在执行时设置：
    - `VIRTUAL_ENV`
    - `PYTHONNOUSERSITE=1`
    - `PATH=<venv>/bin:...`
  - 支持通过 pip 安装 CLI 并直接执行其 entrypoint
  - 安装阶段和执行阶段拆开观测，单独记录 install duration / cache hit
- **Validation**:
  - 相同 Python 依赖且相同 index URL 的两个任务第二次命中缓存
  - 更换 `python_package_index_url` 后会使用不同缓存键
  - Python CLI 可通过 venv `bin` 直接执行
  - package 安装失败时错误信息能通过 result store 返回

### Stage 5: Node environment cache and CLI execution
- **Files modified**:
  - `backend/app/services/sandbox/node_env.py` (new)
  - `backend/app/services/sandbox/cache.py`
  - `backend/app/services/sandbox/manager.py`
  - `deploy/dockerfiles/sandbox-worker.Dockerfile`
- **Specific logic**:
  - 新增 Node 环境缓存层，优先采用 `pnpm` / `corepack` 管理共享 store
  - 基于 Node version + package list + registry config + runtime profile 生成 hash
  - 缓存 `node_modules` / store，并在执行阶段把 `.bin` 放入 PATH
  - 支持 JS CLI 和 node script 两种执行形式
  - 约束 postinstall / registry 来源策略由 policy engine 控制
- **Validation**:
  - 相同 JS 依赖且相同 registry URL 第二次执行命中缓存
  - 更换 `node_package_registry_url` 后会使用不同缓存键
  - `node_modules/.bin/<cli>` 能被正确解析到 PATH
  - 安装和执行日志都能正确写入结果

### Stage 6: Tool, chat, and workflow entry migration
- **Files modified**:
  - `backend/app/llm/tools/sandbox.py`
  - `backend/app/services/tool.py`
  - `backend/app/api/v1/endpoints/chat_helpers/tool_executor.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/api/v1/endpoints/tools.py`
  - `backend/app/services/workflow/executors/code.py`
  - `backend/tests/llm/test_code_sandbox.py`
  - `backend/tests/services/workflow/` 相关测试文件
- **Specific logic**:
  - 将 `execute_code(...)` 从直接 subprocess 执行改为调用 `SandboxGateway`
  - 保留 legacy fallback，例如：
    - 无依赖、简单片段、未启用新 runtime 时仍可走 legacy `CodeSandbox`
  - `ToolExecutor`、聊天 custom code tool、工具测试 API 都统一改走 gateway
  - workflow code node 在保持 `main(inputs)` / `main(params)` 兼容的前提下，也改由 gateway 提交 snippet job
  - 增加 migration flag / runtime selection 逻辑，支持按入口灰度切换
- **Validation**:
  - 工具测试、聊天 custom code tool、workflow code node 三条链路都能通过新 runtime 执行简单样例
  - legacy fallback 在 feature flag 关闭时仍能工作
  - 现有 Python 布尔参数传递测试继续通过

### Stage 7: Skill compilation and frontend editor/test path
- **Files modified**:
  - `backend/app/services/sandbox/compiler.py` (new)
  - `backend/app/services/sandbox/skills.py` (new)
  - `backend/app/api/v1/endpoints/tools.py`
  - `frontend/lib/api/tools.ts`
  - `frontend/app/(platform)/app/tools/code/page.tsx`
  - `frontend/app/(platform)/app/tools/_components/tool-test-panel.tsx`
  - `frontend/app/(dashboard)/tools/_components/tools-client.tsx`
  - `frontend/app/(platform)/app/tools/_components/tool-config-dialog.tsx`
  - 相关 i18n 文案文件
- **Specific logic**:
  - 在后端增加 `SkillSpec -> SandboxJob` 的编译逻辑，支持：
    - packages
    - command template
    - limits
    - artifacts
  - 代码工具编辑器增加 runtime 配置 UI：
    - Python/JS packages
    - Python index URL / Node registry URL
    - 命令模式与纯代码模式
    - 资源限制和 artifact 输出说明
  - 代码即时测试从“直接执行一段代码”扩展为“编译 runtime 配置并测试执行”
  - 保留旧编辑页默认体验，默认仍可以仅写代码、不填 packages 和 command
- **Validation**:
  - 前端可以创建包含 Python 包或 JS 包的代码工具配置
  - 前端测试面板能够展示新 runtime 的 stdout / stderr / duration / error
  - 不配置 packages 的旧代码工具在 UI 和 API 上仍可保存与测试

### Stage 8: Deployment rollout, observability, and legacy deprecation
- **Files modified**:
  - `deploy/k8s/clouisle.yaml`
  - `deploy/docker-compose.yml`
  - `deploy/docker-compose.dev.yml`
  - `deploy/README.md`
  - `backend/app/services/sandbox/metrics.py` (new)
  - `backend/app/services/sandbox/cleanup.py` (new)
  - `backend/app/llm/tools/sandbox.py`
  - `docs/dev/status/WORKFLOW_ENGINE_STATUS.md`
  - `docs/dev/design/app-platform/TOOL_SYSTEM_SPEC.md`
- **Specific logic**:
  - 为 sandbox worker 增加观测指标：
    - queue depth
    - running slots
    - install cache hit/miss
    - job duration
    - timeout / cancel count
    - artifact count / size
  - 增加 workspace / cache GC 机制
  - 在部署清单中加入 sandbox worker 的 scaling、resource requests/limits、安全上下文和 volume
  - 文档明确 legacy `CodeSandbox` 已降级为 fallback，并定义后续删除条件
  - 当新 runtime 覆盖工具测试、聊天、workflow 主路径后，再逐步收紧 legacy 路径使用范围
- **Validation**:
  - 部署文档能指导本地和 k8s 启动 sandbox worker
  - 新 runtime 关键指标可见，且能区分 install 与 run 阶段
  - legacy 路径在灰度完成后只剩 fallback 角色，职责边界清晰

## Testing Strategy

### Happy path tests

1. 简单 snippet 执行
   - Python / JS 无依赖代码通过 gateway 执行成功
   - 结果、日志、耗时可回传

2. Python 包安装与 CLI 执行
   - 创建包含固定版本 pip 包的 job
   - 首次安装成功，第二次命中 cache
   - venv 内 CLI 可以被 PATH 正确解析

3. JS 包安装与 CLI 执行
   - 创建包含固定版本 JS 包的 job
   - 首次安装成功，第二次命中 cache
   - `node_modules/.bin` 中的 CLI 可执行

4. 入口兼容
   - 工具测试页执行 code tool 成功
   - 聊天 custom code tool 成功
   - workflow code node 成功

5. skill 编译
   - 一个 skill spec 能被编译为 `SandboxJob`
   - skill 输入变量正确渲染到 argv 模板中

### Error path tests

1. 安装失败
   - pip / JS package 不存在时，install phase 失败并返回可读错误

2. 命令超时
   - 长时间运行任务触发 timeout，整组进程被回收

3. 输出过大
   - stdout/stderr 超过限制时被截断，并有截断标记

4. 非法命令/策略拒绝
   - 非 argv 命令形式或未固定版本依赖被 policy 拒绝

5. worker 并发压力
   - 超出 slot 的任务进入排队，不把单个 worker 打满导致全体任务饥饿

### Regression scope

重点回归：

- `backend/app/api/v1/endpoints/tools.py` 中代码工具创建、更新、测试
- `backend/app/services/tool.py` 中 custom tool 执行
- `backend/app/api/v1/endpoints/chat.py` 与 `chat_helpers/tool_executor.py` 中 custom code tool 链路
- `backend/app/services/workflow/executors/code.py` 中 workflow code node
- `frontend/app/(platform)/app/tools/code/page.tsx` 编辑器与即时测试
- `frontend/app/(platform)/app/tools/_components/tool-test-panel.tsx` 通用工具测试面板
- 现有 MCP / HTTP tool 行为不应因 sandbox runtime 改造被破坏

## Risks & Mitigation

### 风险 1：单容器多任务 worker 的隔离强度不足
- **Mitigation**:
  - 文档中明确适用范围是受控执行，不宣称 hostile-code 强隔离
  - 通过 workspace、非 root、只读 rootfs、进程组治理、资源限额和窄网络策略降低风险
  - 后续如需要更强隔离，可在同一 `SandboxGateway` 抽象下再引入每任务容器/Pod runner

### 风险 2：依赖安装拖慢 worker，影响整体吞吐
- **Mitigation**:
  - 引入 env cache、文件锁和 install 限流
  - 对高频 skill 预热缓存环境
  - 记录 cache hit/miss 和 install duration，为后续镜像分层提供依据

### 风险 3：入口迁移过多，回归面大
- **Mitigation**:
  - 以 gateway facade 统一切换点，减少每条链路直接感知 runtime 细节
  - 加 feature flag，按 tools -> workflow -> chat 或相反顺序灰度切换
  - 保留 legacy fallback，先迁移主路径再逐步收紧

### 风险 4：schema 设计一次性扩展过大，前端负担高
- **Mitigation**:
  - 保留 legacy code editor 配置结构
  - 新 runtime 配置先作为可选高级配置进入 UI
  - 后端 compiler 负责把 legacy 配置映射到新 job 模型

### 风险 5：部署清单复杂度增加
- **Mitigation**:
  - 本地 compose 先提供最小 sandbox worker
  - k8s 清单只先增加独立 worker Deployment、emptyDir 和资源限制
  - 复杂的 autoscaling / policy / metrics 在后续迭代补齐

### Rollback plan

如果新 runtime 在任一入口引入明显回归，可按以下顺序回退：

1. 关闭对应入口的 feature flag，使其重新走 legacy `CodeSandbox`
2. 保留已创建的 sandbox worker 部署，但停止消费业务入口任务
3. 保留 schema 与 gateway 代码，不回滚已落地的任务契约和文档
4. 仅回退入口绑定，待问题定位后重新灰度发布
