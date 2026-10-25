"""Read complete Feishu Sheets and Bases using their official read APIs."""

import html
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from app.integrations.feishu import FeishuAPIError, FeishuClient
from app.integrations.feishu_content import (
    FeishuContent,
    content_limit_bytes,
    download_media,
    request_json,
)

# Explicit end cells avoid the API's 100-column open-ended-range restriction.
SHEET_CHUNK_ROWS = 200
SHEET_CHUNK_COLUMNS = 100


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _attachment_text(text: str) -> str:
    """Escape table text while retaining parser-generated, supported media URIs."""
    from app.services.document_processor import ALLOWED_MEDIA_MIME_TYPES

    parts: list[str] = []
    offset = 0
    for match in re.finditer(
        r"!\[([^\]\n]*)\]\((data:([^;,]+);base64,[A-Za-z0-9+/=]+)\)", text
    ):
        if match[3] not in ALLOWED_MEDIA_MIME_TYPES:
            continue
        parts.append(_escape(text[offset : match.start()]))
        parts.append(f"![{_escape(match[1])}]({match[2]})")
        offset = match.end()
    parts.append(_escape(text[offset:]))
    return "".join(parts)


class _Output(list[str]):
    """Apply the configured file cap during assembly, before a huge allocation."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.size = 0

    def append(self, value: str) -> None:
        self.size += len(value.encode("utf-8")) + 1
        if self.size > self.limit:
            raise FeishuAPIError(
                "Feishu tabular content exceeds the knowledge-base upload limit"
            )
        super().append(value)

    def extend(self, values) -> None:
        for value in values:
            self.append(value)


def _escape(value: str) -> str:
    """Escape source text without allowing it to alter Markdown structure."""
    value = html.escape(value, quote=False).replace("\\", "\\\\")
    for char in "`*_{}[]()#!|":
        value = value.replace(char, "\\" + char)
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _row(values: list[str]) -> str:
    return "| " + " | ".join(values) + " |"


def _data(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    if not isinstance(data, dict):
        raise FeishuAPIError("Feishu returned invalid tabular data")
    return data


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise FeishuAPIError(f"Feishu returned tabular data without {key}")
    return value


def _column(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


async def _pages(
    client: FeishuClient,
    path: str,
    *,
    page_size: int,
    identity: str,
    method: str = "GET",
    payload: dict | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    tokens: set[str] = set()
    ids: set[str] = set()
    params: dict[str, Any] = {"page_size": page_size}
    total: int | None = None
    while True:
        body = await request_json(client, method, path, params=params, json=payload)
        data = _data(body)
        page = data.get("items")
        if not isinstance(page, list) or any(not isinstance(x, dict) for x in page):
            raise FeishuAPIError("Feishu returned an invalid tabular page")
        if not isinstance(data.get("has_more"), bool):
            raise FeishuAPIError("Feishu did not confirm tabular pagination completion")
        if "total" in data:
            count = data["total"]
            if (
                type(count) is not int
                or count < 0
                or (total is not None and total != count)
            ):
                raise FeishuAPIError(
                    "Feishu tabular inventory changed during pagination"
                )
            total = count
        for item in page:
            identifier = _required_string(item, identity)
            if identifier in ids:
                raise FeishuAPIError("Feishu repeated a tabular item; import aborted")
            ids.add(identifier)
        items.extend(page)
        if not data["has_more"]:
            if total is not None and len(items) != total:
                raise FeishuAPIError("Feishu returned an incomplete tabular inventory")
            return items
        token = data.get("page_token")
        if not isinstance(token, str) or not token or token in tokens:
            raise FeishuAPIError("Feishu tabular pagination did not advance")
        tokens.add(token)
        params["page_token"] = token


class _Renderer:
    def __init__(self, client: FeishuClient, limit: int):
        self.client = client
        self.warnings: list[str] = []
        self.attachments: dict[tuple[str, str | None], str] = {}
        self.limit = limit
        self.downloaded_bytes = 0

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    async def attachment(self, value: dict[str, Any]) -> str:
        token = _required_string(value, "file_token")
        name = str(value.get("name") or token)
        # Only pass API-provided permission context, never fetch its URL/host.
        extra = None
        for key in ("url", "tmp_url"):
            if isinstance(value.get(key), str):
                extra = parse_qs(urlsplit(value[key]).query).get("extra", [None])[0]
                if extra:
                    break
        cache_key = (token, extra)
        if cache_key not in self.attachments:
            content, content_type = await download_media(
                self.client, token, extra=extra
            )
            self.downloaded_bytes += len(content)
            if self.downloaded_bytes > self.limit:
                raise FeishuAPIError(
                    "Feishu tabular attachments exceed the knowledge-base upload limit"
                )
            from app.services.feishu_rich_content import (
                image_data_uri,
                extract_attachment_text,
            )

            mime = content_type.split(";", 1)[0].strip().lower()
            image_uri = image_data_uri(content, mime)
            if image_uri:
                rendered = f"![{_escape(name)}]({image_uri})"
            elif (
                mime.startswith("image/")
                or str(value.get("type", "")).startswith("image/")
                or value.get("type") == "embed-image"
            ):
                self.warn(
                    f"Attachment {name}: unsupported image format; metadata retained."
                )
                rendered = _escape(name)
            else:
                try:
                    text = await extract_attachment_text(content, name, mime)
                except ValueError:
                    text = None
                    self.warn(
                        f"Attachment {name}: text extraction failed; metadata retained."
                    )
                if text:
                    rendered = _escape(name) + ": " + _attachment_text(text)
                else:
                    self.warn(
                        f"Attachment {name}: no extractable text; metadata retained."
                    )
                    rendered = _escape(name)
            self.attachments[cache_key] = rendered
        metadata = {k: v for k, v in value.items() if k not in ("url", "tmp_url")}
        return self.attachments[cache_key] + " (" + _escape(_json(metadata)) + ")"

    async def value(self, value: Any, field: dict | None = None) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            if field and field.get("type") in (5, 1001, 1002):
                try:
                    date = datetime.fromtimestamp(
                        value / 1000, timezone.utc
                    ).isoformat()
                    return _escape(f"{date} (epoch ms: {value})")
                except (ValueError, OverflowError, OSError):
                    self.warn(
                        "A date value could not be formatted; original timestamp retained."
                    )
            return str(value)
        if isinstance(value, str):
            return _escape(value)
        if isinstance(value, list):
            return "; ".join([await self.value(item, field) for item in value])
        if isinstance(value, dict):
            if value.get("fileToken"):
                token = _required_string(value, "fileToken")
                return await self.attachment(
                    {**value, "file_token": token, "name": value.get("text") or token}
                )
            if value.get("file_token"):
                return await self.attachment(value)
            # Preserve labels, URLs, record IDs and unknown display structures,
            # rather than discarding keys to guess a human-readable value.
            return _escape(_json(value))
        raise FeishuAPIError("Feishu returned an unsupported tabular value")


async def _sheet_values(
    client: FeishuClient,
    path: str,
    cell_range: str,
    rows: int,
    columns: int,
    render_option: str,
    revision: list[int | None],
) -> list[list[Any]]:
    body = await request_json(
        client,
        "GET",
        path,
        params={
            "ranges": cell_range,
            "valueRenderOption": render_option,
            "dateTimeRenderOption": "FormattedString",
            "user_id_type": "open_id",
        },
    )
    data = _data(body)
    ranges = data.get("valueRanges")
    if (
        not isinstance(ranges, list)
        or len(ranges) != 1
        or not isinstance(ranges[0], dict)
    ):
        raise FeishuAPIError("Feishu returned incomplete spreadsheet ranges")
    result = ranges[0]
    if (
        result.get("range") not in (cell_range, "")
        or result.get("majorDimension") != "ROWS"
    ):
        raise FeishuAPIError("Feishu returned an unexpected spreadsheet range")
    current_revision = result.get("revision", data.get("revision"))
    if type(current_revision) is int:
        if revision[0] is not None and current_revision != revision[0]:
            raise FeishuAPIError("Feishu spreadsheet changed during import")
        revision[0] = current_revision
    values = result.get("values", [] if result.get("range") == "" else None)
    if not isinstance(values, list) or len(values) > rows:
        raise FeishuAPIError("Feishu returned invalid spreadsheet rows")
    if any(not isinstance(row, list) or len(row) > columns for row in values):
        raise FeishuAPIError("Feishu returned invalid spreadsheet columns")
    if result.get("range") == "" and any(values):
        raise FeishuAPIError("Feishu returned spreadsheet values without a range")
    return values


async def _sheets(
    client: FeishuClient, token: str, output: list[str], renderer: _Renderer
) -> None:
    root = f"/sheets/v3/spreadsheets/{quote(token, safe='')}/sheets"
    sheets = _data(await request_json(client, "GET", root + "/query")).get("sheets")
    if not isinstance(sheets, list) or any(
        not isinstance(sheet, dict) for sheet in sheets
    ):
        raise FeishuAPIError("Feishu returned invalid spreadsheet metadata")
    seen: set[str] = set()
    revision: list[int | None] = [None]
    values_path = f"/sheets/v2/spreadsheets/{quote(token, safe='')}/values_batch_get"
    for sheet in sheets:
        sheet_id = _required_string(sheet, "sheet_id")
        if sheet_id in seen:
            raise FeishuAPIError("Feishu repeated a spreadsheet sheet")
        seen.add(sheet_id)
        output.extend(
            [
                "## " + _escape(str(sheet.get("title") or sheet_id)),
                "",
                "Sheet metadata: " + _escape(_json(sheet)),
                "",
            ]
        )
        if sheet.get("resource_type", "sheet") != "sheet":
            renderer.warn(
                f"Worksheet {sheet_id}: non-grid resource {sheet.get('resource_type')} has no readable cell API."
            )
            continue
        grid = sheet.get("grid_properties")
        if not isinstance(grid, dict):
            raise FeishuAPIError("Feishu spreadsheet is missing its grid dimensions")
        rows, columns = grid.get("row_count"), grid.get("column_count")
        if type(rows) is not int or type(columns) is not int or rows < 0 or columns < 0:
            raise FeishuAPIError("Feishu returned invalid spreadsheet dimensions")
        for first_row in range(1, rows + 1, SHEET_CHUNK_ROWS):
            last_row = min(rows, first_row + SHEET_CHUNK_ROWS - 1)
            # Assemble one row band at a time, preserving every column and row.
            band: list[list[str]] = [[] for _ in range(last_row - first_row + 1)]
            for first_column in range(1, columns + 1, SHEET_CHUNK_COLUMNS):
                last_column = min(columns, first_column + SHEET_CHUNK_COLUMNS - 1)
                count = last_column - first_column + 1
                cell_range = f"{sheet_id}!{_column(first_column)}{first_row}:{_column(last_column)}{last_row}"
                display = await _sheet_values(
                    client,
                    values_path,
                    cell_range,
                    len(band),
                    count,
                    "FormattedValue",
                    revision,
                )
                formulas = await _sheet_values(
                    client,
                    values_path,
                    cell_range,
                    len(band),
                    count,
                    "Formula",
                    revision,
                )
                for row_index, row in enumerate(band):
                    shown = display[row_index] if row_index < len(display) else []
                    raw = formulas[row_index] if row_index < len(formulas) else []
                    for col_index in range(count):
                        value = shown[col_index] if col_index < len(shown) else None
                        original = raw[col_index] if col_index < len(raw) else None
                        rendered = await renderer.value(value)
                        if original != value and original is not None:
                            rendered += (
                                " (source: " + await renderer.value(original) + ")"
                            )
                        row.append(rendered)
            if columns:
                output.extend(
                    [
                        f"### Rows {first_row}–{last_row}",
                        "",
                        _row(["Row"] + [_column(col) for col in range(1, columns + 1)]),
                        _row(["---"] * (columns + 1)),
                    ]
                )
                output.extend(
                    _row([str(first_row + index)] + row)
                    for index, row in enumerate(band)
                )
                output.append("")
    renderer.warn(
        "Sheets API does not calculate cross-sheet references or array formulas; source formulas are retained. Floating images/charts are not cell values and are not extracted."
    )


async def _bitable(
    client: FeishuClient, token: str, output: list[str], renderer: _Renderer
) -> None:
    root = f"/bitable/v1/apps/{quote(token, safe='')}/tables"
    tables = await _pages(client, root, page_size=100, identity="table_id")
    for table in tables:
        table_id = _required_string(table, "table_id")
        path = root + "/" + quote(table_id, safe="")
        fields = await _pages(
            client, path + "/fields", page_size=100, identity="field_id"
        )
        names: set[str] = set()
        for field in fields:
            name = _required_string(field, "field_name")
            if name in names or type(field.get("type")) is not int:
                raise FeishuAPIError("Feishu returned an invalid Base field schema")
            names.add(name)
        records = await _pages(
            client,
            path + "/records/search",
            page_size=500,
            identity="record_id",
            method="POST",
            payload={"automatic_fields": True},
        )
        # Undocumented/new fields must not vanish simply because metadata lagged.
        extras: set[str] = set()
        for record in records:
            values = record.get("fields")
            if not isinstance(values, dict):
                raise FeishuAPIError("Feishu returned a Base record without fields")
            extras.update(values.keys() - names)
        output.extend(
            [
                "## " + _escape(str(table.get("name") or table_id)),
                "",
                "Table metadata: " + _escape(_json(table)),
                "",
                "### Schema",
                "",
                _row(["Field", "Type", "Definition"]),
                _row(["---"] * 3),
            ]
        )
        for field in fields:
            output.append(
                _row(
                    [
                        _escape(field["field_name"]),
                        _escape(str(field.get("ui_type") or field["type"])),
                        _escape(_json(field)),
                    ]
                )
            )
        for name in sorted(extras):
            output.append(
                _row(
                    [
                        _escape(name),
                        "Unknown",
                        "Returned in records without field metadata",
                    ]
                )
            )
            renderer.warn(
                f"Table {table_id}: field {name} was absent from schema; values retained."
            )
        ordered = [field["field_name"] for field in fields] + sorted(extras)
        by_name = {field["field_name"]: field for field in fields}
        output.extend(
            [
                "",
                "### Records",
                "",
                _row(
                    ["Record ID"]
                    + [_escape(name) for name in ordered]
                    + ["Record metadata"]
                ),
                _row(["---"] * (len(ordered) + 2)),
            ]
        )
        for record in records:
            values = record["fields"]
            cells = [
                await renderer.value(values.get(name), by_name.get(name))
                for name in ordered
            ]
            metadata = {
                key: value
                for key, value in record.items()
                if key not in ("fields", "record_id")
            }
            output.append(
                _row(
                    [_escape(record["record_id"])] + cells + [_escape(_json(metadata))]
                )
            )
        output.append("")


async def load_tabular(
    client: FeishuClient, obj_type: str, token: str, title: str
) -> FeishuContent:
    """Import all sheets/tables, rejecting incomplete inventories and malformed pages."""
    limit = await content_limit_bytes()
    renderer = _Renderer(client, limit)
    output = _Output(limit)
    output.extend(["# " + _escape(title), ""])
    if obj_type == "sheet":
        await _sheets(client, token, output, renderer)
    elif obj_type == "bitable":
        await _bitable(client, token, output, renderer)
    else:
        raise FeishuAPIError("Unsupported Feishu tabular object type")
    if renderer.warnings:
        output.extend(
            ["## Import warnings", ""]
            + ["- " + _escape(item) for item in renderer.warnings]
            + [""]
        )
    return FeishuContent(
        filename=title + ".md",
        content="\n".join(output).encode("utf-8"),
        warnings=renderer.warnings,
    )
