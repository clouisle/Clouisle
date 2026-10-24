from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import ContentPart, ContentType
from app.services import chat_context, asset_view


@pytest.mark.asyncio
async def test_context_keeps_native_media_and_extracts_each_asset_only_once(
    monkeypatch,
):
    image = ContentPart(type=ContentType.IMAGE)
    text = ContentPart(type=ContentType.TEXT, text="document body")
    resolve = AsyncMock(
        side_effect=[
            (SimpleNamespace(display_filename="image.png"), image, {}),
            (SimpleNamespace(display_filename="original.txt"), text, {}),
            (
                SimpleNamespace(display_filename="fallback.txt"),
                ContentPart(type=ContentType.TEXT, text=""),
                {},
            ),
        ]
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
    assert (
        extracted
        == '<uploaded_file name="renamed.txt">\ndocument body\n</uploaded_file>\n\n<uploaded_file name="fallback.txt">\n\n</uploaded_file>'
    )
    assert [entry.args[0] for entry in resolve.await_args_list] == [
        "image-ref",
        "text-ref",
        "empty-ref",
    ]
    content = chat_context._build_current_user_content("describe", None, None, parts)
    assert content[0].text == "describe"
    assert content[1] is image
    assert chat_context._stringify_content(content) == "describe\n[image]"
