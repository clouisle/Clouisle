"""
文件解析工具

使用 MarkItDown 解析各种文档格式（PDF、Word、Excel、PPT 等），
将其转换为文本内容供 LLM 分析。

工具入参：files_url: list[str] - 文件 URL 列表
工具出参：str - 解析后的文本内容
"""

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote

import httpx
from markitdown import MarkItDown

from app.core.config import settings

from ..registry import tool_registry, ToolParameter

logger = logging.getLogger(__name__)

# 支持的文件扩展名
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


async def parse_files(
    files_url: list[str],
    max_content_length: int = 100000,
    truncate_strategy: str = "end",
) -> str:
    """
    解析文件内容

    使用 MarkItDown 将各种文档格式转换为 Markdown 文本。

    Args:
        files_url: 文件 URL 列表
        max_content_length: 每个文件的最大内容长度（字符数），默认 100000
        truncate_strategy: 截断策略，可选 "end"（保留开头）、"start"（保留结尾）、"middle"（保留首尾）

    Returns:
        解析后的文本内容，多个文件用分隔符分开
    """
    if not files_url:
        return "错误：未提供文件 URL"

    results = []
    md = MarkItDown()

    for url in files_url:
        try:
            # 检查文件扩展名
            ext = get_extension_from_url(url)
            filename = get_filename_from_url(url)

            if ext and ext not in SUPPORTED_EXTENSIONS:
                results.append(f"--- {filename} ---\n[不支持的文件格式: {ext}]")
                continue

            # 下载文件
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                # 处理内部 URL
                if url.startswith("/"):
                    base_url = str(settings.API_BASE_URL).rstrip("/")
                    url = f"{base_url}{url}"

                response = await client.get(url)
                response.raise_for_status()
                content = response.content

            # 保存到临时文件并解析
            with tempfile.NamedTemporaryFile(
                suffix=ext or ".bin", delete=True
            ) as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()

                # 使用 MarkItDown 解析
                result = md.convert(tmp_file.name)
                text_content = result.text_content if result else ""

            # 截断内容
            if len(text_content) > max_content_length:
                text_content = truncate_content(
                    text_content, max_content_length, truncate_strategy
                )

            results.append(f"--- {filename} ---\n{text_content}")

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to download file {url}: HTTP {e.response.status_code}")
            results.append(f"--- {get_filename_from_url(url)} ---\n[下载失败: HTTP {e.response.status_code}]")
        except Exception as e:
            logger.error(f"Failed to parse file {url}: {e}")
            results.append(f"--- {get_filename_from_url(url)} ---\n[解析失败: {str(e)}]")

    return "\n\n".join(results)


def truncate_content(content: str, max_length: int, strategy: str = "end") -> str:
    """
    截断内容

    Args:
        content: 原始内容
        max_length: 最大长度
        strategy: 截断策略
            - "end": 保留开头，截断结尾
            - "start": 保留结尾，截断开头
            - "middle": 保留首尾，截断中间

    Returns:
        截断后的内容
    """
    if len(content) <= max_length:
        return content

    truncation_marker = "\n\n... [内容已截断] ...\n\n"
    marker_len = len(truncation_marker)

    if strategy == "start":
        # 保留结尾
        return truncation_marker + content[-(max_length - marker_len) :]
    elif strategy == "middle":
        # 保留首尾
        half = (max_length - marker_len) // 2
        return content[:half] + truncation_marker + content[-half:]
    else:
        # 默认保留开头
        return content[: max_length - marker_len] + truncation_marker


def register_file_parser_tools() -> None:
    """注册文件解析工具"""

    tool_registry.register(
        name="markitdown",
        description=(
            "解析文件内容。将 PDF、Word、Excel、PPT 等文档转换为文本。"
            "当用户上传文件并希望你分析其内容时使用此工具。"
            "支持的格式：PDF、Word (.docx/.doc)、Excel (.xlsx/.xls)、"
            "PowerPoint (.pptx/.ppt)、文本文件 (.txt/.md/.csv/.json/.html/.xml)。"
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
