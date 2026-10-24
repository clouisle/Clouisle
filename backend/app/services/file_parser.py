"""
File parsing service using MarkItDown.

Provides file parsing functionality with configurable truncation.
"""

import asyncio
import logging
import mimetypes
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.i18n import t

logger = logging.getLogger(__name__)

# Version of the complete-text normalization used for persisted Asset
# representations. Bump when extraction output can change so stored
# representations are never silently reused across incompatible parsers.
EXTRACTION_VERSION = "2"

# Hard ceiling for one complete extraction. The limit is explicit so a
# pathological source file fails clearly instead of exhausting worker memory.
MAX_EXTRACTED_CHARS = 5_000_000

# Formats whose text is already UTF-8 (or BOM-marked UTF-16/UTF-8) and must
# never go through MarkItDown, which could silently reflow them.
PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}

_BOM_UTF16 = (b"\xff\xfe", b"\xfe\xff")


class ExtractedFile(BaseModel):
    """A complete extraction result, without any truncation."""

    filename: str
    text: str
    mime_type: str
    size: int
    title: str | None = None


class FileParseConfig(BaseModel):
    """Configuration for file parsing"""

    max_content_length: int = Field(
        default=100000,
        description="Maximum content length in characters",
    )
    truncate_strategy: str = Field(
        default="end",
        description="Truncation strategy: 'end', 'start', 'middle'",
    )


class ParsedFile(BaseModel):
    """Result of file parsing"""

    filename: str
    content: str
    mime_type: str
    size: int
    truncated: bool = False
    original_length: int | None = None
    title: str | None = None


