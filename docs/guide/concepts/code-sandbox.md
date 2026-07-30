# Code Sandbox

Clouisle provides a secure, isolated code execution environment — the **Sandbox Runtime** — for running user-supplied Python and JavaScript code within workflows, agents, and tools.

## Architecture

The sandbox uses a dedicated Celery worker that processes code execution tasks in isolation:

```
Agent/Workflow → API → Celery Queue (sandbox) → Sandbox Worker
                                                      ↓
                                              Isolated Process
                                              (resource limits)
Key properties:
- **Process isolation**: each execution runs in a separate subprocess with CPU, memory, and disk quotas
- **Local filesystem**: each job/session gets an isolated workspace directory under `/tmp/clouisle-sandbox/jobs/` with `input/`, `output/`, `tmp/`, and `logs/` subdirectories
- **Symlink protection**: path traversal attacks are blocked by symlink detection on all workspace paths
- **No network access**: sandboxed code cannot reach external networks
- **Input staging**: files are base64-decoded and written into the workspace before execution
- **Automatic cleanup**: one-off jobs cleaned immediately after execution; sessions cleaned on TTL expiry

| Runtime | Base Environment |
|---|---|
| Python | Python 3.13 with standard library and common packages |
| JavaScript | Node.js 22 with core modules |

## Usage in the Platform

### Code Tool

Create reusable code utilities from **Dashboard → Capabilities → Code**. Saved tools can be called by agents and workflows.

### Workflow Code Node

Embed code directly in workflow graphs. The code node receives input variables and returns results to downstream nodes.

### Agent-level Execution

Agents can invoke code tools via function calling. The LLM decides when to run code based on the task.

## Configuration

| Variable | Description |
|---|---|
| `SANDBOX_RUNTIME_ENABLED` | Enable the sandbox runtime (default: `true`) |
| `SANDBOX_WORKER_CONCURRENCY` | Number of parallel sandbox workers |
| `SANDBOX_WORKSPACE_ROOT` | Temp directory for job workspaces |
| `SANDBOX_MAX_DISK_MB` | Per-job disk quota |
| `SANDBOX_SESSION_TTL_HOURS` | Session lifetime before cleanup |
| `SANDBOX_RESULT_TTL_SECONDS` | Result retention period |

## Security Model

- Code runs under a **non-root user** inside the sandbox worker container
- `shell=false` — no shell command execution; only declarative script invocation
- **No credentials or secrets** are exposed to sandboxed code
- Workspace directories are **cleaned up** after session expiry
- Resource limits prevent runaway code from affecting other services

## Development

For local development, start the sandbox worker alongside the main worker:

```bash
# Host process (direct)
uv run --project backend main.py sandbox-worker -c 1

# Container isolation (recommended)
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

For Docker-based deployment, a separate `sandbox-worker` service is included in the Docker Compose and Kubernetes configurations.

---

See also:
- [Tool System](../admin-guide/tools/TOOLS.md) — configuring the code tool
- [Workflow Engine Architecture](../../dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md) — code node integration
