"""
网页搜索工具

提供网页搜索功能，支持多种搜索引擎。
注意：实际使用需要配置搜索 API Key。
"""

import asyncio
import logging
from pathlib import Path
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup
import httpx
import trafilatura

from app.core.i18n import t
from app.schemas.response import BusinessError
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
    is_auto = engine == "auto"
    creds = credentials or {}
    num_results = max(1, min(num_results, 10))

    if is_auto:
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
        if not result.get("success") and is_auto:
            logger.info(
                "Tavily search failed or key missing, falling back to DuckDuckGo"
            )
            fallback_res = await _duckduckgo_search(query, num_results)
            fallback_res["search_engine"] = "duckduckgo"
            return fallback_res
        result["search_engine"] = "tavily"
        return result
    elif engine == "bocha":
        result = await _bocha_search(query, num_results, creds)
        if not result.get("success") and is_auto:
            logger.info(
                "Bocha search failed or key missing, falling back to DuckDuckGo"
            )
            fallback_res = await _duckduckgo_search(query, num_results)
            fallback_res["search_engine"] = "duckduckgo"
            return fallback_res
        result["search_engine"] = "bocha"
        return result
    elif engine in ("duckduckgo", "ddg"):
        res = await _duckduckgo_search(query, num_results)
        res["search_engine"] = "duckduckgo"
        return res
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


def _clean_ddg_href(href: str | None) -> str:
    """解析 DuckDuckGo 结果中的重定向链接。"""
    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    if "uddg=" in href:
        try:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in params and params["uddg"]:
                return params["uddg"][0]
        except Exception:
            pass
    return href


def _parse_ddg_html(html_text: str, max_results: int) -> list[dict[str, Any]]:
    """解析 DuckDuckGo HTML 搜索页面结果。"""
    soup = BeautifulSoup(html_text, "html.parser")
    results: list[dict[str, Any]] = []

    for item in soup.find_all("div", class_="result"):
        # 排除广告赞助卡片
        classes = item.get("class", [])
        if any("badge--ad" in c or "result--ad" in c for c in classes):
            continue

        title_node = item.find("a", class_="result__a")
        if not title_node:
            continue

        raw_href = title_node.get("href")
        url = _clean_ddg_href(raw_href)
        if not url.startswith(("http://", "https://")):
            continue

        title = title_node.get_text(strip=True)
        snippet_node = item.find("a", class_="result__snippet") or item.find(
            "div", class_="result__snippet"
        )
        snippet = snippet_node.get_text(strip=True) if snippet_node else ""

        results.append(
            {
                "title": title,
                "url": url,
                "content": snippet,
            }
        )
        if len(results) >= max_results:
            break

    return results


async def _duckduckgo_search(query: str, num_results: int) -> dict:
    """使用 DuckDuckGo 免配置搜索（纯 HTTP 实现，完全跨平台且安全）。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            response.raise_for_status()
            html_text = response.text

        results = await asyncio.to_thread(_parse_ddg_html, html_text, num_results)
        return {
            "query": query,
            "results": with_web_citation_ids(results),
            "success": True,
        }
    except httpx.TimeoutException:
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
    """Extract readable Markdown and the title from an HTML document."""
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
    return (extracted or "").strip(), title


def _document_payload(
    *,
    url: str,
    title: str | None,
    citation_id: str,
    ref: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Single-document payload rendered by the shared tool-output renderer."""
    segments = document["segments"]
    return {
        "kind": "web.document",
        "success": True,
        "url": url,
        "title": title,
        "citation_id": citation_id,
        "ref": ref,
        "filename": document["filename"],
        "start_line": document["start_line"],
        "total_lines": document["total_lines"],
        "segments": segments,
        "next_cursor": document["next_cursor"],
        "eof": document["eof"],
    }


def _error_payload(
    url: str,
    exc: BusinessError,
    *,
    ref: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": None if url.startswith("data:") else url,
        "error": _translate_business_error(exc),
        "success": False,
    }
    if ref is not None:
        payload["ref"] = ref
    return payload


def _translate_business_error(exc: BusinessError) -> str:
    kwargs = dict(exc.kwargs)
    if exc.msg_key == "fetch_webpage_http_error" and "status_code" not in kwargs:
        kwargs["status_code"] = exc.status_code
    return t(exc.msg_key or "tool_execution_failed", **kwargs)


def _markdown_filename(url: str, title: str | None) -> str:
    from app.services.asset_url_import import safe_display_filename

    base = "" if url.startswith("data:") else safe_display_filename(url, default="")
    stem = Path(base).stem if base else ""
    if not stem and title:
        stem = safe_display_filename(title.replace(" ", "-"), default="")
    return f"{(stem or 'webpage')[:200]}.md"


async def _read_preview(asset: Any) -> dict[str, Any]:
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.asset_document import read_document
    from app.services.upload_storage import get_upload_storage_backend

    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    return await read_document(asset, storage=storage)


