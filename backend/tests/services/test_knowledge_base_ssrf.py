import socket
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError
from app.services.document_processor import DocumentProcessor


@pytest.mark.asyncio
async def test_fetch_url_content_blocks_ssrf_hosts(monkeypatch):
    """fetch_url_content should block private IPs and cloud metadata addresses."""
    processor = DocumentProcessor()

    # Blocked local/metadata URLs
    blocked_urls = [
        "http://127.0.0.1:8000/api/v1/users",
        "http://localhost:3000",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]

    for url in blocked_urls:
        with pytest.raises(BusinessError) as exc_info:
            await processor.fetch_url_content(url)
        assert exc_info.value.msg_key in {
            "http_tool_url_host_not_allowed",
            "http_tool_url_invalid",
        }


@pytest.mark.asyncio
async def test_fetch_url_content_markitdown_redirect_blocked(monkeypatch):
    """MarkItDown fetching through _SSRFProtectedSession should block SSRF redirects."""
    processor = DocumentProcessor()

    # When resolving public host, return public IP; when resolving redirect, return loopback IP
    def fake_getaddrinfo(host, port=None, **kwargs):
        if host == "public.example.org":
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 80),
                )
            ]
        if host in {"127.0.0.1", "localhost", "169.254.169.254"}:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 80))
            ]
        raise socket.gaierror("lookup failed")

    monkeypatch.setattr(
        "app.core.network_security.socket.getaddrinfo", fake_getaddrinfo
    )

    # Simulate MarkItDown using a session that attempts to send a request to a blocked redirect URL
    import requests

    class RedirectSimulatingMarkItDown:
        def __init__(self, requests_session=None):
            self.session = requests_session

        def convert(self, url):
            if self.session:
                req = requests.Request("GET", "http://127.0.0.1:8000/admin").prepare()
                self.session.send(req)
            return SimpleNamespace(text_content="content", title="Title")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=RedirectSimulatingMarkItDown),
    )

    with pytest.raises(BusinessError) as exc_info:
        await processor.fetch_url_content("http://public.example.org/doc")
    assert exc_info.value.msg_key == "http_tool_url_host_not_allowed"


@pytest.mark.asyncio
async def test_fetch_url_content_httpx_fallback_redirect_blocked(monkeypatch):
    """httpx fallback should block redirects to private IPs via request hook."""
    processor = DocumentProcessor()

    def fake_getaddrinfo(host, port=None, **kwargs):
        if host == "public.example.org":
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", port or 80),
                )
            ]
        if host in {"127.0.0.1", "localhost", "169.254.169.254"}:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 80))
            ]
        raise socket.gaierror("lookup failed")

    monkeypatch.setattr(
        "app.core.network_security.socket.getaddrinfo", fake_getaddrinfo
    )
    monkeypatch.setitem(sys.modules, "markitdown", None)

    import httpx

    async def fake_handler(request: httpx.Request):
        if str(request.url) == "http://public.example.org/redirect":
            return httpx.Response(
                302, headers={"location": "http://127.0.0.1:8000/secret"}
            )
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(fake_handler)
    orig_client_init = httpx.AsyncClient.__init__

    def custom_client_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig_client_init(self, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.__init__", custom_client_init)

    with pytest.raises(BusinessError) as exc_info:
        await processor.fetch_url_content("http://public.example.org/redirect")
    assert exc_info.value.msg_key == "http_tool_url_host_not_allowed"


@pytest.mark.anyio
async def test_add_url_document_blocks_ssrf(monkeypatch):
    """add_url_document endpoint should reject URLs pointing to internal/private targets."""
    kb_id = uuid4()
    kb = SimpleNamespace(id=kb_id, name="KB", document_count=0, save=AsyncMock())
    user = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.add_url_document(
            kb_id,
            SimpleNamespace(
                name="Internal AWS",
                source_url="http://169.254.169.254/latest/meta-data/",
            ),
            SimpleNamespace(),
            user,
        )
    assert exc_info.value.msg_key == "http_tool_url_host_not_allowed"


@pytest.mark.anyio
async def test_preview_document_chunks_propagates_ssrf_business_error(monkeypatch):
    """preview_document_chunks should propagate SSRF BusinessError cleanly."""
    kb_id = uuid4()
    doc_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    doc = SimpleNamespace(
        id=doc_id,
        knowledge_base_id=kb_id,
        file_path=None,
        source_url="http://127.0.0.1:8000/api",
        doc_type="url",
    )

    class Query:
        def __init__(self, item):
            self.item = item

        async def first(self):
            return self.item

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )

    # Let fetch_url_content raise BusinessError
    monkeypatch.setattr(
        knowledge_bases.document_processor,
        "fetch_url_content",
        AsyncMock(side_effect=BusinessError(msg_key="http_tool_url_host_not_allowed")),
    )

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.preview_document_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            preview_in=SimpleNamespace(
                clean_text=True,
                separator=None,
                chunk_size=1000,
                chunk_overlap=100,
            ),
            current_user=user,
        )
    assert exc_info.value.msg_key == "http_tool_url_host_not_allowed"


@pytest.mark.asyncio
async def test_fetch_url_content_markitdown_typeerror_fallback(monkeypatch):
    """When MarkItDown does not support requests_session, it falls back to default constructor."""
    processor = DocumentProcessor()

    class OldMarkItDown:
        def __init__(self):
            pass

        def convert(self, url):
            return SimpleNamespace(text_content="legacy text", title="Legacy")

    monkeypatch.setattr(
        "app.core.network_security.validate_external_http_url",
        lambda value, **kwargs: value,
    )
    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=OldMarkItDown),
    )

    text, metadata = await processor.fetch_url_content("https://example.com/doc")
    assert text == "legacy text"
    assert metadata["title"] == "Legacy"


@pytest.mark.anyio
async def test_add_url_document_success(monkeypatch):
    """add_url_document should succeed when URL is a valid external target."""
    kb_id = uuid4()
    doc_id = uuid4()
    kb = SimpleNamespace(id=kb_id, name="KB", document_count=0, save=AsyncMock())
    user = SimpleNamespace(id=uuid4())
    created = SimpleNamespace(id=doc_id)
    loaded = SimpleNamespace(id=doc_id, name="Public Doc")
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document, "create", AsyncMock(return_value=created)
    )

    class FakeDocQuery:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def _coro():
                return loaded

            return _coro().__await__()

    monkeypatch.setattr(
        knowledge_bases.Document, "get", lambda **_kwargs: FakeDocQuery()
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_document",
        AsyncMock(return_value={"id": str(doc_id)}),
    )
    monkeypatch.setattr(
        "app.core.network_security.validate_external_http_url",
        lambda value, **kwargs: value,
    )

    response = await knowledge_bases.add_url_document(
        kb_id,
        SimpleNamespace(
            name="Public Doc",
            source_url="https://example.com/public",
        ),
        SimpleNamespace(),
        user,
    )
    assert response["data"] == {"id": str(doc_id)}
