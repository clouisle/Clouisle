import asyncio
import json
from collections.abc import Coroutine
from types import SimpleNamespace
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
    lifespan,
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


class CompletedTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def __await__(self):
        async def complete() -> None:
            return None

        return complete().__await__()


def close_coroutine(
    coroutine: Coroutine[object, object, object], task: CompletedTask
) -> CompletedTask:
    coroutine.close()
    return task


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_initializers", [False, True])
async def test_lifespan_mocks_initializers_and_external_boundaries(
    monkeypatch: pytest.MonkeyPatch, fail_initializers: bool
) -> None:
    import app.api.v1.endpoints.upload as upload_module
    import app.core.init_data as init_data_module
    import tortoise

    initializer_names = [
        "init_user_locale_field",
        "init_agent_tools_credentials",
        "fix_cascade_delete_policies",
        "init_workflow_visibility_field",
        "init_agent_visibility_values",
        "init_agent_streaming_config",
        "init_agent_context_compression_config",
        "init_message_manual_stop_field",
        "init_message_first_token_field",
        "init_message_round_fields",
        "init_message_branch_parent_field",
        "init_conversation_session_memory_table",
        "init_agent_user_input_request",
        "init_agent_hide_tool_calls_field",
        "init_agent_memory_fields",
        "init_agent_media_generation_fields",
        "init_password_expiration",
        "init_user_approval_status_field",
        "init_totp_fields",
        "init_permission_is_system_field",
        "init_agent_kb_search_mode",
        "init_chunk_status",
        "init_embed_config",
        "init_model_type_unique_constraint",
        "init_kb_rerank_fields",
        "init_skills_table",
        "init_clouisle_import_sessions_table",
        "drop_obsolete_retrieval_evaluation_tables",
    ]
    side_effect = RuntimeError("expected") if fail_initializers else None
    initializers = {
        name: AsyncMock(side_effect=side_effect) for name in initializer_names
    }
    for name, initializer in initializers.items():
        monkeypatch.setattr(init_data_module, name, initializer)

    init_postgres_lexical_search = AsyncMock()
    monkeypatch.setattr(
        init_data_module,
        "init_postgres_lexical_search",
        init_postgres_lexical_search,
    )
    init = AsyncMock()
    generate_schemas = AsyncMock()
    close_connections = AsyncMock()
    validate_upload = AsyncMock()
    close_redis = AsyncMock()
    init_db = AsyncMock(side_effect=side_effect)
    task = CompletedTask()
    monkeypatch.setattr(tortoise.Tortoise, "init", init)
    monkeypatch.setattr(tortoise.Tortoise, "generate_schemas", generate_schemas)
    monkeypatch.setattr(tortoise.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(
        upload_module, "validate_upload_storage_config", validate_upload
    )
    monkeypatch.setattr("app.main.init_db", init_db)
    monkeypatch.setattr("app.main.close_redis", close_redis)
    monkeypatch.setattr("app.main.settings.DATABASE_URL", "")
    monkeypatch.setattr("app.main.settings.POSTGRES_USER", "user")
    monkeypatch.setattr("app.main.settings.POSTGRES_PASSWORD", "pass")
    monkeypatch.setattr("app.main.settings.POSTGRES_SERVER", "db")
    monkeypatch.setattr("app.main.settings.POSTGRES_PORT", 5432)
    monkeypatch.setattr("app.main.settings.POSTGRES_DB", "clouisle")
    monkeypatch.setattr(
        "app.main.asyncio.create_task",
        lambda coroutine: close_coroutine(coroutine, task),
    )

    async with lifespan(SimpleNamespace()):
        generate_schemas.assert_awaited_once()
        validate_upload.assert_awaited_once()

    assert init.await_args.kwargs["db_url"] == "postgres://user:pass@db:5432/clouisle"
    assert all(mock.await_count == 1 for mock in initializers.values())
    init_postgres_lexical_search.assert_awaited_once()
    init_db.assert_awaited_once()
    assert task.cancelled
    close_connections.assert_awaited_once()
    close_redis.assert_awaited_once()


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
