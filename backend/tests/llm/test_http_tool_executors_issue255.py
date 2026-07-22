import json
import socket
from unittest.mock import patch

import httpx
import pytest

from app.core.i18n import t
from app.llm.tools.executors import (
    _build_request_payload,
    _extract_placeholder_name,
    _guess_filename,
    _normalize_file_upload_value,
    _parse_data_url,
    _render_json_template,
    _render_text_template,
    _validate_external_http_url,
    execute_http_tool,
    format_http_result_for_llm,
)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("ftp://example.com", "http_tool_url_invalid"),
        ("http://local", "http_tool_url_host_not_allowed"),
        ("http://127.0.0.1", "http_tool_url_host_not_allowed"),
    ],
)
def test_url_validation_rejects_invalid_and_blocked_hosts(value, message):
    with pytest.raises(ValueError, match=t(message)):
        _validate_external_http_url(value)


def test_url_validation_checks_dns_results():
    with patch(
        "app.llm.tools.executors.socket.getaddrinfo", side_effect=socket.gaierror
    ):
        with pytest.raises(
            ValueError, match=t("http_tool_url_host_cannot_be_resolved")
        ):
            _validate_external_http_url("https://missing.example")

    with patch(
        "app.llm.tools.executors.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    ):
        with pytest.raises(ValueError, match=t("http_tool_url_host_not_allowed")):
            _validate_external_http_url("https://example.com")

    with patch(
        "app.llm.tools.executors.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    ):
        assert (
            _validate_external_http_url("https://example.com") == "https://example.com"
        )


def test_template_and_filename_helpers_cover_value_types():
    variables = {"none": None, "data": {"x": 1}, "flag": False, "text": "hello"}
    assert (
        _render_text_template(
            "{{none}}|{{data}}|{{flag}}|{{text}}|{{missing}}", variables
        )
        == '|{"x": 1}|false|hello|'
    )
    assert (
        _render_json_template(
            '{"text": "prefix {{text}}", "none": {{none}}}', variables
        )
        == '{"text": "prefix hello", "none": null}'
    )
    assert _extract_placeholder_name(None) is None
    assert _extract_placeholder_name("prefix {{name}}") is None
    assert _extract_placeholder_name("{{ name }}") == "name"
    assert _guess_filename("asset", "image/png", "https://cdn.example/a.png") == "a.png"
    assert (
        _guess_filename("asset", "image/png", "https://cdn.example/download")
        == "asset.png"
    )
    with patch("app.llm.tools.executors.mimetypes.guess_extension", return_value=None):
        assert _guess_filename("asset", "image/jpeg") == "asset.jpg"
        assert _guess_filename("asset", None) == "asset.bin"


@pytest.mark.parametrize(
    "value",
    ["plain", "data:image/png;base64", "data:image/png,abc"],
)
def test_parse_data_url_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="Invalid data URL"):
        _parse_data_url(value)


def test_parse_data_url_defaults_mime_type():
    assert _parse_data_url("data:;base64,aGk=") == (b"hi", "application/octet-stream")


@pytest.mark.anyio
async def test_file_upload_normalization_covers_collections_and_errors():
    assert await _normalize_file_upload_value(None, "file", 1) == []
    uploads = await _normalize_file_upload_value(
        [
            {"name": "one.txt", "mimeType": "text/plain", "data": "data:;base64,b25l"},
            "data:text/plain;base64,dHdv",
        ],
        "file",
        1,
    )
    assert [upload[1][0] for upload in uploads] == ["one.txt", "file.txt"]
    assert [upload[1][1] for upload in uploads] == [b"one", b"two"]

    for value in (123, "https://example.com/a.png", "plain"):
        with pytest.raises(ValueError, match="Unsupported file"):
            await _normalize_file_upload_value(value, "file", 1)


@pytest.mark.anyio
async def test_request_payload_covers_multipart_and_empty_cases():
    assert await _build_request_payload({}, {}, "GET", 1) == (None, {})
    assert await _build_request_payload({"body_template": ""}, {}, "POST", 1) == (
        None,
        {},
    )

    body, kwargs = await _build_request_payload(
        {
            "content_type": "multipart/form-data",
            "form_fields": [
                {},
                {"name": "skip", "value": "{{missing}}"},
                {"name": "meta", "value": "{{meta}}"},
                {"name": "enabled", "value": "{{enabled}}"},
                {"name": "title", "value": "prefix {{title}}"},
            ],
        },
        {"meta": [1], "enabled": True, "title": "x"},
        "POST",
        1,
    )
    assert body is None
    assert kwargs == {
        "data": {"meta": "[1]", "enabled": "true", "title": "prefix x"},
        "files": [],
    }


@pytest.mark.anyio
async def test_urlencoded_payload_covers_scalar_conversion_and_invalid_json():
    body, kwargs = await _build_request_payload(
        {
            "content_type": "application/x-www-form-urlencoded",
            "body_template": '{"obj": {{obj}}, "yes": true, "no": false, "nil": null, "n": 2}',
        },
        {"obj": {"x": 1}},
        "POST",
        1,
    )
    assert body is None
    assert kwargs["data"] == {
        "obj": '{"x": 1}',
        "yes": "true",
        "no": "false",
        "nil": "",
        "n": "2",
    }
    assert await _build_request_payload(
        {"content_type": "application/x-www-form-urlencoded", "body_template": "raw"},
        {},
        "POST",
        1,
    ) == ("raw", {})
    assert await _build_request_payload(
        {"content_type": "application/json", "body_template": "raw"}, {}, "POST", 1
    ) == ("raw", {})


class _Response:
    is_success = True
    status_code = 200
    text = "plain"

    def __init__(self, payload=None, json_error=False):
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise ValueError
        return self.payload


@pytest.mark.anyio
async def test_execute_http_tool_covers_credentials_text_and_response_paths():
    captured = {}

    async def request(**kwargs):
        captured.update(kwargs)
        return _Response({"outer": {"value": 3}, "other": 4})

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=request),
    ):
        result = await execute_http_tool(
            {
                "url": "https://example.com",
                "headers": {"Authorization": "{{token}}"},
                "response_path": "outer.value.missing",
            },
            {},
            credentials={"token": "secret"},
        )
    assert captured["headers"] == {"Authorization": "secret"}
    assert result["result"] == 3

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=request),
    ):
        result = await execute_http_tool(
            {"url": "https://example.com", "response_path": "outer.value"}, {}
        )
    assert result["result"] == 3

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", return_value=_Response(json_error=True)),
    ):
        result = await execute_http_tool({"url": "https://example.com"}, {})
    assert result["result"] == "plain"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.TimeoutException("late"), "request_timeout"),
        (RuntimeError("boom"), "tool_execution_failed"),
    ],
)
async def test_execute_http_tool_handles_request_errors(error, message):
    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=error),
    ):
        result = await execute_http_tool({"url": "https://example.com"}, {})
    assert result == {"success": False, "error": t(message)}


def test_format_http_result_for_llm_covers_success_and_error_defaults():
    assert json.loads(format_http_result_for_llm({"success": True, "result": [1]})) == [
        1
    ]
    assert json.loads(format_http_result_for_llm({"success": False})) == {
        "error": t("unknown_error"),
        "status_code": None,
    }
