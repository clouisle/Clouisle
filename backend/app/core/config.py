from typing import Any, List, Union

from pydantic import validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Clouisle"
    API_V1_STR: str = "/api/v1"
    
    # Server URL (used for internal file access)
    API_BASE_URL: str = "http://localhost:8000"

    # Timezone
    TIMEZONE: str = "Asia/Shanghai"

    # Security
    SECRET_KEY: str = "changethis-to-a-secure-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

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

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Next.js dev server
    ]

    # External API Keys
    TAVILY_API_KEY: str | None = None  # Tavily search API key

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return list(v) if isinstance(v, list) else [v]
        raise ValueError(v)

    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: str, values: dict[str, Any]) -> str:
        if isinstance(v, str) and v:
            return v
        return f"postgres://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings()
