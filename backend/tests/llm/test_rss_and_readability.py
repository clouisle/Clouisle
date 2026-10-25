"""
Tests for builtin RSS feed reader and enhanced fetch_webpage readability extraction.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.tools.builtin import rss as rss_subject
from app.llm.tools.builtin import web_search as web_subject
from app.schemas.response import BusinessError
from app.services.citations import stable_citation_id


@pytest.mark.anyio
async def test_rss_feed_reader_success(monkeypatch):
    rss_xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>Tech News Feed</title>
        <link>https://example.com</link>
        <description>Daily tech news &amp; updates</description>
        <item>
          <title>Article 1</title>
          <link>https://example.com/article-1</link>
          <pubDate>Mon, 01 Jan 2026 12:00:00 GMT</pubDate>
          <author>Alice</author>
          <description><![CDATA[<p>Hello <b>World</b> with <script>alert(1)</script> tags.</p>]]></description>
        </item>
        <item>
          <title>Article 2</title>
          <link>https://example.com/article-2</link>
          <pubDate>Tue, 02 Jan 2026 12:00:00 GMT</pubDate>
          <author>Bob</author>
          <description>Simple summary without HTML</description>
        </item>
      </channel>
    </rss>
    """

    class FakeResponse:
        status_code = 200
        content = rss_xml

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(rss_subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await rss_subject.read_rss_feed("https://example.com/feed.xml", limit=5)

    assert result["success"] is True
    assert result["feed_title"] == "Tech News Feed"
    assert result["feed_link"] == "https://example.com"
    assert result["feed_description"] == "Daily tech news & updates"
    assert len(result["articles"]) == 2

    first = result["articles"][0]
    assert first["title"] == "Article 1"
    assert first["link"] == "https://example.com/article-1"
    assert first["author"] == "Alice"
    assert "<script>" not in first["summary"]
    assert "<p>" not in first["summary"]
    assert "Hello World with tags." in first["summary"]
    assert first["citation_id"] == stable_citation_id(
        "web", "https://example.com/article-1"
    )

    second = result["articles"][1]
    assert second["title"] == "Article 2"
    assert second["link"] == "https://example.com/article-2"
    assert second["author"] == "Bob"
    assert second["summary"] == "Simple summary without HTML"
    # 验证没有 author 或 summary 的条目不会暴露空键
    assert "non_existent_key" not in second


@pytest.mark.anyio
async def test_rss_feed_reader_http_error(monkeypatch):
    class FakeResponse:
        status_code = 404
        content = b"Not Found"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(rss_subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(rss_subject, "t", lambda key, **kwargs: (key, kwargs))

    result = await rss_subject.read_rss_feed("https://example.com/not-found.xml")
    assert result["success"] is False
    assert result["error"] == ("fetch_webpage_http_error", {"status_code": 404})


@pytest.mark.anyio
async def test_fetch_webpage_readability_extraction(monkeypatch):
    from app.services import asset_url_import

    sample_html = """<!DOCTYPE html>
    <html>
      <head><title>Test Article Page</title></head>
      <body>
        <nav><a href="/">Home</a><a href="/about">About</a></nav>
        <article>
          <h1>Test Article Page</h1>
          <p>This is the main body content of the article that should be extracted clearly by trafilatura.</p>
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    url = "https://example.com/article"

    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        lambda **_: (
            asset_url_import.AssetScopeType.CONVERSATION,
            uuid.uuid4(),
        ),
    )
    monkeypatch.setattr(
        asset_url_import,
        "load_url_document",
        AsyncMock(
            return_value=asset_url_import.ExternalDocument(
                content=sample_html.encode("utf-8"),
                content_type="text/html",
                filename="article",
                url=url,
                final_url=url,
                charset="utf-8",
            )
        ),
    )
    persisted = SimpleNamespace(asset=SimpleNamespace(id="asset"), ref="abcd")
    persist = AsyncMock(return_value=persisted)
    monkeypatch.setattr(asset_url_import, "persist_scoped_document", persist)
    monkeypatch.setattr(
        web_subject,
        "_read_preview",
        AsyncMock(
            return_value={
                "filename": "article.md",
                "start_line": 1,
                "total_lines": 2,
                "segments": [
                    {"line": 1, "text": "Test Article Page", "continuation": False},
                    {
                        "line": 2,
                        "text": "This is the main body content of the article.",
                        "continuation": False,
                    },
                ],
                "next_cursor": None,
                "eof": True,
            }
        ),
    )

    result = await web_subject.fetch_webpage(url)

    assert result["success"] is True
    assert "Test Article Page" in (result["title"] or "")
    preview_text = "\n".join(segment["text"] for segment in result["segments"])
    assert "This is the main body content" in preview_text
    assert "Copyright 2026" not in preview_text
    assert result["ref"] == "abcd"
    assert result["citation_id"] == stable_citation_id("web", url)
    assert result["eof"] is True
    assert result["total_lines"] == 2
    markdown = persist.await_args.args[0].decode("utf-8")
    assert "This is the main body content" in markdown
    assert "Copyright 2026" not in markdown
    assert persist.await_args.kwargs["filename"] == "article.md"
    assert persist.await_args.kwargs["content_type"] == "text/markdown"
    assert persist.await_args.kwargs["provenance"]["url"] == url


@pytest.mark.anyio
async def test_fetch_webpage_requires_scope_before_network(monkeypatch):
    from app.services import asset_url_import

    load = AsyncMock(side_effect=AssertionError("network must not run"))
    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        lambda **_: (_ for _ in ()).throw(BusinessError(msg_key="validation_error")),
    )
    monkeypatch.setattr(asset_url_import, "load_url_document", load)

    result = await web_subject.fetch_webpage("https://example.com/article")

    assert result["success"] is False
    assert result["url"] == "https://example.com/article"
    load.assert_not_awaited()


@pytest.mark.anyio
async def test_fetch_webpage_reuses_internal_protected_asset(monkeypatch):
    from app.services import asset_url_import

    url = "/api/v1/upload/files/agent-attachments/2026/10/uploaded.md"

    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        lambda **_: (
            asset_url_import.AssetScopeType.CONVERSATION,
            uuid.uuid4(),
        ),
    )
    monkeypatch.setattr(
        asset_url_import,
        "load_url_document",
        AsyncMock(
            return_value=asset_url_import.InternalDocument(
                asset=SimpleNamespace(
                    display_filename="uploaded.md",
                    provenance={"title": "Uploaded"},
                ),
                ref="cafe",
                url=url,
            )
        ),
    )
    persist = AsyncMock(side_effect=AssertionError("must not persist"))
    monkeypatch.setattr(asset_url_import, "persist_scoped_document", persist)
    monkeypatch.setattr(
        web_subject,
        "_read_preview",
        AsyncMock(
            return_value={
                "filename": "uploaded.md",
                "start_line": 1,
                "total_lines": 1,
                "segments": [{"line": 1, "text": "hello", "continuation": False}],
                "next_cursor": None,
                "eof": True,
            }
        ),
    )

    result = await web_subject.fetch_webpage(url)

    assert result["success"] is True
    assert result["ref"] == "cafe"
    assert result["title"] == "Uploaded"
    assert result["segments"][0]["text"] == "hello"
    persist.assert_not_awaited()
