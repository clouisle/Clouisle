from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from openpyxl.drawing.image import Image as WorksheetImage
from openpyxl.drawing.spreadsheet_drawing import (
    AbsoluteAnchor,
    AnchorMarker,
    TwoCellAnchor,
)
from openpyxl.drawing.xdr import XDRPoint2D, XDRPositiveSize2D
from PIL import Image as PILImage

from app.services.kb_xlsx_images import (
    XlsxImageExtractionError,
    extract_xlsx_images,
)


def _png_bytes(color: str = "red") -> bytes:
    output = BytesIO()
    PILImage.new("RGB", (2, 3), color=color).save(output, format="PNG")
    return output.getvalue()


def _workbook_with_images(*, image_count: int = 1) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Quarterly Results"
    for index in range(image_count):
        worksheet.add_image(
            WorksheetImage(BytesIO(_png_bytes())), f"{chr(66 + index)}{index + 3}"
        )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _rewrite_package(content: bytes, transform) -> bytes:
    source = ZipFile(BytesIO(content))
    output = BytesIO()
    with source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            payload = transform(info.filename, payload)
            target.writestr(info.filename, payload)
        for name, payload in getattr(transform, "extra_entries", ()):
            target.writestr(name, payload)
    return output.getvalue()


def test_extract_xlsx_images_returns_payload_and_cell_position():
    extracted = extract_xlsx_images(_workbook_with_images())

    assert len(extracted) == 1
    image = extracted[0]
    assert image.sheet_name == "Quarterly Results"
    assert image.anchor == "B3"
    assert (image.row, image.column) == (2, 1)
    assert image.content_type == "image/png"
    assert image.data == _png_bytes()
    assert image.end_anchor is None


def test_extract_xlsx_images_preserves_two_cell_anchor_and_offsets():
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Anchored"
    image = WorksheetImage(BytesIO(_png_bytes()))
    image.anchor = TwoCellAnchor(
        _from=AnchorMarker(col=4, row=6, colOff=360, rowOff=720),
        to=AnchorMarker(col=8, row=10, colOff=180, rowOff=240),
    )
    worksheet.add_image(image)
    output = BytesIO()
    workbook.save(output)

    record = extract_xlsx_images(output.getvalue())[0]

    assert record.anchor == "E7"
    assert record.end_anchor == "I11"
    assert (record.row_offset_emu, record.column_offset_emu) == (720, 360)
    assert (record.end_row_offset_emu, record.end_column_offset_emu) == (240, 180)


def test_extract_xlsx_images_rejects_image_count_over_limit():
    with pytest.raises(XlsxImageExtractionError, match="more images"):
        extract_xlsx_images(_workbook_with_images(image_count=2), max_count=1)


def test_extract_xlsx_images_rejects_image_payload_over_limit():
    with pytest.raises(XlsxImageExtractionError, match="byte limit"):
        extract_xlsx_images(_workbook_with_images(), max_image_bytes=1)


def test_extract_xlsx_images_rejects_external_relationships():
    def add_external_relationship(name: str, payload: bytes) -> bytes:
        if name == "_rels/.rels":
            payload = payload.replace(
                b"</Relationships>",
                b'<Relationship Id="rIdExternal" '
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                b'Target="https://example.invalid/" TargetMode="External"/>'
                b"</Relationships>",
            )
        return payload

    with pytest.raises(XlsxImageExtractionError, match="External"):
        extract_xlsx_images(
            _rewrite_package(_workbook_with_images(), add_external_relationship)
        )


def test_extract_xlsx_images_rejects_macro_parts():
    def add_macro_project(name: str, payload: bytes) -> bytes:
        return payload

    add_macro_project.extra_entries = (("xl/vbaProject.bin", b"macro"),)
    with pytest.raises(XlsxImageExtractionError, match="Macro"):
        extract_xlsx_images(
            _rewrite_package(_workbook_with_images(), add_macro_project)
        )


def test_extract_xlsx_images_rejects_unsupported_embedded_format():
    def replace_image(name: str, payload: bytes) -> bytes:
        return (
            b"<svg xmlns='http://www.w3.org/2000/svg'/>"
            if name == "xl/media/image1.png"
            else payload
        )

    with pytest.raises(XlsxImageExtractionError, match="Invalid or unsafe"):
        extract_xlsx_images(_rewrite_package(_workbook_with_images(), replace_image))


def test_extract_xlsx_images_rejects_absolute_anchors():
    workbook = Workbook()
    worksheet = workbook.active
    image = WorksheetImage(BytesIO(_png_bytes()))
    image.anchor = AbsoluteAnchor(
        pos=XDRPoint2D(x=0, y=0),
        ext=XDRPositiveSize2D(cx=914400, cy=914400),
    )
    worksheet.add_image(image)
    output = BytesIO()
    workbook.save(output)

    with pytest.raises(XlsxImageExtractionError, match="Absolute"):
        extract_xlsx_images(output.getvalue())


def test_extract_xlsx_images_rejects_compressed_input_over_limit():
    with pytest.raises(XlsxImageExtractionError, match="compressed size"):
        extract_xlsx_images(b"0" * (64 * 1024 * 1024 + 1))
