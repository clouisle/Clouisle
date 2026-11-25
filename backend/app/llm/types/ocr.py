"""
OCR types (text recognition over images and documents).

An OCR model is handed an image or a document and returns the literal text it
contains, page by page. Nothing is asked of it, so the request carries no
prompt: only the source to recognize plus the optional page and block options that
some providers expose. The source must be a URL or an inline base64 payload,
because adapters transmit it over HTTP.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .base import MediaContent, Usage

OCRBlockType = Literal[
    "text",
    "title",
    "table",
    "figure",
    "caption",
    "footnote",
    "formula",
    "signature",
]


class OCRBlock(BaseModel):
    """One recognized content block and where it sits on its page."""

    type: OCRBlockType = Field(default="text", description="Block kind")
    text: str | None = Field(default=None, description="Recognized text")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None,
        description="Bounding box as (x0, y0, x1, y1) in page pixels, top-left origin",
    )
    confidence: float | None = Field(
        default=None, ge=0, le=1, description="Recognition confidence"
    )


class OCRRequest(BaseModel):
    """Recognition request"""

    source: MediaContent = Field(..., description="Image or document to recognize")
    pages: str | list[int] | None = Field(
        default=None,
        description=(
            "Pages to process, 0-based. Accepts a list of integers or a string of "
            "comma-separated numbers and ranges such as '0-5'. Mistral only; other "
            "OCR adapters reject it."
        ),
    )
    include_blocks: bool = Field(
        default=False,
        description=(
            "Return per-block text and bounding boxes instead of page text only. "
            "Mistral only; other OCR adapters reject it."
        ),
    )
    model: str | None = Field(
        default=None, description="Override the model configured on the provider"
    )

    @model_validator(mode="after")
    def validate_source(self) -> "OCRRequest":
        # Adapters transmit the document over HTTP, so a local path can never be
        # sent: reject it here instead of failing later as a provider error.
        if not (self.source.url or self.source.base64):
            raise ValueError("source must carry a url or a base64 payload")
        return self


class OCRPage(BaseModel):
    """Recognized content of one page"""

    index: int = Field(..., ge=0, description="Page index, 0-based")
    markdown: str = Field(default="", description="Page content as Markdown")
    blocks: list[OCRBlock] = Field(
        default_factory=list, description="Per-block content when requested"
    )
    width: float | None = Field(default=None, description="Page width in pixels")
    height: float | None = Field(default=None, description="Page height in pixels")


class OCRResponse(BaseModel):
    """Recognition response"""

    model: str = Field(..., description="Model that produced the recognition")
    pages: list[OCRPage] = Field(
        default_factory=list, description="Recognized pages in source order"
    )
    pages_processed: int | None = Field(
        default=None,
        ge=0,
        strict=True,
        description="Page count reported by the provider, if available",
    )
    usage: Usage = Field(default_factory=Usage, description="使用统计")

    @property
    def text(self) -> str:
        """Concatenated page content for callers that only need the text."""
        return "\n\n".join(
            page.markdown.strip() for page in self.pages if page.markdown.strip()
        )
