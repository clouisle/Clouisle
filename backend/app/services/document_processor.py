"""
Document processing service for knowledge base.
Handles document parsing, text extraction, and chunking.
"""

import asyncio
import base64
import binascii
import hashlib
import logging
import mimetypes
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any
from uuid import UUID

import aiofiles

from app.models.knowledge_base import (
    DocumentType,
)

logger = logging.getLogger(__name__)


MIME_TYPE_MAP: dict[str, str] = {
    "application/pdf": DocumentType.PDF.value,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.DOCX.value,
    "application/msword": DocumentType.DOC.value,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": DocumentType.TXT.value,
    "text/markdown": DocumentType.MD.value,
    "text/html": DocumentType.HTML.value,
    "text/csv": DocumentType.CSV.value,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.XLSX.value,
    "application/vnd.ms-excel": DocumentType.XLS.value,
    "application/json": DocumentType.JSON.value,
}

# File extension to document type mapping
EXT_TYPE_MAP: dict[str, str] = {
    ".pdf": DocumentType.PDF.value,
    ".docx": DocumentType.DOCX.value,
    ".doc": DocumentType.DOC.value,
    ".pptx": "pptx",
    ".txt": DocumentType.TXT.value,
    ".md": DocumentType.MD.value,
    ".markdown": DocumentType.MD.value,
    ".html": DocumentType.HTML.value,
    ".htm": DocumentType.HTML.value,
    ".csv": DocumentType.CSV.value,
    ".xlsx": DocumentType.XLSX.value,
    ".xls": DocumentType.XLS.value,
    ".json": DocumentType.JSON.value,
}

MEDIA_ASSETS_METADATA_KEY = "media_assets"
DATA_URI_IMAGE_RE = re.compile(r"data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=]+)")
ALLOWED_MEDIA_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/webp",
}
MEDIA_MIME_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


