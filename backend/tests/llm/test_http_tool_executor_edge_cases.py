from unittest.mock import patch

import httpx
import pytest

from app.core.i18n import t
from app.llm.tools.executors import execute_http_tool, format_http_result_for_llm


class _Response:
    def __init__(self, status_code: int = 200, body=None, text: str = "plain text"):
        self.is_success = 200 <= status_code < 300
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.mark.anyio
async def test_execute_http_tool_extracts_json_path_and_normalizes_plain_text_response():
    async def json_request(**kwargs):
        return _Response(body={"data": {"answer": 42}})

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=json_request),
    ):
        result = await execute_http_tool(
            {"url": "https://example.com", "response_path": "data.answer"}, {}
        )

    assert result == {
        "success": True,
        "status_code": 200,
        "result": 42,
        "error": None,
    }


@pytest.mark.anyio
async def test_execute_http_tool_uses_text_when_response_json_is_invalid():
    async def request(**kwargs):
        return _Response(body=ValueError("not json"), text="unstructured")

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=request),
    ):
        result = await execute_http_tool({"url": "https://example.com"}, {})

    assert result["success"] is True
    assert result["result"] == "unstructured"
    assert format_http_result_for_llm(result) == '"unstructured"'


@pytest.mark.anyio
async def test_execute_http_tool_rejects_unresolvable_url_before_request():
    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=ValueError("host cannot resolve"),
        ),
        patch("httpx.AsyncClient.request") as request,
    ):
        result = await execute_http_tool({"url": "https://missing.example"}, {})

    assert result == {"success": False, "error": "host cannot resolve"}
    request.assert_not_called()


@pytest.mark.anyio
async def test_execute_http_tool_normalizes_timeout_and_unexpected_client_failure():
    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=httpx.TimeoutException("slow")),
    ):
        timeout_result = await execute_http_tool({"url": "https://example.com"}, {})

    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request", side_effect=RuntimeError("offline")),
    ):
        failure_result = await execute_http_tool({"url": "https://example.com"}, {})

    assert timeout_result == {"success": False, "error": t("request_timeout")}
    assert failure_result == {"success": False, "error": t("tool_execution_failed")}


@pytest.mark.anyio
async def test_execute_http_tool_rejects_invalid_multipart_file_before_request():
    with (
        patch(
            "app.llm.tools.executors._validate_external_http_url",
            side_effect=lambda value: value,
        ),
        patch("httpx.AsyncClient.request") as request,
    ):
        with pytest.raises(ValueError, match="Expected data URL"):
            await execute_http_tool(
                {
                    "url": "https://example.com/upload",
                    "method": "POST",
                    "content_type": "multipart/form-data",
                    "form_fields": [
                        {"name": "attachment", "type": "file", "value": "{{file}}"}
                    ],
                },
                {"file": "https://example.com/file.txt"},
            )

    request.assert_not_called()
