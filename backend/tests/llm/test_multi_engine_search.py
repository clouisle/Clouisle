"""
Tests for credentialed web search (auto, bocha, tavily).
"""

from unittest.mock import AsyncMock, Mock
import pytest

from app.llm.tools.builtin import web_search as subject
from app.services.citations import stable_citation_id


@pytest.mark.anyio
async def test_web_search_auto_routes_to_tavily_when_tavily_key_present(monkeypatch):
    tavily_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "Tavily result"}]}
    )
    monkeypatch.setattr(subject, "_tavily_search", tavily_mock)

    res = await subject.web_search(
        "test query", credentials={"TAVILY_API_KEY": "tvly-123"}
    )
    assert res["success"] is True
    tavily_mock.assert_awaited_once_with(
        "test query", 5, {"TAVILY_API_KEY": "tvly-123"}
    )


@pytest.mark.anyio
async def test_web_search_auto_routes_to_bocha_when_bocha_key_present(monkeypatch):
    bocha_mock = AsyncMock(
        return_value={"success": True, "results": [{"title": "Bocha result"}]}
    )
    monkeypatch.setattr(subject, "_bocha_search", bocha_mock)

    res = await subject.web_search(
        "test query", credentials={"BOCHA_API_KEY": "sk-bocha-123"}
    )
    assert res["success"] is True
    bocha_mock.assert_awaited_once_with(
        "test query", 5, {"BOCHA_API_KEY": "sk-bocha-123"}
    )


@pytest.mark.anyio
@pytest.mark.parametrize("credentials", [None, {}, {"OTHER_KEY": "unused"}])
async def test_auto_without_search_credentials_fails_before_network(
    monkeypatch, credentials
):
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        Mock(side_effect=AssertionError("no network without credentials")),
    )
    result = await subject.web_search("上海天气 今天", credentials=credentials)
    assert result["success"] is False
    assert result["results"] == []
    assert result["error"] == subject.t("web_search_api_key_not_configured")


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["bing", "duckduckgo", "ddg"])
async def test_retired_engines_are_rejected_without_network(monkeypatch, engine):
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        Mock(side_effect=AssertionError("retired engines must not call network")),
    )
    result = await subject.web_search("上海天气 今天", search_engine=engine)
    assert result["success"] is False
    assert result["results"] == []
    assert result["error"] == subject.t(
        "web_search_unsupported_engine", search_engine=engine
    )


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["auto", "tavily", "bocha"])
async def test_explicit_keyed_provider_failure_does_not_switch_engines(
    monkeypatch, engine
):
    import httpx

    client_class = httpx.AsyncClient

    def respond(request):
        assert request.url.host == (
            "api.bochaai.com" if engine == "bocha" else "api.tavily.com"
        )
        return httpx.Response(503)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )
    result = await subject.web_search(
        "python",
        search_engine=engine,
        credentials={"TAVILY_API_KEY": "key", "BOCHA_API_KEY": "key"},
    )
    assert result["success"] is False
    assert result["search_engine"] == ("tavily" if engine == "auto" else engine)
    assert result["results"] == []


@pytest.mark.anyio
async def test_bocha_search_posts_and_normalizes_results(monkeypatch):
    bocha_response_data = {
        "code": 200,
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "Bocha Article",
                        "url": "https://example.com/bocha",
                        "snippet": "This is snippet from Bocha",
                    }
                ]
            }
        },
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return bocha_response_data

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            assert "Bearer sk-bocha" in headers.get("Authorization", "")
            assert json.get("query") == "ai tech"
            return FakeResponse()

    monkeypatch.setattr(subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await subject._bocha_search("ai tech", 3, {"BOCHA_API_KEY": "sk-bocha"})
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Bocha Article"
    assert result["results"][0]["url"] == "https://example.com/bocha"
    assert result["results"][0]["citation_id"] == stable_citation_id(
        "web", "https://example.com/bocha", ""
    )


@pytest.mark.anyio
async def test_get_builtin_tool_credentials_prioritizes_agent_tool_config(monkeypatch):
    from app.api.v1.endpoints.chat_tools import _get_builtin_tool_credentials

    agent_mock = Mock()
    agent_mock.team_id = "team-123"

    fake_tool_config = Mock()
    fake_tool_config.filter.return_value.first = AsyncMock(return_value=None)
    monkeypatch.setattr("app.models.tool_config.ToolConfig", fake_tool_config)

    # 1. Agent 工具配置了专用 bocha key
    creds = await _get_builtin_tool_credentials(
        "web_search",
        agent_mock,
        agent_tool_config={"engine": "bocha", "api_key": "sk-agent-bocha"},
    )
    assert creds.get("BOCHA_API_KEY") == "sk-agent-bocha"

    # 2. Agent 工具配置了专用 tavily key
    creds_tavily = await _get_builtin_tool_credentials(
        "web_search",
        agent_mock,
        agent_tool_config={"engine": "tavily", "api_key": "tvly-agent-tavily"},
    )
    assert creds_tavily.get("TAVILY_API_KEY") == "tvly-agent-tavily"
