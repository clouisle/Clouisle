# Environment Variables

This document provides a complete reference of environment variables used in Clouisle.

## Overview

Environment variables configure:

- **Application settings**: URLs, timezone, CORS
- **Database connections**: PostgreSQL, Redis, Qdrant
- **Security**: Secret key, JWT algorithm, token lifetime
- **Internal services**: API URLs, internal tokens, upload storage mode
- **Retrieval & streaming**: Hybrid retrieval switches, stream timeouts
- **Sandbox runtime**: Sandbox worker configuration
- **External APIs**: Tavily search key

## Configuration System

Clouisle's configuration is not env-only. Values are resolved from three layers:

1. **Backend environment variables** — the variables in the Backend Settings section are read by `backend/app/core/config.py` (Pydantic `Settings`, loaded from `.env` at the project root or the deployment directory). The frontend build/runtime variables documented later are handled by Next.js instead and are not backend `Settings` fields.
2. **Database `SiteSetting` model** — runtime settings that admins manage through the admin UI and are stored in PostgreSQL (`backend/app/models/site_setting.py`). These include SMTP/email, registration, SSO, upload size limits, session timeout, default language, and more. They are **not** environment variables.
3. **LLM provider models** — LLM API keys, base URLs, and model configurations are stored in database models (admin-managed per provider), **not** in environment variables.

Deployment files (`deploy/docker-compose.yml`, Helm values, `deploy/k8s/clouisle.yaml`) set the container-relevant backend values explicitly (e.g. `POSTGRES_SERVER=db`, `API_BASE_URL=http://api:8000`), overriding `.env` defaults. `API_BASE_URL` and `API_INTERNAL_BASE_URL` stay on the private container network; use `PUBLIC_API_URL`, `FRONTEND_URL`, and `BACKEND_CORS_ORIGINS` for browser-facing origins.

## Configuration File

### .env File

**Location**: Root directory of the project for local development; `<installation-directory>/.env` for Docker Compose deployments (see `deploy/.env.example`).

**Format**:
```bash
# Comments start with #
VARIABLE_NAME=value
ANOTHER_VARIABLE=another_value
```

**Example .env file**:
```bash
# Application
PROJECT_NAME=Clouisle
SECRET_KEY=changethis-to-a-secure-random-secret-key
TIMEZONE=Asia/Shanghai

# Internal service URLs; keep these on the private container network.
API_BASE_URL=http://api:8000
API_INTERNAL_BASE_URL=http://api:8000

# Public/browser origins
PUBLIC_API_URL=
FRONTEND_URL=http://localhost:3000
BACKEND_CORS_ORIGINS=["http://localhost:3000"]

# Database
POSTGRES_SERVER=db
POSTGRES_PORT=5432
POSTGRES_DB=clouisle
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secure_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=secure_password

# Qdrant
VECTOR_BACKEND=qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Internal service authentication (required)
INTERNAL_API_TOKEN=generate-a-secure-random-token

UPLOAD_STORAGE_MODE=remote
```

## Backend Settings Variables

The variables in this section are read by the backend Pydantic `Settings` class (`backend/app/core/config.py`). They are distinct from the frontend build-time and runtime variables documented near the end of this page; `NEXT_PUBLIC_*`, `BACKEND_INTERNAL_URL`, and `DEV_ALLOWED_ORIGINS` are not backend `Settings` fields.

### PROJECT_NAME

**Description**: Display name of the application

**Required**: No

**Default**: `Clouisle`

**Example**:
```bash
PROJECT_NAME=Clouisle
```

### API_BASE_URL

**Description**: Internal API URL used by services (file access, sandbox artifact upload, internal calls). Put public domains in `PUBLIC_API_URL` / `FRONTEND_URL` / `BACKEND_CORS_ORIGINS`.

**Required**: Yes in deployments

**Default**: `http://localhost:8000`

**Example**:
```bash
API_BASE_URL=http://api:8000
```

### PUBLIC_API_URL

**Description**: Public API origin used when workflow file URLs must be absolute (browser-visible links)

**Required**: No

**Default**: *(empty)*

**Example**:
```bash
PUBLIC_API_URL=https://example.com
```

### FRONTEND_URL

**Description**: Frontend URL, used for SSO redirect URIs

**Required**: Yes in deployments

**Default**: `http://localhost:3000`

