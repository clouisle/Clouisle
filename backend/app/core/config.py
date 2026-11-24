import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    # Internal service URL; public links use the site setting.
    API_BASE_URL: str = "http://localhost:8000"

    # Seeds the public site_url setting; not used at runtime.
    FRONTEND_URL: str = "http://localhost:3000"

    # Timezone
    TIMEZONE: str = "Asia/Shanghai"

    # Security
    SECRET_KEY: str = "changethis-to-a-secure-random-secret-key"
    ALGORITHM: str = "HS256"

    # Tool-domain envelope encryption keyring (connections, approvals, OAuth,
    # interactions). Comma-separated ``key_id:fernet_key`` entries; Fernet keys
    # are urlsafe-base64 32-byte values. When unset, a derived legacy key id
    # ``secret_key`` keeps upgrades decryptable until rotated.
    TOOL_SECRET_KEYS: str = ""
    TOOL_SECRET_PRIMARY_KEY_ID: str = ""

    # Database. ``DATABASE_URL`` takes precedence over the ``POSTGRES_*``
    # parts; leave it unset to let ``resolve_database_url`` assemble it.
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "clouisle"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = ""
    # Upper bound on aggregation queries one request may hold open at once.
    # Endpoints that fan several independent aggregates out with asyncio.gather
    # must not be able to occupy every slot of the shared Tortoise pool (default
    # maxsize 5) in a single request, which would queue that request's
    # remaining queries behind its own fan-out. Raising the pool size instead is
    # not an option: PostgreSQL max_connections is 100 and the default
    # deployment runs ~17 processes x pool, so the ceiling is approached.
    #
    # gt=0 is load-bearing: a semaphore built with 0 permits deadlocks every
    # aggregate request, and a negative one raises ValueError at import time.
    DB_AGGREGATE_CONCURRENCY: int = Field(default=4, gt=0)

    # API container/Pod identity shared by its Gunicorn processes.
    # Defaults to hostname; override when multiple deployments share a hostname.
    OBSERVABILITY_INSTANCE_ID: str = ""
    OBSERVABILITY_INSTANCE_NAME: str = ""

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None

    # Celery
    CELERY_VISIBILITY_TIMEOUT_SECONDS: int = 3600
    KB_PROCESSING_RECOVERY_AFTER_SECONDS: int = 600
    WECHAT_POLL_BATCH_SIZE: int = Field(default=64, ge=1, le=512)
    WECHAT_POLL_CONCURRENCY: int = Field(default=16, ge=1, le=128)
    WECHAT_POLL_MAX_BATCHES: int = Field(default=8, ge=1, le=128)

    # Vector DB (Qdrant is the only supported backend)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_PREFIX: str = "kb_dim"
    QDRANT_DISTANCE: str = "Cosine"

    # Lexical search
    RETRIEVAL_HYBRID_KILL_SWITCH: bool = False
    RETRIEVAL_SHADOW_ENABLED: bool = False
    RAG_QUERY_CONTEXTUALIZATION_ENABLED: bool = False
    RAG_QUERY_CONTEXTUALIZATION_TIMEOUT_SECONDS: float = 2.0

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",  # Next.js dev server
    ]

    # External API Keys
    TAVILY_API_KEY: str | None = None  # Tavily search API key

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            if v.startswith("["):
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        raise ValueError(v)

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """Resolve the one connection string the whole backend runs against.

        An explicit ``DATABASE_URL`` wins so operators can point the app at a
        managed database; otherwise the URL is assembled from the
        ``POSTGRES_*`` parts. Runtime entry points (API lifespan, Celery
        worker init, migrations, secret rotation) read this resolved value
        instead of re-deriving it.
        """
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgres://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self

    # Streaming timeouts (seconds)
    STREAM_GLOBAL_TIMEOUT: int = 3600  # 60 minutes
    STREAM_HEARTBEAT_INTERVAL: int = 15  # 15 seconds
    STREAM_IDLE_TIMEOUT: int = 180  # max seconds between model stream chunks

    # LLM HTTP client timeouts (seconds)
    STREAM_HTTP_CONNECT_TIMEOUT: int = 10
    STREAM_HTTP_READ_TIMEOUT: int = 200
    STREAM_HTTP_REASONING_READ_TIMEOUT: int = 300
    STREAM_HTTP_WRITE_TIMEOUT: int = 10
    STREAM_GLOBAL_TIMEOUT_WITH_TOOLS: int = 5400  # 90 minutes

    # Tool execution timeouts (seconds)
    STREAM_TOOL_TIMEOUT_HTTP: int = 30
    STREAM_TOOL_TIMEOUT_CODE: int = 60
    STREAM_TOOL_TIMEOUT_MCP: int = 60
    STREAM_TOOL_TIMEOUT_DOWNLOAD: int = 60

    # Server-initiated MCP interactions (sampling approval, elicitation form
    # or URL). This is the hard answer deadline and the upper bound for a
    # live session's callback wait; the agent/workflow worker waits on the
    # durable row, never on an unbounded browser connection.
    MCP_INTERACTION_TTL_SECONDS: int = Field(default=300, ge=10, le=900)
    # Live MCP resource subscriptions are request-scoped; this bounds how long
    # one SSE request may hold the session before sending ttl_expired.
    MCP_SUBSCRIPTION_TTL_SECONDS: int = Field(default=300, ge=10, le=3600)

    # Sandbox runtime
    SANDBOX_WORKSPACE_ROOT: str = "/tmp/clouisle-sandbox/jobs"
    SANDBOX_WORKER_ID: str = ""
    SANDBOX_NODE_ID: str = ""
    SANDBOX_WORKER_INSTANCE_ID: str = ""
    SANDBOX_WORKER_HEARTBEAT_SECONDS: float = Field(
        default=5, gt=0, allow_inf_nan=False
    )
    SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS: int = Field(default=20, gt=0)
    SANDBOX_WORKER_RECOVERY_SECONDS: float = Field(
        default=30, gt=0, allow_inf_nan=False
    )
    SANDBOX_RECOVERY_POLL_SECONDS: float = Field(default=0.5, gt=0, allow_inf_nan=False)
    SANDBOX_SESSION_MAX_RESETS: int = Field(default=1, ge=0)
    SANDBOX_SUPERVISOR_RESTART_SECONDS: float = Field(
        default=1, ge=0, allow_inf_nan=False
    )
    SANDBOX_SUPERVISOR_MAX_RESTARTS: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def validate_sandbox_heartbeat(self) -> "Settings":
        if (
            self.SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS
            <= self.SANDBOX_WORKER_HEARTBEAT_SECONDS
        ):
            raise ValueError("Sandbox heartbeat TTL must exceed its refresh interval")
        return self

    SANDBOX_CHECKPOINT_ROOT: str = ""
    SANDBOX_WORKSPACE_IDLE_SECONDS: int = Field(default=900, gt=0)
    SANDBOX_CHECKPOINT_TIMEOUT_SECONDS: int = Field(default=120, gt=0)
    SANDBOX_FILESYSTEM_ISOLATION_ENABLED: bool = True
    SANDBOX_FILESYSTEM_ISOLATION_BINARY: str = "bwrap"
    SANDBOX_MAX_DISK_MB: int = 8192
    SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS: int = Field(default=300, gt=0, le=3600)
    SANDBOX_TASK_MEMORY_MB: int = Field(default=1024, gt=0, le=8192)
    SANDBOX_TASK_MAX_FILE_SIZE_MB: int = Field(default=1024, gt=0, le=8192)
    SANDBOX_TASK_MAX_OPEN_FILES: int = Field(default=256, ge=32, le=4096)
    SANDBOX_TASK_MAX_CPU_SECONDS: int = Field(default=600, gt=0, le=3600)
    SANDBOX_SESSION_TTL_HOURS: int = 24
    SANDBOX_SESSION_CLEANUP_BATCH_SIZE: int = 100
    SANDBOX_RESULT_TTL_SECONDS: int = 86400
    SANDBOX_DEFAULT_PYTHON_BINARIES: list[str] = [
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        "/bin/python3",
    ]
    SANDBOX_ARTIFACT_UPLOAD_BASE_URL: str | None = None
    SANDBOX_ARTIFACT_UPLOAD_API_KEY: str | None = None
    SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB: float = 10.0
    SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB: float = 10.0
    # Skill packages are pushed into a session workspace through the job API,
    # never read from shared storage by the worker node. Sessions carry the
    # payload bound so a single job cannot exceed the broker message size.
    # The bound is measured on the encoded payload, while import caps the raw
    # package (``_MAX_PACKAGE_PAYLOAD_BYTES`` = 50 MiB); base64 inflates by 4/3,
    # so the default must stay above ~67 MiB or a package that imports fine can
    # never be delivered.
    SKILL_SYNC_MAX_TOTAL_BYTES: int = Field(
        default=72 * 1024 * 1024, gt=0, le=256 * 1024 * 1024
    )
    SKILL_SYNC_TIMEOUT_SECONDS: float = Field(default=120.0, ge=1.0, le=600)

    # IM attachment reclamation: uploads that never became a message.
    IM_ORPHAN_ASSET_TTL_HOURS: int = Field(default=24, gt=0)
    IM_ORPHAN_ASSET_CLEANUP_BATCH_SIZE: int = Field(default=200, ge=1, le=1000)

    # Internal upload gateway (worker -> api file access)
    # UPLOAD_STORAGE_MODE: "local" (api process) | "remote" (worker process)
    UPLOAD_STORAGE_MODE: str = "local"
    API_INTERNAL_BASE_URL: str = ""
    INTERNAL_API_TOKEN: str = ""
    INTERNAL_API_TOKEN_FILE: str = ""

    def get_internal_api_token(self) -> str:
        if self.INTERNAL_API_TOKEN_FILE:
            try:
                token = (
                    Path(self.INTERNAL_API_TOKEN_FILE)
                    .read_text(encoding="utf-8")
                    .strip()
                )
                if token:
                    return token
            except OSError:
                pass
        return self.INTERNAL_API_TOKEN

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(".env", "../.env"),
        extra="ignore",
    )


settings = Settings()
