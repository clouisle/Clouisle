import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import ContentPart, ContentType
from app.services import chat_context, asset_view, asset_access


@pytest.mark.asyncio
async def test_context_keeps_native_media_without_injecting_document_text(
    monkeypatch,
):
    image = ContentPart(type=ContentType.IMAGE)
    resolve = AsyncMock(
        return_value=(SimpleNamespace(display_filename="image.png"), image, {})
    )
    assets = {
        "image-ref": SimpleNamespace(
            id=uuid4(), display_filename="image.png", content_type="image/png", size=10
        ),
        "text-ref": SimpleNamespace(
            id=uuid4(),
            display_filename="original.txt",
            content_type="text/plain",
            size=200000,
        ),
        "empty-ref": SimpleNamespace(
            id=uuid4(),
            display_filename="report.pdf",
            content_type="application/pdf",
            size=200000,
        ),
    }
    monkeypatch.setattr(
        asset_access,
        "resolve_authorized_asset_ref",
        AsyncMock(side_effect=lambda ref, **kwargs: assets[ref]),
    )
    monkeypatch.setattr(asset_view, "resolve_view_content", resolve)
    parts, extracted = await chat_context._resolve_message_asset_parts(
        [
            {},
            {"image": {"asset_ref": "image-ref"}},
            {"asset_ref": "image-ref"},
            SimpleNamespace(asset_ref="text-ref", filename="renamed.txt"),
            {"asset_ref": "empty-ref"},
        ],
        conversation=SimpleNamespace(id=uuid4()),
        user=object(),
        agent=object(),
        model_config=object(),
        input_capabilities=object(),
    )
    assert parts == [image]
    documents = json.loads(extracted)["documents"]
    assert [item["ref"] for item in documents] == ["text-ref", "empty-ref"]
    assert "document body" not in extracted
    assert [entry.args[0] for entry in resolve.await_args_list] == ["image-ref"]
    content = chat_context._build_current_user_content("describe", None, None, parts)
    assert content[0].text == "describe"
    assert content[1] is image
    assert chat_context._stringify_content(content) == "describe\n[image]"
