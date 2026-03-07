"""
Document processing service for knowledge base.
Handles document parsing, text extraction, and chunking.
"""

import hashlib
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any
from uuid import UUID

import aiofiles

from app.models.knowledge_base import (
    DocumentType,
)

logger = logging.getLogger(__name__)


# Supported MIME types mapping
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
            raise ValueError("Invalid document storage path")
        return candidate

    def _sanitize_filename(self, filename: str) -> str:
        safe_name = os.path.basename(filename).strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("Invalid document filename")
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
            f"{file_hash}_{safe_filename}" if len(safe_filename) < 50 else f"{file_hash}{ext}"
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

    async def extract_text(
        self, path: str, doc_type: str, clean_text: bool = True
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
            raise ValueError(f"Failed to extract text: {e}")

        # Clean up text
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
            result = md.convert(path)

            text = result.text_content

            # Extract title if available
            if result.title:
                metadata["title"] = result.title

            return text, metadata

        except ImportError:
            raise ValueError(
                f"MarkItDown not installed. Install with: pip install 'markitdown[pdf,xlsx,xls]'. "
                f"Required for {doc_type} files."
            )

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


# Default chunking settings
DEFAULT_CHUNK_SIZE = 500  # tokens (approximately 4 chars per token)
DEFAULT_CHUNK_OVERLAP = 50


class TextChunker:
    """
    Text chunking service for splitting documents into searchable chunks.

    Uses semantic-aware splitting that respects:
    - Paragraph boundaries
    - Sentence boundaries
    - Token limits
    """

    # Default separators in order of priority
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

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        separators: list[str] | None = None,
    ):
        """
        Initialize chunker.

        Args:
            chunk_size: Target chunk size in tokens (approx 4 chars = 1 token)
            chunk_overlap: Number of overlapping tokens between chunks
            separators: Custom separators list. If provided, text will be split
                       by these separators first, then by default separators.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Store custom separators separately for primary splitting
        self.custom_separators = [s for s in (separators or []) if s]

        # Default separators for secondary splitting (within chunks)
        self.default_separators = self.DEFAULT_SEPARATORS.copy()

        # Combined list: custom first, then defaults
        if self.custom_separators:
            self.separators = self.custom_separators + [
                s for s in self.default_separators if s not in self.custom_separators
            ]
        else:
            self.separators = self.default_separators

        # Approximate chars per token
        self.chars_per_token = 4

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // self.chars_per_token

    def chunk_text(self, text: str) -> list[dict[str, Any]]:
        """
        Split text into chunks.

        If custom separators are provided, text is first split by those separators,
        then each section is further split if it exceeds the target size.

        Args:
            text: Text to chunk

        Returns:
            List of chunk dicts with content, index, and metadata
        """
        if not text.strip():
            return []

        target_chars = self.chunk_size * self.chars_per_token
        overlap_chars = self.chunk_overlap * self.chars_per_token

        # If custom separators are provided, first split by them
        if self.custom_separators:
            chunks = self._split_by_custom_separators(text, target_chars, overlap_chars)
        else:
            chunks = self._split_recursive(text, target_chars, overlap_chars)

        result = []

        # Add content chunks
        for idx, chunk_text in enumerate(chunks):
            result.append(
                {
                    "content": chunk_text,
                    "chunk_index": idx,
                    "token_count": self.estimate_tokens(chunk_text),
                    "char_count": len(chunk_text),
                }
            )

        return result

    def _split_by_custom_separators(
        self, text: str, target_size: int, overlap: int
    ) -> list[str]:
        """
        Split text by custom separators first, then apply size limits.

        This ensures that custom separators are always respected as primary
        split points, regardless of chunk size.
        """
        # Create pattern for all separators
        # Escape separators to handle special regex characters
        pattern = f"({'|'.join(map(re.escape, self.custom_separators))})"

        # Split keeping the separators
        parts = re.split(pattern, text)

        # Reassemble parts attaching separators to the following text
        # e.g. "text1", "###", "text2" -> "text1", "###text2"
        sections = []
        current_section = ""

        for part in parts:
            if part in self.custom_separators:
                if current_section:
                    sections.append(current_section)
                current_section = part
            else:
                current_section += part

        if current_section:
            sections.append(current_section)

        # Filter empty sections (but keep whitespace-only sections if they exist)
        sections = [s for s in sections if s]

        # Now process each section
        all_chunks = []
        previous_chunk_tail = ""

        for section in sections:
            section_chunks = []

            # Check size in tokens
            if self.estimate_tokens(section) <= self.chunk_size:
                section_chunks = [section]
            else:
                # Section is too large, split using default separators
                section_chunks = self._split_recursive_with_separators(
                    section, target_size, overlap, self.default_separators
                )

            # Apply overlap from previous section's last chunk to this section's first chunk
            if previous_chunk_tail and overlap > 0 and section_chunks:
                section_chunks[0] = previous_chunk_tail + section_chunks[0]

            all_chunks.extend(section_chunks)

            # Update previous chunk tail for next iteration
            if section_chunks:
                last_chunk = section_chunks[-1]
                if overlap > 0:
                    if len(last_chunk) > overlap:
                        previous_chunk_tail = last_chunk[-overlap:]
                    else:
                        previous_chunk_tail = last_chunk
                else:
                    previous_chunk_tail = ""

        return all_chunks

    def _apply_overlap(self, chunks: list[str], overlap: int) -> list[str]:
        """Apply overlap between chunks by prepending end of previous chunk."""
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]

            # Get the overlap portion from the end of previous chunk
            if len(prev_chunk) > overlap:
                overlap_text = prev_chunk[-overlap:]
            else:
                overlap_text = prev_chunk

            # Prepend overlap to current chunk
            result.append(overlap_text + curr_chunk)

        return result

    def _split_recursive_with_separators(
        self, text: str, target_size: int, overlap: int, separators: list[str]
    ) -> list[str]:
        """Recursively split text using specific separators."""
        if len(text) <= target_size:
            return [text] if text else []

        # Find the best separator
        for separator in separators:
            if separator:
                splits = text.split(separator)
            else:
                # Character-level split
                splits = list(text)

            if len(splits) > 1:
                return self._merge_splits(
                    splits, separator, target_size, overlap, separators
                )

        # Fallback: hard split
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + target_size, len(text))
            chunks.append(text[start:end])
            if overlap > 0:
                start = end - overlap
                if start >= len(text) - overlap:
                    break
            else:
                start = end
                if start >= len(text):
                    break

        return chunks

    def _split_recursive(self, text: str, target_size: int, overlap: int) -> list[str]:
        """Recursively split text using separators."""
        if len(text) <= target_size:
            return [text] if text.strip() else []

        # Find the best separator
        for separator in self.separators:
            if separator:
                splits = text.split(separator)
            else:
                # Character-level split
                splits = list(text)

            if len(splits) > 1:
                return self._merge_splits(splits, separator, target_size, overlap)

        # Fallback: hard split
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + target_size, len(text))
            chunks.append(text[start:end])
            if overlap > 0:
                start = end - overlap
                if start >= len(text) - overlap:
                    break
            else:
                start = end
                if start >= len(text):
                    break

        return chunks

    def _merge_splits(
        self,
        splits: list[str],
        separator: str,
        target_size: int,
        overlap: int,
        available_separators: list[str] | None = None,
    ) -> list[str]:
        """Merge splits into chunks respecting size limits."""
        if available_separators is None:
            available_separators = self.separators

        chunks = []
        current_chunk: list[str] = []
        current_size = 0

        for split in splits:
            split_size = len(split) + len(separator)

            if current_size + split_size > target_size and current_chunk:
                # Save current chunk
                chunk_text = separator.join(current_chunk)
                chunks.append(chunk_text)

                # Start new chunk with overlap (only if overlap > 0)
                if overlap > 0:
                    overlap_tokens: list[str] = []
                    overlap_size = 0
                    for s in reversed(current_chunk):
                        if overlap_size + len(s) + len(separator) <= overlap:
                            overlap_tokens.insert(0, s)
                            overlap_size += len(s) + len(separator)
                        else:
                            break

                    current_chunk = overlap_tokens
                    current_size = overlap_size
                else:
                    current_chunk = []
                    current_size = 0

            # If this split itself is too large, recursively split it
            if split_size > target_size:
                # First, save any existing chunk
                if current_chunk:
                    chunk_text = separator.join(current_chunk)
                    chunks.append(chunk_text)
                    current_chunk = []
                    current_size = 0

                # Recursively split this large split using remaining separators
                # Find the next separator in the list
                sep_index = -1
                for i, s in enumerate(available_separators):
                    if s == separator:
                        sep_index = i
                        break

                if sep_index >= 0 and sep_index < len(available_separators) - 1:
                    # Try splitting with a more granular separator
                    remaining_seps = available_separators[sep_index + 1 :]
                    sub_chunks = self._split_recursive_with_separators(
                        split, target_size, overlap, remaining_seps
                    )
                    chunks.extend(sub_chunks)
                else:
                    # Fallback: hard split by character count
                    start = 0
                    while start < len(split):
                        end = min(start + target_size, len(split))
                        chunks.append(split[start:end])
                        if overlap > 0:
                            start = end - overlap
                            if start >= len(split) - overlap:
                                break
                        else:
                            start = end
            else:
                current_chunk.append(split)
                current_size += split_size

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = separator.join(current_chunk)
            if chunk_text:
                chunks.append(chunk_text)

        return chunks


# Global instances
document_processor = DocumentProcessor()
text_chunker = TextChunker()