class FileParserService:
    """
    MarkItDown 文件解析服务。

    支持：pdf、doc/docx、ppt/pptx、xls/xlsx、txt、md、csv、json、html。
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
        ".html": "text/html",
        ".htm": "text/html",
    }
    SUPPORTED_TEMP_SUFFIXES = {
        ".pdf": ".pdf",
        ".docx": ".docx",
        ".doc": ".doc",
        ".pptx": ".pptx",
        ".ppt": ".ppt",
        ".xlsx": ".xlsx",
        ".xls": ".xls",
        ".txt": ".txt",
        ".md": ".md",
        ".csv": ".csv",
        ".json": ".json",
        ".html": ".html",
        ".htm": ".htm",
    }

    def __init__(self):
        self._md = None

    def _get_markitdown(self):
        """Lazy load MarkItDown instance"""
        if self._md is None:
            try:
                from markitdown import MarkItDown

                self._md = MarkItDown()
            except ImportError:
                raise ValueError("document_processing_failed_generic")
        return self._md

    def is_supported(self, filename: str) -> bool:
        """Check if file type is supported"""
        ext = Path(filename).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def get_mime_type(self, filename: str) -> str:
        """Get MIME type for file"""
        ext = Path(filename).suffix.lower()
        return self.SUPPORTED_EXTENSIONS.get(
            ext, mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )

    @staticmethod
    def _normalize_newlines(text: str) -> str:
        """Normalize CRLF/CR so persisted line positions are deterministic."""
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _decode_plain_text(file_content: bytes, *, strict: bool) -> str:
        """Decode text formats without silently discarding invalid bytes."""
        try:
            text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            if strict:
                if file_content.startswith(_BOM_UTF16):
                    try:
                        return file_content.decode("utf-16")
                    except UnicodeDecodeError as exc:
                        raise ValueError("document_extraction_decode_failed") from exc
                raise ValueError("document_extraction_decode_failed") from None
            # Legacy truncating parse tolerated malformed text.
            text = file_content.decode("utf-8", errors="ignore")
        return text

    def _convert_to_text(
        self,
        file_content: bytes,
        filename: str,
        *,
        strict: bool,
    ) -> tuple[str, str | None]:
        """Convert source bytes to text.

        Newline normalization is applied only by the complete extraction path.
        Synchronous by design: callers run it in a thread so document
        conversion never blocks the event loop.
        """
        ext = Path(filename).suffix.lower()
        if not self.is_supported(filename):
            raise ValueError("unsupported_file_type")

        if ext in PLAIN_TEXT_EXTENSIONS:
            return self._decode_plain_text(file_content, strict=strict), None

        md = self._get_markitdown()
        with tempfile.NamedTemporaryFile(
            suffix=self.SUPPORTED_TEMP_SUFFIXES[ext], delete=False
        ) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            try:
                result = md.convert(tmp_path)
            except Exception as exc:
                if not strict:
                    # Legacy truncating parse preserves the parser's own
                    # exception type for existing callers/tests.
                    raise
                raise ValueError("document_processing_failed_generic") from exc
            text = result.text_content
            title = result.title
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return text, title

    def extract_text(self, file_content: bytes, filename: str) -> tuple[str, str]:
        """Extract the complete normalized text of one file.

        Returns ``(text, title)``. Raises a stable ``ValueError`` key for
        unsupported, undecodable, empty, or oversized extractions. This path
        never truncates and never discards undecodable bytes.
        """
        text, title = self._convert_to_text(file_content, filename, strict=True)
        text = self._normalize_newlines(text)
        if not text.strip():
            raise ValueError("document_extraction_empty")
        if len(text) > MAX_EXTRACTED_CHARS:
            raise ValueError("asset_document_resource_limit_exceeded")
        return text, title or ""

    async def extract_file(
        self,
        file_content: bytes,
        filename: str,
    ) -> ExtractedFile:
        """Complete extraction with conversion kept off the event loop."""
        mime_type = self.get_mime_type(filename)
        text, title = await asyncio.to_thread(self.extract_text, file_content, filename)
        return ExtractedFile(
            filename=filename,
            text=text,
            mime_type=mime_type,
            size=len(file_content),
            title=title or None,
        )

    def truncate_content(
        self,
        content: str,
        max_length: int,
        strategy: str = "end",
        locale: str | None = None,
    ) -> tuple[str, bool, int]:
        """
        Truncate content according to strategy.

        Args:
            content: Original content
            max_length: Maximum length
            strategy: 'end' (keep start), 'start' (keep end), 'middle' (keep both)
            locale: User's locale for i18n markers

        Returns:
            Tuple of (truncated_content, was_truncated, original_length)
        """
        original_length = len(content)

        if original_length <= max_length:
            return content, False, original_length

        if strategy == "start":
            # Keep the end
            truncated = (
                t("truncation_marker", lang=locale) + "\n\n" + content[-max_length:]
            )
        elif strategy == "middle":
            # Keep both start and end
            half = max_length // 2
            truncated = (
                content[:half]
                + "\n\n"
                + t(
                    "truncation_middle_marker",
                    lang=locale,
                    count=str(original_length - max_length),
                )
                + "\n\n"
                + content[-half:]
            )
        else:  # "end" - default, keep start
            truncated = (
                content[:max_length] + "\n\n" + t("truncation_marker", lang=locale)
            )

        return truncated, True, original_length

    async def parse_file(
        self,
        file_content: bytes,
        filename: str,
        config: FileParseConfig | None = None,
    ) -> ParsedFile:
        """
        Parse file content using MarkItDown.

        Args:
            file_content: Raw file content
            filename: Original filename
            config: Parsing configuration

        Returns:
            ParsedFile with parsed content
        """
        config = config or FileParseConfig()

        # Validate file type
        if not self.is_supported(filename):
            raise ValueError("unsupported_file_type")

        mime_type = self.get_mime_type(filename)
        file_size = len(file_content)

        # Legacy truncating parse keeps its lenient decoding and only ever
        # returns at most ``max_content_length`` characters.
        text, title = await asyncio.to_thread(
            self._convert_to_text, file_content, filename, strict=False
        )

        # Apply truncation
        truncated_text, was_truncated, original_length = self.truncate_content(
            text,
            config.max_content_length,
            config.truncate_strategy,
        )

        return ParsedFile(
            filename=filename,
            content=truncated_text,
            mime_type=mime_type,
            size=file_size,
            truncated=was_truncated,
            original_length=original_length if was_truncated else None,
            title=title,
        )

    def format_files_for_prompt(
        self,
        files: list[ParsedFile],
        separator: str = "\n\n---\n\n",
        locale: str | None = None,
    ) -> str:
        """
        Format multiple parsed files for injection into prompt.

        Args:
            files: List of parsed files
            separator: Separator between files
            locale: User's locale for i18n headers

        Returns:
            Formatted string for prompt injection
        """
        if not files:
            return ""

        if len(files) == 1:
            file = files[0]
            header = t("file_header", lang=locale, filename=file.filename)
            if file.truncated:
                header += t(
                    "file_header_truncated_suffix",
                    lang=locale,
                    length=file.original_length,
                )
            return f"{header}\n\n{file.content}"

        # Multiple files
        parts = []
        for i, file in enumerate(files, 1):
            header = t(
                "file_header_indexed", lang=locale, index=i, filename=file.filename
            )
            if file.truncated:
                header += t(
                    "file_header_truncated_suffix",
                    lang=locale,
                    length=file.original_length,
                )
            parts.append(f"{header}\n\n{file.content}")

        return separator.join(parts)


# Global service instance
file_parser_service = FileParserService()