**Example**:
```bash
FRONTEND_URL=https://clouisle.example.com
```

### TIMEZONE

**Description**: Server timezone (affects scheduled tasks)

**Required**: No

**Default**: `Asia/Shanghai`

**Example**:
```bash
TIMEZONE=Asia/Shanghai
```

### BACKEND_CORS_ORIGINS

**Description**: Allowed CORS origins. Accepts a JSON array or a comma-separated list.

**Required**: No

**Default**: `["http://localhost:3000"]`

**Example**:
```bash
BACKEND_CORS_ORIGINS=["https://clouisle.example.com","https://app.example.com"]
```

**Production**: Always specify exact origins, never `*`.

## Security Settings

### SECRET_KEY

**Description**: Application secret key used for JWT signing

**Required**: Yes

**Default**: `changethis-to-a-secure-random-secret-key`

**Example**:
```bash
SECRET_KEY=your-very-secure-random-key-here
```

**Generate**:
```bash
openssl rand -base64 32
```

**Security**:
- Must be random and unique
- Never commit to git
- Change if compromised (changing it invalidates all existing sessions)

### ALGORITHM

**Description**: JWT signing algorithm

**Required**: No

**Default**: `HS256`

**Values**: `HS256`, `HS384`, `HS512`

**Example**:
```bash
ALGORITHM=HS256
```

### ACCESS_TOKEN_EXPIRE_MINUTES

**Description**: JWT access token lifetime in minutes — the config fallback used by `create_access_token` when no explicit expiry is passed. Actual session duration is controlled by the database `session_timeout_days` site setting (admin-configurable, default **30 days**), which login/SSO flows pass as an explicit expiry; this env only kicks in when no explicit expiry is provided.

**Required**: No

**Default**: `11520` (8 days) — JWT fallback only; effective session default is the `session_timeout_days` site setting (30 days)

**Example**:
```bash
ACCESS_TOKEN_EXPIRE_MINUTES=11520
```

## Database Configuration

### PostgreSQL

#### POSTGRES_SERVER

**Description**: PostgreSQL server hostname

**Required**: Yes

**Default**: `localhost`

**Example**:
```bash
POSTGRES_SERVER=db
```

#### POSTGRES_PORT

**Description**: PostgreSQL server port

**Required**: No

**Default**: `5432`

**Example**:
```bash
POSTGRES_PORT=5432
```

#### POSTGRES_DB

**Description**: Database name

**Required**: Yes

**Default**: `clouisle`

**Example**:
```bash
POSTGRES_DB=clouisle
```

#### POSTGRES_USER

**Description**: Database username

**Required**: Yes

**Default**: `postgres`

**Example**:
```bash
POSTGRES_USER=postgres
```

#### POSTGRES_PASSWORD

**Description**: Database password

**Required**: Yes (Compose refuses to start without it)

**Default**: `password` (config default; `deploy/.env.example` leaves it empty)

**Example**:
```bash
POSTGRES_PASSWORD=secure_password_here
```

**Security**: Use strong password, never commit to git

#### DATABASE_URL

**Description**: Complete database connection URL. If set, overrides the individual `POSTGRES_*` variables.

**Required**: No

**Format**: `postgres://user:password@host:port/database`

**Example**:
```bash
DATABASE_URL=postgres://clouisle:password@db:5432/clouisle
```

### Redis

#### REDIS_HOST

**Description**: Redis server hostname

**Required**: Yes

**Default**: `localhost`

**Example**:
```bash
REDIS_HOST=redis
```

#### REDIS_PORT

**Description**: Redis server port

**Required**: No

**Default**: `6379`

**Example**:
```bash
REDIS_PORT=6379
```

#### REDIS_PASSWORD

**Description**: Redis password

**Required**: No (but recommended)

**Default**: None

**Example**:
```bash
REDIS_PASSWORD=secure_password_here
```

The Celery broker and result backend are derived from `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` (`redis://.../0` broker, `redis://.../1` backend) in `backend/app/core/celery.py`. There are no separate `REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` variables.

### Qdrant (Vector Database)

#### VECTOR_BACKEND

**Description**: Vector database backend

**Required**: No

**Default**: `qdrant`

**Example**:
```bash
VECTOR_BACKEND=qdrant
```

#### QDRANT_URL

**Description**: Complete Qdrant connection URL

