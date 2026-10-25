"""Site-managed web search configuration schemas.

The site owns one web search configuration. Agents and teams can only choose
among the providers and credentials the site administrator configured.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WebSearchEngine = Literal["tavily", "bocha", "searxng", "deepseek"]

# Ordered provider catalog shared by configuration and runtime validation.
WEB_SEARCH_ENGINES: tuple[WebSearchEngine, ...] = (
    "tavily",
    "bocha",
    "searxng",
    "deepseek",
)

# Provider API keys are opaque; bound them so oversized input cannot reach
# storage or the provider request bodies.
SECRET_MAX_LENGTH = 1024
BASE_URL_MAX_LENGTH = 2048


class WebSearchConfigUpdate(BaseModel):
    """Update the site web search configuration.

    Secret fields follow the partial-update contract: omitted or ``null``
    preserves the stored secret, an empty string clears it, and any non-empty
    value replaces it. Raw secrets are never returned to clients.
    """

    model_config = ConfigDict(extra="forbid")

    default_engine: WebSearchEngine
    tavily_enabled: bool
    bocha_enabled: bool
    searxng_enabled: bool
    deepseek_enabled: bool
    tavily_api_key: str | None = Field(default=None, max_length=SECRET_MAX_LENGTH)
    bocha_api_key: str | None = Field(default=None, max_length=SECRET_MAX_LENGTH)
    deepseek_api_key: str | None = Field(default=None, max_length=SECRET_MAX_LENGTH)
    searxng_base_url: str | None = Field(default=None, max_length=BASE_URL_MAX_LENGTH)
    searxng_auth_token: str | None = Field(default=None, max_length=SECRET_MAX_LENGTH)

    @field_validator(
        "tavily_api_key",
        "bocha_api_key",
        "deepseek_api_key",
        "searxng_auth_token",
    )
    @classmethod
    def _normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # API keys never contain meaningful surrounding whitespace; trimming
        # also turns a whitespace-only value into an explicit clear.
        return value.strip()

    @field_validator("searxng_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class WebSearchConfigOut(BaseModel):
    """Public site web search configuration; secrets are only reported as flags."""

    default_engine: str
    tavily_enabled: bool
    bocha_enabled: bool
    searxng_enabled: bool
    deepseek_enabled: bool
    tavily_api_key_configured: bool
    bocha_api_key_configured: bool
    deepseek_api_key_configured: bool
    searxng_base_url: str
    searxng_auth_token_configured: bool
    legacy_credentials_present: bool


class WebSearchTestInput(BaseModel):
    """Administrator connectivity check against the saved site configuration."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    engine: Literal["auto", "tavily", "bocha", "searxng", "deepseek"] = "auto"

    @field_validator("query")
    @classmethod
    def _require_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized
