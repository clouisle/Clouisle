from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.feishu import FeishuAPIError
from app.services import feishu_tabular as tabular


@pytest.fixture(autouse=True)
def content_limit(monkeypatch):
    monkeypatch.setattr(
        tabular, "content_limit_bytes", AsyncMock(return_value=10 * 1024 * 1024)
    )


def envelope(data):
    return {"code": 0, "data": data}


def page(items, **kwargs):
    return envelope({"items": items, "has_more": False, **kwargs})


@pytest.mark.asyncio
async def test_sheets_cover_every_row_and_column_and_keep_header_and_formula(
    monkeypatch,
):
    monkeypatch.setattr(tabular, "SHEET_CHUNK_ROWS", 2)
    monkeypatch.setattr(tabular, "SHEET_CHUNK_COLUMNS", 2)
    requested = []
    values = {
        "s!A1:B2": [["Header|one", "Header\ntwo"], ["100%", True]],
        "s!C1:D2": [
            ["Third", "Fourth"],
            ["2026-01-01", {"text": "Site", "link": "https://example.com"}],
        ],
        "s!A3:B3": [["last-row", "last-b"]],
        "s!C3:D3": [["last-c", "last-column"]],
    }

    async def request(_client, method, path, *, params=None, **_kwargs):
        assert method == "GET"
        if path.endswith("/query"):
            return envelope(
                {
                    "sheets": [
                        {
                            "sheet_id": "s",
                            "title": "Sheet|title",
                            "resource_type": "sheet",
                            "hidden": True,
                            "grid_properties": {"row_count": 3, "column_count": 4},
                        }
                    ]
                }
            )
        assert path == "/sheets/v2/spreadsheets/book/values_batch_get"
        assert params["dateTimeRenderOption"] == "FormattedString"
        cell_range = params["ranges"]
        requested.append((cell_range, params["valueRenderOption"]))
        rows = [row[:] for row in values[cell_range]]
        if cell_range == "s!A1:B2" and params["valueRenderOption"] == "Formula":
            rows[1][0] = "=SUM(A1:A2)"
        return envelope(
            {
                "revision": 4,
                "valueRanges": [
                    {"range": cell_range, "majorDimension": "ROWS", "values": rows}
                ],
            }
        )

    monkeypatch.setattr(tabular, "request_json", request)
    result = await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "A title")
    text = result.content.decode()
    assert result.filename == "A title.md"
    assert "| Row | A | B | C | D |" in text
    assert "| 1 | Header\\|one | Header<br>two | Third | Fourth |" in text
    assert "100% (source: =SUM\\(A1:A2\\))" in text
    assert '"link":"https://example.com"' in text
    assert "| 3 | last-row | last-b | last-c | last-column |" in text
    assert len(requested) == 8
    assert {item[0] for item in requested} == set(values)
    assert result.warnings and "array formulas" in result.warnings[0]


@pytest.mark.asyncio
async def test_empty_cells_and_empty_range_preserve_grid_coordinates(monkeypatch):
    responses = [
        envelope(
            {
                "sheets": [
                    {
                        "sheet_id": "s",
                        "grid_properties": {"row_count": 2, "column_count": 2},
                    }
                ]
            }
        ),
        envelope({"valueRanges": [{"range": "", "majorDimension": "ROWS"}]}),
        envelope(
            {"valueRanges": [{"range": "", "majorDimension": "ROWS", "values": []}]}
        ),
    ]
    monkeypatch.setattr(tabular, "request_json", AsyncMock(side_effect=responses))
    result = await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "Title")
    text = result.content.decode()
    assert "| 1 |  |  |" in text and "| 2 |  |  |" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken",
    [
        {"valueRanges": []},
        {
            "valueRanges": [
                {"range": "wrong!A1:B2", "majorDimension": "ROWS", "values": []}
            ]
        },
        {
            "valueRanges": [
                {"range": "s!A1:B2", "majorDimension": "COLUMNS", "values": []}
            ]
        },
        {
            "valueRanges": [
                {"range": "s!A1:B2", "majorDimension": "ROWS", "values": [[1, 2, 3]]}
            ]
        },
        {
            "valueRanges": [
                {"range": "s!A1:B2", "majorDimension": "ROWS", "values": [[], [], []]}
            ]
        },
    ],
)
async def test_malformed_sheet_ranges_fail_closed(monkeypatch, broken):
    request = AsyncMock(
        side_effect=[
            envelope(
                {
                    "sheets": [
                        {
                            "sheet_id": "s",
                            "grid_properties": {"row_count": 2, "column_count": 2},
                        }
                    ]
                }
            ),
            envelope(broken),
        ]
    )
    monkeypatch.setattr(tabular, "request_json", request)
    with pytest.raises(FeishuAPIError):
        await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "Title")


@pytest.mark.asyncio
async def test_sheet_revision_change_aborts_import(monkeypatch):
    def values(revision):
        return envelope(
            {
                "revision": revision,
                "valueRanges": [
                    {"range": "s!A1:A1", "majorDimension": "ROWS", "values": [[1]]}
                ],
            }
        )

    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                envelope(
                    {
                        "sheets": [
                            {
                                "sheet_id": "s",
                                "grid_properties": {"row_count": 1, "column_count": 1},
                            }
                        ]
                    }
                ),
                values(1),
                values(2),
            ]
        ),
    )
    with pytest.raises(FeishuAPIError, match="changed during import"):
        await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "Title")


@pytest.mark.asyncio
async def test_bitable_paginates_all_inventories_and_preserves_schema_and_values(
    monkeypatch,
):
    requested = []
    fields = [
        {"field_id": "f1", "field_name": "Name|value", "type": 1, "ui_type": "Text"},
        {
            "field_id": "f2",
            "field_name": "Calc",
            "type": 20,
            "ui_type": "Formula",
            "property": {"formula_expression": "SUM([Amount])", "formatter": "0.00%"},
        },
        {
            "field_id": "f3",
            "field_name": "Date",
            "type": 5,
            "property": {"date_formatter": "yyyy/MM/dd"},
        },
    ]

    async def request(_client, method, path, *, params=None, json=None):
        requested.append((method, path, dict(params), json))
        token = params.get("page_token")
        if path.endswith("/tables"):
            return (
                page([{"table_id": "t", "name": "First"}])
                if token
                else page([], has_more=True, page_token="tables-next")
            )
        if path.endswith("/fields"):
            return (
                page(fields)
                if token
                else page([], has_more=True, page_token="fields-next")
            )
        assert path.endswith("/records/search") and method == "POST"
        assert json == {"automatic_fields": True}
        assert params["page_size"] == 500
        record = {
            "record_id": "r1" if not token else "r2",
            "fields": {
                "Name|value": [
                    {"text": "Alice", "type": "text"},
                    {"text": "@Bob", "token": "user-id", "type": "mention"},
                ],
                "Calc": {"type": 2, "value": [0.25]},
                "Date": 0,
                "Unexpected": {
                    "link_record_ids": ["other-record"],
                    "text": "Visible label",
                },
            },
            "created_time": 1,
        }
        return page(
            [record],
            total=2,
            has_more=not token,
            **({"page_token": "records-next"} if not token else {}),
        )

    monkeypatch.setattr(tabular, "request_json", request)
    result = await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")
    text = result.content.decode()
    assert "### Schema" in text and "### Records" in text
    assert "SUM\\(\\[Amount\\]\\)" in text and "0.00%" in text
    assert (
        "| Record ID | Name\\|value | Calc | Date | Unexpected | Record metadata |"
        in text
    )
    assert "1970-01-01T00:00:00+00:00 \\(epoch ms: 0\\)" in text
    assert "Alice" in text and "@Bob" in text and "user-id" in text
    assert "other-record" in text and "Visible label" in text
    assert "| r1 |" in text and "| r2 |" in text
    assert len(requested) == 6
    assert "absent from schema" in result.warnings[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pages",
    [
        [{"items": [], "has_more": True}],
        [{"items": [], "has_more": True, "page_token": "same"}] * 2,
        [{"items": [], "has_more": False, "total": 1}],
        [{"items": [], "total": 0}],
        [{"items": ["not-an-item"], "has_more": False}],
        [
            {"items": [{"table_id": "same"}], "has_more": True, "page_token": "next"},
            {"items": [{"table_id": "same"}], "has_more": False},
        ],
        [
            {
                "items": [{"table_id": "t"}],
                "has_more": True,
                "page_token": "next",
                "total": 1,
            },
            {"items": [], "has_more": False, "total": 2},
        ],
    ],
)
async def test_incomplete_or_invalid_pagination_aborts(monkeypatch, pages):
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(side_effect=[envelope(item) for item in pages]),
    )
    with pytest.raises(FeishuAPIError):
        await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")


