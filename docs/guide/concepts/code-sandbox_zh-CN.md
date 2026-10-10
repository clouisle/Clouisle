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

### 会话亲和与恢复

Sandbox Worker 只有在工作区和检查点目录通过可写磁盘探测后，才会发布短时 Redis 就绪租约。每个会话绑定到具体 Worker 进程实例、节点、存储身份和工作区代次；会话任务及生命周期任务都进入该 Worker 的专属 Celery 队列。API 和普通 Agent Worker 不需要访问沙箱 Worker 的物理文件系统。

同一份持久化本地磁盘上的 Celery 子进程重启后，会获得新的实例 ID，并可从本地检查点恢复会话。如果原存储在有界恢复时间内仍不可用，运行时可在其他就绪 Worker 上准备全新的工作区，再原子地推进会话代次。AgentRun 会收到 `WORKSPACE_RESET`，必须重新规划。旧代次的排队任务会被拒绝；执行结果不确定的运行中命令不会自动重放。这是节点本地持久化，不是共享存储或副本：原磁盘永久丢失时，未保存的数据无法恢复。

### 沙箱任务审计事件

管理员审计日志会记录可执行沙箱任务及其有结果记录的工作区准备/检查点任务的生命周期事件：开始、完成、失败、取消和恢复。日志包含任务/会话标识，以及可用的操作者、团队、来源、Worker、耗时、状态和错误码；不会记录代码、输入参数、标准输出/错误、结果负载或原始异常文本。可在 **管理后台 → 审计日志** 中按资源类型 `sandbox_task` 筛选。

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

## 在对话与沙箱之间传递文件

对话上传文件、生成的媒体和已收集的沙箱产物都会作为持久化 `Asset` 保存。Agent 工具通过 `<available_assets>` 中的 4 字符 `asset_ref` 访问它们。ref 属于特定对话或工作流运行，不是全局文件 ID，也不是工作区路径。

- `materialize_asset(ref, path)` 会在当前已授权的对话或工作流运行范围内解析 ref，并把校验过的文件内容暂存到当前沙箱会话的 `/workspace`。生成的图片和视频都可以这样暂存；图片还可通过 `reference_image_refs` 作为生图参考图。
- `read_asset` 只直接读取文本 MIME、JSON 和 XML。`parse_asset` 处理受支持的文档类型；图片可作为视觉输入。视频和其他二进制文件需要先暂存，再由沙箱代码处理；具体操作取决于沙箱运行时是否提供相应解码器和依赖包。
- 只有被任务收集为 Artifact 的沙箱输出才会成为可复用 Asset，并绑定到当前对话或工作流运行。未收集的文件只留在会话工作区；会话有效期间可用沙箱文件工具访问。已收集的产物会出现在后续 Agent 运行构建的 Asset 清单中。
- `workflow_asset_refs` 可将选定的工作流运行 Asset 导入对话。服务端会分别授权来源运行和目标对话后再建立关联。
- 跨范围或跨 team 访问不是文件格式转换。每次操作都会重新校验来源和目标权限；生成媒体与沙箱产物的下载 URL 受保护。在对话中点击指向已收集沙箱产物的 Markdown 链接，会在已认证的文件预览中打开；复制的 URL 仍需要带认证信息的请求。拖动预览分隔条时，只有对话面板达到 400 px 最小宽度，对话历史侧栏才会自动收起；面板宽于该阈值时保持展开。之后可通过侧栏开关重新打开。拖动期间预览视口保持原尺寸，松开后再适配新尺寸。不要猜测 ref，也不要复用其他对话的路径。

## 配置

