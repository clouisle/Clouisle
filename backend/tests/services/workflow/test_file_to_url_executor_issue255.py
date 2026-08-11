import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.workflow.executors.subworkflow import FileToURLNodeExecutor


def node(**config):
    return {"data": {"config": config}}


@pytest.mark.asyncio
async def test_rejects_missing_invalid_and_unsupported_inputs():
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=None))
    executor = FileToURLNodeExecutor()

    missing = await executor.execute(
        node(inputVariable="file"), context, SimpleNamespace()
    )
    assert missing.error == "validation_error"

    context.resolve_variable_ref.return_value = "not-base64"
    unsupported = await executor.execute(
        node(inputVariable="file", inputType="content"), context, SimpleNamespace()
    )
    assert unsupported.error == "validation_error"

    context.resolve_variable_ref.return_value = "payload"
    unavailable_url = await executor.execute(
        node(inputVariable="file", inputType="base64", outputType="url"),
        context,
        SimpleNamespace(),
    )
    assert unavailable_url.error == "workflow_execution_error"


@pytest.mark.asyncio
async def test_returns_existing_base64_content_and_decoded_size():
    content = base64.b64encode(b"hello").decode()
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=content))

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", inputType="base64", outputType="base64"),
        context,
        SimpleNamespace(),
    )

    assert result.outputs == {"content": content, "size": 5}
    context.resolve_variable_ref.assert_awaited_once_with("file")


@pytest.mark.asyncio
async def test_legacy_input_variable_returns_upload_url_without_reading_file():
    """Workflow file parameter values are upload URLs; no filesystem access."""
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(
            return_value="/api/v1/upload/files/documents/2026/08/a.pdf"
        )
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", ensureAbsolute=False),
        context,
        SimpleNamespace(),
    )

    assert result.outputs["url"] == ("/api/v1/upload/files/documents/2026/08/a.pdf")
    assert result.outputs["filename"] == "a.pdf"
    assert result.outputs["mimeType"] == "application/pdf"


@pytest.mark.asyncio
async def test_ensure_absolute_uses_public_api_url_when_configured():
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value="/files/report.txt")
    )
    from app.core.config import settings

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(settings, "PUBLIC_API_URL", "http://public.example:8000")
        result = await FileToURLNodeExecutor().execute(
            node(inputVariable="file", ensureAbsolute=True),
            context,
            SimpleNamespace(),
        )

    assert result.outputs["url"] == "http://public.example:8000/files/report.txt"
    assert result.outputs["filename"] == "report.txt"


@pytest.mark.asyncio
async def test_ensure_absolute_preserves_relative_url_without_public_origin():
    from app.core.config import settings

    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value="/files/report.txt")
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(settings, "PUBLIC_API_URL", "")
        monkeypatch.setattr(settings, "API_BASE_URL", "http://internal-api:8000")
        result = await FileToURLNodeExecutor().execute(
            node(inputVariable="file", ensureAbsolute=True),
            context,
            SimpleNamespace(),
        )

    assert result.outputs["url"] == "/files/report.txt"


@pytest.mark.asyncio
async def test_legacy_path_to_base64_streams_internal_upload(monkeypatch):
    import httpx
    from app.core.config import settings

    async def aiter_bytes():
        yield b"hel"
        yield b"lo"

    stream_response = SimpleNamespace(raise_for_status=Mock(), aiter_bytes=aiter_bytes)

    class StreamContext:
        async def __aenter__(self):
            return stream_response

        async def __aexit__(self, *_args):
            return None

    class Client:
        def __init__(self):
            self.stream = Mock(return_value=StreamContext())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    client = Client()
    monkeypatch.setattr(httpx, "AsyncClient", Mock(return_value=client))
    monkeypatch.setattr(settings, "API_INTERNAL_BASE_URL", "http://api:8000")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "internal-token")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", "")
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(
            return_value="/api/v1/upload/files/documents/2026/08/report.txt"
        )
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", inputType="path", outputType="base64"),
        context,
        SimpleNamespace(),
    )

    assert result.outputs["content"] == base64.b64encode(b"hello").decode()
    assert result.outputs["size"] == 5
    client.stream.assert_called_once_with(
        "GET",
        "/internal/uploads/read",
        params={"key": "documents/2026/08/report.txt"},
    )


@pytest.mark.asyncio
async def test_legacy_path_to_base64_rejects_absolute_storage_key():
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value="/uploads//etc/passwd")
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", inputType="path", outputType="base64"),
        context,
        SimpleNamespace(),
    )

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_file_to_url_config_inputs_map_multiple_urls():
    config = {
        "ensureAbsolute": False,
        "inputs": [
            {"name": "doc_url", "sourceVariable": "{{start.document}}"},
            {"name": "image_url", "sourceVariable": "{{start.image}}"},
        ],
    }
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(side_effect=["/files/a.pdf", "/files/b.png"])
    )

    result = await FileToURLNodeExecutor().execute(
        {"data": {"fileToUrlConfig": config}}, context, SimpleNamespace()
    )

    assert result.outputs == {
        "doc_url": "/files/a.pdf",
        "image_url": "/files/b.png",
    }


@pytest.mark.asyncio
async def test_multi_file_value_produces_url_list():
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value=["/files/a.png", "/files/b.png"])
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="images", ensureAbsolute=False),
        context,
        SimpleNamespace(),
    )

    assert result.outputs["urls"] == ["/files/a.png", "/files/b.png"]
    assert result.outputs["filename"] == "a.png"


@pytest.mark.asyncio
async def test_file_to_url_config_skips_empty_input_entries():
    config = {
        "ensureAbsolute": False,
        "inputs": [
            {"name": "", "sourceVariable": "{{start.a}}"},
            {"name": "url", "sourceVariable": ""},
        ],
    }
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=None))

    result = await FileToURLNodeExecutor().execute(
        {"data": {"fileToUrlConfig": config}}, context, SimpleNamespace()
    )

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_file_to_url_config_rejects_resolved_none_value():
    config = {
        "ensureAbsolute": False,
        "inputs": [{"name": "url", "sourceVariable": "{{start.missing}}"}],
    }
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=None))

    result = await FileToURLNodeExecutor().execute(
        {"data": {"fileToUrlConfig": config}}, context, SimpleNamespace()
    )

    assert result.error == "validation_error"
    context.resolve_variable_ref.assert_awaited_once_with("{{start.missing}}")


@pytest.mark.asyncio
async def test_legacy_node_without_input_variable_is_rejected():
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value="x"))

    result = await FileToURLNodeExecutor().execute(
        node(inputType="path"), context, SimpleNamespace()
    )

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_non_string_file_value_is_rejected():
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=123))

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", ensureAbsolute=False),
        context,
        SimpleNamespace(),
    )

    assert result.error == "validation_error"


def test_output_metadata_matches_requested_mode():
    executor = FileToURLNodeExecutor()

    assert [item["name"] for item in executor.get_output_variables({})] == [
        "url",
        "filename",
        "mimeType",
        "size",
    ]
    assert [
        item.name for item in executor.get_output_specs({"outputType": "base64"})
    ] == [
        "content",
        "filename",
        "mimeType",
        "size",
    ]
