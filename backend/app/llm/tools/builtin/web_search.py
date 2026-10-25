"""
网页搜索工具

提供网页搜索功能，支持多种搜索引擎。
搜索引擎与 API Key 由站点管理员统一配置；工具调用方不能传入或覆盖凭证。
"""

import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.i18n import t
from app.schemas.response import BusinessError
from app.services.citations import stable_citation_id, with_web_citation_ids
from app.services.web_search_config import (
    build_searxng_search_url,
    get_web_search_runtime,
)
from ..registry import tool_registry, ToolParameter, ToolConcurrency

logger = logging.getLogger(__name__)

SEARXNG_TIMEOUT_SECONDS = 30


async def web_search(
    query: str,
    num_results: int = 5,
    search_engine: str = "auto",
) -> dict:
    """
    搜索网页。

    Provider selection and credentials are site-managed. The tool never reads
    caller-supplied credentials, and there is no fallback between providers:
    - auto: use the site administrator's configured default engine.
    - tavily: use the site Tavily configuration (must be enabled).
    - bocha: use the site Bocha configuration (must be enabled).

    Args:
        query: 搜索关键词或问题
        num_results: 返回结果数量，默认 5，最大 10
        search_engine: 站点已启用的搜索引擎：'auto', 'tavily', 'bocha'

    Returns:
        包含标准搜索结果与引用 ID 的结构化字典
    """
    requested = (search_engine or "auto").strip().lower()
    num_results = max(1, min(num_results, 10))

    try:
        engine, provider_config = await get_web_search_runtime(requested)
    except BusinessError as exc:
        return {
            "query": query,
            "error": _translate_business_error(exc),
            "success": False,
            "results": [],
        }

    if engine == "tavily":
        result = await _tavily_search(query, num_results, provider_config)
    elif engine == "bocha":
        result = await _bocha_search(query, num_results, provider_config)
    elif engine == "searxng":
        result = await _searxng_search(query, num_results, provider_config)
    else:
        # get_web_search_runtime only resolves configured providers.
        return {
            "query": query,
            "error": t("web_search_unsupported_engine", search_engine=engine),
            "success": False,
            "results": [],
        }

    result["search_engine"] = engine
    return result


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


async def _searxng_search(
    query: str, num_results: int, credentials: dict[str, str] | None = None
) -> dict:
    """使用站点配置的 SearXNG 实例搜索（需要实例启用 JSON 输出）。"""
    config = credentials or {}
    base_url = str(config.get("SEARXNG_BASE_URL") or "").strip()
    if not base_url:
        logger.warning("SearXNG base URL is missing from the site configuration")
        return {
            "query": query,
            "error": t("web_search_engine_not_configured", engine="searxng"),
            "success": False,
            "results": [],
        }

    headers = {"Accept": "application/json"}
    token = config.get("SEARXNG_AUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(
            timeout=SEARXNG_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            response = await client.post(
                build_searxng_search_url(base_url),
                data={"q": query, "format": "json"},
                headers=headers,
            )
    except httpx.TimeoutException:
        logger.error("SearXNG search timed out")
        return {
            "query": query,
            "error": t("web_search_searxng_timeout"),
            "success": False,
            "results": [],
        }
    except Exception as exc:
        # Never log provider payloads: upstream errors can echo configuration.
        logger.error("SearXNG search error: %s", type(exc).__name__)
        return {
            "query": query,
            "error": t("tool_execution_failed"),
            "success": False,
            "results": [],
        }

    if 300 <= response.status_code < 400:
        logger.error(
            "SearXNG search refused a redirect (status=%s)", response.status_code
        )
        return {
            "query": query,
            "error": t("web_search_searxng_redirect"),
            "success": False,
            "results": [],
        }
    if response.status_code == 403:
        logger.error("SearXNG search is forbidden (status=403)")
        return {
            "query": query,
            "error": t("web_search_searxng_forbidden"),
            "success": False,
            "results": [],
        }
    if response.status_code >= 400:
        logger.error("SearXNG search HTTP error: %s", response.status_code)
        return {
            "query": query,
            "error": t("web_search_api_error", status_code=response.status_code),
            "success": False,
            "results": [],
        }

    try:
        data = response.json()
    except ValueError:
        logger.error("SearXNG search returned invalid JSON")
        return {
            "query": query,
            "error": t("web_search_searxng_invalid_response"),
            "success": False,
            "results": [],
        }

    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        logger.error("SearXNG search response is missing a results list")
        return {
            "query": query,
            "error": t("web_search_searxng_invalid_response"),
            "success": False,
            "results": [],
        }

    results = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url_value = item.get("url")
        if not isinstance(url_value, str):
            continue
        url = url_value.strip()
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
        except ValueError:
            continue
        title = item.get("title")
        content = item.get("content")
        results.append(
            {
                "title": title.strip() if isinstance(title, str) else "",
                "url": url,
                "content": content.strip() if isinstance(content, str) else "",
            }
        )
        if len(results) >= num_results:
            break

    if not results:
        logger.warning("SearXNG search returned no usable results")
        return {
            "query": query,
            "error": t("web_search_searxng_empty_results"),
            "success": False,
            "results": [],
        }

    return {
        "query": query,
        "results": with_web_citation_ids(results),
        "success": True,
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
