"""Bounded, page-oriented native text and visual extraction for knowledge-base PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Iterator
from pypdf import PdfReader

import pypdfium2 as pdfium

PdfiumError = pdfium.PdfiumError

DEFAULT_MAX_INPUT_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_PAGES = 100
DEFAULT_MAX_PAGE_OBJECTS = 10_000
DEFAULT_MAX_TEXT_CHARS = 200_000
DEFAULT_MAX_TEXT_REGIONS = 5_000
DEFAULT_MAX_RENDER_WIDTH = 1_600
DEFAULT_MAX_RENDER_HEIGHT = 1_600
DEFAULT_MAX_PAGE_DIMENSION_PT = 14_400.0
DEFAULT_MIN_TEXT_CHARS = 24

HARD_MAX_INPUT_BYTES = 64 * 1024 * 1024
HARD_MAX_PAGES = 500
HARD_MAX_PAGE_OBJECTS = 50_000
HARD_MAX_TEXT_CHARS = 500_000
HARD_MAX_TEXT_REGIONS = 10_000
HARD_MAX_RENDER_DIMENSION = 4_096
HARD_MAX_RENDER_PIXELS = 16_777_216
HARD_MAX_PAGE_DIMENSION_PT = 28_800.0
MAX_FORM_DEPTH = 8


class PDFProcessingError(ValueError):
    """Base error for a PDF that cannot be safely extracted."""


class InvalidPDFError(PDFProcessingError):
    """The input is not a readable PDF or contains invalid page data."""


class EncryptedPDFError(PDFProcessingError):
    """Password-protected or unsupported-encryption PDFs are not accepted."""


class PDFResourceLimitError(PDFProcessingError):
    """A PDF exceeds a configured input, page, object, text, or render bound."""


class PDFRenderError(PDFProcessingError):
    """PDFium failed to render a page selected for visual recognition."""


@dataclass(frozen=True, slots=True)
class PDFTextRegion:
    """Native text within a PDFium bounding box, in PDF points from bottom-left."""

    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PDFPage:
    """One 1-based PDF page; image fields are populated only when recognition is needed."""

    page_number: int
    text: str
    text_regions: tuple[PDFTextRegion, ...]
    needs_visual_recognition: bool
    image_png: bytes | None = None
    image_width: int | None = None
    image_height: int | None = None


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _extract_text_regions(
    text_page, max_text_regions: int, max_region_text_chars: int
) -> tuple[PDFTextRegion, ...]:
    count = text_page.count_rects()
    if count > max_text_regions:
        raise PDFResourceLimitError(
            f"PDF page has {count} native text regions; limit is {max_text_regions}"
        )

    regions: list[PDFTextRegion] = []
    total_chars = 0
    for index in range(count):
        bbox = text_page.get_rect(index)
        region_text = text_page.get_text_bounded(*bbox).strip()
        if region_text:
            total_chars += len(region_text)
            if total_chars > max_region_text_chars:
                raise PDFResourceLimitError(
                    "PDF native text regions exceed the configured character limit"
                )
            regions.append(PDFTextRegion(text=region_text, bbox=bbox))
    return tuple(regions)


def _has_visual_objects(page, max_page_objects: int) -> bool:
    visual_types = {
        pdfium.raw.FPDF_PAGEOBJ_IMAGE,
        pdfium.raw.FPDF_PAGEOBJ_PATH,
        pdfium.raw.FPDF_PAGEOBJ_SHADING,
        # Forms can contain images or vector content; treat them conservatively as visual.
        pdfium.raw.FPDF_PAGEOBJ_FORM,
    }
    object_count = 0
    has_visual = False
    for page_object in page.get_objects(max_depth=MAX_FORM_DEPTH):
        object_count += 1
        if object_count > max_page_objects:
            raise PDFResourceLimitError(
                f"PDF page has more than {max_page_objects} page objects"
            )
        if page_object.type in visual_types:
            has_visual = True
    return has_visual


def _render_png(
    page,
    *,
    page_number: int,
    max_width: int,
    max_height: int,
    max_page_dimension_pt: float,
) -> tuple[bytes, int, int]:
    width_pt, height_pt = page.get_size()
    if (
        not math.isfinite(width_pt)
        or not math.isfinite(height_pt)
        or width_pt <= 0
        or height_pt <= 0
        or width_pt > max_page_dimension_pt
        or height_pt > max_page_dimension_pt
    ):
        raise PDFResourceLimitError(
            f"PDF page {page_number} has invalid or excessive dimensions "
            f"({width_pt!r} x {height_pt!r} pt)"
        )

    rotation = page.get_rotation()
    display_width, display_height = (
        (height_pt, width_pt) if rotation in (90, 270) else (width_pt, height_pt)
    )
    scale = min(max_width / display_width, max_height / display_height)
    # PDFium rounds pixel dimensions upward; bias the scale down to keep the
    # actual allocation within the configured width and height limits.
    scale = math.nextafter(scale, 0.0)
    expected_width = math.ceil(display_width * scale)
    expected_height = math.ceil(display_height * scale)
    if (
        expected_width < 1
        or expected_height < 1
        or expected_width > max_width
        or expected_height > max_height
        or expected_width * expected_height > HARD_MAX_RENDER_PIXELS
    ):
        raise PDFResourceLimitError(
            f"PDF page {page_number} cannot be rendered within "
            f"{max_width}x{max_height} pixels"
        )

    try:
        bitmap = page.render(scale=scale, rotation=rotation, rev_byteorder=True)
    except Exception as exc:
        raise PDFRenderError(f"Unable to render PDF page {page_number}") from exc

    try:
        width, height = bitmap.width, bitmap.height
        if (
            width != expected_width
            or height != expected_height
            or width > max_width
            or height > max_height
            or width * height > max_width * max_height
            or width * height > HARD_MAX_RENDER_PIXELS
        ):
            raise PDFResourceLimitError(
                f"PDF page {page_number} rendered to invalid dimensions "
                f"{width}x{height} (limit {max_width}x{max_height})"
            )
        image = bitmap.to_pil()
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), width, height
    except PDFProcessingError:
        raise
    except Exception as exc:
        raise PDFRenderError(
            f"Unable to encode rendered PDF page {page_number} as PNG"
        ) from exc
    finally:
        bitmap.close()


def iter_pdf_pages(
    content: bytes,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_page_objects: int = DEFAULT_MAX_PAGE_OBJECTS,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    max_text_regions: int = DEFAULT_MAX_TEXT_REGIONS,
    max_render_width: int = DEFAULT_MAX_RENDER_WIDTH,
    max_render_height: int = DEFAULT_MAX_RENDER_HEIGHT,
    max_page_dimension_pt: float = DEFAULT_MAX_PAGE_DIMENSION_PT,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> Iterator[PDFPage]:
    """Lazily yield bounded page text and rendered PNGs where visual recognition is needed.

    Native text is returned for every page. A page is rendered when it has fewer
    than ``min_text_chars`` of native text (e.g. a scan) or contains an image,
    path, shading, or form object (e.g. embedded images, charts, and diagrams).
    Image/vector detection is conservative and cannot identify every semantic
    visual element in arbitrary PDF content streams.

    The iterator owns a single native PDFium document and closes each page,
    text page, bitmap, and the document as iteration advances or the iterator is
    closed. Page numbers are 1-based. Text region boxes use PDF points with the
    origin at the bottom-left; they aid alignment but are not an exact OCR-to-text
    mapping.
    """
    for name, value in (
        ("max_input_bytes", max_input_bytes),
        ("max_pages", max_pages),
        ("max_page_objects", max_page_objects),
        ("max_text_chars", max_text_chars),
        ("max_text_regions", max_text_regions),
        ("max_render_width", max_render_width),
        ("max_render_height", max_render_height),
    ):
        _require_positive_int(name, value)
    if max_render_width < 2 or max_render_height < 2:
        raise PDFResourceLimitError("PDF cannot be rendered below 2 pixels")
    for name, value, hard_limit in (
        ("max_input_bytes", max_input_bytes, HARD_MAX_INPUT_BYTES),
        ("max_pages", max_pages, HARD_MAX_PAGES),
        ("max_page_objects", max_page_objects, HARD_MAX_PAGE_OBJECTS),
        ("max_text_chars", max_text_chars, HARD_MAX_TEXT_CHARS),
        ("max_text_regions", max_text_regions, HARD_MAX_TEXT_REGIONS),
        ("max_render_width", max_render_width, HARD_MAX_RENDER_DIMENSION),
        ("max_render_height", max_render_height, HARD_MAX_RENDER_DIMENSION),
    ):
        if value > hard_limit:
            raise ValueError(f"{name} cannot exceed hard limit {hard_limit}")

    if not isinstance(content, bytes) or not content:
        if isinstance(content, bytes) and len(content) > max_input_bytes:
            raise PDFResourceLimitError(
                f"PDF input is {len(content)} bytes; limit is {max_input_bytes}"
            )
        raise InvalidPDFError("PDF input must be non-empty bytes")
    if len(content) > max_input_bytes:
        raise PDFResourceLimitError(
            f"PDF input is {len(content)} bytes; limit is {max_input_bytes}"
        )
    if (
        isinstance(max_page_dimension_pt, bool)
        or not isinstance(max_page_dimension_pt, (int, float))
        or not math.isfinite(max_page_dimension_pt)
        or max_page_dimension_pt <= 0
        or max_page_dimension_pt > HARD_MAX_PAGE_DIMENSION_PT
    ):
        raise ValueError(
            f"max_page_dimension_pt must be positive and at most {HARD_MAX_PAGE_DIMENSION_PT}"
        )
    if (
        isinstance(min_text_chars, bool)
        or not isinstance(min_text_chars, int)
        or min_text_chars < 0
        or min_text_chars > HARD_MAX_TEXT_CHARS
    ):
        raise ValueError(f"min_text_chars must be between 0 and {HARD_MAX_TEXT_CHARS}")

    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise EncryptedPDFError("Encrypted PDFs are not supported")
    except EncryptedPDFError:
        raise
    except Exception as exc:
        raise InvalidPDFError("Unable to open invalid PDF") from exc

    try:
        document = pdfium.PdfDocument(content)
    except PdfiumError as exc:
        if exc.err_code in {pdfium.raw.FPDF_ERR_PASSWORD, pdfium.raw.FPDF_ERR_SECURITY}:
            raise EncryptedPDFError("Encrypted PDFs are not supported") from exc
        raise InvalidPDFError("Unable to open invalid or unsupported PDF") from exc
    except Exception as exc:
        raise InvalidPDFError("Unable to open invalid PDF") from exc

    try:
        page_count = len(document)
        if page_count <= 0:
            raise InvalidPDFError("PDF has no pages")
        if page_count > max_pages:
            raise PDFResourceLimitError(
                f"PDF has {page_count} pages; limit is {max_pages}"
            )

        for page_index in range(page_count):
            page_number = page_index + 1
            page = None
            text_page = None
            try:
                page = document.get_page(page_index)
                text_page = page.get_textpage()
                char_count = text_page.count_chars()
                if char_count > max_text_chars:
                    raise PDFResourceLimitError(
                        f"PDF page {page_number} has {char_count} native text characters; "
                        f"limit is {max_text_chars}"
                    )
                text = text_page.get_text_bounded().replace("\r\n", "\n").strip()
                if len(text) > max_text_chars:
                    raise PDFResourceLimitError(
                        f"PDF page {page_number} native text exceeds "
                        f"the {max_text_chars}-character limit"
                    )
                text_regions = _extract_text_regions(
                    text_page,
                    max_text_regions,
                    max_region_text_chars=max_text_chars,
                )
                has_visual_objects = _has_visual_objects(page, max_page_objects)
                needs_visual_recognition = (
                    len(text) < min_text_chars or has_visual_objects
                )
                image_png = None
                image_width = None
                image_height = None
                if needs_visual_recognition:
                    image_png, image_width, image_height = _render_png(
                        page,
                        page_number=page_number,
                        max_width=max_render_width,
                        max_height=max_render_height,
                        max_page_dimension_pt=max_page_dimension_pt,
                    )
                result = PDFPage(
                    page_number=page_number,
                    text=text,
                    text_regions=text_regions,
                    needs_visual_recognition=needs_visual_recognition,
                    image_png=image_png,
                    image_width=image_width,
                    image_height=image_height,
                )
            except PDFProcessingError:
                raise
            except PdfiumError as exc:
                raise InvalidPDFError(
                    f"Unable to extract PDF page {page_number}"
                ) from exc
            except Exception as exc:
                raise InvalidPDFError(
                    f"Unable to extract PDF page {page_number}"
                ) from exc
            finally:
                if text_page is not None:
                    text_page.close()
                if page is not None:
                    page.close()
            yield result
    finally:
        document.close()
