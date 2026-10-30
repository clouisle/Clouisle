from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.services import kb_pdf_images as pdf_module
from app.services.kb_pdf_images import (
    HARD_MAX_PAGES,
    EncryptedPDFError,
    InvalidPDFError,
    PDFResourceLimitError,
    _extract_text_regions,
    _has_visual_objects,
    _render_png,
    _require_positive_int,
    iter_pdf_pages,
)


def make_pdf(*page_contents: bytes, encrypt: bool = False, rotate: int = 0) -> bytes:
    writer = PdfWriter()
    for contents in page_contents:
        page = writer.add_blank_page(width=612, height=792)
        if rotate:
            page.rotate(rotate)
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


def test_positive_int_validation_rejects_booleans_and_zero():
    with pytest.raises(ValueError, match="positive integer"):
        _require_positive_int("pages", True)
    with pytest.raises(ValueError, match="positive integer"):
        _require_positive_int("pages", 0)


def test_text_region_count_and_character_limits():
    class TooMany:
        def count_rects(self):
            return 3

    with pytest.raises(PDFResourceLimitError, match="text regions"):
        _extract_text_regions(TooMany(), max_text_regions=2, max_region_text_chars=10)

    class TwoRegions:
        def count_rects(self):
            return 2

        def get_rect(self, _index):
            return (0, 0, 1, 1)

        def get_text_bounded(self, *_box):
            return "" if self.calls == 0 else "xx"

        calls = 0

    class TextPage(TwoRegions):
        def get_text_bounded(self, *_box):
            value = "" if self.calls == 0 else "xx"
            self.calls += 1
            return value

    with pytest.raises(PDFResourceLimitError, match="character limit"):
        _extract_text_regions(TextPage(), max_text_regions=10, max_region_text_chars=1)


def test_visual_object_count_limit_and_detection():
    class Page:
        def __init__(self, objects):
            self._objects = objects

        def get_objects(self, **_kwargs):
            return iter(self._objects)

    visual = SimpleNamespace(type=pdf_module.pdfium.raw.FPDF_PAGEOBJ_IMAGE)
    plain = SimpleNamespace(type=pdf_module.pdfium.raw.FPDF_PAGEOBJ_TEXT)
    assert _has_visual_objects(Page([plain]), 10) is False
    assert _has_visual_objects(Page([visual]), 10) is True
    with pytest.raises(PDFResourceLimitError, match="page objects"):
        _has_visual_objects(Page([plain, plain]), 1)


def test_render_rejects_invalid_dimensions_and_bitmap_size(monkeypatch):
    class BadPage:
        def get_size(self):
            return (float("nan"), 10)

    with pytest.raises(PDFResourceLimitError, match="dimensions"):
        _render_png(
            BadPage(),
            page_number=1,
            max_width=10,
            max_height=10,
            max_page_dimension_pt=100,
        )

    class Bitmap:
        width = 99
        height = 99

        def close(self):
            pass

    class Page:
        def get_size(self):
            return (10, 10)

        def get_rotation(self):
            return 0

        def render(self, **_kwargs):
            return Bitmap()

    with pytest.raises(PDFResourceLimitError, match="rendered to invalid"):
        _render_png(
            Page(),
            page_number=1,
            max_width=10,
            max_height=10,
            max_page_dimension_pt=100,
        )


def test_hard_limits_and_scalar_bounds_are_enforced():
    pdf = make_pdf(b"")
    with pytest.raises(ValueError, match="hard limit"):
        list(iter_pdf_pages(pdf, max_pages=HARD_MAX_PAGES + 1))
    with pytest.raises(ValueError, match="max_page_dimension_pt"):
        list(iter_pdf_pages(pdf, max_page_dimension_pt=0))
    with pytest.raises(ValueError, match="min_text_chars"):
        list(iter_pdf_pages(pdf, min_text_chars=-1))
    with pytest.raises(PDFResourceLimitError, match="below 2 pixels"):
        list(iter_pdf_pages(pdf, max_render_width=1))


def test_pdfium_encrypted_and_empty_documents(monkeypatch):
    class Encrypted:
        def __init__(self, _content):
            raise pdf_module.PdfiumError(
                "password", err_code=pdf_module.pdfium.raw.FPDF_ERR_PASSWORD
            )

    monkeypatch.setattr(pdf_module.pdfium, "PdfDocument", Encrypted)
    with pytest.raises(EncryptedPDFError):
        list(iter_pdf_pages(make_pdf(b"")))

    class Empty:
        def __init__(self, _content):
            pass

        def __len__(self):
            return 0

        def close(self):
            pass

    monkeypatch.setattr(pdf_module.pdfium, "PdfDocument", Empty)
    with pytest.raises(InvalidPDFError, match="no pages"):
        list(iter_pdf_pages(make_pdf(b"")))


def test_page_text_character_limit_is_enforced():
    text = b"BT /F1 12 Tf 72 700 Td (abcdef) Tj ET\n"
    with pytest.raises(PDFResourceLimitError, match="native text characters"):
        list(iter_pdf_pages(make_pdf(text), max_text_chars=1))


def test_pdfium_non_encryption_errors_are_invalid_pdfs(monkeypatch):
    class Broken:
        def __init__(self, _content):
            raise pdf_module.PdfiumError("bad", err_code=1)

    monkeypatch.setattr(pdf_module.pdfium, "PdfDocument", Broken)
    with pytest.raises(InvalidPDFError, match="invalid or unsupported"):
        list(iter_pdf_pages(make_pdf(b"")))


def test_text_length_and_page_lookup_errors(monkeypatch):
    class TextPage:
        def count_chars(self):
            return 1

        def get_text_bounded(self, *_args):
            return "longer than limit"

        def count_rects(self):
            return 0

        def close(self):
            pass

    class Page:
        def get_textpage(self):
            return TextPage()

        def get_objects(self, **_kwargs):
            return iter(())

        def close(self):
            pass

    class LongTextDocument:
        def __init__(self, _content):
            pass

        def __len__(self):
            return 1

        def get_page(self, _index):
            return Page()

        def close(self):
            pass

    monkeypatch.setattr(pdf_module.pdfium, "PdfDocument", LongTextDocument)
    with pytest.raises(PDFResourceLimitError, match="native text exceeds"):
        list(iter_pdf_pages(make_pdf(b""), max_text_chars=1))

    class BrokenPageDocument:
        def __init__(self, _content):
            pass

        def __len__(self):
            return 1

        def get_page(self, _index):
            raise pdf_module.PdfiumError("page", err_code=1)

        def close(self):
            pass

    monkeypatch.setattr(pdf_module.pdfium, "PdfDocument", BrokenPageDocument)
    with pytest.raises(InvalidPDFError, match="Unable to extract PDF page"):
        list(iter_pdf_pages(make_pdf(b"")))


def test_page_rotation_is_not_applied_twice():
    (page,) = iter_pdf_pages(make_pdf(b"", rotate=90))
    assert page.needs_visual_recognition is True
    assert page.image_width is not None and page.image_height is not None
    assert page.image_width > page.image_height
