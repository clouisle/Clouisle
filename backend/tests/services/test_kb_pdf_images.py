from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.services.kb_pdf_images import (
    EncryptedPDFError,
    InvalidPDFError,
    PDFResourceLimitError,
    iter_pdf_pages,
)


def make_pdf(*page_contents: bytes, encrypt: bool = False) -> bytes:
    writer = PdfWriter()
    for contents in page_contents:
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        stream.set_data(contents)
        page.replace_contents(stream)
        if b"Tf" in contents:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
    if encrypt:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_mixed_native_text_and_vector_page_keeps_both_text_and_image():
    text = b"BT /F1 12 Tf 72 700 Td (Native text alongside a chart.) Tj ET\n"
    vector = b"0 0 m 100 100 l S\n"

    (page,) = iter_pdf_pages(make_pdf(text + vector))

    assert page.page_number == 1
    assert page.text == "Native text alongside a chart."
    assert page.text_regions
    assert page.needs_visual_recognition is True
    assert page.image_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert page.image_width is not None and page.image_width <= 1600
    assert page.image_height is not None and page.image_height <= 1600


def test_native_text_page_avoids_rendering_when_no_visual_objects():
    content = (
        b"BT /F1 12 Tf 72 700 Td "
        b"(This is enough native text to avoid visual recognition.) Tj ET\n"
    )

    (page,) = iter_pdf_pages(make_pdf(content))

    assert page.text.startswith("This is enough native text")
    assert page.needs_visual_recognition is False
    assert page.image_png is None
    assert page.image_width is None
    assert page.image_height is None


def test_scanned_page_is_rendered_with_explicit_one_based_page_number():
    pages = list(iter_pdf_pages(make_pdf(b"", b"")))

    assert [page.page_number for page in pages] == [1, 2]
    assert all(page.needs_visual_recognition for page in pages)
    assert all(
        page.image_png and page.image_png.startswith(b"\x89PNG") for page in pages
    )


def test_input_page_count_and_invalid_pdf_limits_fail_clearly():
    pdf = make_pdf(b"", b"")

    with pytest.raises(PDFResourceLimitError, match="page"):
        list(iter_pdf_pages(pdf, max_pages=1))
    with pytest.raises(PDFResourceLimitError, match="input"):
        list(iter_pdf_pages(pdf, max_input_bytes=len(pdf) - 1))
    with pytest.raises(InvalidPDFError, match="non-empty bytes"):
        list(iter_pdf_pages(b""))
    with pytest.raises(InvalidPDFError, match="invalid"):
        list(iter_pdf_pages(b"not a PDF"))


def test_encrypted_pdf_fails_without_password_fallback():
    with pytest.raises(EncryptedPDFError, match="Encrypted PDFs"):
        list(iter_pdf_pages(make_pdf(b"", encrypt=True)))


def test_page_dimension_and_render_pixel_limits_are_enforced():
    pdf = make_pdf(b"")

    with pytest.raises(PDFResourceLimitError, match="dimensions"):
        list(iter_pdf_pages(pdf, max_page_dimension_pt=100))
    with pytest.raises(PDFResourceLimitError, match="cannot be rendered"):
        list(iter_pdf_pages(pdf, max_render_width=1, max_render_height=1))