**Required**: Yes

**Format**: `http://host:port`

**Example**:
```bash
QDRANT_URL=http://qdrant:6333
```

#### QDRANT_API_KEY

**Description**: Qdrant API key (if authentication enabled)

**Required**: No

**Default**: None

**Example**:
```bash
QDRANT_API_KEY=your-api-key-here
```

#### QDRANT_COLLECTION_PREFIX

**Description**: Qdrant collection name prefix

**Required**: No

**Default**: `kb_dim`

**Example**:
```bash
QDRANT_COLLECTION_PREFIX=kb_dim
```

#### QDRANT_DISTANCE

**Description**: Vector distance metric

**Required**: No

**Default**: `Cosine`

**Example**:
```bash
QDRANT_DISTANCE=Cosine
```

## Internal Service Configuration

### INTERNAL_API_TOKEN / INTERNAL_API_TOKEN_FILE

**Description**: Shared secret token that authenticates worker → API requests on the internal upload gateway (`/internal/uploads/...` in `backend/app/api/v1/endpoints/internal_uploads.py`). `INTERNAL_API_TOKEN_FILE` points at a file containing the token (used in Kubernetes); the file takes precedence when set.

**Required**: Yes for Compose (`docker-compose.yml` fails fast if unset) and Kubernetes

**Default**: *(empty)*

**Example**:
```bash
INTERNAL_API_TOKEN=generate-a-secure-random-token
# or
INTERNAL_API_TOKEN_FILE=/var/run/secrets/clouisle/internal-api-token
```

**Generate**:
```bash
openssl rand -hex 32
```

### API_INTERNAL_BASE_URL

**Description**: Internal base URL used by the worker process to reach the API for the upload gateway when `UPLOAD_STORAGE_MODE=remote`.

**Required**: No

**Default**: *(empty; Compose sets it to `http://api:8000`)*

**Example**:
```bash
API_INTERNAL_BASE_URL=http://api:8000
```

### UPLOAD_STORAGE_MODE

**Description**: How worker processes access uploaded files: `local` (api process only) or `remote` (worker reaches files through the authenticated API gateway).

**Required**: No

**Default**: `local`

**Values**: `local`, `remote`

**Example**:
```bash
UPLOAD_STORAGE_MODE=remote
```

In the supplied Compose/K8s deployments the `worker` and `sandbox-worker` services set `remote` — they have **no** uploads volume mount.

## Retrieval Configuration

### RETRIEVAL_HYBRID_KILL_SWITCH

**Description**: Emergency environment override that forces vector-only retrieval (disables the hybrid lexical/vector path). Lexical search uses pg_search in PostgreSQL; Qdrant remains the vector backend.

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
RETRIEVAL_HYBRID_KILL_SWITCH=false
```

### RETRIEVAL_SHADOW_ENABLED

**Description**: Run hybrid retrieval in shadow mode for rollout-excluded teams; stores IDs, ranks, versions, and latency only.

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
RETRIEVAL_SHADOW_ENABLED=false
```

### RAG_QUERY_CONTEXTUALIZATION_ENABLED

**Description**: Enable best-effort standalone query rewrite for conversational AUTO retrieval.

**Required**: No

**Default**: `false`

**Values**: `true`, `false`

**Example**:
```bash
RAG_QUERY_CONTEXTUALIZATION_ENABLED=false
```

### RAG_QUERY_CONTEXTUALIZATION_TIMEOUT_SECONDS

**Description**: Timeout (seconds) for the contextualization LLM call.

**Required**: No

**Default**: `2.0`

**Example**:
```bash
RAG_QUERY_CONTEXTUALIZATION_TIMEOUT_SECONDS=2.0
```

## Streaming Timeouts

Streaming behavior defaults (seconds), all configurable in `config.py`:

