import json
from typing import Any

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Clouisle"
    API_V1_STR: str = "/api/v1"

    # Server URL (used for internal file access)
    API_BASE_URL: str = "http://localhost:8000"

    # Frontend URL (used for SSO redirects)
    FRONTEND_URL: str = "http://localhost:3000"

    # Timezone
    TIMEZONE: str = "Asia/Shanghai"

    # Security
    SECRET_KEY: str = "changethis-to-a-secure-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "clouisle"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = ""

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None

    # Celery
    CELERY_VISIBILITY_TIMEOUT_SECONDS: int = 3600
    KB_PROCESSING_RECOVERY_AFTER_SECONDS: int = 600

    # Vector DB (Qdrant)
    VECTOR_BACKEND: str = "qdrant"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_PREFIX: str = "kb_dim"
    QDRANT_DISTANCE: str = "Cosine"

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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str, info: ValidationInfo) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        return f"postgres://{data.get('POSTGRES_USER')}:{data.get('POSTGRES_PASSWORD')}@{data.get('POSTGRES_SERVER')}:{data.get('POSTGRES_PORT')}/{data.get('POSTGRES_DB')}"

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

    # Upload storage
    UPLOAD_STORAGE_BACKEND: str = "local"
    OBJECT_STORAGE_ENDPOINT: str | None = None
    OBJECT_STORAGE_BUCKET: str | None = None
    OBJECT_STORAGE_REGION: str | None = None
    OBJECT_STORAGE_ACCESS_KEY: str | None = None
    OBJECT_STORAGE_SECRET_KEY: str | None = None
    OBJECT_STORAGE_FORCE_PATH_STYLE: bool = True
    OBJECT_STORAGE_SECURE: bool = True

    # Sandbox runtime flags
    SANDBOX_RUNTIME_ENABLED: bool = True
    SANDBOX_LEGACY_FALLBACK_ENABLED: bool = True
    SANDBOX_WORKSPACE_ROOT: str = "/tmp/clouisle-sandbox/jobs"
    SANDBOX_MAX_DISK_MB: int = 8192
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

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(".env", "../.env"),
        extra="ignore",
    )


settings = Settings()