@pytest.mark.asyncio
async def test_bitable_attachments_extract_images_and_documents_and_warn_unsupported(
    monkeypatch,
):
    from app.services import feishu_rich_content

    attachments = [
        {
            "file_token": "image",
            "name": "photo.png",
            "type": "image/png",
            "url": "https://untrusted.example/ignored?extra=%7B%22bitablePerm%22%3A%7B%22tableId%22%3A%22t%22%7D%7D",
        },
        {"file_token": "text", "name": "notes.txt", "type": "text/plain"},
        {"file_token": "binary", "name": "archive.zip", "type": "application/zip"},
    ]
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                page([{"table_id": "t", "name": "Files"}]),
                page([{"field_id": "f", "field_name": "Files", "type": 17}]),
                page([{"record_id": "r", "fields": {"Files": attachments}}]),
            ]
        ),
    )
    downloads = AsyncMock(
        side_effect=[
            (b"image-bytes", "image/png"),
            (b"hello", "text/plain"),
            (b"zip", "application/zip"),
        ]
    )
    monkeypatch.setattr(tabular, "download_media", downloads)
    extractor = AsyncMock(side_effect=["Real text | from\nattachment", None])
    monkeypatch.setattr(feishu_rich_content, "extract_attachment_text", extractor)
    result = await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")
    text = result.content.decode()
    assert "![photo.png](data:image/png;base64,aW1hZ2UtYnl0ZXM=)" in text
    assert "Real text \\| from<br>attachment" in text
    assert "archive.zip" in text and "binary" in text
    assert any(
        "archive.zip" in warning and "no extractable text" in warning
        for warning in result.warnings
    )
    assert downloads.await_args_list[0].kwargs == {
        "extra": '{"bitablePerm":{"tableId":"t"}}'
    }
    assert extractor.await_count == 2


@pytest.mark.asyncio
async def test_attachment_download_permission_error_is_not_hidden(monkeypatch):
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                page([{"table_id": "t"}]),
                page([{"field_id": "f", "field_name": "Files", "type": 17}]),
                page(
                    [
                        {
                            "record_id": "r",
                            "fields": {"Files": [{"file_token": "denied"}]},
                        }
                    ]
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        tabular,
        "download_media",
        AsyncMock(side_effect=FeishuAPIError("permission", code=1254303)),
    )
    with pytest.raises(FeishuAPIError, match="permission"):
        await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")


@pytest.mark.asyncio
async def test_unknown_sheet_resource_is_explicitly_reported(monkeypatch):
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            return_value=envelope(
                {
                    "sheets": [
                        {
                            "sheet_id": "board",
                            "title": "Board",
                            "resource_type": "board",
                        },
                    ]
                }
            )
        ),
    )
    result = await tabular.load_tabular(SimpleNamespace(), "sheet", "app", "Book")
    assert any("non-grid resource board" in warning for warning in result.warnings)
    assert "Board" in result.content.decode()


