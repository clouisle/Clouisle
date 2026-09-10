"""
RSS / Atom 订阅源解析工具

获取并解析 RSS/Atom 订阅源，返回结构化的文章列表。
"""

import asyncio
import html
import logging
from typing import Any
import bleach
import feedparser
import httpx

from app.core.i18n import t
from app.services.citations import stable_citation_id
from ..registry import ToolConcurrency, ToolParameter, tool_registry

logger = logging.getLogger(__name__)


def _clean_html_text(raw_html: str | None) -> str:
    """清理 HTML 标签并保留纯文本内容。"""
    if not raw_html:
        return ""
    # strip=True 会将 HTML 标签剥离掉，仅保留文字
    text = bleach.clean(raw_html, tags=[], strip=True)
    # 反转义 HTML 实体（例如 &amp; -> &）
    text = html.unescape(text)
    # 合并多余空白符
    return " ".join(text.split())


def _parse_feed_content(content: str | bytes) -> dict[str, Any]:
    """在同步线程中解析 Feed 内容。"""
    return feedparser.parse(content)


async def read_rss_feed(url: str, limit: int = 10) -> dict[str, Any]:
    """
    读取并解析 RSS 或 Atom 订阅源。

    Args:
        url: RSS 或 Atom 订阅源 URL
        limit: 返回文章的最大条数，默认为 10，最大 30

    Returns:
        结构化的订阅源元数据与文章列表
    """
    limit = max(1, min(limit, 30))

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; Clouisle-RSSReader/1.0; +https://clouisle.com)"
                )
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
            raw_content = response.content

        # 在单独线程中运行 feedparser，避免阻塞异步主事件循环
        feed_data = await asyncio.to_thread(_parse_feed_content, raw_content)

        # 检查是否发生严重解析错误或缺少 entries/feed 结构
        if feed_data.bozo and not feed_data.entries and not feed_data.feed:
            bozo_exc = feed_data.get("bozo_exception")
            logger.warning("Feedparser failed to parse %s: %s", url, bozo_exc)
            return {
                "url": url,
                "error": t("rss_feed_parse_error"),
                "success": False,
            }

        feed_info = feed_data.get("feed", {})
        feed_title = feed_info.get("title") or "Untitled Feed"
        feed_link = feed_info.get("link") or url
        feed_description = _clean_html_text(
            feed_info.get("description") or feed_info.get("subtitle")
        )

        articles = []
        for entry in feed_data.entries[:limit]:
            entry_title = entry.get("title") or "Untitled"
            entry_link = entry.get("link")
            published = entry.get("published") or entry.get("updated")
            author = entry.get("author")

            # 获取摘要：优先 summary，其次 description，再从 content 中寻找
            raw_summary = entry.get("summary") or entry.get("description") or ""
            if not raw_summary and "content" in entry and entry.content:
                raw_summary = entry.content[0].get("value", "")
            summary = _clean_html_text(raw_summary)

            article_item: dict[str, Any] = {"title": entry_title}
            if entry_link:
                article_item["link"] = entry_link
                article_item["citation_id"] = stable_citation_id("web", entry_link)
            if published:
                article_item["published"] = published
            if author:
                article_item["author"] = author
            if summary:
                article_item["summary"] = summary

            articles.append(article_item)

        result: dict[str, Any] = {
            "url": url,
            "feed_title": feed_title,
            "feed_link": feed_link,
            "articles": articles,
            "total_articles": len(articles),
            "citation_id": stable_citation_id("web", url),
            "success": True,
        }
        if feed_description:
            result["feed_description"] = feed_description

        return result
    except httpx.TimeoutException:
        return {"url": url, "error": t("tool_execution_timeout"), "success": False}
    except Exception as e:
        logger.exception("Failed to read RSS feed from %s: %s", url, e)
        return {"url": url, "error": t("tool_execution_failed"), "success": False}


def register_rss_tools() -> None:
    """注册 RSS 相关内置工具。"""
    tool_registry.register(
        name="rss_feed_reader",
        concurrency=ToolConcurrency.SHARED,
        description="抓取并解析 RSS 或 Atom 订阅源，返回包含最新文章标题、作者、发布时间、摘要及原文链接的结构化列表。",
        parameters=[
            ToolParameter(
                name="url",
                type="string",
                description="RSS 或 Atom 订阅源的完整 URL 地址（例如 https://example.com/feed.xml）",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="返回的文章最大条数，默认 10，最大 30",
                required=False,
                default=10,
            ),
        ],
    )(read_rss_feed)
