from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentCreate, AgentUpdate, ToolConfig
from app.services.clouisle_package_resources import _agent_fields


@pytest.mark.parametrize(
    "field",
    ["api_key", "TAVILY_API_KEY", "BOCHA_API_KEY", "DEEPSEEK_API_KEY", "base_url"],
)
def test_search_tool_cannot_store_credentials_or_endpoints(field):
    with pytest.raises(ValidationError):
        ToolConfig(
            type="builtin",
            name="web_search",
            config={"engine": "tavily", field: "private-value"},
        )


@pytest.mark.parametrize("schema", [AgentCreate, AgentUpdate])
@pytest.mark.parametrize(
    "key",
    ["TAVILY_API_KEY", "BOCHA_API_KEY", "SEARXNG_AUTH_TOKEN", "DEEPSEEK_API_KEY"],
)
def test_agent_credentials_cannot_override_site_search(schema, key):
    values = {"tools_credentials": {key: "private-value"}}
    if schema is AgentCreate:
        values.update(name="Search", team_id=uuid4())
    with pytest.raises(ValidationError):
        schema(**values)


def test_imported_agent_keeps_deepseek_without_importing_credentials():
    result = _agent_fields(
        {
            "tools_config": [
                {
                    "type": "builtin",
                    "name": "web_search",
                    "config": {"engine": "deepseek", "api_key": "sk-private"},
                }
            ]
        },
        {},
    )
    assert result["tools_config"] == [
        {"type": "builtin", "name": "web_search", "config": {"engine": "deepseek"}}
    ]
    assert result["tools_credentials"] == {}


def test_imported_agent_keeps_provider_without_importing_credentials():
    result = _agent_fields(
        {
            "tools_config": [
                {
                    "type": "builtin",
                    "name": "web_search",
                    "config": {
                        "engine": "bocha",
                        "api_key": "private-value",
                        "base_url": "http://internal",
                    },
                }
            ]
        },
        {},
    )
    assert result["tools_config"] == [
        {"type": "builtin", "name": "web_search", "config": {"engine": "bocha"}}
    ]
    assert result["tools_credentials"] == {}


@pytest.mark.parametrize("engine", [[], {}, 1, None])
def test_search_tool_rejects_non_string_engine_values(engine):
    with pytest.raises(ValidationError, match="Unsupported search engine"):
        ToolConfig(type="builtin", name="web_search", config={"engine": engine})
