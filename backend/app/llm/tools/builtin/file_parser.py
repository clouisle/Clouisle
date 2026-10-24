"""
文件解析工具

使用受保护的 Asset 保存完整的 MarkItDown 提取文本，并按有界行窗口返回预览，
模型可继续通过 read_asset/search_asset 读取到 eof。

工具入参：files_url: list[str] - 文件 URL 或当前范围内的受保护附件 URL
工具出参：包含每个文件 ref、citation 和有界预览的结构化结果
"""

import json
import logging
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.i18n import t
from app.llm.tools.registry import ToolConcurrency

from ..registry import tool_registry, ToolParameter

logger = logging.getLogger(__name__)

MAX_FILES = 10
MAX_CALL_PREVIEW_BYTES = 32 * 1024
PREVIEW_OMITTED_READING = (
    "Preview omitted to stay within the response budget. "
    "Use read_asset with this ref to read the document; search_asset locates text."
)

# 支持的文件扩展名（与 app.services.file_parser.FileParserService 保持一致）
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".xml",
    ".rtf",
}


def get_filename_from_url(url: str) -> str:
    """从 URL 中提取文件名"""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    return Path(path).name


def get_extension_from_url(url: str) -> str:
    """从 URL 中提取文件扩展名"""
    filename = get_filename_from_url(url)
    return Path(filename).suffix.lower()


def _resolve_extension(filename: str, content_type: str) -> str | None:
    """Pick a canonical parser extension from the filename or declared type."""
    extension = Path(filename).suffix.lower()
    if extension in SUPPORTED_EXTENSIONS:
        return extension
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized.startswith("text/"):
        return ".md" if "markdown" in normalized else ".txt"
    inferred = {
        "application/json": ".json",
        "application/xml": ".xml",
        "application/rtf": ".rtf",
    }.get(normalized)
    if inferred:
        return inferred
    from app.services.asset_url_import import infer_filename_extension

    guessed = infer_filename_extension(normalized, filename)
    return guessed if guessed in SUPPORTED_EXTENSIONS else None


def _preview_fields(document: dict) -> dict:
    """Bounded read fields shared by every per-file entry."""
    return {
        "start_line": document["start_line"],
        "total_lines": document["total_lines"],
        "segments": document["segments"],
        "next_cursor": document["next_cursor"],
        "eof": document["eof"],
    }


def _error_entry(
    url: str,
    error: str,
    *,
    filename: str | None = None,
    ref: str | None = None,
) -> dict:
    display_url = "data:" if url.startswith("data:") else url
    entry = {
        "url": display_url,
        "filename": filename or get_filename_from_url(display_url),
        "error": error,
        "success": False,
    }
    if ref is not None:
        entry["ref"] = ref
    return entry


def _business_error_entry(url: str, exc) -> dict:
    kwargs = dict(exc.kwargs)
    if exc.msg_key == "fetch_webpage_http_error" and "status_code" not in kwargs:
        kwargs["status_code"] = exc.status_code
    return _error_entry(
        url,
        t(exc.msg_key or "tool_execution_failed", **kwargs),
    )


async def _read_preview(asset) -> dict:
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.asset_document import read_document
    from app.services.upload_storage import get_upload_storage_backend

    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    return await read_document(asset, storage=storage)


async def _with_preview(
    entry: dict,
    asset,
    *,
    preview_budget: int,
) -> tuple[dict, int]:
    """Attach one bounded preview while respecting the whole-call budget."""
    if preview_budget <= 0:
        entry["preview_omitted"] = True
        entry["reading"] = PREVIEW_OMITTED_READING
        return entry, 0
    try:
        document = await _read_preview(asset)
    except ValueError as exc:
        entry["success"] = False
        entry["error"] = t(str(exc))
        return entry, 0
    except RuntimeError:
        entry["success"] = False
        entry["error"] = t("file_not_found")
        return entry, 0
    segments = document["segments"]
    size = len(json.dumps(segments, ensure_ascii=False).encode("utf-8"))
    entry["filename"] = document["filename"]
    entry["total_lines"] = document["total_lines"]
    if size > preview_budget:
        entry["preview_omitted"] = True
        entry["reading"] = PREVIEW_OMITTED_READING
        return entry, 0
    entry.update(_preview_fields(document))
    return entry, size


