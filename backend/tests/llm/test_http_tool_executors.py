"""
Tests for HTTP tool executor payload rendering.
"""

from unittest.mock import patch

import pytest

from app.core.i18n import t
from app.llm.tools.executors import execute_http_tool


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.is_success = 200 <= status_code < 300
        self.status_code = status_code
        self.text = "error"

    def json(self):
        return {"ok": self.is_success}


class TestHttpToolExecutors:
    @pytest.mark.anyio
    async def test_json_body_preserves_parameter_types(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            result = await execute_http_tool(
                http_config={
                    "url": "https://example.com/reviews",
                    "method": "POST",
                    "content_type": "application/json",
                    "body_template": """
                    {
                        "title": "{{title}}",
                        "count": "{{count}}",
                        "enabled": "{{enabled}}",
                        "meta": "{{meta}}",
                        "tags": "{{tags}}"
                    }
                    """,
                },
                arguments={
                    "title": "Review task",
                    "count": 3,
                    "enabled": True,
                    "meta": {"source": "mes"},
                    "tags": ["urgent", "qa"],
                },
            )

        assert result["success"] is True
        assert captured["json"] == {
            "title": "Review task",
            "count": 3,
            "enabled": True,
            "meta": {"source": "mes"},
            "tags": ["urgent", "qa"],
        }
        assert captured["content"] is None

    @pytest.mark.anyio
    async def test_json_body_supports_top_level_array(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            await execute_http_tool(
                http_config={
                    "url": "https://example.com/batch",
                    "method": "POST",
                    "content_type": "application/json",
                    "body_template": "{{items}}",
                },
                arguments={
                    "items": [{"id": 1}, {"id": 2}],
                },
            )

        assert captured["json"] == [{"id": 1}, {"id": 2}]
        assert captured["content"] is None

    @pytest.mark.anyio
    async def test_rejects_url_templates(self):
        result = await execute_http_tool(
            http_config={"url": "https://{{host}}/reviews", "method": "GET"},
            arguments={"host": "example.com"},
        )

        assert result["success"] is False
        assert result["error"] == t("http_tool_url_templates_not_supported")

    @pytest.mark.anyio
    async def test_rejects_blocked_http_url_without_raising(self):
        result = await execute_http_tool(
            http_config={"url": "http://localhost:8000/reviews", "method": "GET"},
            arguments={},
        )

        assert result["success"] is False
        assert result["error"] == t("http_tool_url_host_not_allowed")

    @pytest.mark.anyio
    async def test_omitted_optional_values_do_not_leave_query_or_header_placeholders(
        self,
    ):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            result = await execute_http_tool(
                http_config={
                    "url": "https://example.com/search",
                    "method": "GET",
                    "headers": {
                        "X-Keyword": "{{keyword}}",
                        "X-Optional": "{{optional_header}}",
                    },
                    "query_params": {
                        "q": "{{keyword}}",
                        "page": "{{optional_page}}",
                    },
                },
                arguments={"keyword": "docs"},
            )

        assert result["success"] is True
        assert captured["headers"] == {
            "X-Keyword": "docs",
            "X-Optional": "",
        }
        assert captured["params"] == {
            "q": "docs",
            "page": "",
        }
        assert "{{" not in str(captured["headers"])
        assert "{{" not in str(captured["params"])

    @pytest.mark.anyio
    async def test_omitted_optional_values_do_not_leave_json_body_placeholders(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            result = await execute_http_tool(
                http_config={
                    "url": "https://example.com/reviews",
                    "method": "POST",
                    "content_type": "application/json",
                    "body_template": """
                    {
                        "title": "{{title}}",
                        "note": "{{optional_note}}"
                    }
                    """,
                },
                arguments={"title": "Review task"},
            )

        assert result["success"] is True
        assert captured["json"] == {
            "title": "Review task",
            "note": "",
        }
        assert "{{" not in str(captured["json"])

    @pytest.mark.anyio
    async def test_http_error_status_returns_user_visible_error(self):
        async def fake_request(**kwargs):
            return _FakeResponse(status_code=404)

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            result = await execute_http_tool(
                http_config={
                    "url": "https://example.com/missing",
                    "method": "GET",
                },
                arguments={},
            )

        assert result["success"] is False
        assert result["status_code"] == 404
        assert result["error"] == t(
            "http_tool_request_failed_status",
            status_code=404,
        )
        assert result["result"] == {"ok": False}

    @pytest.mark.anyio
    async def test_multipart_form_data_handles_text_and_file_fields(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with (
            patch(
                "app.llm.tools.executors._validate_external_http_url",
                side_effect=lambda value: value,
            ),
            patch("httpx.AsyncClient.request", side_effect=fake_request),
        ):
            result = await execute_http_tool(
                http_config={
                    "url": "https://example.com/upload",
                    "method": "POST",
                    "content_type": "multipart/form-data",
                    "headers": {"Content-Type": "multipart/form-data"},
                    "form_fields": [
                        {"name": "title", "type": "text", "value": "{{title}}"},
                        {"name": "meta", "type": "text", "value": "{{meta}}"},
                        {"name": "image", "type": "file", "value": "{{image}}"},
                    ],
                },
                arguments={
                    "title": "Review task",
                    "meta": {"source": "mes"},
                    "image": "data:image/png;base64,aGVsbG8=",
                },
            )

        assert result["success"] is True
        assert captured["headers"] == {}
        assert captured["data"] == {
            "title": "Review task",
            "meta": '{"source": "mes"}',
        }
        assert len(captured["files"]) == 1
        field_name, file_tuple = captured["files"][0]
        assert field_name == "image"
        assert file_tuple[0].endswith(".png")
        assert file_tuple[1] == b"hello"
        assert file_tuple[2] == "image/png"