| Variable | Default | Description |
|---|---|---|
| `STREAM_GLOBAL_TIMEOUT` | `3600` | Global cap for a streaming response (60 minutes) |
| `STREAM_GLOBAL_TIMEOUT_WITH_TOOLS` | `5400` | Global cap when the agent has a tool runtime (90 minutes) |
| `STREAM_HEARTBEAT_INTERVAL` | `15` | Heartbeat interval sent to the client |
| `STREAM_IDLE_TIMEOUT` | `180` | Max seconds between model stream chunks |
| `STREAM_HTTP_CONNECT_TIMEOUT` | `10` | LLM HTTP client connect timeout |
| `STREAM_HTTP_READ_TIMEOUT` | `200` | LLM HTTP client read timeout |
| `STREAM_HTTP_REASONING_READ_TIMEOUT` | `300` | LLM HTTP read timeout for reasoning models |
| `STREAM_HTTP_WRITE_TIMEOUT` | `10` | LLM HTTP client write timeout |
| `STREAM_TOOL_TIMEOUT_HTTP` | `30` | Tool execution timeout for HTTP tools |
| `STREAM_TOOL_TIMEOUT_CODE` | `60` | Tool execution timeout for code tools |
| `STREAM_TOOL_TIMEOUT_MCP` | `60` | Tool execution timeout for MCP tools |
| `STREAM_TOOL_TIMEOUT_DOWNLOAD` | `60` | Tool execution timeout for downloads |

## Celery / Background Tasks

### CELERY_VISIBILITY_TIMEOUT_SECONDS

**Description**: Celery broker visibility timeout (how long an unacked task stays reserved).

**Required**: No

**Default**: `3600`

**Example**:
```bash
CELERY_VISIBILITY_TIMEOUT_SECONDS=3600
```

### KB_PROCESSING_RECOVERY_AFTER_SECONDS

**Description**: Delay before knowledge-base processing tasks that died mid-flight are recovered and requeued.

**Required**: No

**Default**: `600`

**Example**:
```bash
KB_PROCESSING_RECOVERY_AFTER_SECONDS=600
```

## External API Keys

### TAVILY_API_KEY

**Description**: Tavily web search API key (used by the built-in `web_search` tool). Only used as a fallback when no admin-managed search credentials exist.

**Required**: No

**Default**: None

**Example**:
```bash
TAVILY_API_KEY=tvly-xxxxxxxx
```

> **Note**: LLM provider keys (OpenAI-compatible, Anthropic, etc.) are **not** environment variables — they are configured per provider in database models and managed through the admin UI.

## Sandbox Runtime

| Variable | Generic Default | Deployment Default | Description |
|---|---|---|---|
| `SANDBOX_RUNTIME_ENABLED` | `true` | `true` | Route code, Bash, skill, and workflow execution through the sandbox runtime |
| `SANDBOX_LEGACY_FALLBACK_ENABLED` | `true` | `true` | Allow supported code paths to fall back to the legacy runner when the runtime is unavailable |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `false` | `true` for sandbox-worker | Launch executable payloads in a Bubblewrap mount namespace |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `bwrap` | `/usr/bin/bwrap` | Bubblewrap executable name or absolute path |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | `1` | Sandbox Celery worker concurrency |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | Same | Root directory for job and session workspaces |
| `SANDBOX_MAX_DISK_MB` | `8192` | Same | Maximum workspace disk limit accepted by policy |
| `SANDBOX_SESSION_TTL_HOURS` | `24` | Same | Session lifetime before cleanup |
| `SANDBOX_RESULT_TTL_SECONDS` | `86400` | Same | Redis result retention period |

The generic application default leaves filesystem isolation disabled so unsupported host development environments can still start. The supplied sandbox-worker Docker image, Docker Compose service, and Helm deployment enable it explicitly:

```bash
SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true
SANDBOX_FILESYSTEM_ISOLATION_BINARY=/usr/bin/bwrap
```

