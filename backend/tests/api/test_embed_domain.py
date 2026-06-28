from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.endpoints.embed import _check_embed_domain
from app.main import EmbedHeadersMiddleware
from app.schemas.response import BusinessError


def make_request(origin: str | None = None, referer: str | None = None) -> Request:
    headers = []
    if origin:
        headers.append((b"origin", origin.encode()))
    if referer:
        headers.append((b"referer", referer.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/embed/agents/agent-id/info",
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


def make_target(allowed_domains: list[str] | None) -> SimpleNamespace:
    return SimpleNamespace(embed_config={"allowed_domains": allowed_domains or []})


@pytest.mark.parametrize(
    ("allowed_domains", "origin"),
    [
        ([], "https://evil.example"),
        (["example.com"], "https://example.com"),
        (["example.com:3000"], "http://example.com:3000"),
        (["*.example.com"], "https://foo.example.com"),
        (["*.example.com"], "https://example.com"),
        (["*.example.com:3000"], "https://foo.example.com:3000"),
        (["https://example.com"], "https://example.com"),
        (["example.com:443"], "https://example.com"),
        (["https://example.com:443"], "https://example.com"),
        (["example.com:80"], "http://example.com"),
        (["http://example.com:80"], "http://example.com"),
    ],
)
def test_check_embed_domain_allows_matching_origins(
    allowed_domains: list[str],
    origin: str,
) -> None:
    _check_embed_domain(make_request(origin=origin), make_target(allowed_domains))


@pytest.mark.parametrize(
    ("allowed_domains", "origin"),
    [
        (["example.com:3000"], "http://example.com:4000"),
        (["*.example.com:3000"], "https://foo.example.com:4000"),
        (["example.com:443"], "http://example.com"),
        (["example.com:notaport"], "http://example.com"),
        (["example.com"], "https://evil.example"),
    ],
)
def test_check_embed_domain_rejects_non_matching_origins(
    allowed_domains: list[str],
    origin: str,
) -> None:
    with pytest.raises(BusinessError):
        _check_embed_domain(make_request(origin=origin), make_target(allowed_domains))


def test_check_embed_domain_uses_referer_when_origin_missing() -> None:
    _check_embed_domain(
        make_request(referer="https://docs.example.com/page"),
        make_target(["*.example.com"]),
    )


@pytest.mark.asyncio
async def test_embed_headers_middleware_handles_preflight() -> None:
    middleware = EmbedHeadersMiddleware(app=lambda *_args: None)
    request = Request(
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/api/v1/embed/agents/agent-id/info",
            "headers": [
                (b"access-control-request-headers", b"authorization,content-type")
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )

    async def call_next(_request: Request) -> Response:
        raise AssertionError("preflight should not continue to routing")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
    assert (
        response.headers["Access-Control-Allow-Headers"] == "authorization,content-type"
    )
