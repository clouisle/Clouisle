import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.tools.builtin import web_search as subject
from app.services.citations import stable_citation_id


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


@pytest.mark.anyio
async def test_web_search_dispatches_tavily_and_rejects_other_engines(monkeypatch):
    tavily = AsyncMock(return_value={"success": True})
    translate = Mock(side_effect=lambda key, **kwargs: (key, kwargs))
    monkeypatch.setattr(subject, "_tavily_search", tavily)
    monkeypatch.setattr(subject, "t", translate)

    assert await subject.web_search(
        "cloud", 3, search_engine="tavily", credentials={"token": "x"}
    ) == {"success": True, "search_engine": "tavily"}
    unsupported = await subject.web_search("cloud", search_engine="other")

    tavily.assert_awaited_once_with("cloud", 3, {"token": "x"})
    assert unsupported == {
        "query": "cloud",
        "error": ("web_search_unsupported_engine", {"search_engine": "other"}),
        "success": False,
        "results": [],
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
    assert result["query"] == "cloud security"
    assert result["answer"] == "A concise answer"
    assert result["success"] is True
    assert all(item["citation_id"].startswith("web_") for item in result["results"])
    assert [
        {key: value for key, value in item.items() if key != "citation_id"}
        for item in result["results"]
    ] == [
        {
            "title": "Result",
            "url": "https://example.test/page",
            "content": "Excerpt",
            "score": 0.9,
        },
        {"title": "", "url": "", "content": "", "score": None},
    ]


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


def _patch_fetch_dependencies(monkeypatch, *, source, persisted=None):
    from app.services import asset_url_import

    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        lambda **_: (asset_url_import.AssetScopeType.CONVERSATION, uuid.uuid4()),
    )
    monkeypatch.setattr(
        asset_url_import, "load_url_document", AsyncMock(return_value=source)
    )
    persist = AsyncMock(return_value=persisted)
    monkeypatch.setattr(asset_url_import, "persist_scoped_document", persist)
    return persist


def _preview(filename="page.md"):
    return {
        "filename": filename,
        "start_line": 1,
        "total_lines": 2,
        "segments": [
            {"line": 1, "text": "Page Title", "continuation": False},
            {"line": 2, "text": "Body text", "continuation": False},
        ],
        "next_cursor": None,
        "eof": True,
    }


@pytest.mark.anyio
async def test_fetch_webpage_persists_complete_extracted_markdown(monkeypatch):
    from app.services import asset_url_import

    url = "https://example.test/page"
    persist = _patch_fetch_dependencies(
        monkeypatch,
        source=asset_url_import.ExternalDocument(
            content=b"<html><body><article>Body text</article></body></html>",
            content_type="text/html",
            filename="page",
            url=url,
            final_url=url,
        ),
        persisted=SimpleNamespace(asset=SimpleNamespace(id="a"), ref="abcd"),
    )
    monkeypatch.setattr(subject, "_read_preview", AsyncMock(return_value=_preview()))
    monkeypatch.setattr(
        subject,
        "_extract_readable_content",
        lambda html, target: ("# Page Title\nBody text", "Page Title"),
    )

    result = await subject.fetch_webpage(url)

    assert result["success"] is True
    assert result["url"] == url
    assert result["ref"] == "abcd"
    assert result["citation_id"] == stable_citation_id("web", url)
    assert [segment["text"] for segment in result["segments"]] == [
        "Page Title",
        "Body text",
    ]
    assert result["segments"][1]["text"] == "Body text"
    assert persist.await_args.args[0] == b"# Page Title\nBody text"
    assert persist.await_args.kwargs["filename"] == "page.md"


@pytest.mark.anyio
async def test_fetch_webpage_omits_data_url_from_payload(monkeypatch):
    from app.services import asset_url_import

    persist = _patch_fetch_dependencies(
        monkeypatch,
        source=asset_url_import.ExternalDocument(
            content=b"<p>Body</p>",
            content_type="text/html",
            filename="data.html",
            url="data:text/html,<p>Body</p>",
            final_url="data:text/html,<p>Body</p>",
        ),
        persisted=SimpleNamespace(asset=SimpleNamespace(id="a"), ref="abcd"),
    )
    monkeypatch.setattr(subject, "_read_preview", AsyncMock(return_value=_preview()))
    monkeypatch.setattr(
        subject,
        "_extract_readable_content",
        lambda html, target: ("Body", None),
    )

    result = await subject.fetch_webpage("data:text/html,<p>Body</p>")

    assert result["success"] is True
    assert result["url"] is None
    assert persist.await_args.kwargs["provenance"]["url"] is None


@pytest.mark.anyio
async def test_fetch_webpage_maps_business_errors(monkeypatch):
    from app.services import asset_url_import
    from app.schemas.response import BusinessError

    _patch_fetch_dependencies(monkeypatch, source=None)
    monkeypatch.setattr(
        asset_url_import,
        "load_url_document",
        AsyncMock(
            side_effect=BusinessError(
                msg_key="fetch_webpage_http_error", status_code=404
            )
        ),
    )

    result = await subject.fetch_webpage("https://example.test/missing")

    assert result["success"] is False
    assert result["url"] == "https://example.test/missing"
    assert "404" in result["error"]


@pytest.mark.anyio
async def test_fetch_webpage_requires_scope_before_loading(monkeypatch):
    from app.services import asset_url_import
    from app.schemas.response import BusinessError

    load = AsyncMock(side_effect=AssertionError("must not load"))
    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        Mock(side_effect=BusinessError(msg_key="validation_error")),
    )
    monkeypatch.setattr(asset_url_import, "load_url_document", load)

    result = await subject.fetch_webpage("https://example.test/page")

    assert result["success"] is False
    assert result["error"]
    load.assert_not_awaited()


def test_extract_readable_content_removes_boilerplate():
    html = """
    <html><head><title>Article Title</title></head><body>
    <nav>Home About</nav>
    <article><h1>Article Title</h1><p>Main article body content.</p></article>
    <footer>Copyright 2026</footer>
    </body></html>
    """
    text, title = subject._extract_readable_content(html, "https://example.test/a")

    assert "Main article body content" in text
    assert "Copyright 2026" not in text
    assert title == "Article Title"


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
    ]


@pytest.mark.anyio
async def test_duckduckgo_challenge_page_is_a_failure_not_an_empty_success(monkeypatch):
    install_client(
        monkeypatch,
        FakeClient(post=fake_response(text="<html><body>challenge</body></html>")),
    )
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)

    result = await subject._duckduckgo_search("上海 天气", 5)

    assert result["success"] is False
    assert result["results"] == []
    assert result["error"] == "web_search_blocked_or_empty"


@pytest.mark.anyio
async def test_duckduckgo_parsed_results_remain_successful(monkeypatch):
    html = '<div class="result"><a class="result__a" href="https://example.test/a">A</a><a class="result__snippet">S</a></div>'
    install_client(monkeypatch, FakeClient(post=fake_response(text=html)))

    result = await subject._duckduckgo_search("weather", 5)

    assert result["success"] is True
    assert result["results"][0]["url"] == "https://example.test/a"
