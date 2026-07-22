from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow.executors.subworkflow import FileToURLNodeExecutor


def node(**config):
    return {"data": {"config": config}}


@pytest.mark.asyncio
async def test_path_reports_missing_file(tmp_path):
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value=str(tmp_path / "missing.txt"))
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputType="path"), context, SimpleNamespace()
    )

    assert result.error == "file_not_found"


@pytest.mark.asyncio
async def test_invalid_base64_uses_encoded_length():
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value="not-base64"))

    result = await FileToURLNodeExecutor().execute(
        node(inputType="base64", outputType="base64"), context, SimpleNamespace()
    )

    assert result.outputs == {"content": "not-base64", "size": 10}


@pytest.mark.asyncio
async def test_file_read_error_is_translated(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("content")
    context = SimpleNamespace(
        resolve_variable_ref=AsyncMock(return_value=str(file_path))
    )

    with (
        patch("os.path.getsize", side_effect=OSError("private detail")),
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value="public_error",
        ) as translate,
    ):
        result = await FileToURLNodeExecutor().execute(
            node(inputType="path"), context, SimpleNamespace()
        )

    assert result.error == "public_error"
    translate.assert_called_once()


def test_remaining_output_metadata_modes():
    executor = FileToURLNodeExecutor()

    assert [
        item["name"] for item in executor.get_output_variables({"outputType": "base64"})
    ] == ["content", "filename", "mimeType", "size"]
    assert [item.name for item in executor.get_output_specs({})] == [
        "url",
        "filename",
        "mimeType",
        "size",
    ]
