# Role Management Admin Guide

Clouisle provides fine-grained Role-Based Access Control (RBAC) allowing workspace administrators to create custom roles and assign precise permission scopes.

---

## 1. Managing Roles

Navigate to **System Settings > Roles** (`/roles`):

1. **System Built-in Roles**:
   - `Superuser`: Unrestricted platform-wide administrative control.
   - `Admin`: Workspace-level administration (models, teams, audit logs, system settings).
   - `Member`: Standard collaborative user who can create and use agents, workflows, and knowledge bases.
   - `Viewer`: Read-only access to published resources.
2. **Creating Custom Roles**:
   - Click **Create Role**, provide a unique code and display name.
   - Select individual permissions across scopes (`agent:*`, `workflow:*`, `kb:*`, `tool:*`, `model:*`, `audit:*`).
3. **Assigning Roles**:
   - Assign roles to users during creation or edit existing user permissions under **User Management**.

---

# Security & Observability Admin Guide

## 1. Security Settings (`/site-settings/security`)

- **SSRF Outbound Network Allowlist**: Restrict HTTP request nodes, Webhook triggers, and document URL importers to prevent Server-Side Request Forgery against private subnets.
- **Click Captcha Verification**: Configure human verification thresholds for registration and login pages to defend against automated brute-force attacks.

## 2. System Observability (`/dashboard/observability`)

- **Real-time Overview**: Track active agent sessions, workflow run throughput, and token consumption rates.
- **Worker & Queue Health**: Monitor Celery backlog and active worker concurrency across `default`, `agent`, `knowledge`, and `workflow` queues.
- **Slow Queries & Interrupted Runs**: Identify and diagnose long-running SQL queries or unexpected worker restarts that resulted in interrupted executions.
