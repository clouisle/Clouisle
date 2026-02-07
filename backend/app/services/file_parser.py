"""
File parsing service using MarkItDown.

Provides file parsing functionality with configurable truncation.
"""

import logging
import mimetypes
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.i18n import t

logger = logging.getLogger(__name__)


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

    def __init__(self):
        self._md = None

    def _get_markitdown(self):
        """Lazy load MarkItDown instance"""
        if self._md is None:
            try:
                from markitdown import MarkItDown

                self._md = MarkItDown()
            except ImportError:
                raise ValueError(
                    "MarkItDown not installed. Install with: pip install 'markitdown[pdf,xlsx,xls]'"
                )
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
            ext = Path(filename).suffix.lower()
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS.keys())}"
            )

        mime_type = self.get_mime_type(filename)
        file_size = len(file_content)

        # Parse using MarkItDown
        ext = Path(filename).suffix.lower()

        # For plain text files, read directly
        if ext in {".txt", ".md", ".csv", ".json"}:
            try:
                text = file_content.decode("utf-8")
            except UnicodeDecodeError:
                text = file_content.decode("utf-8", errors="ignore")
            title = None
        else:
            # Use MarkItDown for other formats
            md = self._get_markitdown()

            # Write to temp file for MarkItDown
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                result = md.convert(tmp_path)
                text = result.text_content
                title = result.title
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)

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
