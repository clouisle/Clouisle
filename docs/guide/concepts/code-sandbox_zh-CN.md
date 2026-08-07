# 代码沙箱

Clouisle 提供一个安全、隔离的代码执行环境——**沙箱运行时**——用于在工作流、Agent 和工具中运行用户提供的 Python 和 JavaScript 代码。

## 架构

沙箱任务进入专用 Celery Worker，Worker 使用 rootless Bubblewrap 为每个可执行任务创建独立的挂载命名空间：

```text
Agent/工作流 → API → Celery 队列 (sandbox) → 沙箱 Worker
                                                  ↓
                                         Bubblewrap 进程
                                                  ↓
                              /workspace → 当前任务/会话目录
```

核心特性：

- **真实 `/workspace` 路径**：当前任务或会话目录以读写方式 bind mount 到 `/workspace`，Python、Node.js、原生库和子进程看到相同路径。
- **文件系统隔离**：任务命名空间不会挂载其他会话、`/app` 或 `/app/uploads`；必要的系统运行时目录和依赖缓存只读挂载。
- **进程生命周期隔离**：每次执行使用独立进程组，超时会终止整个进程组。
- **路径防护**：输入暂存、文件工具和产物收集会拒绝逃逸工作空间及符号链接穿越。
- **根目录扫描收敛**：Agent 直接执行的 `find /` 会转换为 `find /workspace`；脚本自行启动的命令也只能看到 Bubblewrap 暴露的最小文件系统。
- **执行边界**：任务超时、输出限制、工作空间磁盘检查和 Worker 容器资源限制共同约束失控任务。
- **网络策略独立**：Bubblewrap 不隔离网络命名空间；如需限制外网访问，应使用 Docker 或 Kubernetes 网络策略。
- **自动清理**：一次性任务执行完毕立即清理；会话按 TTL 过期清理。

## 支持的运行时

| 运行时 | 基础环境 |
|---|---|
| Python | Python 3.13，包含标准库和任务配置的依赖 |
| JavaScript | Node.js 22，包含核心模块和任务配置的依赖 |

## 平台中的使用场景

### 代码工具

在 **管理后台 → 功能 → 代码** 中创建可复用的代码工具。保存后的工具可被 Agent 和工作流调用。

### 工作流代码节点

在工作流图中直接嵌入代码。代码节点接收输入变量并将结果返回给下游节点。

### Agent 级执行

Agent 可以通过函数调用触发代码工具。LLM 根据任务需要决定何时运行代码。

## 配置

| 变量 | 通用默认值 | Sandbox Worker 部署值 | 说明 |
|---|---|---|---|
| `SANDBOX_RUNTIME_ENABLED` | `true` | `true` | 启用沙箱运行时 |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `false` | `true` | 在 Bubblewrap 文件系统命名空间内启动可执行任务 |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `bwrap` | `/usr/bin/bwrap` | Bubblewrap 命令名或绝对路径 |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | `1` | Sandbox Worker 并发槽位数 |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | 相同 | 任务和会话目录在 Worker 上的根路径 |
| `SANDBOX_MAX_DISK_MB` | `8192` | 相同 | 允许请求的最大工作空间磁盘限制 |
| `SANDBOX_SESSION_TTL_HOURS` | `24` | 相同 | 会话过期清理时间 |
| `SANDBOX_RESULT_TTL_SECONDS` | `86400` | 相同 | 结果保留时间 |

Sandbox Worker 镜像会安装 Bubblewrap 并启用隔离。启用隔离后，如果找不到 `bwrap` 或任务没有工作空间根目录，任务会直接失败，不会降级为未隔离执行。

## 安全模型

- Sandbox Worker 和 Bubblewrap 进程均以**非 root 用户**运行。
- Docker Compose 和 Helm 禁止提权并丢弃全部 Linux capabilities。
- Rootless Bubblewrap 需要 namespace/mount 系统调用。项目部署默认对 sandbox-worker 使用 `seccomp=unconfined`；禁止该设置的集群需要提供允许必要系统调用的 Localhost seccomp profile。
- 任务命名空间内只有当前工作空间及其临时目录可写。
- 依赖缓存及必要运行时目录只读挂载。
- 子进程只接收过滤后的环境变量，而不是 Worker 的完整进程环境。
- 会话过期后自动清理工作目录。

## 开发

本地开发时，在主 Worker 旁启动 Sandbox Worker：

```bash
# 宿主机进程：除非显式启用，否则不使用文件系统隔离
uv run --project backend main.py sandbox-worker -c 1

# 容器模式：构建并运行已启用 Bubblewrap 的 sandbox-worker 镜像
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

如需在支持 user namespace 的 Linux 宿主机上启用同等隔离，请安装 Bubblewrap 并设置：

```bash
SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true
SANDBOX_FILESYSTEM_ISOLATION_BINARY=/usr/bin/bwrap
```

Docker Compose 和 Helm 默认启用这两个配置。标准容器 seccomp profile 通常会阻止 rootless Bubblewrap 使用的 namespace/mount 系统调用，因此必须保留项目提供的 sandbox-worker 安全配置。

基于 Docker 的部署中，Docker Compose 和 Kubernetes 配置中包含独立的 `sandbox-worker` 服务。

---

参见：
- [工具系统](../admin-guide/tools/TOOLS_zh-CN.md) — 配置代码工具
- [工作流引擎架构](../../dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md) — 代码节点集成
