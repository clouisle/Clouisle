"""Site-managed web search dispatch, isolated from caller-supplied credentials."""

import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.tools.builtin import web_search as subject
from app.llm.tools.registry import ToolRegistry
from app.schemas.response import BusinessError


def install_runtime(monkeypatch, engine="tavily", config=None, error=None):
    config = config if config is not None else {"TAVILY_API_KEY": "site-key"}
    if error is not None:
        runtime = AsyncMock(side_effect=error)
    else:
        runtime = AsyncMock(return_value=(engine, config))
    monkeypatch.setattr(subject, "get_web_search_runtime", runtime)
    return runtime


def install_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def respond(request):
        requests.append(request)
        return handler(request)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        subject.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    return requests


@pytest.mark.anyio
async def test_registry_rejects_an_injected_credentials_argument(monkeypatch):
    runtime = install_runtime(monkeypatch)
    registry = ToolRegistry()
    registry.register(name="web_search", description="search")(subject.web_search)

    with pytest.raises(TypeError):
        await registry.execute(
            "web_search",
            {"query": "q", "credentials": {"TAVILY_API_KEY": "attacker"}},
        )

    runtime.assert_not_awaited()


@pytest.mark.anyio
async def test_site_failure_returns_a_localized_failure_payload(monkeypatch):
    install_runtime(
        monkeypatch,
        error=BusinessError(msg_key="web_search_engine_disabled", engine="tavily"),
    )
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))
    factory = Mock(side_effect=AssertionError("runtime failure must not search"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", factory)

    result = await subject.web_search("cloud")

    assert result == {
        "query": "cloud",
        "error": ("web_search_engine_disabled", {"engine": "tavily"}),
        "success": False,
        "results": [],
    }
    factory.assert_not_called()


@pytest.mark.anyio
async def test_unresolvable_runtime_provider_is_rejected(monkeypatch):
    install_runtime(monkeypatch, engine="google", config={})
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject.web_search("cloud")

    assert result["success"] is False
    assert result["error"] == (
        "web_search_unsupported_engine",
        {"search_engine": "google"},
    )


@pytest.mark.anyio
async def test_tavily_request_uses_only_the_site_key(monkeypatch):
    install_runtime(
        monkeypatch, engine="tavily", config={"TAVILY_API_KEY": "site-tavily"}
    )

    def handler(request):
        return httpx.Response(
            200,
            json={
                "answer": "answer",
                "results": [
                    {
                        "title": "Tavily Article",
                        "url": "https://example.test/tavily",
                        "content": "Snippet",
                        "score": 0.8,
                    }
                ],
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject.web_search("cloud", num_results=99)

    assert len(requests) == 1
    assert requests[0].url == "https://api.tavily.com/search"
    body = json.loads(requests[0].content)
    assert body["api_key"] == "site-tavily"
    assert body["max_results"] == 10
    assert result["success"] is True
    assert result["search_engine"] == "tavily"
    assert result["results"][0]["url"] == "https://example.test/tavily"
    assert result["results"][0]["citation_id"].startswith("web_")


@pytest.mark.anyio
async def test_bocha_request_uses_only_the_site_key(monkeypatch):
    install_runtime(monkeypatch, engine="bocha", config={"BOCHA_API_KEY": "site-bocha"})

    def handler(request):
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Bocha Article",
                                "url": "https://example.test/bocha",
                                "snippet": "Snippet",
                            }
                        ]
                    }
                },
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject.web_search("上海天气", num_results=3, search_engine="bocha")

    assert len(requests) == 1
    assert requests[0].url == "https://api.bochaai.com/v1/web-search"
    assert requests[0].headers["authorization"] == "Bearer site-bocha"
    body = json.loads(requests[0].content)
    assert body["query"] == "上海天气"
    assert body["count"] == 3
    assert result["success"] is True
    assert result["search_engine"] == "bocha"
    assert result["results"][0]["title"] == "Bocha Article"


@pytest.mark.anyio
async def test_deepseek_request_uses_only_the_site_key(monkeypatch):
    install_runtime(
        monkeypatch, engine="deepseek", config={"DEEPSEEK_API_KEY": "site-deepseek"}
    )

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "rerank_score": 2.4,
                        "title": "DeepSeek Article",
                        "url": "https://example.test/deepseek",
                        "snippet": "Short snippet",
                        "summary": "Model-facing long summary",
                        "content": "",
                    },
                    {
                        "title": "Snippet only",
                        "url": "https://example.test/deepseek-2",
                        "snippet": "Fallback snippet",
                    },
                ]
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject.web_search(
        "DeepSeek 发布", num_results=2, search_engine="deepseek"
    )

    assert len(requests) == 1
    assert requests[0].url == "https://api.deepseek.com/v1/tools/search"
    assert requests[0].headers["authorization"] == "Bearer site-deepseek"
    body = json.loads(requests[0].content)
    assert body == {
        "query": "DeepSeek 发布",
        "count": 2,
        "need_content": False,
    }
    assert result["success"] is True
    assert result["search_engine"] == "deepseek"
    assert result["results"][0]["content"] == "Model-facing long summary"
    assert result["results"][0]["score"] == 2.4
    assert result["results"][1]["content"] == "Fallback snippet"
    assert result["results"][0]["citation_id"].startswith("web_")


@pytest.mark.anyio
async def test_deepseek_malformed_response_is_explicit(monkeypatch):
    install_runtime(
        monkeypatch, engine="deepseek", config={"DEEPSEEK_API_KEY": "site-deepseek"}
    )

    requests = install_transport(
        monkeypatch, lambda request: httpx.Response(200, json={"results": "no"})
    )

    result = await subject.web_search("cloud", search_engine="deepseek")

    assert len(requests) == 1
    assert result["success"] is False
    assert result["results"] == []


@pytest.mark.anyio
async def test_deepseek_billing_failure_is_explicit(monkeypatch):
    install_runtime(
        monkeypatch, engine="deepseek", config={"DEEPSEEK_API_KEY": "site-deepseek"}
    )
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))
    requests = install_transport(monkeypatch, lambda request: httpx.Response(402))

    result = await subject.web_search("cloud", search_engine="deepseek")

    assert len(requests) == 1
    assert result["success"] is False
    assert result["error"] == ("web_search_api_error", {"status_code": 402})


@pytest.mark.anyio
async def test_provider_failure_does_not_fall_back_to_another_provider(monkeypatch):
    install_runtime(
        monkeypatch, engine="tavily", config={"TAVILY_API_KEY": "site-tavily"}
    )

    def handler(request):
        return httpx.Response(503)

    requests = install_transport(monkeypatch, handler)

    result = await subject.web_search("cloud", search_engine="auto")

    assert [str(request.url) for request in requests] == [
        "https://api.tavily.com/search"
    ]
    assert result["success"] is False
    assert result["search_engine"] == "tavily"
    assert result["results"] == []