@pytest.mark.asyncio
async def test_sheet_cell_embedded_image_uses_official_file_token(monkeypatch):
    image = {
        "fileToken": "sheet-image",
        "type": "embed-image",
        "text": "",
        "width": 10,
        "height": 20,
    }
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                envelope(
                    {
                        "sheets": [
                            {
                                "sheet_id": "s",
                                "grid_properties": {"row_count": 1, "column_count": 1},
                            }
                        ]
                    }
                ),
                envelope(
                    {
                        "valueRanges": [
                            {
                                "range": "s!A1:A1",
                                "majorDimension": "ROWS",
                                "values": [[image]],
                            }
                        ]
                    }
                ),
                envelope(
                    {
                        "valueRanges": [
                            {
                                "range": "s!A1:A1",
                                "majorDimension": "ROWS",
                                "values": [[image]],
                            }
                        ]
                    }
                ),
            ]
        ),
    )
    download = AsyncMock(return_value=(b"pixels", "image/png"))
    monkeypatch.setattr(tabular, "download_media", download)
    result = await tabular.load_tabular(SimpleNamespace(), "sheet", "app", "Images")
    assert "data:image/png;base64,cGl4ZWxz" in result.content.decode()
    download.assert_awaited_once_with(
        download.await_args.args[0], "sheet-image", extra=None
    )


@pytest.mark.asyncio
async def test_content_limit_fails_instead_of_truncating(monkeypatch):
    monkeypatch.setattr(tabular, "content_limit_bytes", AsyncMock(return_value=5))
    request = AsyncMock()
    monkeypatch.setattr(tabular, "request_json", request)
    with pytest.raises(FeishuAPIError, match="upload limit"):
        await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Long title")
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields,records",
    [
        ([{"field_id": "f", "field_name": "Name"}], []),
        (
            [
                {"field_id": "f", "field_name": "Name", "type": 1},
                {"field_id": "f2", "field_name": "Name", "type": 1},
            ],
            [],
        ),
        ([{"field_id": "f", "field_name": "Name", "type": 1}], [{"record_id": "r"}]),
    ],
)
async def test_malformed_base_schema_or_records_fail_closed(
    monkeypatch, fields, records
):
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                page([{"table_id": "t"}]),
                page(fields),
                page(records),
            ]
        ),
    )
    with pytest.raises(FeishuAPIError):
        await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")


