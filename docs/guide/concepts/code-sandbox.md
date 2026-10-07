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

### Session Affinity and Recovery

Each ready sandbox worker advertises a short Redis lease only after its workspace and checkpoint roots pass writable-disk checks. A session binds to one worker, process instance, node, storage identity and workspace generation. Its jobs and lifecycle tasks use that worker's dedicated Celery queue; API and Agent workers do not need access to the worker's physical filesystem.

A supervised Celery-process restart on the same retained disk gets a new instance ID and can restore the session checkpoint. If the original storage remains unavailable through the bounded recovery window, the runtime may prepare a fresh workspace on another ready worker and atomically advance the session generation. AgentRun receives `WORKSPACE_RESET` and must replan. Old-generation queued jobs are rejected, and a running command with uncertain completion is never replayed automatically. This is node-local persistence, not shared storage or replication: permanent loss of the original disk means its uncheckpointed files cannot be restored.

### Sandbox Task Audit Events

The admin audit log records lifecycle events for executable sandbox jobs and their result-tracked workspace-preparation/checkpoint jobs: started, completed, failed, cancelled, and recovered. Entries include task/session identifiers and available actor, team, source, worker, duration, status, and error-code context. They exclude code, input arguments, stdout/stderr, result payloads, and raw exception text. Filter **Admin → Audit Logs** by resource type `sandbox_task`.

### Deep-Dive Bubblewrap Namespace & Mount Layout

When filesystem isolation is enabled (`SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true`), the sandbox launcher wraps executions in a dedicated `bwrap` process configured with strict namespace isolation:

```text
bwrap \
  --unshare-user --unshare-pid --unshare-ipc --unshare-uts \
  --die-with-parent --hostname clouisle-sandbox \
  --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /etc /etc \
  --dir /proc --dev /dev \
  --bind <host_job_dir> /workspace \
  --bind <host_job_dir>/tmp /tmp \
  --chdir /workspace \
  -- <command> <args...>
```

#### 1. Namespace & Process Confinement
- **Unshared Namespaces**: `--unshare-user`, `--unshare-pid`, `--unshare-ipc`, `--unshare-uts` create an isolated environment with its own process tree (PID 1 mapping), inter-process communication boundary, and isolated hostname (`clouisle-sandbox`).
- **`--die-with-parent`**: Guarantees that all child processes inside the sandbox are instantly reaped if the supervising Celery worker exits or times out.

#### 2. Filesystem Mount Table (`RUNTIME_READONLY_ROOTS`)
- **Read-Only System Roots**: `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc` are mounted as `--ro-bind`, ensuring code cannot modify system binaries, Python site-packages, or OS configuration.
- **Isolated Workspace Mapping**: The host job directory is mapped directly to `/workspace`. Code interacts with a standard, clean `/workspace` root regardless of where jobs are physically stored on the host.
- **Dedicated `/tmp` Sub-mount**: The workspace contains an isolated `tmp` directory mounted at `/tmp` (`--bind <workspace>/tmp /tmp`), isolating temporary files from host `/tmp`.
- **Logical Path Auto-Rewriting**: `_logical_workspace_path` and `_map_workspace_value` automatically rewrite command arguments and environment paths so tasks only ever see `/workspace/...`.

#### 3. Container Runtimes & CJK Font Support
- **Runtimes**: Pre-installed Python 3.13 (managed via `uv`), Node.js 22, and standard numerical computing toolchains.
- **CJK Fonts Included**: The `clouisle-sandbox-worker` image packages `fontconfig`, `fonts-wqy-zenhei`, and `fonts-wqy-microhei` with `fc-cache -fv`. Because `/usr/share/fonts` is exposed via read-only bind mount, sandbox scripts generating charts (`matplotlib`, `seaborn`, `Pillow`) render Chinese, Japanese, and Korean text flawlessly without font missing boxes (`tofu`).
## Usage in the Platform

### Code Tool

Create reusable code utilities from **Dashboard → Capabilities → Code**. Saved tools can be called by agents and workflows.

### Workflow Code Node

Embed code directly in workflow graphs. The code node receives input variables and returns results to downstream nodes.

### Agent-level Execution

Agents can invoke code tools via function calling. The LLM decides when to run code based on the task.

## Moving files between chat and sandbox

Chat uploads, generated media, and collected sandbox artifacts are durable `Asset`s. Agent tools see four-character `asset_ref` values in `<available_assets>`. A ref is scoped to one conversation or workflow run, not a global file ID or workspace path.

