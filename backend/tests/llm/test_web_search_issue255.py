import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from app.llm.tools.builtin import web_search as subject


class FakeClient:
    def __init__(self, *, post=None, get=None):
        self.post = AsyncMock(side_effect=post if isinstance(post, Exception) else None)
        self.get = AsyncMock(side_effect=get if isinstance(get, Exception) else None)
        if post is not None and not isinstance(post, Exception):
            self.post.return_value = post
        if get is not None and not isinstance(get, Exception):
            self.get.return_value = get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def install_client(monkeypatch, client):
    factory = Mock(return_value=client)
    monkeypatch.setattr(subject.httpx, "AsyncClient", factory)
    return factory


def fake_response(*, text="", content_type="text/html", data=None):
    response = Mock(text=text, headers={"content-type": content_type})
    response.json.return_value = data or {}
    return response


def http_error(status_code=503):
    request = httpx.Request("GET", "https://example.test")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("rejected", request=request, response=response)


def install_markitdown(monkeypatch, *, text_content="", exc=None):
    converter = MagicMock()
    if exc is not None:
        converter.convert.side_effect = exc
    else:
        converter.convert.return_value = SimpleNamespace(text_content=text_content)
    monkeypatch.setattr(subject, "MarkItDown", lambda: converter)
    return converter


@pytest.mark.anyio
async def test_web_search_dispatches_tavily_and_rejects_other_engines(monkeypatch):
    tavily = AsyncMock(return_value={"success": True})
    translate = Mock(side_effect=lambda key, **kwargs: (key, kwargs))
    monkeypatch.setattr(subject, "_tavily_search", tavily)
    monkeypatch.setattr(subject, "t", translate)

    assert await subject.web_search("cloud", 3, credentials={"token": "x"}) == {
        "success": True
    }
    unsupported = await subject.web_search("cloud", search_engine="other")

    tavily.assert_awaited_once_with("cloud", 3, {"token": "x"})
    assert unsupported == {
        "query": "cloud",
        "error": ("web_search_unsupported_engine", {"search_engine": "other"}),
        "success": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("credentials", [None, {}, {"OTHER": "value"}])
async def test_tavily_requires_key_without_opening_client(monkeypatch, credentials):
    factory = Mock(side_effect=AssertionError("network client must not be created"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", factory)
    monkeypatch.setattr(subject, "t", lambda key, **_kwargs: key)

    result = await subject._tavily_search("safe query", 5, credentials)

    assert result == {
        "query": "safe query",
        "error": "tavily_api_key_not_configured",
        "success": False,
        "results": [],
    }
    factory.assert_not_called()


@pytest.mark.anyio
async def test_tavily_posts_expected_payload_and_normalizes_results(monkeypatch):
    response = fake_response(
        data={
            "answer": "A concise answer",
            "results": [
                {
                    "title": "Result",
                    "url": "https://example.test/page",
                    "content": "Excerpt",
                    "score": 0.9,
                },
                {},
            ],
        }
    )
    client = FakeClient(post=response)
    factory = install_client(monkeypatch, client)

    result = await subject._tavily_search(
        "cloud security", 2, {"TAVILY_API_KEY": "secret"}
    )

    factory.assert_called_once_with(timeout=30)
    client.post.assert_awaited_once_with(
        "https://api.tavily.com/search",
        json={
            "api_key": "secret",
            "query": "cloud security",
            "max_results": 2,
            "include_answer": True,
            "include_raw_content": False,
        },
    )
    response.raise_for_status.assert_called_once_with()
    assert result == {
        "query": "cloud security",
        "answer": "A concise answer",
        "results": [
            {
                "title": "Result",
                "url": "https://example.test/page",
                "content": "Excerpt",
                "score": 0.9,
            },
            {"title": "", "url": "", "content": "", "score": None},
        ],
        "success": True,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (http_error(429), ("web_search_api_error", {"status_code": 429})),
        (httpx.ConnectError("offline"), ("tool_execution_failed", {})),
    ],
)
async def test_tavily_maps_provider_failures(monkeypatch, failure, expected_error):
    response = fake_response()
    if isinstance(failure, httpx.HTTPStatusError):
        response.raise_for_status.side_effect = failure
        client = FakeClient(post=response)
    else:
        client = FakeClient(post=failure)
    install_client(monkeypatch, client)
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject._tavily_search("cloud", 1, {"TAVILY_API_KEY": "secret"})

    assert result == {
        "query": "cloud",
        "error": expected_error,
        "success": False,
        "results": [],
    }


@pytest.mark.anyio
async def test_fetch_webpage_converts_url_via_markitdown_and_truncates(monkeypatch):
    converter = install_markitdown(monkeypatch, text_content="x" * 100)

    result = await subject.fetch_webpage("https://example.test/page", 10)

    converter.convert.assert_called_once_with("https://example.test/page")
    assert result == {
        "url": "https://example.test/page",
        "content": "xxxxxxxxxx...",
        "success": True,
    }


@pytest.mark.anyio
async def test_fetch_webpage_preserves_images_in_markdown():
    html = (
        "<h1>Title</h1><script>secret</script>"
        "<img src='https://example.test/cat.png' alt='A cat'>"
    )
    data_uri = (
        "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode()
    )

    result = await subject.fetch_webpage(data_uri, 5000)

    assert result["success"] is True
    content = result["content"]
    assert "Title" in content
    assert "https://example.test/cat.png" in content
    assert "A cat" in content
    assert "secret" not in content


@pytest.mark.anyio
async def test_fetch_webpage_maps_http_errors(monkeypatch):
    class FakeHTTPError(Exception):
        def __init__(self, status_code):
            self.response = SimpleNamespace(status_code=status_code)

    install_markitdown(monkeypatch, exc=FakeHTTPError(404))
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject.fetch_webpage("https://example.test/missing")

    assert result == {
        "url": "https://example.test/missing",
        "error": ("fetch_webpage_http_error", {"status_code": 404}),
        "success": False,
    }


@pytest.mark.anyio
async def test_fetch_webpage_maps_generic_errors(monkeypatch):
    install_markitdown(monkeypatch, exc=RuntimeError("boom"))
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject.fetch_webpage("https://example.test/page")

    assert result == {
        "url": "https://example.test/page",
        "error": ("tool_execution_failed", {}),
        "success": False,
    }


def test_register_web_search_tools_defines_both_handlers(monkeypatch):
    registrations = []

    def register(**kwargs):
        def decorator(handler):
            registrations.append((kwargs, handler))
            return handler

        return decorator

    monkeypatch.setattr(subject.tool_registry, "register", register)

    subject.register_web_search_tools()

    assert [entry[0]["name"] for entry in registrations] == [
        "web_search",
        "fetch_webpage",
    ]
    assert [entry[1] for entry in registrations] == [
        subject.web_search,
        subject.fetch_webpage,
    ]
    search_parameters = registrations[0][0]["parameters"]
    fetch_parameters = registrations[1][0]["parameters"]
    assert [(item.name, item.required, item.default) for item in search_parameters] == [
        ("query", True, None),
        ("num_results", False, 5),
    ]
    assert [(item.name, item.required, item.default) for item in fetch_parameters] == [
        ("url", True, None),
        ("max_length", False, 5000),
    ]
