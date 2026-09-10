"""
网页搜索工具

提供网页搜索功能，支持多种搜索引擎。
注意：实际使用需要配置搜索 API Key。
"""

import asyncio
import logging
from typing import Any

import httpx
from markitdown import MarkItDown
import trafilatura
from app.core.i18n import t
from app.services.citations import stable_citation_id, with_web_citation_ids
from ..registry import tool_registry, ToolParameter, ToolConcurrency

logger = logging.getLogger(__name__)


async def web_search(
    query: str,
    num_results: int = 5,
    search_engine: str = "auto",
    credentials: dict[str, str] | None = None,
) -> dict:
    """
    搜索网页。

    支持多引擎架构：
    - auto: 优先使用已配置 API Key 的商业搜索引擎（Tavily、Bocha 等），若未配置则自动使用免 Key 的 DuckDuckGo。
    - tavily: 使用 Tavily 搜索（需要 TAVILY_API_KEY）。
    - bocha: 使用国内博查 AI 搜索（需要 BOCHA_API_KEY）。
    - duckduckgo / ddg: 免配置、零 Key 网页搜索。

    Args:
        query: 搜索关键词或问题
        num_results: 返回结果数量，默认 5，最大 10
        search_engine: 搜索引擎，支持 'auto', 'tavily', 'bocha', 'duckduckgo'
        credentials: 凭证信息（可包含 TAVILY_API_KEY, BOCHA_API_KEY 等）

    Returns:
        包含标准搜索结果与引用 ID 的结构化字典
    """
    engine = (search_engine or "auto").strip().lower()
    creds = credentials or {}
    num_results = max(1, min(num_results, 10))

    if engine == "auto":
        # 根据可用凭证自动路由优先级：Tavily -> Bocha -> DuckDuckGo 零配置兜底
        if creds.get("TAVILY_API_KEY"):
            engine = "tavily"
        elif creds.get("BOCHA_API_KEY"):
            engine = "bocha"
        else:
            engine = "duckduckgo"

    if engine == "tavily":
        result = await _tavily_search(query, num_results, creds)
        # 若 Tavily 因为未配 Key 或网络异常失败，且是 auto 模式发起的，则尝试 DuckDuckGo 兜底
        if not result.get("success") and search_engine == "auto":
            logger.info(
                "Tavily search failed or key missing, falling back to DuckDuckGo"
            )
            return await _duckduckgo_search(query, num_results)
        return result
    elif engine == "bocha":
        result = await _bocha_search(query, num_results, creds)
        if not result.get("success") and search_engine == "auto":
            logger.info(
                "Bocha search failed or key missing, falling back to DuckDuckGo"
            )
            return await _duckduckgo_search(query, num_results)
        return result
    elif engine in ("duckduckgo", "ddg"):
        return await _duckduckgo_search(query, num_results)
    else:
        return {
            "query": query,
            "error": t("web_search_unsupported_engine", search_engine=search_engine),
            "success": False,
            "results": [],
        }


async def _tavily_search(
    query: str, num_results: int, credentials: dict[str, str] | None = None
) -> dict:
    """使用 Tavily API 搜索。"""
    api_key = credentials.get("TAVILY_API_KEY") if credentials else None
    if not api_key:
        logger.warning("No Tavily API key found in credentials")
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
                "results": with_web_citation_ids(results),
                "success": True,
            }
    except httpx.HTTPStatusError as e:
        logger.error("Tavily search HTTP error: %s", e)
        return {
            "query": query,
            "error": t("web_search_api_error", status_code=e.response.status_code),
            "success": False,
            "results": [],
        }
    except Exception as e:
        logger.error("Tavily search error: %s", e)
        return {
            "query": query,
            "error": t("tool_execution_failed"),
            "success": False,
            "results": [],
        }


async def _bocha_search(
    query: str, num_results: int, credentials: dict[str, str] | None = None
) -> dict:
    """
    使用博查 AI (Bocha) OpenAPI 搜索。
    针对国内信息与长尾中文内容有良好优化。
    https://bocha.ai/
    """
    api_key = credentials.get("BOCHA_API_KEY") if credentials else None
    if not api_key:
        logger.warning("No Bocha API key found in credentials")
        return {
            "query": query,
            "error": t("bocha_api_key_not_configured"),
            "success": False,
            "results": [],
        }

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                "https://api.bochaai.com/v1/web-search",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "query": query,
                    "count": num_results,
                    "summary": True,
                },
            )
            response.raise_for_status()
            data = response.json()

            raw_results = (
                data.get("data", {}).get("webPages", {}).get("value", [])
                if isinstance(data.get("data"), dict)
                else data.get("webPages", {}).get("value", [])
            )
            results = []
            for item in raw_results:
                results.append(
                    {
                        "title": item.get("name", "") or item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("snippet", "") or item.get("summary", ""),
                    }
                )

            return {
                "query": query,
                "results": with_web_citation_ids(results),
                "success": True,
            }
    except httpx.HTTPStatusError as e:
        logger.error("Bocha search HTTP error: %s", e)
        return {
            "query": query,
            "error": t("web_search_api_error", status_code=e.response.status_code),
            "success": False,
            "results": [],
        }
    except Exception as e:
        logger.error("Bocha search error: %s", e)
        return {
            "query": query,
            "error": t("tool_execution_failed"),
            "success": False,
            "results": [],
        }


def _sync_ddg_search(query: str, num_results: int) -> list[dict[str, Any]]:
    """同步执行 DuckDuckGo 搜索。"""
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=num_results))