- `materialize_asset(ref, path)` resolves the ref in the active authorized conversation or workflow-run scope and stages verified bytes under `/workspace` in the active sandbox session. Generated images and videos can be staged this way; images can also be supplied as `reference_image_refs` for image generation.
- `read_asset` returns text only for text MIME types and JSON/XML. `parse_asset` handles supported document types; images are vision inputs. Video and other binary assets must be materialized and processed by sandbox code; available decoders and packages determine supported operations.
- A sandbox output becomes a reusable Asset only when the job collects it as an artifact. Collected artifacts are bound to the active conversation or workflow run; uncollected files remain workspace-only. Sandbox file tools can access session files while the session exists. Collected artifacts appear in the Asset manifest on a later Agent run.
- `workflow_asset_refs` imports selected workflow-run Assets into a conversation. The server authorizes both the source run and destination conversation before linking them.
- Cross-scope or cross-team access is not a file conversion. Each operation reauthorizes its source and destination; generated-media and artifact download URLs are protected. Never guess refs or reuse paths from another conversation.

## Configuration

| Variable | Generic Default | Sandbox Worker Deployment | Description |
|---|---|---|---|
| `SANDBOX_RUNTIME_ENABLED` | `true` | `true` | Enable the sandbox runtime |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `true` | `true` | Launch executable payloads inside the Bubblewrap filesystem namespace |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `bwrap` | `/usr/bin/bwrap` | Bubblewrap executable name or absolute path |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | `1` | Number of concurrent sandbox worker slots |
| `SANDBOX_WORKER_ID` | Empty; generated and persisted per disk | Leave unset for per-disk identity | Optional explicit worker identity; a retained disk keeps its worker/storage IDs |
| `SANDBOX_NODE_ID` | Empty; hostname | Kubernetes node name or `compose-local` | Node identity used to prefer the original storage location during recovery |
| `SANDBOX_WORKER_INSTANCE_ID` | Empty; generated per process | Fresh ID per supervised process | Process incarnation; never reuse it across restarts |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | `/var/lib/clouisle/sandbox/jobs` | Common virtual root configured on API, Agent workers and sandbox workers; only sandbox workers mount its physical parent |
| `SANDBOX_CHECKPOINT_ROOT` | Empty | `/var/lib/clouisle/sandbox/checkpoints` | Local full-tree checkpoints; generic default is a `checkpoints` sibling of `SANDBOX_WORKSPACE_ROOT` |
| `SANDBOX_WORKER_HEARTBEAT_SECONDS` | `5` | `5` | Readiness heartbeat interval |
| `SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS` | `20` | `20` | Redis readiness lease lifetime; must exceed the heartbeat interval |
| `SANDBOX_WORKER_RECOVERY_SECONDS` | `30` | `30` | Recovery-attempt bound, capped by the original job deadline |
| `SANDBOX_RECOVERY_POLL_SECONDS` | `0.5` | `0.5` | Poll interval for worker availability and physical-preparation acknowledgement |
| `SANDBOX_SESSION_MAX_RESETS` | `1` | `1` | Maximum fresh-workspace generation replacements per session |
| `SANDBOX_SUPERVISOR_RESTART_SECONDS` | `1` | `1` | Delay before restarting an exited Celery child on the retained disk |
| `SANDBOX_SUPERVISOR_MAX_RESTARTS` | `3` | `3` | Child restarts allowed before the sandbox-worker container exits |
| `SANDBOX_WORKSPACE_IDLE_SECONDS` | `900` | `900` | Idle time before an inactive session workspace is evicted to its checkpoint |
| `SANDBOX_CHECKPOINT_TIMEOUT_SECONDS` | `120` | `120` | Maximum wait for an owning worker to acknowledge a round checkpoint |
| `SANDBOX_MAX_DISK_MB` | `8192` | Same | Maximum requested workspace disk limit |
| `SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS` | `300` | Same | Maximum time allowed for Python/Node dependency installation; timed-out installs are terminated and not cached |
| `SANDBOX_TASK_MEMORY_MB` | `1024` | Same | Per-process address-space limit enforced by `prlimit`; worker/container memory limits still cap the aggregate process tree |
| `SANDBOX_TASK_MAX_FILE_SIZE_MB` | `1024` | Same | Maximum size of each regular file created by a sandbox process; not a total workspace quota |
| `SANDBOX_TASK_MAX_OPEN_FILES` | `256` | Same | File-descriptor limit inherited by sandbox child processes |
| `SANDBOX_TASK_MAX_CPU_SECONDS` | `600` | Same | Upper CPU-time limit for each launch; the task timeout may impose a lower value |
| `SANDBOX_SESSION_TTL_HOURS` | `24` | Same | Session lifetime before cleanup |
| `SANDBOX_RESULT_TTL_SECONDS` | `86400` | Same | Result retention period |

