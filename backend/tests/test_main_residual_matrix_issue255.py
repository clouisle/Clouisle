import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from app.main import (
    EmbedHeadersMiddleware,
    LanguageMiddleware,
    LoggingMiddleware,
    cleanup_expired_clouisle_import_sessions_loop,
    health,
    http_exception_handler,
    root,
    validation_exception_handler,
)
from app.schemas.response import ResponseCode


def make_request(
    *,
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
    client: tuple[str, int] | None = ("client.test", 5000),
) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": client,
        },
        receive,
    )


def payload(response: Response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_validation_and_http_handler_residual_fallbacks() -> None:
    validation_error = RequestValidationError(
        [{"type": "missing", "loc": ("body", "name")}]
    )
    with patch("app.main.t", return_value="invalid"):
        validation = await validation_exception_handler(
            make_request(), validation_error
        )

    assert payload(validation)["data"] == {"errors": {"name": ["invalid"]}}

    with (
        patch("app.main.get_language", return_value="en"),
        patch("app.main.has_translation", return_value=False),
        patch("app.main.get_code_message", return_value="fallback") as message,
    ):
        response = await http_exception_handler(
            make_request(), HTTPException(status_code=418, detail={"hidden": True})
        )

    assert response.status_code == 418
    assert payload(response)["code"] == ResponseCode.UNKNOWN_ERROR
    assert payload(response)["msg"] == "fallback"
    message.assert_called_once_with(ResponseCode.UNKNOWN_ERROR, lang="en")


@pytest.mark.asyncio
async def test_cleanup_loop_logs_cleaned_count_and_propagates_cancel() -> None:
    cleanup = AsyncMock(side_effect=[2, asyncio.CancelledError])
    with (
        patch(
            "app.services.clouisle_package.ClouislePackageService.cleanup_expired_sessions",
            cleanup,
        ),
        patch("app.main.asyncio.sleep", AsyncMock()),
        patch("app.main.logger.info") as info,
        pytest.raises(asyncio.CancelledError),
    ):
        await cleanup_expired_clouisle_import_sessions_loop()

    info.assert_called_once_with("Cleaned %s expired Clouisle import sessions", 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "client", "expected_ip"),
    [
        ([(b"x-real-ip", b" 198.51.100.4 ")], ("ignored", 1), "198.51.100.4"),
        ([], ("192.0.2.3", 1), "192.0.2.3"),
        ([], None, "unknown"),
    ],
)
async def test_logging_middleware_ip_matrix(
    headers: list[tuple[bytes, bytes]],
    client: tuple[str, int] | None,
    expected_ip: str,
) -> None:
    middleware = LoggingMiddleware(app=Mock())
    with patch("app.main.logger.info") as info:
        response = await middleware.dispatch(
            make_request(headers=headers, client=client),
            AsyncMock(return_value=Response(status_code=204)),
        )

    assert response.status_code == 204
    assert expected_ip in info.call_args_list[0].args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "content_type"),
    [("/stream", "application/json"), ("/plain", "text/event-stream")],
)
async def test_logging_middleware_stream_paths(path: str, content_type: str) -> None:
    response = Response(status_code=200, media_type=content_type)
    result = await LoggingMiddleware(app=Mock()).dispatch(
        make_request(path=path), AsyncMock(return_value=response)
    )
    assert result is response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ([(b"content-type", b"application/json")], b"not-json"),
        ([(b"content-type", b"application/x-www-form-urlencoded")], b"a=1"),
        ([(b"content-type", b"application/json")], b"[1, 2]"),
        ([], b"ignored"),
    ],
)
async def test_logging_middleware_request_body_matrix(
    headers: list[tuple[bytes, bytes]], body: bytes
) -> None:
    result = await LoggingMiddleware(app=Mock()).dispatch(
        make_request(method="PATCH", headers=headers, body=body),
        AsyncMock(return_value=Response(status_code=200)),
    )
    assert result.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected"),
    [(b"failure", b"failure"), (b"", b"")],
)
async def test_logging_middleware_non_json_error_matrix(
    body: bytes, expected: bytes
) -> None:
    async def call_next(_request: Request) -> StreamingResponse:
        return StreamingResponse(iter([body]), status_code=500)

    response = await LoggingMiddleware(app=Mock()).dispatch(make_request(), call_next)
    assert response.status_code == 500
    assert response.body == expected


@pytest.mark.asyncio
async def test_language_embed_and_route_residuals() -> None:
    language = LanguageMiddleware(app=Mock())
    expected = Response(status_code=204)
    with patch("app.main.set_language") as set_language:
        result = await language.dispatch(
            make_request(headers=[(b"accept-language", b"zh-CN,zh;q=0.9")]),
            AsyncMock(return_value=expected),
        )
    assert result is expected
    set_language.assert_called_once_with("zh-CN")

    embed = EmbedHeadersMiddleware(app=Mock())
    preflight = await embed.dispatch(
        make_request(
            method="OPTIONS",
            path="/api/v1/embed/widget",
            headers=[(b"access-control-request-headers", b"authorization")],
        ),
        AsyncMock(),
    )
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-headers"] == "authorization"

    embed_response = await embed.dispatch(
        make_request(path="/api/v1/embed/widget"),
        AsyncMock(return_value=Response()),
    )
    assert embed_response.headers["content-security-policy"] == "frame-ancestors *"

    with patch("app.main.success", side_effect=lambda **kwargs: kwargs):
        assert await root() == {"msg_key": "welcome_message"}
        assert await health() == {"data": {"status": "healthy"}}
