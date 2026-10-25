"""Feishu inbound normalization and channel reply splitting boundaries.

``parse_message`` turns a provider message body into text plus attachments and
``prepare_input`` turns those attachments into private conversation Assets.
These tests pin the shapes that must never leak into a chat: malformed JSON,
non-object bodies, missing keys, folders, duplicated references, unknown
languages, and the extension/size limits applied both on download and on a
re-registered Asset.

``split_message_text`` is the byte-bounded splitter every channel shares, so
its structural guarantees (repeated table headers, repeated code fences,
preserved CRLF, per-cell overflow) are pinned here too.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.services.feishu_agent_input import parse_message, prepare_input
from app.services.message_split import split_message_text


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


# --- parse_message -----------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected_text", "expected_attachments"),
    [
        # A body that is not JSON at all.
        ({"message_type": "text", "content": "{not json"}, "", []),
        # A JSON body that is not an object.
        ({"message_type": "text", "content": "[]"}, "", []),
        ({"message_type": "text", "content": "null"}, "", []),
        # A JSON scalar is not an object either.
        ({"message_type": "text", "content": "7"}, "", []),
        # No content key at all.
        ({"message_type": "text"}, "", []),
        # An unknown message type is ignored, not parsed.
        ({"message_type": "sticker", "content": {"text": "hi"}}, "", []),
        # A text message with no text field.
        ({"message_type": "text", "content": {}}, "", []),
        # A file message without a key carries nothing.
        ({"message_type": "file", "content": {}}, "", []),
        ({"message_type": "image", "content": {}}, "", []),
        # A non-string key is rejected.
        ({"message_type": "file", "content": {"file_key": 5}}, "", []),
        # A post message whose localized body is not an object.
        ({"message_type": "post", "content": {"zh_cn": "text"}}, "", []),
        # A post message with no localized body at all.
        ({"message_type": "post", "content": {}}, "", []),
        # A post message with an empty body still yields no text.
        ({"message_type": "post", "content": {"content": []}}, "", []),
    ],
)
def test_parse_message_rejects_unusable_bodies(
    message, expected_text, expected_attachments
):
    assert parse_message(message) == (expected_text, expected_attachments)


def test_parse_message_reads_text_and_image_keys():
    text, attachments = parse_message(
        {"message_type": "text", "content": {"text": "  hello  "}}
    )
    assert text == "hello"
    assert attachments == []

    text, attachments = parse_message(
        {"message_type": "image", "content": {"image_key": "img_1"}}
    )
    assert text == ""
    assert attachments == [{"kind": "image", "key": "img_1", "name": ""}]

    text, attachments = parse_message(
        {
            "message_type": "file",
            "content": {"file_key": "file_1", "file_name": "r.txt"},
        }
    )
    assert attachments == [{"kind": "file", "key": "file_1", "name": "r.txt"}]


def test_parse_message_prefers_zh_cn_then_en_us_then_any_body():
    body = {
        "title": "标题",
        "content": [[{"tag": "text", "text": "内容"}]],
    }
    message = {
        "message_type": "post",
        "content": {"zh_cn": body, "en_us": {"title": "x"}},
    }
    text, attachments = parse_message(message)
    assert text == "标题\n内容"

    message = {"message_type": "post", "content": {"en_us": body}}
    assert parse_message(message)[0] == "标题\n内容"

    # Neither zh_cn nor en_us: the first value is used.
    message = {"message_type": "post", "content": {"ja_jp": body}}
    assert parse_message(message)[0] == "标题\n内容"


def test_parse_message_extracts_links_and_ignores_unknown_tags():
    message = {
        "message_type": "post",
        "content": {
            "content": [
                [
                    {"tag": "text", "text": "看"},
                    {"tag": "a", "href": "https://example.test"},
                    {"tag": "at", "user_id": "ou_x"},
                    {"tag": "img", "image_key": "img_1", "file_name": "pic.png"},
                    {"tag": "file"},
                    {"tag": "img", "image_key": ""},
                    {"tag": "file", "file_key": "file_1", "file_name": "doc.txt"},
                ]
            ]
        },
    }
    text, attachments = parse_message(message)
    assert text == "看https://example.test"
    assert attachments == [
        {"kind": "image", "key": "img_1", "name": "pic.png"},
        {"kind": "file", "key": "file_1", "name": "doc.txt"},
    ]


def test_parse_message_skips_folders_and_duplicated_top_level_files():
    message = {
        "message_type": "post",
        "content": {
            "content": [
                [{"tag": "file", "file_key": "inline", "file_name": "inline.txt"}]
            ],
            "files": [
                {"file_key": "inline", "file_name": "inline.txt"},
                {"file_key": "folder_1", "file_name": "docs", "is_folder": True},
                {"file_key": "top", "file_name": "top.txt", "is_folder": False},
                {"file_key": None},
            ],
        },
    }
    text, attachments = parse_message(message)
    assert attachments == [
        {"kind": "file", "key": "inline", "name": "inline.txt"},
        {"kind": "file", "key": "top", "name": "top.txt"},
    ]


def test_parse_message_handles_a_post_body_without_rows():
    # A body with a content key but no rows keeps only its title.
    assert parse_message(
        {"message_type": "post", "content": {"title": "只有标题", "content": None}}
    ) == ("只有标题", [])


# --- prepare_input -----------------------------------------------------------


def _receipt(**overrides):
    values = dict(
        id="11111111-1111-1111-1111-111111111111",
        message_id="om_1",
        text="hello",
        attachments=[],
        created_at=datetime(2026, 1, 15, 12, 0, 0),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _agent(**overrides):
    values = dict(
        enable_attachments=True,
        attachment_config={},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class _Asset:
    def __init__(self, **overrides):
        values = dict(
            id="22222222-2222-2222-2222-222222222222",
            storage_key="agent-attachments/2026/01/key",
            original_filename="report.txt",
            display_filename="report.txt",
            content_type="text/plain",
            size=12,
        )
        values.update(overrides)
        for key, value in values.items():
            setattr(self, key, value)


@pytest.mark.asyncio
async def test_prepare_input_returns_plain_message_without_attachments():
    request = await prepare_input(_receipt(), None, _agent(), None, None)
    assert request.message == "hello"
    assert request.images == [] and request.file_urls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, "feishu_agent_too_many_files"),
        ({"max_files": 1}, "feishu_agent_too_many_files"),
    ],
)
async def test_prepare_input_rejects_too_many_files(db, config, expected):
    attachments = [
        {"kind": "file", "key": f"file_{index}", "name": "a.txt"} for index in range(6)
    ]
    receipt = _receipt(attachments=attachments)
    with pytest.raises(Exception) as error:
        await prepare_input(receipt, None, _agent(attachment_config=config), None, None)
    assert getattr(error.value, "msg_key", None) == expected


@pytest.mark.asyncio
async def test_prepare_input_rejects_attachments_when_the_agent_disabled_them():
    receipt = _receipt(attachments=[{"kind": "file", "key": "a", "name": "a.txt"}])
    with pytest.raises(Exception) as error:
        await prepare_input(receipt, None, _agent(enable_attachments=False), None, None)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_attachments_disabled"


@pytest.mark.asyncio
async def test_prepare_input_rejects_a_disallowed_extension(db, monkeypatch):
    from app.services import feishu_agent_input as inputs

    receipt = _receipt(attachments=[{"kind": "file", "key": "a", "name": "a.exe"}])
    client = SimpleNamespace(
        download_message_resource=AsyncMock(
            return_value=(b"MZ", "a.exe", "application/octet-stream")
        )
    )
    monkeypatch.setattr(inputs, "_store_upload", AsyncMock())

    with pytest.raises(Exception) as error:
        await prepare_input(
            receipt,
            SimpleNamespace(conversation_id="33333333-3333-3333-3333-333333333333"),
            _agent(attachment_config={"allowed_extensions": [".txt"]}),
            SimpleNamespace(id="44444444-4444-4444-4444-444444444444"),
            client,
        )
    assert getattr(error.value, "msg_key", None) == "feishu_agent_file_type_unsupported"


@pytest.mark.asyncio
async def test_prepare_input_rejects_a_registerd_asset_with_a_disallowed_extension(
    monkeypatch,
):
    from app.services import feishu_agent_input as inputs

    existing = _Asset(original_filename="already.bin")
    monkeypatch.setattr(inputs.Asset, "filter", lambda **kwargs: _FirstQuery(existing))
    monkeypatch.setattr(inputs, "_store_upload", AsyncMock())
    receipt = _receipt(attachments=[{"kind": "file", "key": "a", "name": "a.txt"}])

    with pytest.raises(Exception) as error:
        await prepare_input(
            receipt,
            SimpleNamespace(conversation_id="33333333-3333-3333-3333-333333333333"),
            _agent(
                attachment_config={
                    "allowed_extensions": [".txt"],
                    "max_file_size": 1024,
                }
            ),
            SimpleNamespace(id="44444444-4444-4444-4444-444444444444"),
            None,
        )
    assert getattr(error.value, "msg_key", None) == "feishu_agent_file_type_unsupported"


@pytest.mark.asyncio
async def test_prepare_input_rejects_a_registered_asset_that_is_too_large(monkeypatch):
    from app.services import feishu_agent_input as inputs

    existing = _Asset(size=10 * 1024 * 1024)
    monkeypatch.setattr(inputs.Asset, "filter", lambda **kwargs: _FirstQuery(existing))
    receipt = _receipt(attachments=[{"kind": "file", "key": "a", "name": "a.txt"}])

    with pytest.raises(Exception) as error:
        await prepare_input(
            receipt,
            SimpleNamespace(conversation_id="33333333-3333-3333-3333-333333333333"),
            _agent(attachment_config={"max_file_size": 1024}),
            SimpleNamespace(id="44444444-4444-4444-4444-444444444444"),
            None,
        )
    assert getattr(error.value, "msg_key", None) == "feishu_agent_file_too_large"


@pytest.mark.asyncio
async def test_prepare_input_downloads_and_registers_a_new_attachment(monkeypatch):
    from app.services import feishu_agent_input as inputs

    registered = {}

    async def register_bytes(**kwargs):
        registered.update(kwargs)
        return _Asset()

    async def get_or_create_ref(**kwargs):
        return SimpleNamespace(ref="ref-1")

    monkeypatch.setattr(inputs.Asset, "filter", lambda **kwargs: _FirstQuery(None))
    monkeypatch.setattr(inputs, "_store_upload", AsyncMock())
    monkeypatch.setattr(inputs.asset_service, "register_bytes", register_bytes)
    monkeypatch.setattr(inputs.asset_service, "get_or_create_ref", get_or_create_ref)
    client = SimpleNamespace(
        download_message_resource=AsyncMock(
            return_value=(b"hello world", "remote.txt", "text/plain")
        )
    )
    receipt = _receipt(attachments=[{"kind": "file", "key": "file_1", "name": ""}])

    request = await prepare_input(
        receipt,
        SimpleNamespace(conversation_id="33333333-3333-3333-3333-333333333333"),
        _agent(),
        SimpleNamespace(id="44444444-4444-4444-4444-444444444444"),
        client,
    )

    # A missing remote name falls back to the provider mime type.
    assert registered["original_filename"] == "remote.txt"
    assert registered["content_type"] == "text/plain"
    assert registered["team_id"] is None
    assert registered["provenance"]["feishu_message_id"] == "om_1"
    assert request.file_urls[0].filename == "report.txt"
    assert request.file_urls[0].url.startswith("/api/v1/upload/files/")
    assert request.file_urls[0].mime_type == "text/plain"
    assert request.file_urls[0].size == 12


@pytest.mark.asyncio
async def test_prepare_input_infers_a_missing_extension_from_the_mime_type(monkeypatch):
    from app.services import feishu_agent_input as inputs

    registered = {}

    async def register_bytes(**kwargs):
        registered.update(kwargs)
        return _Asset()

    monkeypatch.setattr(inputs.Asset, "filter", lambda **kwargs: _FirstQuery(None))
    monkeypatch.setattr(inputs, "_store_upload", AsyncMock())
    monkeypatch.setattr(inputs.asset_service, "register_bytes", register_bytes)
    monkeypatch.setattr(
        inputs.asset_service,
        "get_or_create_ref",
        AsyncMock(return_value=SimpleNamespace(ref="ref-1")),
    )
    client = SimpleNamespace(
        download_message_resource=AsyncMock(return_value=(b"binary", "", "image/png"))
    )
    receipt = _receipt(
        attachments=[{"kind": "image", "key": "img_1", "name": "picture"}]
    )

    request = await prepare_input(
        receipt,
        SimpleNamespace(conversation_id="33333333-3333-3333-3333-333333333333"),
        _agent(),
        SimpleNamespace(id="44444444-4444-4444-4444-444444444444"),
        client,
    )

    assert registered["original_filename"] == "picture.png"
    assert request.images[0].url.startswith("/api/v1/upload/files/")
    assert request.file_urls == []


class _FirstQuery:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


# --- message_split -----------------------------------------------------------


def bounded(chunks, limit):
    assert all(0 < len(chunk.encode("utf-8")) <= limit for chunk in chunks)


def test_split_preserves_content_and_repeats_table_headers():
    header = "| 名称 | 值 |\n| --- | ---: |\n"
    rows = [f"| 行 {index} | {index} |\n" for index in range(30)]
    chunks = split_message_text("说明：\n" + header + "".join(rows), limit=120)
    bounded(chunks, 120)
    tables = [chunk[chunk.index(header) :] for chunk in chunks if header in chunk]
    recovered = "".join(table[len(header) :] for table in tables)
    assert recovered == "".join(rows)
    assert chunks[0].startswith("说明：\n")


def test_split_repeats_code_fences_and_handles_an_unclosed_fence():
    body = "".join(f"line {index}\n" for index in range(40))
    chunks = split_message_text("```python\n" + body + "```", limit=80)
    bounded(chunks, 80)
    assert all(
        chunk.startswith("```python\n") and chunk.endswith("```") for chunk in chunks
    )
    assert "".join(chunk[len("```python\n") : -3] for chunk in chunks) == body

    # An unterminated fence closes with its own marker so every chunk parses.
    chunks = split_message_text("```python\n" + body, limit=80)
    bounded(chunks, 80)
    assert all(chunk.startswith("```python\n") for chunk in chunks)
    assert all(chunk.endswith("```") for chunk in chunks)


def test_split_handles_crlf_line_endings_and_oversized_rows():
    crlf = "| a |\r\n| --- |\r\n" + "".join(
        f"| 值 {index} |\r\n" for index in range(20)
    )
    chunks = split_message_text(crlf, limit=100)
    bounded(chunks, 100)
    header = "| a |\r\n| --- |\r\n"
    assert all(chunk.startswith(header) for chunk in chunks)
    rows = [
        line + "\r\n"
        for chunk in chunks
        for line in chunk[len(header) :].split("\r\n")
        if line
    ]
    assert rows == [f"| 值 {index} |\r\n" for index in range(20)]

    # A row wider than the whole budget keeps its column structure.
    wide = "| a | b |\n| --- | --- |\n" + f"|{'很长的值' * 20}|x|\n"
    chunks = split_message_text(wide, limit=60)
    bounded(chunks, 60)
    rows = [
        line for chunk in chunks for line in chunk.splitlines() if line.startswith("|")
    ]
    assert all(line.count("|") == 3 for line in rows)


def test_split_prefers_paragraph_then_line_then_sentence_boundaries():
    paragraphs = "第一段。" * 6 + "\n\n" + "第二段。" * 6
    chunks = split_message_text(paragraphs, limit=100)
    bounded(chunks, 100)
    assert "".join(chunks) == paragraphs
    # The first paragraph fits whole, so the break lands on the blank line.
    assert chunks[0] == "第一段。" * 6 + "\n\n"

    lines = "第一行\n" * 12
    chunks = split_message_text(lines, limit=40)
    bounded(chunks, 40)
    assert "".join(chunks) == lines
    assert all(chunk.endswith("\n") for chunk in chunks)

    sentences = "句子一。句子二。句子三。" * 5
    chunks = split_message_text(sentences, limit=30)
    bounded(chunks, 30)
    assert "".join(chunks) == sentences
    assert all(chunk.endswith("。") for chunk in chunks)


def test_split_rejects_limits_that_cannot_hold_one_character():
    with pytest.raises(ValueError, match="Unicode character"):
        split_message_text("🙂", limit=1)


def test_split_preserves_escaped_pipes_and_inline_code_cells():
    from app.services.message_split import _cells

    row = "| a \\| b | `c | d` |\n| --- | --- |\n"
    chunks = split_message_text(row * 20, limit=70)
    bounded(chunks, 70)
    # Every data row keeps two cells even though it contains three pipes.
    data_rows = [
        line
        for chunk in chunks
        for line in chunk.splitlines()
        if line.startswith("| a")
    ]
    assert data_rows
    assert all(_cells(line) == [" a \\| b ", " `c | d` "] for line in data_rows)


def test_split_returns_the_original_text_when_it_fits():
    assert split_message_text("short") == ["short"]
    assert split_message_text("") == []
    with pytest.raises(ValueError):
        split_message_text("x", limit=0)