When enabled, Bubblewrap must be installed and usable. Rootless Bubblewrap needs namespace and mount syscalls, so the supplied Docker Compose and Helm configurations use an unconfined seccomp profile for this worker only. A cluster that prohibits `Unconfined` must provide an equivalent Localhost seccomp profile. The supplied deployments run the worker as root with `CAP_SYS_ADMIN` added to the runtime default cap set so it can create user/mount namespaces even on hosts that gate non-privileged user namespaces; privilege escalation stays disabled. Custom deployments that keep the worker non-root need the host kernel to permit unprivileged user namespaces — on restricted hosts (Ubuntu 23.10+ with `kernel.apparmor_restrict_unprivileged_userns=1`, Debian with `kernel.unprivileged_userns_clone=0`) every sandbox job fails with `bwrap: No permissions to create new namespace` (see [Code Sandbox → Host Kernel Requirements](../concepts/code-sandbox.md#host-kernel-requirements)).

### Sandbox Artifact Upload

| Variable | Default | Description |
|---|---|---|
| `SANDBOX_ARTIFACT_UPLOAD_BASE_URL` | *(empty)* | Internal API base URL used by sandbox workers to upload artifacts (Compose sets `http://api:8000`). Keep it internal, never `localhost` inside containers. |
| `SANDBOX_ARTIFACT_UPLOAD_API_KEY` | *(empty)* | Optional API-key authentication for sandbox artifact uploads |
| `SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB` | `10` | Maximum single artifact file size in MB |
| `SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB` | `10` | Maximum total artifact size per job in MB |
| `SANDBOX_SESSION_CLEANUP_BATCH_SIZE` | `100` | Sandbox session cleanup batch size |
| `SANDBOX_DEFAULT_PYTHON_BINARIES` | `/usr/local/bin/python3`, `/usr/bin/python3`, `/bin/python3` | Candidate Python interpreters for sandbox execution (JSON list) |

## Frontend Build & Runtime Variables (Not Backend Settings)

These variables configure the separate Next.js frontend image, not the backend Pydantic `Settings` class. The frontend image is built with `bun run build`; the first three values are baked in as build-time ARGs (see `deploy/dockerfiles/frontend.Dockerfile`):

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `/api/v1` | Browser-visible API base path used by the Next.js client |
| `NEXT_PUBLIC_APP_VERSION` | `0.0.0-dev` | Version string shown in the UI |
| `NEXT_PUBLIC_BUILD_DATE` | `unknown` | Build date string shown in the UI |

Runtime environment variables for the frontend container:

| Variable | Default | Description |
|---|---|---|
| `BACKEND_INTERNAL_URL` | `http://localhost:8000` | Backend URL the Next.js server uses for SSR and its `/api/*` rewrites (Compose sets `http://api:8000`) |
| `DEV_ALLOWED_ORIGINS` | *(empty)* | Comma-separated extra origins allowed for dev-server LAN access (`allowedDevOrigins`); production builds ignore it |

## Best Practices

### Security

**✅ Do:**
- Use strong, random secrets
- Never commit secrets to git
- Use different secrets per environment
- Rotate secrets regularly
- Use environment-specific values
- Encrypt secrets at rest

**❌ Don't:**
- Use default or weak secrets
- Commit .env to version control
- Share secrets via email/chat
- Use same secrets everywhere
- Hardcode secrets in code

### Organization

**✅ Do:**
- Group related variables
- Use clear, descriptive names
- Document custom variables
- Use .env.example template
- Validate required variables

**❌ Don't:**
- Mix unrelated variables
- Use cryptic names
- Skip documentation
- Forget to update template

### Management

**✅ Do:**
- Use secret management tools
- Backup .env files securely
- Test configuration changes
- Document dependencies
- Version control .env.example

**❌ Don't:**
- Store secrets in plain text
- Forget to backup
- Change without testing
- Skip documentation

## Validation

There is no `app.scripts.check_config` command — `backend/app/scripts/` does not exist. Configuration is validated when the backend starts:

- Pydantic `Settings` fails fast on type errors (e.g. an invalid `BACKEND_CORS_ORIGINS` JSON).
- `docker compose up` fails fast when required values are missing (e.g. `INTERNAL_API_TOKEN`, `POSTGRES_PASSWORD` in the supplied Compose file).
- Runtime config (SMTP, SSO, upload limits, session timeout) is stored in and validated through the database `SiteSetting` model.

### Common Issues

**Missing required variables:**
```
Error: INTERNAL_API_TOKEN is required
```
**Solution**: Generate a token (`openssl rand -hex 32`) and set it in `.env` (or as a Kubernetes Secret).

**Invalid format:**
```
Error: POSTGRES_PORT must be an integer
```
**Solution**: Check variable format

**Connection failed:**
```
Error: Cannot connect to database
```
**Solution**: Verify host, port, credentials; in Compose these are the service names `db`, `redis`, `qdrant`.

## Related Documentation

- [Docker Deployment](./docker-compose.md) - Docker setup
- [Kubernetes Deployment](./kubernetes.md) - K8s setup
- [Deployment Guide](./DEPLOYMENT.md) - Full deployment guide
- [Troubleshooting](./troubleshooting.md) - Common issues

---

**Last Updated**: 2026-08-14
