"""Issue #255 branch coverage for HTTP tool executors."""

import socket
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.i18n import t
from app.llm.tools.executors import (
    _build_request_payload,
    _normalize_file_upload_value,
    _validate_external_http_url,
    execute_http_tool,
    format_http_result_for_llm,
)


class _Response:
    is_success = True
    status_code = 200
    text = "plain response"

    def json(self):
        raise ValueError("not JSON")


@pytest.mark.parametrize(
    "url,error",
    [
        ("ftp://example.com", "http_tool_url_invalid"),
        ("http://127.0.0.1", "http_tool_url_host_not_allowed"),
    ],
)
def test_url_validation_rejects_invalid_and_private_hosts(url, error):
    with pytest.raises(ValueError, match=t(error)):
        _validate_external_http_url(url)


def test_url_validation_handles_dns_success_private_result_and_failure():
    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]

    with patch("socket.getaddrinfo", return_value=public):
        assert (
            _validate_external_http_url("https://example.com") == "https://example.com"
        )
    with (
        patch("socket.getaddrinfo", return_value=private),
        pytest.raises(ValueError, match=t("http_tool_url_host_not_allowed")),
    ):
        _validate_external_http_url("https://example.com")
    with (
        patch("socket.getaddrinfo", side_effect=socket.gaierror),
        pytest.raises(ValueError, match=t("http_tool_url_host_cannot_be_resolved")),
    ):
        _validate_external_http_url("https://missing.example")


@pytest.mark.anyio
async def test_file_upload_normalizes_lists_metadata_and_absence():
    value = [
        None,
        {
            "name": "photo.jpg",
            "mimeType": "image/jpeg",
            "content": "data:image/jpeg;base64,aGk=",
        },
    ]

    assert await _normalize_file_upload_value(value, "asset", 1) == [
        ("asset", ("photo.jpg", b"hi", "image/jpeg"))
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "value",
    [42, "https://example.com/file.png", "data:text/plain,hello", "data:;base64,%%%"],
)
async def test_file_upload_rejects_unsupported_or_invalid_values(value):
    with pytest.raises(ValueError):
        await _normalize_file_upload_value(value, "asset", 1)


@pytest.mark.anyio
async def test_payload_handles_no_body_and_urlencoded_values():
    assert await _build_request_payload({}, {}, "GET", 1) == (None, {})
    assert await _build_request_payload({}, {}, "POST", 1) == (None, {})

    body, kwargs = await _build_request_payload(
        {
            "content_type": "application/x-www-form-urlencoded",
            "body_template": '{"meta":"{{meta}}","yes":"{{yes}}","no":"{{no}}","nil":"{{nil}}"}',
        },
        {"meta": [1], "yes": True, "no": False, "nil": None},
        "POST",
        1,
    )
    assert body is None
    assert kwargs["data"] == {
        "meta": "[1]",
        "yes": "true",
        "no": "false",
        "nil": "",
    }

    body, kwargs = await _build_request_payload(
        {
            "content_type": "application/x-www-form-urlencoded",
            "body_template": "not-json",
        },
        {},
        "POST",
        1,
    )
    assert (body, kwargs) == ("not-json", {})


@pytest.mark.anyio
async def test_execute_returns_text_and_extracts_nested_json_path():
    json_response = AsyncMock()
    json_response.is_success = True
    json_response.status_code = 200
    json_response.json = lambda: {"data": {"value": 7}}

    with (
        patch("app.llm.tools.executors._validate_external_http_url", side_effect=str),
        patch("httpx.AsyncClient.request", side_effect=[json_response, _Response()]),
    ):
        nested = await execute_http_tool(
            {"url": "https://example.com", "response_path": "data.value"}, {}
        )
        text = await execute_http_tool({"url": "https://example.com"}, {})

    assert nested["result"] == 7
    assert text["result"] == "plain response"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.TimeoutException("late"), "request_timeout"),
        (RuntimeError("broken"), "tool_execution_failed"),
    ],
)
async def test_execute_translates_request_failures(failure, expected):
    with (
        patch("app.llm.tools.executors._validate_external_http_url", side_effect=str),
        patch("httpx.AsyncClient.request", side_effect=failure),
    ):
        result = await execute_http_tool({"url": "https://example.com"}, {})

    assert result == {"success": False, "error": t(expected)}


def test_format_http_result_covers_success_failure_and_missing_error():
    assert (
        format_http_result_for_llm({"success": True, "result": {"ok": True}})
        == '{"ok": true}'
    )
    assert format_http_result_for_llm(
        {"success": False, "error": "bad", "status_code": 500}
    ) == ('{"error": "bad", "status_code": 500}')
    assert t("unknown_error") in format_http_result_for_llm({"success": False})
