"""
网页搜索工具

提供网页搜索功能，支持多种搜索引擎。
注意：实际使用需要配置搜索 API Key。
"""

import logging

import httpx

from app.core.config import settings

from ..registry import tool_registry, ToolParameter

logger = logging.getLogger(__name__)


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
            "error": f"Unsupported search engine: {search_engine}",
            "success": False,
        }


async def _tavily_search(query: str, num_results: int, credentials: dict[str, str] | None = None) -> dict:
    """
    使用 Tavily API 搜索

    Tavily 是一个专为 AI 优化的搜索 API
    https://tavily.com/
    """
    # 只从 credentials 获取 API key
    api_key = None
    if credentials:
        api_key = credentials.get("TAVILY_API_KEY")
        logger.info(f"Tavily API key from credentials: {api_key[:15] if api_key else 'None'}...{api_key[-4:] if api_key and len(api_key) > 19 else ''}")
    else:
        logger.warning("No credentials provided to Tavily search")

    if not api_key:
        logger.error("No Tavily API key found in credentials")
        return {
            "query": query,
            "error": "Tavily API key not configured. Please configure it in tool settings.",
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
            "error": f"Search API error: {e.response.status_code}",
            "success": False,
            "results": [],
        }
    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return {
            "query": query,
            "error": str(e),
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
                # 简单提取文本（实际项目可用 BeautifulSoup 等解析）
                text = response.text
                # 移除脚本和样式
                import re

                text = re.sub(
                    r"<script[^>]*>.*?</script>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(
                    r"<style[^>]*>.*?</style>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                # 移除 HTML 标签
                text = re.sub(r"<[^>]+>", " ", text)
                # 清理空白
                text = re.sub(r"\s+", " ", text).strip()

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
                    "error": f"Unsupported content type: {content_type}",
                    "success": False,
                }

    except httpx.HTTPStatusError as e:
        return {
            "url": url,
            "error": f"HTTP error: {e.response.status_code}",
            "success": False,
        }
    except Exception as e:
        return {
            "url": url,
            "error": str(e),
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
