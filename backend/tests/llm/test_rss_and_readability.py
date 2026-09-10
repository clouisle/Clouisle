"""
Tests for builtin RSS feed reader and enhanced fetch_webpage readability extraction.
"""

import pytest

from app.llm.tools.builtin import rss as rss_subject
from app.llm.tools.builtin import web_search as web_subject
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

    class FakeResponse:
        status_code = 200
        text = sample_html

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(web_subject.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await web_subject.fetch_webpage(
        "https://example.com/article", max_length=5000
    )

    assert result["success"] is True
    assert "Test Article Page" in (result["title"] or "")
    assert "This is the main body content" in result["content"]
    assert "Copyright 2026" not in result["content"]
