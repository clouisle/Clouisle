"""
网页搜索工具

提供网页搜索功能，支持多种搜索引擎。
注意：实际使用需要配置搜索 API Key。
"""

import logging
from html.parser import HTMLParser

import httpx

from app.core.i18n import t
from ..registry import tool_registry, ToolParameter

logger = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text while skipping script and style content."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self._chunks)


async def web_search(
    query: str,
    num_results: int = 5,
    search_engine: str = "tavily",
    credentials: dict[str, str] | None = None,
) -> dict:
    """
    搜索网页

    Args:
        query: 搜索关键词
        num_results: 返回结果数量，默认 5
        search_engine: 搜索引擎，目前支持 "tavily"
        credentials: 凭证信息（包含 TAVILY_API_KEY）

    Returns:
        搜索结果列表
    """
    if search_engine == "tavily":
        return await _tavily_search(query, num_results, credentials)
    else:
        return {
            "query": query,
            "error": t("web_search_unsupported_engine", search_engine=search_engine),
            "success": False,
        }


async def _tavily_search(
    query: str, num_results: int, credentials: dict[str, str] | None = None
) -> dict:
    """
    使用 Tavily API 搜索

    Tavily 是一个专为 AI 优化的搜索 API
    https://tavily.com/
    """
    # 只从 credentials 获取 API key
    api_key = None
    if credentials:
        api_key = credentials.get("TAVILY_API_KEY")
        logger.info("Tavily credentials received: %s", bool(api_key))
    else:
        logger.warning("No credentials provided to Tavily search")

    if not api_key:
        logger.error("No Tavily API key found in credentials")
        return {
            "query": query,
            "error": t("tavily_api_key_not_configured"),
            "success": False,
            "results": [],
        }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": num_results,
                    "include_answer": True,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                        "score": item.get("score"),
                    }
                )

            return {
                "query": query,
                "answer": data.get("answer"),
                "results": results,
                "success": True,
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Tavily search HTTP error: {e}")
        return {
            "query": query,
            "error": t("web_search_api_error", status_code=e.response.status_code),
            "success": False,
            "results": [],
        }
    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return {
            "query": query,
            "error": t("tool_execution_failed"),
            "success": False,
            "results": [],
        }


async def fetch_webpage(url: str, max_length: int = 5000) -> dict:
    """
    获取网页内容

    Args:
        url: 网页 URL
        max_length: 返回内容的最大长度

    Returns:
        网页内容
    """
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CloudisleBot/1.0)",
                },
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                extractor = _HTMLTextExtractor()
                extractor.feed(response.text)
                extractor.close()
                text = " ".join(extractor.get_text().split())

                if len(text) > max_length:
                    text = text[:max_length] + "..."

                return {
                    "url": url,
                    "content": text,
                    "content_type": "text/html",
                    "success": True,
                }
            elif "application/json" in content_type:
                return {
                    "url": url,
                    "content": response.text[:max_length],
                    "content_type": "application/json",
                    "success": True,
                }
            else:
                return {
                    "url": url,
                    "error": t(
                        "fetch_webpage_unsupported_content_type",
                        content_type=content_type,
                    ),
                    "success": False,
                }

    except httpx.HTTPStatusError as e:
        return {
            "url": url,
            "error": t("fetch_webpage_http_error", status_code=e.response.status_code),
            "success": False,
        }
    except Exception as e:
        return {
            "url": url,
            "error": t("tool_execution_failed"),
            "success": False,
        }


def register_web_search_tools() -> None:
    """注册网页搜索相关工具"""

    tool_registry.register(
        name="web_search",
        description="搜索网页。使用搜索引擎查找相关信息。当需要获取最新信息、查找事实或研究某个话题时使用此工具。",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词或问题",
                required=True,
            ),
            ToolParameter(
                name="num_results",
                type="integer",
                description="返回结果数量，默认 5，最大 10",
                required=False,
                default=5,
            ),
        ],
    )(web_search)

    tool_registry.register(
        name="fetch_webpage",
        description="获取网页内容。读取指定 URL 的网页文本内容。用于深入阅读搜索结果中感兴趣的页面。",
        parameters=[
            ToolParameter(
                name="url",
                type="string",
                description="要获取的网页 URL",
                required=True,
            ),
            ToolParameter(
                name="max_length",
                type="integer",
                description="返回内容的最大字符数，默认 5000",
                required=False,
                default=5000,
            ),
        ],
    )(fetch_webpage)
