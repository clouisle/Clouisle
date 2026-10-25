"""SearXNG provider behavior through the site configuration runtime."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs

import httpx
import pytest

from app.llm.tools.builtin import web_search as subject
from app.schemas.response import BusinessError
from app.services import web_search_config as config_service

BASE_URL = "https://search.example.test/searx"
SEARCH_URL = f"{BASE_URL}/search"
REAL_ASYNC_CLIENT = httpx.AsyncClient


def install_transport(monkeypatch, handler):
    real_client = REAL_ASYNC_CLIENT
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


def install_site_config(monkeypatch, *, token=None, validate=True):
    credentials = {
        "default_engine": "searxng",
        "searxng_enabled": "true",
        "SEARXNG_BASE_URL": BASE_URL,
    }
    if token is not None:
        credentials["SEARXNG_AUTH_TOKEN"] = token
    monkeypatch.setattr(
        config_service,
        "_get_global_config",
        AsyncMock(return_value=SimpleNamespace(credentials=credentials)),
    )
    if validate:
        monkeypatch.setattr(
            config_service,
            "validate_searxng_base_url",
            AsyncMock(side_effect=lambda value: value),
        )


def form_body(request):
    return parse_qs(request.content.decode())


@pytest.mark.anyio
async def test_searxng_result_normalization_filters_bad_entries(monkeypatch):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Valid",
                        "url": "https://example.test/page",
                        "content": "  Snippet  ",
                    },
                    {"title": "FTP", "url": "ftp://example.test/file"},
                    {"title": "No host", "url": "https:///path"},
                    {"title": "Malformed", "url": "https://["},
                    {"title": "Missing URL"},
                    "not-a-dict",
                    {"title": 5, "url": "https://example.test/two", "content": None},
                ]
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject._searxng_search("query", 10, {"SEARXNG_BASE_URL": BASE_URL})

    assert len(requests) == 1
    assert result["success"] is True
    assert result["results"] == [
        {
            "title": "Valid",
            "url": "https://example.test/page",
            "content": "Snippet",
            "citation_id": result["results"][0]["citation_id"],
        },
        {
            "title": "",
            "url": "https://example.test/two",
            "content": "",
            "citation_id": result["results"][1]["citation_id"],
        },
    ]
    assert result["results"][0]["citation_id"].startswith("web_")


@pytest.mark.anyio
async def test_searxng_posts_json_format_to_subpath_with_bearer(monkeypatch):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "One", "url": "https://example.test/1", "content": "C"},
                    {"title": "Two", "url": "https://example.test/2", "content": "C"},
                ]
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject._searxng_search(
        "site search", 1, {"SEARXNG_BASE_URL": BASE_URL, "SEARXNG_AUTH_TOKEN": "tok"}
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == SEARCH_URL
    assert request.headers["authorization"] == "Bearer tok"
    body = form_body(request)
    assert body == {"q": ["site search"], "format": ["json"]}
    assert result["success"] is True
    assert len(result["results"]) == 1


@pytest.mark.anyio
async def test_web_search_uses_saved_config_and_searxng_provider(monkeypatch):
    """Config service -> web_search -> actual SearXNG transport (no forwarding mock)."""
    install_site_config(monkeypatch, token=None)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Saved config result",
                        "url": "https://example.test/saved",
                        "content": "From SearXNG",
                    }
                ]
            },
        )

    requests = install_transport(monkeypatch, handler)

    result = await subject.web_search("saved query", search_engine="searxng")

    assert [str(request.url) for request in requests] == [SEARCH_URL]
    assert result["success"] is True
    assert result["search_engine"] == "searxng"
    assert result["results"][0]["url"] == "https://example.test/saved"


@pytest.mark.anyio
async def test_web_search_fails_closed_when_ssrf_policy_blocks_base_url(monkeypatch):
    install_site_config(monkeypatch, token=None, validate=False)
    monkeypatch.setattr(
        config_service,
        "ensure_external_http_url_allowed",
        AsyncMock(
            side_effect=BusinessError(
                msg_key="http_tool_url_host_not_allowed",
                host="search.example.test",
                reason="private address 10.0.0.10",
            )
        ),
    )
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: (key, kwargs))
    factory = Mock(side_effect=AssertionError("blocked target must not be called"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", factory)

    result = await subject.web_search("query")

    assert result["success"] is False
    assert result["results"] == []
    assert result["error"] == (
        "http_tool_url_host_not_allowed",
        {"host": "search.example.test", "reason": "private address 10.0.0.10"},
    )
    factory.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "error"),
    [
        (302, "web_search_searxng_redirect"),
        (403, "web_search_searxng_forbidden"),
        (500, "web_search_api_error"),
    ],
)
async def test_searxng_http_status_failures(monkeypatch, status_code, error):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)
    requests = install_transport(
        monkeypatch, lambda request: httpx.Response(status_code)
    )

    result = await subject._searxng_search("query", 5, {"SEARXNG_BASE_URL": BASE_URL})

    assert result["success"] is False
    assert result["error"] == error
    assert result["results"] == []
    # Redirects are refused, never followed.
    assert len(requests) == 1


@pytest.mark.anyio
async def test_searxng_invalid_json_and_empty_results_are_explicit(monkeypatch):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)

    install_transport(
        monkeypatch, lambda request: httpx.Response(200, content=b"not-json")
    )
    invalid = await subject._searxng_search("query", 5, {"SEARXNG_BASE_URL": BASE_URL})

    install_transport(monkeypatch, lambda request: httpx.Response(200, json={}))
    missing = await subject._searxng_search("query", 5, {"SEARXNG_BASE_URL": BASE_URL})

    install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"results": [{"url": "ftp://bad"}]}),
    )
    empty = await subject._searxng_search("query", 5, {"SEARXNG_BASE_URL": BASE_URL})

    assert invalid["error"] == "web_search_searxng_invalid_response"
    assert missing["error"] == "web_search_searxng_invalid_response"
    assert empty["error"] == "web_search_searxng_empty_results"
    assert all(result["success"] is False for result in (invalid, missing, empty))
    assert all(result["results"] == [] for result in (invalid, missing, empty))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.ReadTimeout("slow"), "web_search_searxng_timeout"),
        (httpx.ConnectError("offline"), "tool_execution_failed"),
    ],
)
async def test_searxng_transport_failures(monkeypatch, failure, error):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)
    install_transport(monkeypatch, lambda request: (_ for _ in ()).throw(failure))

    result = await subject._searxng_search("query", 5, {"SEARXNG_BASE_URL": BASE_URL})

    assert result["success"] is False
    assert result["error"] == error
    assert result["results"] == []


@pytest.mark.anyio
async def test_searxng_missing_base_url_fails_without_network(monkeypatch):
    monkeypatch.setattr(subject, "t", lambda key, **kwargs: key)
    factory = AsyncMock(side_effect=AssertionError("no base URL, no network"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", factory)

    result = await subject._searxng_search("query", 5, {})

    assert result["success"] is False
    assert result["error"] == "web_search_engine_not_configured"
    factory.assert_not_awaited()