@pytest.mark.asyncio
async def test_failed_attachment_extraction_warns_and_retains_metadata(monkeypatch):
    from app.services import feishu_rich_content

    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(
            side_effect=[
                page([{"table_id": "t"}]),
                page([{"field_id": "f", "field_name": "File", "type": 17}]),
                page(
                    [
                        {
                            "record_id": "r",
                            "fields": {
                                "File": [
                                    {
                                        "file_token": "doc",
                                        "name": "corrupt.pdf",
                                        "size": 5,
                                    }
                                ]
                            },
                        }
                    ]
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        tabular,
        "download_media",
        AsyncMock(return_value=(b"broken", "application/pdf")),
    )
    monkeypatch.setattr(
        feishu_rich_content,
        "extract_attachment_text",
        AsyncMock(side_effect=ValueError("parser error")),
    )
    result = await tabular.load_tabular(SimpleNamespace(), "bitable", "app", "Base")
    assert any("text extraction failed" in warning for warning in result.warnings)
    assert (
        "corrupt.pdf" in result.content.decode()
        and '"size":5' in result.content.decode()
    )


def test_column_names_beyond_open_ended_api_limit():
    assert tabular._column(26) == "Z"
    assert tabular._column(27) == "AA"
    assert tabular._column(101) == "CW"
    assert tabular._column(703) == "AAA"


@pytest.mark.asyncio
async def test_attachment_aggregate_limit_and_duplicate_cache(monkeypatch):
    from app.services import feishu_rich_content

    download = AsyncMock(return_value=(b"x" * 6, "application/octet-stream"))
    monkeypatch.setattr(tabular, "download_media", download)
    monkeypatch.setattr(
        feishu_rich_content, "extract_attachment_text", AsyncMock(return_value=None)
    )
    renderer = tabular._Renderer(SimpleNamespace(), 10)
    first = {"file_token": "one", "name": "one.bin"}
    await renderer.attachment(first)
    await renderer.attachment(first)
    assert download.await_count == 1
    with pytest.raises(FeishuAPIError, match="attachments exceed"):
        await renderer.attachment({"file_token": "two", "name": "two.bin"})


@pytest.mark.asyncio
async def test_unsupported_image_is_warned_not_embedded(monkeypatch):
    monkeypatch.setattr(
        tabular, "download_media", AsyncMock(return_value=(b"TIFF", "image/tiff"))
    )
    renderer = tabular._Renderer(SimpleNamespace(), 100)
    text = await renderer.attachment(
        {"file_token": "tiff", "name": "scan.tiff", "type": "image/tiff"}
    )
    assert "data:" not in text and "scan.tiff" in text
    assert any("unsupported image format" in warning for warning in renderer.warnings)


@pytest.mark.asyncio
async def test_attachment_infrastructure_failure_propagates(monkeypatch):
    from app.services import feishu_rich_content

    monkeypatch.setattr(
        tabular, "download_media", AsyncMock(return_value=(b"doc", "application/pdf"))
    )
    monkeypatch.setattr(
        feishu_rich_content,
        "extract_attachment_text",
        AsyncMock(side_effect=OSError("storage unavailable")),
    )
    renderer = tabular._Renderer(SimpleNamespace(), 100)
    with pytest.raises(OSError, match="storage unavailable"):
        await renderer.attachment({"file_token": "pdf", "name": "document.pdf"})


def test_parsed_attachment_images_remain_promotable_with_safe_table_text():
    rendered = tabular._attachment_text(
        "text | table\n![chart](data:image/png;base64,cGl4ZWxz)"
    )
    assert rendered == "text \\| table<br>![chart](data:image/png;base64,cGl4ZWxz)"


@pytest.mark.asyncio
async def test_generic_octet_stream_image_is_sniffed(monkeypatch):
    content = b"\x89PNG\r\n\x1a\n" + b"pixels"
    monkeypatch.setattr(
        tabular,
        "download_media",
        AsyncMock(return_value=(content, "application/octet-stream")),
    )
    renderer = tabular._Renderer(SimpleNamespace(), 100)
    text = await renderer.attachment({"file_token": "image", "name": "image.png"})
    assert "data:image/png;base64," in text
    assert renderer.warnings == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sheets",
    [
        None,
        [None],
        [{"sheet_id": "s"}],
        [{"sheet_id": "s", "grid_properties": {"row_count": -1, "column_count": 1}}],
        [{"sheet_id": "s", "grid_properties": {"row_count": True, "column_count": 1}}],
    ],
)
async def test_invalid_sheet_metadata_aborts_before_partial_import(monkeypatch, sheets):
    monkeypatch.setattr(
        tabular, "request_json", AsyncMock(return_value=envelope({"sheets": sheets}))
    )
    with pytest.raises(FeishuAPIError):
        await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "Broken")


@pytest.mark.asyncio
async def test_repeated_sheet_identity_aborts_instead_of_duplicate_content(monkeypatch):
    sheet = {"sheet_id": "s", "grid_properties": {"row_count": 0, "column_count": 0}}
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(return_value=envelope({"sheets": [sheet, sheet]})),
    )
    with pytest.raises(FeishuAPIError, match="repeated"):
        await tabular.load_tabular(SimpleNamespace(), "sheet", "book", "Repeated")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value_range",
    [
        {"range": "other!A1", "majorDimension": "ROWS", "values": []},
        {"range": "s!A1", "majorDimension": "COLUMNS", "values": []},
        {"range": "s!A1", "majorDimension": "ROWS", "values": None},
        {"range": "s!A1", "majorDimension": "ROWS", "values": [[1], [2]]},
        {"range": "s!A1", "majorDimension": "ROWS", "values": [[1, 2]]},
        {"range": "s!A1", "majorDimension": "ROWS", "values": ["not a row"]},
        {"range": "", "majorDimension": "ROWS", "values": [[1]]},
    ],
)
async def test_sheet_range_mismatch_never_becomes_silent_data_loss(
    monkeypatch, value_range
):
    monkeypatch.setattr(
        tabular,
        "request_json",
        AsyncMock(return_value=envelope({"valueRanges": [value_range]})),
    )
    with pytest.raises(FeishuAPIError):
        await tabular._sheet_values(
            SimpleNamespace(), "/values", "s!A1", 1, 1, "FormattedValue", [None]
        )
