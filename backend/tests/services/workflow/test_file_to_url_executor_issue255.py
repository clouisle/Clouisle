import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
@pytest.mark.parametrize("output_type", ["base64", "url"])
async def test_converts_existing_file_to_content_or_upload_url(tmp_path, output_type):
    uploads_root = tmp_path / "uploads"
    file_path = uploads_root / "reports" / "result.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("hello")
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value=str(file_path))
    )

    if output_type == "url":
        import app.services.workflow.executors.subworkflow as module

        original_path = module.Path
        module.Path = lambda value: (
            uploads_root if value.startswith("/Users/") else original_path(value)
        )
    try:
        result = await FileToURLNodeExecutor().execute(
            node(inputVariable="file", inputType="path", outputType=output_type),
            context,
            SimpleNamespace(),
        )
    finally:
        if output_type == "url":
            module.Path = original_path

    assert result.outputs["filename"] == "result.txt"
    assert result.outputs["mimeType"] == "text/plain"
    assert result.outputs["size"] == 5
    if output_type == "base64":
        assert base64.b64decode(result.outputs["content"]) == b"hello"
    else:
        assert result.outputs["url"].endswith("/uploads/reports/result.txt")


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
