import asyncio
import json
import logging
from collections.abc import Coroutine
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.main import (
    EmbedHeadersMiddleware,
    LanguageMiddleware,
    LoggingMiddleware,
    business_exception_handler,
    cleanup_expired_clouisle_import_sessions_loop,
    http_exception_handler,
    lifespan,
    validation_exception_handler,
)
from app.schemas.response import BusinessError, ResponseCode


def make_request(
    *,
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
    client: tuple[str, int] | None = ("testclient", 50000),
) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
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


def response_json(response: JSONResponse) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_validation_handler_groups_fields_and_rejects_untrusted_messages() -> (
    None
):
    exc = RequestValidationError(
        [
            {"type": "missing", "loc": ("body", "user", "email"), "msg": "known"},
            {"type": "value_error", "loc": ("body", "user", "email"), "msg": "leak me"},
            {"type": "missing", "loc": (), "msg": 123},
        ]
    )

    with (
        patch("app.main.has_translation", side_effect=lambda key, *_: key == "known"),
        patch("app.main.t", side_effect=lambda key, **_: f"translated:{key}"),
    ):
        response = await validation_exception_handler(make_request(), exc)

    assert response.status_code == 422
    assert response_json(response) == {
        "code": ResponseCode.VALIDATION_ERROR,
        "data": {
            "errors": {
                "user.email": ["translated:known", "translated:validation_error"],
                "unknown": ["translated:validation_error"],
            }
        },
        "msg": "translated:validation_error",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BusinessError(msg="direct", msg_key="ignored"), "direct"),
        (
            BusinessError(msg_key="item_missing", item="agent"),
            "translated:item_missing",
        ),
        (BusinessError(code=ResponseCode.NOT_FOUND), "code:4000"),
        (BusinessError(code=9999), "translated:unknown_error"),
    ],
)
async def test_business_handler_message_precedence(
    error: BusinessError, expected: str
) -> None:
    with (
        patch("app.main.t", side_effect=lambda key, **_: f"translated:{key}"),
        patch(
            "app.main.get_code_message", side_effect=lambda code: f"code:{int(code)}"
        ),
    ):
        response = await business_exception_handler(make_request(), error)

    assert response.status_code == error.status_code
    assert response_json(response)["msg"] == expected


@pytest.mark.asyncio
async def test_http_handler_translates_known_detail_in_selected_language() -> None:
    with (
        patch("app.main.get_language", return_value="zh"),
        patch("app.main.has_translation", return_value=True) as has_translation,
        patch("app.main.t", return_value="translated detail") as translate,
    ):
        response = await http_exception_handler(
            make_request(), HTTPException(status_code=401, detail="login_required")
        )

    assert response.status_code == 401
    assert response_json(response) == {
        "code": ResponseCode.UNAUTHORIZED,
        "data": None,
        "msg": "translated detail",
    }
    has_translation.assert_called_once_with("login_required", "zh")
    translate.assert_called_once_with("login_required", lang="zh")


@pytest.mark.asyncio
async def test_http_handler_does_not_reflect_untrusted_detail() -> None:
    with (
        patch("app.main.get_language", return_value="en"),
        patch("app.main.has_translation", return_value=False),
        patch("app.main.get_code_message", return_value="Not found"),
    ):
        response = await http_exception_handler(
            make_request(),
            HTTPException(status_code=404, detail="secret resource name"),
        )

    payload = response_json(response)
    assert payload["code"] == ResponseCode.NOT_FOUND
    assert payload["msg"] == "Not found"
    assert "secret resource name" not in response.body.decode()


@pytest.mark.asyncio
async def test_language_middleware_prefers_explicit_header_and_parses_locale() -> None:
    middleware = LanguageMiddleware(app=lambda *_: None)
    request = make_request(
        headers=[
            (b"x-language", b"zh-CN; q=0.9"),
            (b"accept-language", b"en-US,en;q=0.8"),
        ]
    )
    expected = Response(status_code=204)

    with patch("app.main.set_language") as set_language:
        response = await middleware.dispatch(request, AsyncMock(return_value=expected))

    assert response is expected
    set_language.assert_called_once_with("zh-CN")


@pytest.mark.asyncio
async def test_embed_headers_apply_only_to_embed_routes() -> None:
    middleware = EmbedHeadersMiddleware(app=lambda *_: None)

    async def framed_response(_request: Request) -> Response:
        return Response(headers={"X-Frame-Options": "DENY"})

    embed = await middleware.dispatch(
        make_request(path="/api/v1/embed/agents/id"), framed_response
    )
    regular = await middleware.dispatch(
        make_request(path="/api/v1/agents/id"), framed_response
    )

    assert "x-frame-options" not in embed.headers
    assert embed.headers["content-security-policy"] == "frame-ancestors *"
    assert embed.headers["access-control-allow-origin"] == "*"
    assert regular.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" not in regular.headers