| 变量 | 通用默认值 | Sandbox Worker 部署值 | 说明 |
|---|---|---|---|
| `SANDBOX_RUNTIME_ENABLED` | `true` | `true` | 启用沙箱运行时 |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `true` | `true` | 在 Bubblewrap 文件系统命名空间内启动可执行任务 |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `bwrap` | `/usr/bin/bwrap` | Bubblewrap 命令名或绝对路径 |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | `1` | Sandbox Worker 并发槽位数 |
| `SANDBOX_WORKER_ID` | 空；按磁盘生成并持久化 | 留空以使用每磁盘身份 | 可选显式 Worker 身份；保留磁盘会保留其 Worker/存储 ID |
| `SANDBOX_NODE_ID` | 空；使用 hostname | Kubernetes 节点名或 `compose-local` | 恢复时用于优先选择原节点的身份 |
| `SANDBOX_WORKER_INSTANCE_ID` | 空；按进程生成 | 监督器为每个进程分配新 ID | Worker 进程实例；重启后不可复用旧 ID |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | `/var/lib/clouisle/sandbox/jobs` | API、Agent Worker 与 Sandbox Worker 使用相同的虚拟根路径；仅 Sandbox Worker 挂载其物理父目录 |
| `SANDBOX_CHECKPOINT_ROOT` | 空 | `/var/lib/clouisle/sandbox/checkpoints` | 本地完整工作区检查点；通用默认值是 `SANDBOX_WORKSPACE_ROOT` 的同级 `checkpoints` 目录 |
| `SANDBOX_WORKER_HEARTBEAT_SECONDS` | `5` | `5` | 就绪心跳间隔 |
| `SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS` | `20` | `20` | Redis 就绪租约时长，必须大于心跳间隔 |
| `SANDBOX_WORKER_RECOVERY_SECONDS` | `30` | `30` | 单次恢复时限，并受原任务截止时间约束 |
| `SANDBOX_RECOVERY_POLL_SECONDS` | `0.5` | `0.5` | 等待 Worker 就绪及物理工作区准备确认时的轮询间隔 |
| `SANDBOX_SESSION_MAX_RESETS` | `1` | `1` | 每个会话允许切换到全新工作区代次的最大次数 |
| `SANDBOX_SUPERVISOR_RESTART_SECONDS` | `1` | `1` | 在保留的本地磁盘上重启已退出 Celery 子进程前的等待时间 |
| `SANDBOX_SUPERVISOR_MAX_RESTARTS` | `3` | `3` | Sandbox Worker 容器退出前允许的子进程重启次数 |
| `SANDBOX_WORKSPACE_IDLE_SECONDS` | `900` | `900` | 不活跃会话工作区被释放到检查点前的空闲时长 |
| `SANDBOX_CHECKPOINT_TIMEOUT_SECONDS` | `120` | `120` | 等待所属 Worker 确认轮次检查点的最长时间 |
| `SANDBOX_MAX_DISK_MB` | `8192` | 相同 | 允许请求的最大工作空间磁盘限制 |
| `SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS` | `300` | 相同 | Python/Node 依赖安装最长执行时间；超时后终止安装进程且不缓存未完成环境 |
| `SANDBOX_TASK_MEMORY_MB` | `1024` | 相同 | `prlimit` 强制执行的单进程虚拟地址空间上限；Worker/容器资源限制仍负责限制进程树总量 |
| `SANDBOX_TASK_MAX_FILE_SIZE_MB` | `1024` | 相同 | 沙箱进程可创建的单个普通文件最大尺寸；不是整个工作区的总容量配额 |
| `SANDBOX_TASK_MAX_OPEN_FILES` | `256` | 相同 | 沙箱进程及其子进程可打开的文件描述符上限 |
| `SANDBOX_TASK_MAX_CPU_SECONDS` | `600` | 相同 | 每次启动的 CPU 时间上限；任务超时可能设置更低的值 |
| `SANDBOX_SESSION_TTL_HOURS` | `24` | 相同 | 会话过期清理时间 |
| `SANDBOX_RESULT_TTL_SECONDS` | `86400` | 相同 | 结果保留时间 |