class DocumentProcessor:
    """
    Document processing service.

    Handles:
    - Document file storage
    - Text extraction from various formats
    - Text chunking with overlap
    - Metadata extraction
    """

    def __init__(self, upload_dir: str | None = None):
        """
        Initialize document processor.

        Args:
            upload_dir: Base directory for document uploads
        """
        if upload_dir is None:
            # Default to project root uploads/documents
            # __file__ = backend/app/services/document_processor.py
            # Need 4 levels up to get project root
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            upload_dir = os.path.join(base_dir, "uploads", "documents")

        self.upload_dir = str(Path(upload_dir).resolve())
        os.makedirs(self.upload_dir, exist_ok=True)

    def _resolve_storage_path(self, *parts: str) -> Path:
        """Resolve a path under the document upload directory."""
        root = Path(self.upload_dir).resolve()
        candidate = root.joinpath(*parts).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("validation_error")
        return candidate

    def _sanitize_filename(self, filename: str) -> str:
        safe_name = os.path.basename(filename).strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("validation_error")
        return safe_name

    def get_document_type(
        self, filename: str, content_type: str | None = None
    ) -> str | None:
        """
        Determine document type from filename or content type.

        Args:
            filename: Original filename
            content_type: MIME type if available

        Returns:
            Document type string or None if unsupported
        """
        # Try content type first
        if content_type and content_type in MIME_TYPE_MAP:
            return MIME_TYPE_MAP[content_type]

        # Fall back to extension
        ext = os.path.splitext(filename)[1].lower()
        return EXT_TYPE_MAP.get(ext)

    def get_storage_path(self, kb_id: UUID, filename: str) -> str:
        """
        Generate storage path for a document.

        Args:
            kb_id: Knowledge base ID
            filename: Original filename

        Returns:
            Full path for storing the document
        """
        safe_filename = self._sanitize_filename(filename)

        # Organize by KB ID and date
        date_path = datetime.now().strftime("%Y/%m")

        # Generate unique filename
        file_hash = hashlib.md5(
            f"{kb_id}{safe_filename}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:8]
        ext = os.path.splitext(safe_filename)[1]
        unique_name = (
            f"{file_hash}_{safe_filename}"
            if len(safe_filename) < 50
            else f"{file_hash}{ext}"
        )

        dir_path = self._resolve_storage_path(str(kb_id), *date_path.split("/"))
        os.makedirs(dir_path, exist_ok=True)

        return str(
            self._resolve_storage_path(str(kb_id), *date_path.split("/"), unique_name)
        )

    async def save_file(self, content: bytes, path: str) -> int:
        """
        Save file content to disk.

        Args:
            content: File content bytes
            path: Target path

        Returns:
            File size in bytes
        """
        resolved_path = self._resolve_storage_path(path)
        os.makedirs(resolved_path.parent, exist_ok=True)
        async with aiofiles.open(resolved_path, "wb") as f:
            await f.write(content)
        return len(content)

    async def read_file(self, path: str) -> bytes:
        """
        Read file content from disk.

        Args:
            path: File path

        Returns:
            File content bytes
        """
        resolved_path = self._resolve_storage_path(path)
        async with aiofiles.open(resolved_path, "rb") as f:
            return await f.read()

    def delete_file(self, path: str) -> bool:
        """
        Delete a file from disk.

        Args:
            path: File path

        Returns:
            True if deleted, False if not found
        """
        resolved_path = self._resolve_storage_path(path)
        if os.path.exists(resolved_path):
            os.remove(resolved_path)
            return True
        return False

    def delete_media_assets(self, kb_id: UUID, document_id: UUID) -> None:
        asset_dir = self._resolve_storage_path(str(kb_id), "media", str(document_id))
        if asset_dir.exists():
            shutil.rmtree(asset_dir, ignore_errors=True)

    def _get_media_asset_extension(self, content_type: str) -> str:
        return MEDIA_MIME_EXTENSIONS.get(
            content_type,
            mimetypes.guess_extension(content_type, strict=False) or ".bin",
        )

    def get_media_asset_path(
        self, kb_id: UUID, document_id: UUID, filename: str
    ) -> Path:
        return self._resolve_storage_path(
            str(kb_id), "media", str(document_id), self._sanitize_filename(filename)
        )

    def _save_media_asset(
        self,
        *,
        kb_id: UUID,
        document_id: UUID,
        content_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()[:16]
        extension = self._get_media_asset_extension(content_type)
        filename = self._sanitize_filename(f"{digest}{extension}")
        file_path = self.get_media_asset_path(kb_id, document_id, filename)
        os.makedirs(file_path.parent, exist_ok=True)
        if not file_path.exists():
            temp_file_path = file_path.with_name(f".tmp_{file_path.name}")
            try:
                temp_file_path.write_bytes(content)
                temp_file_path.replace(file_path)
            except Exception:
                temp_file_path.unlink(missing_ok=True)
                raise
        url = (
            f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/media/{filename}"
        )
        return {
            "path": str(file_path),
            "url": url,
            "filename": filename,
            "content_type": content_type,
            "size": len(content),
        }

    def replace_embedded_media_data_uris(
        self,
        text: str,
        *,
        kb_id: UUID,
        document_id: UUID,
    ) -> tuple[str, list[dict[str, Any]]]:
        assets: list[dict[str, Any]] = []

        def replace(match: re.Match[str]) -> str:
            content_type = match.group(1).lower()
            if content_type not in ALLOWED_MEDIA_MIME_TYPES:
                return match.group(0)
            try:
                content = base64.b64decode(match.group(2), validate=True)
            except binascii.Error:
                return match.group(0)
            asset = self._save_media_asset(
                kb_id=kb_id,
                document_id=document_id,
                content_type=content_type,
                content=content,
            )
            assets.append(asset)
            return asset["url"]

        return DATA_URI_IMAGE_RE.sub(replace, text), assets

    async def extract_text(
        self,
        path: str,
        doc_type: str,
        clean_text: bool = True,
        kb_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Extract text content from a document.

        Args:
            path: File path
            doc_type: Document type
            clean_text: Whether to clean and normalize text

        Returns:
            Tuple of (extracted_text, metadata)
        """
        resolved_path = str(self._resolve_storage_path(path))
        content = await self.read_file(resolved_path)
        metadata: dict[str, Any] = {
            "file_size": len(content),
            "doc_type": doc_type,
        }

        try:
            if doc_type == DocumentType.TXT.value:
                text = content.decode("utf-8", errors="ignore")
            elif doc_type == DocumentType.MD.value:
                text = content.decode("utf-8", errors="ignore")
                metadata["format"] = "markdown"
            elif doc_type == DocumentType.CSV.value:
                text = self._extract_csv_text(content)
            elif doc_type == DocumentType.JSON.value:
                text = self._extract_json_text(content)
            elif doc_type in [
                DocumentType.PDF.value,
                DocumentType.DOCX.value,
                DocumentType.DOC.value,
                DocumentType.XLSX.value,
                DocumentType.XLS.value,
                DocumentType.HTML.value,
                "pptx",
            ]:
                # Use MarkItDown for PDF, Office documents, Excel, and HTML
                text, doc_meta = self._extract_with_markitdown(resolved_path, doc_type)
                metadata.update(doc_meta)
            else:
                # Try to decode as text
                text = content.decode("utf-8", errors="ignore")

        except Exception as e:
            logger.error(f"Error extracting text from {resolved_path}: {e}")
            raise ValueError("document_processing_failed_generic")

        # Clean up text
        if kb_id is not None and document_id is not None:
            text, media_assets = await asyncio.to_thread(
                self.replace_embedded_media_data_uris,
                text,
                kb_id=kb_id,
                document_id=document_id,
            )
            if media_assets:
                metadata[MEDIA_ASSETS_METADATA_KEY] = media_assets
        text = self._clean_text(text, clean=clean_text)
        metadata["char_count"] = len(text)

        return text, metadata

    def _clean_text(self, text: str, clean: bool = True) -> str:
        """Clean and normalize text.

        Args:
            text: Text to clean
            clean: Whether to perform aggressive cleaning. If False, only
                   removes null bytes and normalizes line endings.
        """
        # Always remove null bytes
        text = text.replace("\x00", "")
        # Always normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        if clean:
            # Remove excessive blank lines (collapse consecutive newlines to single newline)
            text = re.sub(r"\n{2,}", "\n", text)
            # Remove excessive spaces on the same line (but preserve newlines)
            text = re.sub(r"[^\S\n]+", " ", text)
            # Strip leading/trailing whitespace from each line
            lines = [line.strip() for line in text.split("\n")]
            text = "\n".join(lines)

            # Strip leading/trailing whitespace from the whole text
            text = text.strip()

        return text

    def _extract_with_markitdown(
        self, path: str, doc_type: str
    ) -> tuple[str, dict[str, Any]]:
        """
        Extract text from documents using MarkItDown.

        Supports: PDF, DOCX, DOC, PPTX, XLSX, XLS and more.
        MarkItDown converts documents to Markdown format.
        """
        metadata: dict[str, Any] = {"format": "markdown"}

        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(path, keep_data_uris=True)

            text = result.text_content

            # Extract title if available
            if result.title:
                metadata["title"] = result.title

            return text, metadata

        except ImportError:
            raise ValueError("document_processing_failed_generic")

    def _extract_csv_text(self, content: bytes) -> str:
        """Extract text from CSV content."""
        import csv
        import io

        text = content.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(text))

        rows = []
        for row in reader:
            rows.append(" | ".join(row))

        return "\n".join(rows)

    def _extract_json_text(self, content: bytes) -> str:
        """Extract text from JSON content."""
        import json

        data = json.loads(content.decode("utf-8", errors="ignore"))

        def flatten_json(obj: Any, prefix: str = "") -> list[str]:
            items = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{prefix}.{k}" if prefix else k
                    items.extend(flatten_json(v, new_key))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    items.extend(flatten_json(v, f"{prefix}[{i}]"))
            else:
                items.append(f"{prefix}: {obj}")
            return items

        return "\n".join(flatten_json(data))

    async def fetch_url_content(
        self, url: str, clean_text: bool = True
    ) -> tuple[str, dict[str, Any]]:
        """
        Fetch and extract content from a URL.

        Args:
            url: Web page URL
            clean_text: Whether to clean and normalize text

        Returns:
            Tuple of (extracted_text, metadata)
        """
        metadata: dict[str, Any] = {"source_url": url}

        try:
            # Use MarkItDown for URL fetching (supports YouTube, HTML, etc.)
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(url)

            text = result.text_content
            metadata["format"] = "markdown"

            if result.title:
                metadata["title"] = result.title

        except ImportError:
            # Fallback to httpx
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                metadata["content_type"] = content_type

                if "application/json" in content_type:
                    text = self._extract_json_text(response.content)
                else:
                    text = response.text

        text = self._clean_text(text, clean=clean_text)
        metadata["char_count"] = len(text)

        return text, metadata


# Default chunking settings (in characters)
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 100

# Default separators in order of priority (shared with LangChain splitter)
DEFAULT_SEPARATORS = [
    "\n\n",  # Paragraph
    "\n",  # Line
    "。",  # Chinese period
    "！",  # Chinese exclamation
    "？",  # Chinese question
    ". ",  # Sentence
    "! ",
    "? ",
    "；",  # Chinese semicolon
    "; ",
    "，",  # Chinese comma
    ", ",
    " ",  # Word
    "",  # Character
]

CHARS_PER_TOKEN = 4

# Escape sequences the user can type in a custom-separator field (e.g. "\n")
# so that a literal backslash-n in the request body splits on a real newline.
_ESCAPE_SEQUENCES: dict[str, str] = {
    "\\n": "\n",
    "\\r": "\r",
    "\\t": "\t",
    "\\\\": "\\",
}


def _decode_separator_escapes(separator: str) -> str:
    """
    Interpret common escape sequences in a user-supplied separator string.

    The frontend renders separator hints like ``\\n\\n`` (literal backslash-n),
    so the API receives the two-character sequence ``\\n`` rather than a real
    newline. LangChain's splitter does a literal match, so it would never
    split on actual newlines. This helper turns the typed escape sequences
    into the characters they represent before they reach the splitter.
    """
    if "\\" not in separator:
        return separator

    decoded: list[str] = []
    i = 0
    while i < len(separator):
        if separator[i] == "\\" and i + 1 < len(separator):
            pair = separator[i : i + 2]
            if pair in _ESCAPE_SEQUENCES:
                decoded.append(_ESCAPE_SEQUENCES[pair])
                i += 2
                continue
        decoded.append(separator[i])
        i += 1
    return "".join(decoded)


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Split text into chunks using LangChain's RecursiveCharacterTextSplitter,
    then apply exact character-level overlap.

    LangChain's built-in overlap works at the split-unit level, which can
    produce much larger overlaps than requested for CJK text (where sentence
    separators create units larger than the overlap value). To fix this, we
    split with overlap=0 first, then prepend the exact trailing characters
    from the previous chunk.

    When the caller provides a custom separator it is treated as a hard split
    boundary: the text is pre-split on the (escape-decoded) separator first,
    and each piece is then passed through the splitter so that pieces still
    larger than ``chunk_size`` are broken down further. Without this,
    LangChain returns the whole text as a single chunk whenever it already
    fits in ``chunk_size``, ignoring the user's separator entirely.

    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        separators: Optional custom separators. Each separator may contain
            escape sequences (``\\n``, ``\\r``, ``\\t``, ``\\\\``) which are
            decoded to their real characters before splitting.

    Returns:
        List of chunk dicts with content, chunk_index, token_count, char_count
    """
    if not text.strip():
        return []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if separators:
        custom = [_decode_separator_escapes(s) for s in separators if s]
        seps = custom + [s for s in DEFAULT_SEPARATORS if s not in custom]
    else:
        seps = list(DEFAULT_SEPARATORS)

    # Pre-split on the user's primary custom separator so it acts as a hard
    # boundary, even when the whole text fits within chunk_size.
    texts = _split_on_custom_separator(text, seps[0]) if seps else [text]

    # If no piece is over chunk_size we still need to honour the splitter's
    # secondary separators (e.g. when the custom separator is not present in
    # the text at all, leave the splitter's default behaviour in charge).
    if len(texts) == 1 and texts[0] == text:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=0,
            separators=seps,
            length_function=len,
        )
        texts = splitter.split_text(text)
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=0,
            separators=seps[1:] if len(seps) > 1 else [""],
            length_function=len,
        )
        chunked: list[str] = []
        for piece in texts:
            chunked.extend(splitter.split_text(piece) if piece else [])
        texts = chunked

    # Apply exact character-level overlap and track overlap lengths
    overlap_lengths: list[int] = [0] * len(texts)
    if chunk_overlap > 0 and len(texts) > 1:
        overlapped: list[str] = [texts[0]]
        for i in range(1, len(texts)):
            prev = texts[i - 1]
            overlap_text = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            overlap_lengths[i] = len(overlap_text)
            overlapped.append(overlap_text + texts[i])
        texts = overlapped

    return [
        {
            "content": t,
            "chunk_index": idx,
            "token_count": len(t) // CHARS_PER_TOKEN,
            "char_count": len(t),
            "overlap_length": overlap_lengths[idx],
        }
        for idx, t in enumerate(texts)
    ]


def _split_on_custom_separator(text: str, separator: str) -> list[str]:
    """
    Split ``text`` on ``separator`` only when the separator actually appears.

    Returns ``[text]`` unchanged when the separator is the empty-string fallback
    or when it is not present, so the caller can fall back to the default
    splitter.
    """
    if not separator or separator not in text:
        return [text]
    return text.split(separator)


# Global instance
document_processor = DocumentProcessor()