@pytest.mark.asyncio
async def test_logging_middleware_redacts_credentials_and_uses_proxy_ip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    middleware = LoggingMiddleware(app=lambda *_: None)
    request = make_request(
        method="POST",
        headers=[
            (b"content-type", b"application/json"),
            (b"x-forwarded-for", b"203.0.113.7, 10.0.0.1"),
        ],
        body=b'{"username":"ada","password":"hidden","token":"also-hidden"}',
    )

    with caplog.at_level(logging.INFO, logger="app.main"):
        response = await middleware.dispatch(
            request, AsyncMock(return_value=Response(status_code=201))
        )

    messages = "\n".join(caplog.messages)
    assert response.status_code == 201
    assert "IP: 203.0.113.7" in messages
    assert '"password": "***"' in messages
    assert '"token": "***"' in messages
    assert "hidden" not in messages


@pytest.mark.asyncio
async def test_logging_middleware_preserves_error_response_body() -> None:
    middleware = LoggingMiddleware(app=lambda *_: None)

    async def call_next(_request: Request) -> StreamingResponse:
        return StreamingResponse(
            iter([b'{"code":4000,"msg":"missing"}']),
            status_code=404,
            media_type="application/json",
            headers={"x-trace-id": "trace-1"},
        )

    response = await middleware.dispatch(make_request(client=None), call_next)

    assert response.status_code == 404
    assert response.headers["x-trace-id"] == "trace-1"
    assert response.body == b'{"code":4000,"msg":"missing"}'


@pytest.mark.asyncio
async def test_logging_middleware_translates_unhandled_exception() -> None:
    middleware = LoggingMiddleware(app=lambda *_: None)

    async def fail(_request: Request) -> Response:
        raise RuntimeError("boom")

    with patch("app.main.t", return_value="Internal error"):
        response = await middleware.dispatch(make_request(), fail)

    assert response.status_code == 500
    assert response_json(response) == {
        "code": -1,
        "data": None,
        "msg": "Internal error",
    }


@pytest.mark.asyncio
async def test_cleanup_loop_logs_failure_then_remains_cancellable() -> None:
    cleanup = AsyncMock(side_effect=RuntimeError("temporary failure"))

    async def stop_after_retry(_delay: float) -> None:
        raise asyncio.CancelledError

    with (
        patch(
            "app.services.clouisle_package.ClouislePackageService.cleanup_expired_sessions",
            cleanup,
        ),
        patch("app.main.asyncio.sleep", side_effect=stop_after_retry),
        patch("app.main.logger.warning") as warning,
    ):
        with pytest.raises(asyncio.CancelledError):
            await cleanup_expired_clouisle_import_sessions_loop()

    cleanup.assert_awaited_once()
    warning.assert_called_once_with(
        "Clouisle import session cleanup failed: %s", cleanup.side_effect
    )


class CompletedTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def __await__(self):
        async def completed() -> None:
            return None

        return completed().__await__()


def close_coroutine_and_return_task(
    coroutine: Coroutine[object, object, object], task: CompletedTask
) -> CompletedTask:
    coroutine.close()
    return task


@pytest.mark.asyncio
async def test_lifespan_isolates_optional_init_failures_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.endpoints.upload as upload_module
    import app.core.init_data as init_data_module
    import tortoise

    migration_names = [
        name
        for name in vars(init_data_module)
        if name.startswith("init_") or name == "fix_cascade_delete_policies"
    ]
    migrations = {name: AsyncMock() for name in migration_names}
    migrations["init_user_locale_field"].side_effect = RuntimeError("already applied")
    for name, mock in migrations.items():
        monkeypatch.setattr(init_data_module, name, mock)

    task = CompletedTask()
    init = AsyncMock()
    generate_schemas = AsyncMock()
    close_connections = AsyncMock()
    validate_upload = AsyncMock()
    close_cache = AsyncMock()
    monkeypatch.setattr(tortoise.Tortoise, "init", init)
    monkeypatch.setattr(tortoise.Tortoise, "generate_schemas", generate_schemas)
    monkeypatch.setattr(tortoise.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(
        upload_module, "validate_upload_storage_config", validate_upload
    )
    monkeypatch.setattr(
        "app.main.init_db", AsyncMock(side_effect=RuntimeError("seed failed"))
    )
    monkeypatch.setattr("app.main.close_redis", close_cache)
    monkeypatch.setattr(
        "app.main.asyncio.create_task",
        lambda coroutine: close_coroutine_and_return_task(coroutine, task),
    )
    monkeypatch.setattr("app.main.settings.DATABASE_URL", "postgres://explicit/db")

    with (
        patch("app.main.logger.warning") as warning,
        patch("app.main.logger.error") as error_log,
    ):
        async with lifespan(SimpleNamespace()):
            assert generate_schemas.await_count == 1
            validate_upload.assert_awaited_once()

    assert init.await_args.kwargs["db_url"] == "postgres://explicit/db"
    warning.assert_any_call("User locale migration failed: already applied")
    error_log.assert_called_once_with("Error seeding data: seed failed")
    assert task.cancelled is True
    close_connections.assert_awaited_once()
    close_cache.assert_awaited_once()
