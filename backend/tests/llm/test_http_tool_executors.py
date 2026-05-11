"""
Tests for HTTP tool executor payload rendering.
"""

from unittest.mock import patch

import pytest

from app.llm.tools.executors import execute_http_tool


class _FakeResponse:
    def __init__(self):
        self.is_success = True
        self.status_code = 200

    def json(self):
        return {"ok": True}


class TestHttpToolExecutors:
    @pytest.mark.anyio
    async def test_json_body_preserves_parameter_types(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with patch("httpx.AsyncClient.request", side_effect=fake_request):
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

        with patch("httpx.AsyncClient.request", side_effect=fake_request):
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
        with pytest.raises(ValueError, match="URL templates"):
            await execute_http_tool(
                http_config={"url": "https://{{host}}/reviews", "method": "GET"},
                arguments={"host": "example.com"},
            )

    @pytest.mark.anyio
    async def test_multipart_form_data_handles_text_and_file_fields(self):
        captured: dict = {}

        async def fake_request(**kwargs):
            captured.update(kwargs)
            return _FakeResponse()

        with patch("httpx.AsyncClient.request", side_effect=fake_request):
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