Sandbox egress is configured in [Settings → Security → Sandbox Egress Allowlist](../admin-guide/settings/system-settings.md#sandbox-egress-allowlist), not by an environment variable. The initial defaults permit `pypi.org`, `files.pythonhosted.org`, `pypi.python.org`, and `registry.npmjs.org`. The saved exact-host policy is read for every job; an empty list blocks external hosts, and custom package indexes must use HTTPS.

AgentRun round boundaries are checkpointed on the session's owning sandbox worker before the run becomes completed, waiting for a user answer, or stopped. Idle runtime directories are evicted after checkpointing and restored on the next task. Persist workspace, checkpoint, identity, lock and cache paths on the same worker-local disk. TTL cleanup permanently deletes session data when a worker can process the cleanup task; an unreachable node's local files cannot be deleted remotely.

The caller fails closed: when `SANDBOX_RUNTIME_ENABLED` is false, code execution returns a failure without running a local fallback. A failed sandbox task also returns failure. The sandbox-worker image installs Bubblewrap and enables isolation; a missing binary or workspace root fails the task instead of launching the payload without isolation.

## Security Model

- The task payload executes inside a fresh Bubblewrap **user + mount namespace**, never in the worker's own namespaces.
- Supplied deployments run the worker as root with `CAP_SYS_ADMIN`, `CAP_SETFCAP`, and `CAP_NET_ADMIN`. `NET_ADMIN` lets the trusted egress bridge enable loopback in the isolated network namespace; it then sets `no-new-privileges` and clears its capability sets before starting the payload. Direct payloads use Bubblewrap `--cap-drop ALL`. The worker uses `seccomp=unconfined` because Bubblewrap's `pivot_root` fails under Docker's default seccomp profile.
- `prlimit` applies inherited per-process address-space, CPU-time, file-size, and open-file limits. Captured stdout/stderr retain at most their configured byte limits; Compose also caps the worker at 512 processes and 2 GiB, while Kubernetes relies on node-level `podPidsLimit` plus the pod's CPU/memory limits.
- Only the current workspace and its temporary directory are writable inside the task namespace.
- The dependency cache and required runtime directories are read-only.
- The child receives a filtered environment rather than the worker's full process environment.
- With filesystem isolation enabled, each sandbox process uses a fresh network namespace and reaches external hosts only through its per-job egress proxy. The persisted **Sandbox Egress Allowlist** matches exact DNS hostnames; blocked hosts are included in execution diagnostics.
- Session workspaces are cleaned after TTL expiry.

## Host Kernel Requirements

Bubblewrap creates a new user namespace with `unshare(CLONE_NEWUSER)`. Supplied deployments run the worker as root with `CAP_SYS_ADMIN` and `CAP_SETFCAP` for namespace/mount setup, plus `CAP_NET_ADMIN` so the trusted egress bridge can enable loopback inside the isolated network namespace. No host sysctl changes are required. Kubernetes clusters must separately configure kubelet `podPidsLimit` to bound worker process counts.

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

The sandbox task runs in a fresh Bubblewrap user + mount namespace, so it cannot directly reach the worker container's capabilities. If a task escapes Bubblewrap, it lands inside the worker container as root with `CAP_SYS_ADMIN`, `CAP_SETFCAP`, and `CAP_NET_ADMIN`. On a default Docker daemon the container shares the host's initial user namespace, which makes `CAP_SYS_ADMIN` host-user-namespace-scoped and exposes well-known escape chains (cgroup `release_agent`, remounting `/proc` to write `kernel.core_pattern`, sysctl writes) in principle. `CAP_NET_ADMIN` is scoped to the worker container's network namespace; it is required to enable loopback only inside each isolated task namespace.

For Docker Compose deployments, enable **daemon user namespace remapping** (`"userns-remap": "default"` in `/etc/docker/daemon.json`) to place every container in a nested user namespace — `CAP_SYS_ADMIN` then only applies to the container's own user namespace and the host-escape chains no longer work. `CAP_NET_ADMIN` remains scoped to the worker's container network namespace. The sandbox worker still creates its Bubblewrap user namespace (privileged inside the remapped namespace), so sandbox functionality is unaffected. See [Deployment Guide → User Namespace Remapping](../deployment/DEPLOYMENT.md#user-namespace-remapping-hardening) for configuration, verification, and volume ownership impact.

For Kubernetes, configure **Sandbox Egress Allowlist** in Security settings to constrain isolated sandbox-process egress through the proxy. Apply a NetworkPolicy as an additional pod-level egress restriction, and keep Bubblewrap updated and monitor its CVEs.

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