async def fetch_webpage(
    url: str,
    agent: Any | None = None,
    user: Any | None = None,
    conversation_id: Any = None,
    workflow_run_id: Any = None,
) -> dict[str, Any]:
    """
    获取网页内容并在当前执行范围内保存完整正文。

    正文会完整保存为受保护的 Asset；本次响应只返回有界行窗口，模型可通过
    read_asset/search_asset 继续读取到 eof，不会静默截断。

    Args:
        url: 网页 URL，也可以是当前范围内受保护的附件文件 URL

    Returns:
        网页标题、有界正文预览、引用 ID 与 Asset ref
    """
    from app.services.asset_url_import import (
        InternalDocument,
        decode_text,
        infer_filename_extension,
        is_html_document,
        load_url_document,
        persist_scoped_document,
        resolve_document_scope,
    )

    try:
        scope_type, scope_id = resolve_document_scope(
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
    except BusinessError:
        return {
            "url": url if not url.startswith("data:") else None,
            "error": t("agent_context_required"),
            "success": False,
        }

    display_url = None if url.startswith("data:") else url
    expected_team_id = getattr(agent, "team_id", None)
    try:
        source = await load_url_document(
            url,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=expected_team_id,
        )
    except BusinessError as exc:
        return _error_payload(url, exc)

    citation_id = stable_citation_id("web", url)

    if isinstance(source, InternalDocument):
        try:
            document = await _read_preview(source.asset)
        except ValueError as exc:
            return {
                "url": display_url,
                "ref": source.ref,
                "error": t(str(exc)),
                "success": False,
            }
        except RuntimeError:
            return {
                "url": display_url,
                "error": t("file_not_found"),
                "success": False,
            }
        title = (source.asset.provenance or {}).get("title")
        return _document_payload(
            url=display_url,
            title=title,
            citation_id=citation_id,
            ref=source.ref,
            document=document,
        )

    title: str | None = None
    if is_html_document(source.content_type, source.filename):
        try:
            html = decode_text(source.content, source.charset)
        except ValueError as exc:
            return {
                "url": display_url,
                "error": t(str(exc)),
                "success": False,
            }
        try:
            text, title = await asyncio.to_thread(
                _extract_readable_content, html, source.final_url
            )
        except Exception:
            logger.warning(
                "Readability extraction failed for %s", source.final_url, exc_info=True
            )
            text, title = "", None
        if not text:
            from app.services.file_parser import file_parser_service

            try:
                extracted = await file_parser_service.extract_file(
                    source.content, "webpage.html"
                )
            except ValueError as exc:
                return _error_payload(url, BusinessError(msg_key=str(exc)))
            text = extracted.text
            title = title or extracted.title
        from app.services.file_parser import MAX_EXTRACTED_CHARS

        if len(text) > MAX_EXTRACTED_CHARS:
            return _error_payload(
                url,
                BusinessError(msg_key="asset_document_resource_limit_exceeded"),
            )
        content = text.encode("utf-8")
        content_type = "text/markdown"
        filename = _markdown_filename(url, title)
    else:
        content = source.content
        content_type = source.content_type
        filename = source.filename
        if not Path(filename).suffix:
            filename = f"{filename}{infer_filename_extension(content_type, filename)}"

    try:
        persisted = await persist_scoped_document(
            content,
            filename=filename,
            content_type=content_type,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=expected_team_id,
            provenance={
                "origin": "web",
                "url": display_url,
                "final_url": None
                if source.final_url.startswith("data:")
                else source.final_url,
                "title": title,
                "source_content_type": source.content_type,
                "citation_id": citation_id,
            },
        )
    except BusinessError as exc:
        return _error_payload(url, exc)

    try:
        document = await _read_preview(persisted.asset)
    except ValueError as exc:
        return {
            "url": display_url,
            "title": title,
            "ref": persisted.ref,
            "citation_id": citation_id,
            "error": t(str(exc)),
            "success": False,
        }
    except RuntimeError:
        return {
            "url": display_url,
            "error": t("file_not_found"),
            "success": False,
        }

    return _document_payload(
        url=display_url,
        title=title,
        citation_id=citation_id,
        ref=persisted.ref,
        document=document,
    )


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
        ],
    )(web_search)

    tool_registry.register(
        name="fetch_webpage",
        concurrency=ToolConcurrency.SHARED,
        description=(
            "获取网页内容。读取指定 URL 的网页正文，完整内容会保存为受保护的文档并返回"
            "有界预览与 ref；需要更多内容时用 read_asset 继续读取到 eof，或用 "
            "search_asset 定位文本。也支持当前范围内的受保护附件 URL。"
        ),
        parameters=[
            ToolParameter(
                name="url",
                type="string",
                description="要获取的网页 URL，或当前范围内的受保护附件文件 URL",
                required=True,
            ),
        ],
    )(fetch_webpage)
