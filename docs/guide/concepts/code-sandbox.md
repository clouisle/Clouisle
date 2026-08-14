# Code Sandbox

Clouisle provides a secure, isolated code execution environment — the **Sandbox Runtime** — for running user-supplied Python and JavaScript code within workflows, agents, and tools.

## Architecture

Sandbox tasks are submitted to a dedicated Celery worker. The worker launches each executable payload inside a rootless Bubblewrap mount namespace:

```text
Agent/Workflow → API → Celery Queue (sandbox) → Sandbox Worker
                                                      ↓
                                             Bubblewrap process
                                                      ↓
                                  /workspace → current job/session directory
```

Key properties:

- **Real `/workspace` path**: the current job or session directory is bind-mounted read-write at `/workspace`, so Python, Node.js, native libraries, and child processes use the same path.
- **Filesystem isolation**: sibling workspaces, `/app`, and `/app/uploads` are not mounted into the task namespace. Required system runtime directories and the dependency cache are mounted read-only.
- **Process lifecycle isolation**: each execution uses a new process group; timeout handling terminates the whole group.
- **Path protection**: input staging, file tools, and artifact collection reject workspace escapes and symlink traversal.
- **Root-scan confinement**: direct Agent commands such as `find /` are normalized to `find /workspace`; commands launched from code still see only the minimal Bubblewrap filesystem.
- **Bounded execution**: task timeout, output limits, workspace disk checks, and worker container resource limits constrain runaway jobs.
- **Network policy is separate**: Bubblewrap does not unshare the network namespace. Restrict outbound access with Docker or Kubernetes network policy when required.
- **Automatic cleanup**: one-off jobs are cleaned immediately after execution; sessions are cleaned on TTL expiry.

| Runtime | Base Environment |
|---|---|
| Python | Python 3.13 with standard library and configured packages |
| JavaScript | Node.js 22 with core modules and configured packages |

## Usage in the Platform

### Code Tool

Create reusable code utilities from **Dashboard → Capabilities → Code**. Saved tools can be called by agents and workflows.

### Workflow Code Node

Embed code directly in workflow graphs. The code node receives input variables and returns results to downstream nodes.

### Agent-level Execution

Agents can invoke code tools via function calling. The LLM decides when to run code based on the task.

## Configuration

| Variable | Generic Default | Sandbox Worker Deployment | Description |
|---|---|---|---|
| `SANDBOX_RUNTIME_ENABLED` | `true` | `true` | Enable the sandbox runtime |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `false` | `true` | Launch executable payloads inside the Bubblewrap filesystem namespace |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `bwrap` | `/usr/bin/bwrap` | Bubblewrap executable name or absolute path |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | `1` | Number of concurrent sandbox worker slots |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | Same | Host-side root for job and session directories |
| `SANDBOX_MAX_DISK_MB` | `8192` | Same | Maximum requested workspace disk limit |
| `SANDBOX_SESSION_TTL_HOURS` | `24` | Same | Session lifetime before cleanup |
| `SANDBOX_RESULT_TTL_SECONDS` | `86400` | Same | Result retention period |

The sandbox-worker image installs Bubblewrap and enables isolation. When isolation is enabled, a missing binary or missing workspace root fails the task instead of falling back to direct execution.

## Security Model

- The task payload executes inside a fresh Bubblewrap **user + mount namespace**, never in the worker's own namespaces.
- The supplied deployments run the sandbox worker as **root with `CAP_SYS_ADMIN` added to the runtime default cap set**: the image's non-root user has empty effective capabilities, and a privileged worker can create user namespaces even on hosts that gate unprivileged user namespaces. The worker keeps `allowPrivilegeEscalation=false` and `seccomp=unconfined` (sandbox worker only).
- Rootless Bubblewrap needs namespace and mount syscalls. The supplied deployment uses `seccomp=unconfined` for the sandbox worker; clusters that prohibit this setting must provide a Localhost seccomp profile allowing the required syscalls.
- Only the current workspace and its temporary directory are writable inside the task namespace.
- The dependency cache and required runtime directories are read-only.
- The child receives a filtered environment rather than the worker's full process environment.
- Session workspaces are cleaned after TTL expiry.

