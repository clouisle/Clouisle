from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow.executors.subworkflow import FileToURLNodeExecutor


def node(**config):
    return {"data": {"config": config}}


@pytest.mark.asyncio
async def test_empty_input_value_is_rejected():
    context = SimpleNamespace(
        get_public_base_url=lambda: None,
        resolve_variable_ref=AsyncMock(return_value=""),
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file"), context, SimpleNamespace()
    )

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_invalid_base64_uses_encoded_length():
    context = SimpleNamespace(
        get_public_base_url=lambda: None,
        resolve_variable_ref=AsyncMock(return_value="not-base64"),
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputType="base64", outputType="base64"), context, SimpleNamespace()
    )

    assert result.outputs == {"content": "not-base64", "size": 10}


@pytest.mark.asyncio
async def test_resolve_error_is_translated():
    context = SimpleNamespace(
        get_public_base_url=lambda: None,
        resolve_variable_ref=AsyncMock(side_effect=OSError("private detail")),
    )

    with (
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value="public_error",
        ) as translate,
    ):
        result = await FileToURLNodeExecutor().execute(
            node(inputVariable="file"), context, SimpleNamespace()
        )

    assert result.error == "public_error"
    translate.assert_called_once()


@pytest.mark.asyncio
async def test_absolute_urls_are_passed_through_unchanged():
    context = SimpleNamespace(
        get_public_base_url=lambda: None,
        resolve_variable_ref=AsyncMock(
            return_value="https://cdn.example.com/files/a.pdf"
        ),
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", ensureAbsolute=True),
        context,
        SimpleNamespace(),
    )

    assert result.outputs["url"] == "https://cdn.example.com/files/a.pdf"


@pytest.mark.asyncio
async def test_http_absolute_url_is_not_rebaselined():
    context = SimpleNamespace(
        get_public_base_url=lambda: None,
        resolve_variable_ref=AsyncMock(return_value="http://cdn.example.com/a.pdf"),
    )

    result = await FileToURLNodeExecutor().execute(
        node(inputVariable="file", ensureAbsolute=True),
        context,
        SimpleNamespace(),
    )

    assert result.outputs["url"] == "http://cdn.example.com/a.pdf"


def test_remaining_output_metadata_modes():
    executor = FileToURLNodeExecutor()

    assert [
        item["name"] for item in executor.get_output_variables({"outputType": "base64"})
    ] == ["content", "filename", "mimeType", "size"]
    assert [item.name for item in executor.get_output_specs({})] == [
        "url",
        "urls",
        "filename",
        "mimeType",
        "size",
    ]
    urls_spec = executor.get_output_specs({})[1].type
    assert urls_spec.kind == "array"
    assert urls_spec.item is not None and urls_spec.item.kind == "string"