沙箱出网策略在[设置 → 安全 → 沙箱出网白名单](../admin-guide/settings/system-settings.md#sandbox-egress-allowlist)中配置，不再通过环境变量设置。初始默认值允许 `pypi.org`、`files.pythonhosted.org`、`pypi.python.org` 和 `registry.npmjs.org`。每个任务都会读取当前已保存的精确主机名策略；空列表会阻止外部主机，自定义包索引必须使用 HTTPS。

AgentRun 每轮结束时，系统会先在会话所属的 Sandbox Worker 上保存检查点，再将运行标记为完成、等待用户回答或停止。空闲工作区会在达到阈值后被释放，并在下次任务到来时恢复。工作区、检查点、身份、锁和缓存目录应一起保存在同一份 Worker 本地磁盘上，不会跨节点复制。TTL 到期后，Worker 能处理清理任务时会永久删除会话数据；若节点不可访问，其他节点无法远程删除其本地文件。

调用侧采用 fail-closed：`SANDBOX_RUNTIME_ENABLED=false` 时，代码执行直接失败，不会在当前进程启用本地降级；沙箱任务失败也会返回失败。Sandbox Worker 镜像会安装 Bubblewrap 并启用隔离；若缺少 `bwrap` 或工作空间根目录，任务会失败，不会在未隔离的情况下启动负载。

## 安全模型

- 任务负载在全新的 Bubblewrap **用户+挂载命名空间**内执行，绝不会运行在 Worker 自身的命名空间里。
- 项目部署以 root 运行 Worker，授予 `CAP_SYS_ADMIN`、`CAP_SETFCAP` 和 `CAP_NET_ADMIN`。`NET_ADMIN` 让可信的出网代理在隔离网络命名空间内启用 loopback；随后代理会设置 `no-new-privileges` 并清空自身 capability 集，再启动任务负载。无代理的任务则由 Bubblewrap 使用 `--cap-drop ALL` 启动。Worker 使用 `seccomp=unconfined`，因为实测 Docker 默认 seccomp 会导致 Bubblewrap 的 `pivot_root` 返回 `Operation not permitted`。
- `prlimit` 为每个进程设置虚拟地址空间、CPU 时间、单文件大小和文件描述符上限，子进程继承这些限制。标准输出/错误只在内存中保留配置的字节数；Compose 还把 Worker 限制为最多 512 个进程和 2 GiB，Kubernetes 则依赖节点级 kubelet `podPidsLimit` 及 Pod CPU/内存限制。
- 任务命名空间内只有当前工作空间及其临时目录可写。
- 依赖缓存及必要运行时目录只读挂载。
- 子进程只接收过滤后的环境变量，而不是 Worker 的完整进程环境。
- 启用文件系统隔离时，每个沙箱进程都运行在新的网络命名空间中，只能通过该任务的出网代理访问外部主机。持久化的**沙箱出网白名单**按 DNS 主机名精确匹配；被拦截的主机名会写入执行诊断信息。
- 会话过期后自动清理工作目录。

## 宿主内核要求

Bubblewrap 通过 `unshare(CLONE_NEWUSER)` 创建新的用户命名空间。项目部署以 root 运行 Worker：`CAP_SYS_ADMIN` 和 `CAP_SETFCAP` 用于命名空间/挂载设置，`CAP_NET_ADMIN` 供可信出网代理在隔离任务网络命名空间内启用 loopback。无需修改宿主 sysctl。Kubernetes 集群还需配置 kubelet `podPidsLimit`，以限制 Worker 进程总数。

自定义部署若保持 Worker **非 root**，则依赖宿主内核允许非特权用户命名空间，否则所有沙箱任务都会失败，报错为：

```text
bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.
```

部分常见宿主发行版默认限制该能力，且 `seccomp=unconfined` **无法**解决——限制发生在容器 seccomp profile 更底层的宿主内核：

| 发行版 | 限制 | 修复 |
|---|---|---|
| Ubuntu 23.10+ | AppArmor 禁止非特权进程创建用户命名空间（`kernel.apparmor_restrict_unprivileged_userns=1`） | `sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` |
| Debian / 旧内核 | 用户命名空间克隆被禁用（`kernel.unprivileged_userns_clone=0`） | `sysctl -w kernel.unprivileged_userns_clone=1` |

检查当前状态并验证用户命名空间确实可创建：

```bash
sysctl kernel.apparmor_restrict_unprivileged_userns kernel.unprivileged_userns_clone 2>/dev/null
unshare -U true && echo "user namespaces OK"
```

使修改持久化：

```bash
echo 'kernel.apparmor_restrict_unprivileged_userns=0' > /etc/sysctl.d/99-clouisle-userns.conf
sysctl --system
```

注意事项：

- sysctl 是**宿主/节点级**设置。在 Kubernetes 中无法按 Pod 设置：需要对每个节点生效（自管节点写入 `/etc/sysctl.d/`，托管集群使用自定义节点镜像或等效的节点初始化配置）。
- 允许非特权用户命名空间是 rootless 容器（Bubblewrap、Flatpak、Podman）的标准前提。

### 加固：收敛 Worker 的 `CAP_SYS_ADMIN`

沙箱任务运行在全新的 Bubblewrap 用户+挂载命名空间内，无法直接触及 Worker 容器的 capabilities。但如果任务成功逃出 Bubblewrap，落点就是容器内 root，并拥有 `CAP_SYS_ADMIN`、`CAP_SETFCAP` 和 `CAP_NET_ADMIN`。默认 Docker daemon 下容器与宿主共享初始用户命名空间，`CAP_SYS_ADMIN` 属于宿主 userns 范围，经典逃逸链（cgroup `release_agent`、重挂 `/proc` 写入 `kernel.core_pattern`、sysctl 写入）在原理上可达。`CAP_NET_ADMIN` 仅作用于 Worker 容器的网络命名空间；它用于在每个隔离任务网络命名空间中启用 loopback。

Docker Compose 部署建议启用 **daemon 用户命名空间重映射**（`/etc/docker/daemon.json` 中 `"userns-remap": "default"`），让每个容器进入嵌套用户命名空间——`CAP_SYS_ADMIN` 只作用于容器自身 userns，宿主逃逸链全部失效。`CAP_NET_ADMIN` 仍限制在 Worker 容器的网络命名空间内。沙箱 Worker 仍能在重映射后的命名空间内特权创建自己的 Bubblewrap userns，沙箱功能不受影响。配置、验证方法与卷属主影响见[部署指南 → 用户命名空间重映射](../deployment/DEPLOYMENT_zh-CN.md#用户命名空间重映射加固)。

Kubernetes 中，通过安全设置里的**沙箱出网白名单**限制隔离沙箱进程经代理的出网。还应使用 NetworkPolicy 增加 Pod 级出网限制，并及时升级 Bubblewrap、关注其 CVE。

## 开发

本地开发时，在主 Worker 旁启动 Sandbox Worker：

```bash
# 宿主机进程：除非显式启用，否则不使用文件系统隔离
uv run --project backend main.py sandbox-worker -c 1

# 容器模式：构建并运行已启用 Bubblewrap 的 sandbox-worker 镜像
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

如需在 Linux 宿主机上启用同等隔离（宿主需允许非特权用户命名空间，见上文「宿主内核要求」），请安装 Bubblewrap 并设置：

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
