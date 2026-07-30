# 代码沙箱

Clouisle 提供一个安全、隔离的代码执行环境——**沙箱运行时**——用于在工作流、Agent 和工具中运行用户提供的 Python 和 JavaScript 代码。

## 架构

沙箱使用专用的 Celery Worker 在隔离环境中处理代码执行任务：

```
Agent/工作流 → API → Celery 队列 (sandbox) → 沙箱 Worker
                                                  ↓
                                            隔离进程
                                          （资源限制）
                                                  ↓
                                            结果 / 产物
```

核心特性：
- **进程隔离**：每次执行在独立子进程中运行，具有 CPU、内存和磁盘配额
- **本地文件系统**：每个任务/会话在 `/tmp/clouisle-sandbox/jobs/` 下拥有独立的工作空间目录，包含 `input/`、`output/`、`tmp/`、`logs/` 子目录
- **符号链接防护**：对所有工作空间路径进行符号链接检测，阻止路径穿越攻击
- **无网络访问**：沙箱代码无法访问外部网络
- **输入暂存**：文件在执行前以 base64 解码写入工作空间
- **自动清理**：一次性任务执行完毕立即清理；会话按 TTL 过期清理

## 支持的运行时

| 运行时 | 基础环境 |
|---|---|
| Python | Python 3.13 含标准库和常用包 |
| JavaScript | Node.js 22 含核心模块 |

## 平台中的使用场景

### 代码工具

在 **管理后台 → 功能 → 代码** 中创建可复用的代码工具。保存后的工具可被 Agent 和工作流调用。

### 工作流代码节点

在工作流图中直接嵌入代码。代码节点接收输入变量并将结果返回给下游节点。

### Agent 级执行

Agent 可以通过函数调用触发代码工具。LLM 根据任务需要决定何时运行代码。

## 配置

| 变量 | 说明 |
|---|---|
| `SANDBOX_RUNTIME_ENABLED` | 启用沙箱运行时（默认：`true`） |
| `SANDBOX_WORKER_CONCURRENCY` | 并行沙箱 Worker 数量 |
| `SANDBOX_WORKSPACE_ROOT` | 任务工作空间的临时目录 |
| `SANDBOX_MAX_DISK_MB` | 每任务的磁盘配额 |
| `SANDBOX_SESSION_TTL_HOURS` | 会话生命周期（超时清理） |
| `SANDBOX_RESULT_TTL_SECONDS` | 结果保留时间 |

## 安全模型

- 代码在沙箱 Worker 容器内的**非 root 用户**下运行
- `shell=false` — 禁止 Shell 命令执行，仅允许声明式脚本调用
- 沙箱代码**无法访问凭据或密钥**
- 会话过期后**自动清理**工作目录
- 资源限制防止失控代码影响其他服务

## 开发

本地开发时，在主 Worker 旁启动沙箱 Worker：

```bash
# 宿主机进程（直接运行）
uv run --project backend main.py sandbox-worker -c 1

# 容器隔离（推荐）
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

基于 Docker 的部署中，Docker Compose 和 Kubernetes 配置中包含独立的 `sandbox-worker` 服务。

---

参见：
- [工具系统](../admin-guide/tools/TOOLS_zh-CN.md) — 配置代码工具
- [工作流引擎架构](../../dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md) — 代码节点集成