async def _parse_one(
    url: str,
    *,
    scope_type,
    scope_id,
    user,
    expected_team_id,
    preview_budget: int,
) -> tuple[dict, int]:
    from app.schemas.response import BusinessError
    from app.services.asset_url_import import (
        InternalDocument,
        internal_storage_key,
        load_url_document,
        persist_scoped_document,
    )
    from app.services.citations import stable_citation_id
    from app.services.file_parser import file_parser_service

    is_internal = internal_storage_key(url) is not None
    if not is_internal and not url.startswith("data:"):
        extension = get_extension_from_url(url)
        if extension and extension not in SUPPORTED_EXTENSIONS:
            return _error_entry(url, t("unsupported_file_type")), 0

    try:
        source = await load_url_document(
            url,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=expected_team_id,
        )
    except BusinessError as exc:
        return _business_error_entry(url, exc), 0

    if isinstance(source, InternalDocument):
        entry = {
            "url": url,
            "filename": source.asset.display_filename,
            "mime_type": source.asset.content_type,
            "size": source.asset.size,
            "citation_id": stable_citation_id("asset", source.asset.id),
            "ref": source.ref,
            "success": True,
        }
        title = (source.asset.provenance or {}).get("title")
        if title:
            entry["title"] = title
        return await _with_preview(entry, source.asset, preview_budget=preview_budget)

    filename = source.filename
    extension = _resolve_extension(filename, source.content_type)
    if extension is None:
        return _error_entry(url, t("unsupported_file_type"), filename=filename), 0
    if not Path(filename).suffix:
        filename = f"{filename}{extension}"

    try:
        extracted = await file_parser_service.extract_file(source.content, filename)
    except ValueError as exc:
        return _error_entry(url, t(str(exc)), filename=filename), 0

    display_filename = f"{Path(filename).stem[:195]}.md"
    try:
        persisted = await persist_scoped_document(
            extracted.text.encode("utf-8"),
            filename=display_filename,
            content_type="text/markdown",
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=expected_team_id,
            provenance={
                "origin": "external_url",
                "url": None if url.startswith("data:") else url,
                "final_url": None
                if source.final_url.startswith("data:")
                else source.final_url,
                "title": extracted.title,
                "original_filename": filename,
                "source_content_type": source.content_type,
            },
        )
    except BusinessError as exc:
        return _business_error_entry(url, exc), 0

    entry = {
        "url": url if not url.startswith("data:") else None,
        "filename": display_filename,
        "title": extracted.title,
        "mime_type": extracted.mime_type,
        "size": extracted.size,
        "citation_id": stable_citation_id("asset", persisted.asset.id),
        "ref": persisted.ref,
        "success": True,
    }
    return await _with_preview(entry, persisted.asset, preview_budget=preview_budget)


async def parse_files(
    files_url: list[str],
    agent=None,
    user=None,
    conversation_id=None,
    workflow_run_id=None,
) -> dict:
    """
    解析文件内容并在当前执行范围内保存完整提取文本。

    每个文件只返回有界行窗口；需要更多内容时用 read_asset 继续读取到 eof，
    或用 search_asset 定位文本。当前范围内的受保护附件 URL 直接复用原 Asset，
    不经过公开 HTTP。

    Args:
        files_url: 文件 URL 列表（也支持受保护附件 URL）

    Returns:
        每个文件的 ref、citation 与有界预览
    """
    from app.schemas.response import BusinessError
    from app.services.asset_url_import import resolve_document_scope

    if not files_url:
        return {"error": t("file_required"), "success": False, "files": []}
    if not isinstance(files_url, list) or not all(
        isinstance(item, str) and item for item in files_url
    ):
        return {"error": t("validation_error"), "success": False, "files": []}
    if len(files_url) > MAX_FILES:
        return {
            "error": t("validation_error"),
            "success": False,
            "files": [],
            "detail": f"files_url accepts at most {MAX_FILES} entries per call",
        }

    try:
        scope_type, scope_id = resolve_document_scope(
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
    except BusinessError:
        return {
            "error": t("agent_context_required"),
            "success": False,
            "files": [],
        }

    expected_team_id = getattr(agent, "team_id", None)
    files: list[dict] = []
    preview_budget = MAX_CALL_PREVIEW_BYTES
    for url in files_url:
        try:
            entry, used = await _parse_one(
                url,
                scope_type=scope_type,
                scope_id=scope_id,
                user=user,
                expected_team_id=expected_team_id,
                preview_budget=preview_budget,
            )
            preview_budget -= used
            files.append(entry)
        except BusinessError as exc:
            files.append(_business_error_entry(url, exc))
        except Exception as exc:
            logger.exception("Failed to parse file %s: %s", url, exc)
            files.append(_error_entry(url, t("file_parse_error")))

    return {
        "kind": "document.files",
        "success": all(entry.get("success") for entry in files),
        "files": files,
    }


def register_file_parser_tools() -> None:
    """注册文件解析工具"""

    tool_registry.register(
        name="markitdown",
        concurrency=ToolConcurrency.SHARED,
        description=(
            "解析文件内容。将 PDF、Word、Excel、PPT 等文档转换为文本并保存为受保护的"
            "文档，返回有界预览与 ref；需要更多内容时用 read_asset 继续读取到 eof，"
            "或用 search_asset 定位文本。支持的格式：PDF、Word (.docx/.doc)、"
            "Excel (.xlsx/.xls)、PowerPoint (.pptx/.ppt)、文本文件 "
            "(.txt/.md/.csv/.json/.html/.xml)。"
        ),
        parameters=[
            ToolParameter(
                name="files_url",
                type="array",
                description="文件 URL 列表。每个 URL 指向一个需要解析的文件。",
                required=True,
                items={"type": "string"},
            ),
        ],
    )(parse_files)
