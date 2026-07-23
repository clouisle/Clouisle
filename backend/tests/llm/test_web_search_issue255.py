from unittest.mock import AsyncMock, Mock

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


def test_html_extractor_skips_script_and_style_content():
    extractor = subject._HTMLTextExtractor()
    extractor.feed(
        "<main>Visible<script>hidden<style>also hidden</style></script> tail</main>"
    )
    extractor.handle_endtag("script")
    extractor.handle_data("   ")

    assert extractor.get_text() == "Visible  tail"


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
@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        (
            "<h1> Title </h1><script>secret</script><p> body text </p>",
            50,
            "Title body text",
        ),
        ("<p>abcdef</p>", 4, "abcd..."),
    ],
)
async def test_fetch_webpage_extracts_and_limits_html(
    monkeypatch, text, max_length, expected
):
    response = fake_response(text=text)
    client = FakeClient(get=response)
    factory = install_client(monkeypatch, client)

    result = await subject.fetch_webpage("https://example.test/page", max_length)

    factory.assert_called_once_with(timeout=30, follow_redirects=True)
    client.get.assert_awaited_once_with(
        "https://example.test/page",
        headers={"User-Agent": "Mozilla/5.0 (compatible; CloudisleBot/1.0)"},
    )
    assert result == {
        "url": "https://example.test/page",
        "content": expected,
        "content_type": "text/html",
        "success": True,
    }


@pytest.mark.anyio
async def test_fetch_webpage_returns_limited_json(monkeypatch):
    response = fake_response(
        text='{"long":"value"}', content_type="application/json; charset=utf-8"
    )
    install_client(monkeypatch, FakeClient(get=response))

    result = await subject.fetch_webpage("https://example.test/data", 7)

    assert result == {
        "url": "https://example.test/data",
        "content": '{"long"',
        "content_type": "application/json",
        "success": True,
    }


@pytest.mark.anyio
async def test_fetch_webpage_rejects_unsupported_content(monkeypatch):
    response = fake_response(content_type="image/png")
    install_client(monkeypatch, FakeClient(get=response))
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject.fetch_webpage("https://example.test/image")

    assert result == {
        "url": "https://example.test/image",
        "error": (
            "fetch_webpage_unsupported_content_type",
            {"content_type": "image/png"},
        ),
        "success": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (http_error(404), ("fetch_webpage_http_error", {"status_code": 404})),
        (httpx.ConnectError("offline"), ("tool_execution_failed", {})),
    ],
)
async def test_fetch_webpage_maps_failures(monkeypatch, failure, expected_error):
    response = fake_response()
    if isinstance(failure, httpx.HTTPStatusError):
        response.raise_for_status.side_effect = failure
        client = FakeClient(get=response)
    else:
        client = FakeClient(get=failure)
    install_client(monkeypatch, client)
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await subject.fetch_webpage("https://example.test/page")

    assert result == {
        "url": "https://example.test/page",
        "error": expected_error,
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