## Host Kernel Requirements

Bubblewrap creates a new user namespace with `unshare(CLONE_NEWUSER)`. The **supplied deployments** run the worker as root with `CAP_SYS_ADMIN`, so user namespace creation is privileged and works even on hosts that restrict non-privileged user namespaces — no host sysctl changes are required.

Custom deployments that keep the worker **non-root** rely on the host kernel permitting unprivileged user namespaces; otherwise every sandbox job fails with:

```text
bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.
```

Several common host distributions restrict this by default, and `seccomp=unconfined` does **not** help here because the restriction is enforced below the container seccomp profile:

| Distribution | Restriction | Fix |
|---|---|---|
| Ubuntu 23.10+ | AppArmor blocks user namespaces for unprivileged processes (`kernel.apparmor_restrict_unprivileged_userns=1`) | `sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` |
| Debian / older kernels | User namespace cloning disabled (`kernel.unprivileged_userns_clone=0`) | `sysctl -w kernel.unprivileged_userns_clone=1` |

Check the current state and verify that a user namespace can actually be created:

```bash
sysctl kernel.apparmor_restrict_unprivileged_userns kernel.unprivileged_userns_clone 2>/dev/null
unshare -U true && echo "user namespaces OK"
```

Make the change persistent:

```bash
echo 'kernel.apparmor_restrict_unprivileged_userns=0' > /etc/sysctl.d/99-clouisle-userns.conf
sysctl --system
```

Notes:

- The sysctl is a **host/node-level** setting. In Kubernetes it cannot be set per pod: apply it to every node (custom node image, `/etc/sysctl.d/` on self-managed nodes, or the equivalent node bootstrap for managed clusters).
- Enabling unprivileged user namespaces is the standard prerequisite for rootless containers (Bubblewrap, Flatpak, Podman).

### Hardening: contain the worker's `CAP_SYS_ADMIN`

The sandbox task runs in a fresh Bubblewrap user + mount namespace, so it cannot directly reach the worker container's capabilities. If a task ever escapes Bubblewrap, however, it lands inside the worker container as root with `CAP_SYS_ADMIN`. On a default Docker daemon the container shares the host's initial user namespace, which makes that capability host-user-namespace-scoped and exposes well-known escape chains (cgroup `release_agent`, remounting `/proc` to write `kernel.core_pattern`, sysctl writes) in principle.

For Docker Compose deployments, enable **daemon user namespace remapping** (`"userns-remap": "default"` in `/etc/docker/daemon.json`) to place every container in a nested user namespace — `CAP_SYS_ADMIN` then only applies to the container's own user namespace and the host-escape chains no longer work. The sandbox worker still creates its Bubblewrap user namespace (privileged inside the remapped namespace), so sandbox functionality is unaffected. See [Deployment Guide → User Namespace Remapping](../deployment/DEPLOYMENT.md#user-namespace-remapping-hardening) for configuration, verification, and volume ownership impact.

For Kubernetes, daemon-level remapping does not apply; rely on NetworkPolicy for outbound sandbox traffic, keep Bubblewrap updated, and monitor its CVEs, or use node-level user namespace support where the cluster provides it.

## Development

For local development, start the sandbox worker alongside the main worker:

```bash
# Host process: filesystem isolation remains disabled unless explicitly enabled
uv run --project backend main.py sandbox-worker -c 1

# Container mode: builds the sandbox-worker image with Bubblewrap enabled
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

To enable the same isolation on a Linux host (the host must permit unprivileged user namespaces, see [Host Kernel Requirements](#host-kernel-requirements)), install Bubblewrap and set:

```bash
SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true
SANDBOX_FILESYSTEM_ISOLATION_BINARY=/usr/bin/bwrap
```

Docker Compose and Helm enable these settings by default. Their sandbox-worker security configuration is required because standard container seccomp profiles normally block the namespace and mount syscalls used by rootless Bubblewrap.

For Docker-based deployment, a separate `sandbox-worker` service is included in the Docker Compose and Kubernetes configurations.

---

See also:
- [Tool System](../admin-guide/tools/TOOLS.md) — configuring the code tool
- [Workflow Engine Architecture](../../dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md) — code node integration