async def _duckduckgo_search(query: str, num_results: int) -> dict:
    """使用 DuckDuckGo 免配置搜索。"""
    try:
        raw_results = await asyncio.wait_for(
            asyncio.to_thread(_sync_ddg_search, query, num_results),
            timeout=20,
        )
        results = []
        for item in raw_results:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", "") or item.get("url", ""),
                    "content": item.get("body", "") or item.get("snippet", ""),
                }
            )
        return {
            "query": query,
            "results": with_web_citation_ids(results),
            "success": True,
        }
    except asyncio.TimeoutException:
        return {
            "query": query,
            "error": t("tool_execution_timeout"),
            "success": False,
            "results": [],
        }
    except Exception as e:
        logger.error("DuckDuckGo search error: %s", e)
        return {
            "query": query,
            "error": t("tool_execution_failed"),
            "success": False,
            "results": [],
        }


def _extract_readable_content(html: str, url: str) -> tuple[str, str | None]:
    """使用 trafilatura 提取网页正文与标题，并在失败时兜底。"""
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_images=False,
        include_tables=True,
        favor_precision=True,
    )
    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = metadata.title if metadata and metadata.title else None

    if extracted and extracted.strip():
        return extracted.strip(), title

    # Trafilatura 无法提取正文（例如非文章页面或极简结构），使用 MarkItDown 兜底
    fallback_result = MarkItDown().convert(url)
    fallback_text = (fallback_result.text_content or "").strip()
    fallback_title = (
        title or (getattr(fallback_result, "title", None) or "").strip() or None
    )
    return fallback_text, fallback_title


async def fetch_webpage(url: str, max_length: int = 5000) -> dict[str, Any]:
    """
    获取网页内容并提取正文 Markdown。

    优先通过 HTTP 请求并结合 Trafilatura 提取纯正文和元数据；
    若非普通 HTTP(S) URL（如 data: 协议或本地文档）、网络异常或正文提取为空，
    则回退至 MarkItDown 引擎解析。

    Args:
        url: 网页 URL
        max_length: 返回内容的最大长度，默认 5000

    Returns:
        网页标题与正文内容
    """
    # 如果是 data: 协议或非标准 HTTP URL，直接用 MarkItDown 处理
    if not url.startswith(("http://", "https://")):
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(MarkItDown().convert, url), timeout=30
            )
            text = (result.text_content or "").strip()
            title = (getattr(result, "title", None) or "").strip() or None
            if len(text) > max_length:
                text = text[:max_length] + "..."
            return {
                "url": url,
                "title": title,
                "content": text,
                "citation_id": stable_citation_id("web", url),
                "success": True,
            }
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code is not None:
                return {
                    "url": url,
                    "error": t("fetch_webpage_http_error", status_code=status_code),
                    "success": False,
                }
            return {"url": url, "error": t("tool_execution_failed"), "success": False}

    try:
        async with httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                return {
                    "url": url,
                    "error": t(
                        "fetch_webpage_http_error", status_code=response.status_code
                    ),
                    "success": False,
                }
            html_text = response.text

        # 在后台线程中执行正文提取
        text, title = await asyncio.to_thread(_extract_readable_content, html_text, url)

        if len(text) > max_length:
            text = text[:max_length] + "..."

        return {
            "url": url,
            "title": title,
            "content": text,
            "citation_id": stable_citation_id("web", url),
            "success": True,
        }
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code if e.response else 500
        return {
            "url": url,
            "error": t("fetch_webpage_http_error", status_code=status_code),
            "success": False,
        }
    except httpx.TimeoutException:
        return {"url": url, "error": t("tool_execution_timeout"), "success": False}
    except Exception as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code is not None:
            return {
                "url": url,
                "error": t("fetch_webpage_http_error", status_code=status_code),
                "success": False,
            }
        logger.warning(
            "fetch_webpage HTTP fetch failed for %s: %s, falling back to MarkItDown",
            url,
            e,
        )
        try:
            fallback = await asyncio.wait_for(
                asyncio.to_thread(MarkItDown().convert, url), timeout=15
            )
            text = (fallback.text_content or "").strip()
            title = (getattr(fallback, "title", None) or "").strip() or None
            if len(text) > max_length:
                text = text[:max_length] + "..."
            return {
                "url": url,
                "title": title,
                "content": text,
                "citation_id": stable_citation_id("web", url),
                "success": True,
            }
        except Exception as fallback_e:
            status_code = getattr(
                getattr(fallback_e, "response", None), "status_code", None
            )
            if status_code is not None:
                return {
                    "url": url,
                    "error": t("fetch_webpage_http_error", status_code=status_code),
                    "success": False,
                }
            return {"url": url, "error": t("tool_execution_failed"), "success": False}


def register_web_search_tools() -> None:
    """注册网页搜索相关工具"""

    tool_registry.register(
        name="web_search",
        concurrency=ToolConcurrency.SHARED,
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
            ToolParameter(
                name="search_engine",
                type="string",
                description="搜索引擎类型，支持 'auto'（自动检测凭证并兜底 DuckDuckGo）, 'tavily', 'bocha'（博查搜索）, 'duckduckgo'（免 Key 搜索）。默认为 auto。",
                required=False,
                default="auto",
                enum=["auto", "tavily", "bocha", "duckduckgo"],
            ),
        ],
    )(web_search)

    tool_registry.register(
        name="fetch_webpage",
        concurrency=ToolConcurrency.SHARED,
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
