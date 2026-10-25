"""
Tests for multi-engine web search (auto, bocha, bing, tavily).
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
@pytest.mark.parametrize(
    ("engine", "credentials"),
    [
        ("auto", {}),
        ("bing", {}),
        ("auto", {"TAVILY_API_KEY": "bad-key"}),
        ("auto", {"BOCHA_API_KEY": "bad-key"}),
    ],
)
async def test_keyless_and_auto_fallback_search_return_cited_bing_hits(
    monkeypatch, engine, credentials
):
    import httpx

    client_class = httpx.AsyncClient
    rss = """<rss><channel><item><title>Asyncio</title>
    <link>https://docs.python.org/3/library/asyncio.html</link>
    <description>Asynchronous I/O</description></item></channel></rss>"""

    def respond(request):
        if request.url.host == "www.bing.com":
            return httpx.Response(200, text=rss)
        return httpx.Response(503)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )

    result = await subject.web_search(
        "python asyncio", search_engine=engine, credentials=credentials
    )
    assert result["success"] is True
    assert result["search_engine"] == "bing"
    assert result["results"] == [
        {
            "title": "Asyncio",
            "url": "https://docs.python.org/3/library/asyncio.html",
            "content": "Asynchronous I/O",
            "citation_id": stable_citation_id(
                "web", "https://docs.python.org/3/library/asyncio.html", ""
            ),
        }
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["tavily", "bocha"])
async def test_explicit_keyed_provider_failure_does_not_switch_engines(
    monkeypatch, engine
):
    import httpx

    client_class = httpx.AsyncClient

    def respond(request):
        assert request.url.host != "www.bing.com"
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
    assert result["search_engine"] == engine
    assert result["results"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", "http", "challenge", "empty"])
async def test_bing_failures_are_not_reported_as_empty_success(monkeypatch, failure):
    import httpx

    client_class = httpx.AsyncClient

    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if failure == "http":
            return httpx.Response(429)
        return httpx.Response(
            200,
            text=(
                "<html><body>challenge</body></html>"
                if failure == "challenge"
                else "<rss><channel/></rss>"
            ),
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )
    result = await subject.web_search("python", search_engine="bing")
    assert result["success"] is False
    assert result["search_engine"] == "bing"
    assert result["results"] == []
    assert result["error"]


def test_bing_result_limit_counts_only_usable_links():
    rss = """<rss><channel>
    <item><title>Bad</title><link>javascript:alert(1)</link></item>
    <item><title>A</title><link>https://a.test/</link></item>
    <item><title>B</title><link>https://b.test/</link></item>
    </channel></rss>"""
    assert subject._parse_bing_rss(rss, 1) == [
        {"title": "A", "url": "https://a.test/", "content": ""}
    ]


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
async def test_bing_search_uses_rss_and_normalizes_results(monkeypatch):
    sample_rss = """
    <rss><channel>
      <item>
        <title>Bing Title</title>
        <link>https://example.com/bing</link>
        <description>&lt;p&gt;Bing &lt;b&gt;Body&lt;/b&gt; snippet&lt;/p&gt;</description>
      </item>
      <item>
        <title>Invalid</title>
        <link>javascript:alert(1)</link>
        <description>skip</description>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        status_code = 200
        text = sample_rss

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None):
            assert url == "https://www.bing.com/search"
            assert params["format"] == "rss"
            assert params["mkt"] == "zh-CN"
            return FakeResponse()

    monkeypatch.setattr(subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await subject._bing_search("上海 天气", 2)
    assert result["success"] is True
    assert len(result["results"]) == 1
    assert result["results"][0] == {
        "title": "Bing Title",
        "url": "https://example.com/bing",
        "content": "Bing Body snippet",
        "citation_id": stable_citation_id("web", "https://example.com/bing", ""),
    }


@pytest.mark.anyio
async def test_bing_search_uses_english_market_for_latin_queries(monkeypatch):
    captured = {}

    class FakeResponse:
        text = "<rss><channel></channel></rss>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None):
            captured.update(params)
            return FakeResponse()

    monkeypatch.setattr(subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)

    result = await subject._bing_search("python asyncio", 5)
    assert captured["mkt"] == "en-US"
    assert result == {
        "query": "python asyncio",
        "error": "web_search_blocked_or_empty",
        "success": False,
        "results": [],
    }


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
