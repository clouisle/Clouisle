"""Secure URL-to-Asset import: scope, SSRF, storage, and persistence."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.asset import Asset, AssetScopeType, AssetSource, AssetStatus
from app.schemas.response import BusinessError
from app.services import asset_url_import
from app.services.asset_url_import import (
    ExternalDocument,
    InternalDocument,
    decode_data_url,
    fetch_external_url,
    internal_storage_key,
    load_url_document,
    persist_scoped_document,
    resolve_document_scope,
    safe_display_filename,
)
from app.services.upload_storage import LocalUploadStorage


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    from app.api.v1.endpoints import upload

    monkeypatch.setattr(upload, "UPLOAD_ROOT", tmp_path)
    return tmp_path


def test_internal_storage_key_only_accepts_relative_or_same_origin(monkeypatch):
    monkeypatch.setattr(
        asset_url_import.settings, "API_BASE_URL", "https://api.example.test/"
    )

    assert internal_storage_key("/api/v1/upload/files/agent/2026/10/a.txt") == (
        "agent/2026/10/a.txt"
    )
    assert (
        internal_storage_key(
            "https://api.example.test/api/v1/upload/files/agent/2026/10/a.txt"
        )
        == "agent/2026/10/a.txt"
    )
    assert (
        internal_storage_key(
            "https://api.example.test/api/v1/upload/files/agent%2F2026%2F10%2Fa.txt"
        )
        == "agent/2026/10/a.txt"
    )
    assert (
        internal_storage_key(
            "https://other.example.test/api/v1/upload/files/agent/2026/10/a.txt"
        )
        is None
    )
    assert internal_storage_key("https://example.test/files/a.txt") is None
    assert internal_storage_key("file:///api/v1/upload/files/a.txt") is None


def test_safe_display_filename_strips_paths_and_controls():
    assert safe_display_filename("https://x.test/a/b%20c.pdf?q=1", default="d") == (
        "b c.pdf"
    )
    assert safe_display_filename("https://x.test/bad%00name.txt", default="d") == (
        "bad_name.txt"
    )
    assert safe_display_filename("https://x.test/", default="fallback") == "fallback"
    assert safe_display_filename("../x", default="fallback") == "x"


def test_resolve_document_scope_prefers_workflow_and_rejects_absent():
    scope_type, scope_id = resolve_document_scope(
        conversation_id=uuid4(), workflow_run_id=uuid4()
    )
    assert scope_type == AssetScopeType.WORKFLOW_RUN

    with pytest.raises(BusinessError):
        resolve_document_scope(conversation_id=None, workflow_run_id=None)
    with pytest.raises(BusinessError):
        resolve_document_scope(conversation_id="not-a-uuid", workflow_run_id=None)


@pytest.mark.asyncio
async def test_load_internal_url_authorizes_asset_without_network(
    database, monkeypatch
):
    scope_id = uuid4()
    team_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="agent-attachments/2026/10/a.txt",
        source=AssetSource.UPLOAD,
        status=AssetStatus.AVAILABLE,
    )
    query = SimpleNamespace(first=AsyncMock(return_value=asset))
    monkeypatch.setattr(asset_url_import.Asset, "filter", lambda **_: query)
    authorize_scope = AsyncMock(return_value=team_id)
    authorize_asset = AsyncMock(return_value=asset)
    monkeypatch.setattr(asset_url_import, "authorize_asset_scope", authorize_scope)
    monkeypatch.setattr(asset_url_import, "authorize_asset_for_scope", authorize_asset)
    get_or_create_ref = AsyncMock(return_value=SimpleNamespace(ref="a1b2"))
    monkeypatch.setattr(
        asset_url_import.asset_service, "get_or_create_ref", get_or_create_ref
    )
    resolve_ref = AsyncMock(return_value=asset)
    monkeypatch.setattr(asset_url_import, "resolve_authorized_asset_ref", resolve_ref)
    fetch = AsyncMock(side_effect=AssertionError("network must not run"))
    monkeypatch.setattr(asset_url_import, "fetch_external_url", fetch)

    source = await load_url_document(
        "/api/v1/upload/files/agent-attachments/2026/10/a.txt",
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=scope_id,
        user=None,
        expected_team_id=team_id,
    )

    assert isinstance(source, InternalDocument)
    assert source.ref == "a1b2"
    authorize_scope.assert_awaited_once()
    authorize_asset.assert_awaited_once()
    get_or_create_ref.assert_awaited_once()
    resolve_ref.assert_awaited_once()
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_internal_url_propagates_scope_denial(database, monkeypatch):
    monkeypatch.setattr(
        asset_url_import,
        "authorize_asset_scope",
        AsyncMock(side_effect=BusinessError(msg_key="access_denied", status_code=403)),
    )

    with pytest.raises(BusinessError) as denied:
        await load_url_document(
            "/api/v1/upload/files/agent-attachments/2026/10/a.txt",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4()),
            expected_team_id=None,
        )
    assert denied.value.status_code == 403


def _fakes(monkeypatch, responses, requests):
    class FakeResponse:
        def __init__(self, status_code, body, headers=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {}

        async def aiter_bytes(self):
            for offset in range(0, len(self._body), 3):
                yield self._body[offset : offset + 3]

    class FakeStream:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *_args):
            return False

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False
            assert kwargs["timeout"] == asset_url_import.DEFAULT_TIMEOUT

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, method, url):
            requests.append(url)
            return FakeStream(responses[url])

    monkeypatch.setattr(asset_url_import.httpx, "AsyncClient", FakeClient)


@pytest.mark.asyncio
async def test_fetch_external_follows_redirect_with_ssrf_checks(monkeypatch):
    first = "https://example.test/a"
    second = "https://example.test/b"
    responses = {
        first: _response(302, b"", {"location": "/b"}),
        second: _response(
            200,
            b"hello world",
            {"content-type": "text/plain; charset=utf-8"},
        ),
    }
    requests: list[str] = []
    _fakes(monkeypatch, responses, requests)
    checked = []

    async def check(url):
        checked.append(url)

    monkeypatch.setattr(asset_url_import, "ensure_external_http_url_allowed", check)

    fetched = await fetch_external_url(first)

    assert requests == [first, second]
    assert checked == [first, second]
    assert fetched.content == b"hello world"
    assert fetched.content_type == "text/plain"
    assert fetched.charset == "utf-8"
    assert fetched.filename == "b"


@pytest.mark.asyncio
async def test_fetch_external_stops_before_private_redirect_target(monkeypatch):
    first = "https://example.test/a"
    responses = {first: _response(302, b"", {"location": "http://127.0.0.1/x"})}
    requests: list[str] = []
    _fakes(monkeypatch, responses, requests)

    async def check(url):
        if "127.0.0.1" in url:
            raise BusinessError(msg_key="http_tool_url_host_not_allowed")

    monkeypatch.setattr(asset_url_import, "ensure_external_http_url_allowed", check)

    with pytest.raises(BusinessError) as blocked:
        await fetch_external_url(first)
    assert blocked.value.msg_key == "http_tool_url_host_not_allowed"
    assert requests == [first]


@pytest.mark.asyncio
async def test_fetch_external_enforces_declared_and_streamed_limits(monkeypatch):
    url = "https://example.test/big"
    _fakes(
        monkeypatch,
        {url: _response(200, b"abcdef", {"content-length": "6"})},
        [],
    )
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as too_large:
        await fetch_external_url(url, max_bytes=4)
    assert too_large.value.msg_key == "file_too_large"


@pytest.mark.asyncio
async def test_fetch_external_http_error_and_empty_body(monkeypatch):
    url = "https://example.test/missing"
    _fakes(monkeypatch, {url: _response(404, b"")}, [])
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as http_error:
        await fetch_external_url(url)
    assert http_error.value.msg_key == "fetch_webpage_http_error"
    assert http_error.value.kwargs == {"status_code": 404}

    _fakes(monkeypatch, {url: _response(200, b"")}, [])
    with pytest.raises(BusinessError) as empty:
        await fetch_external_url(url)
    assert empty.value.msg_key == "file_download_failed"


def test_decode_data_url_supports_plain_and_base64():
    plain = decode_data_url("data:text/plain,hello%20world")
    assert plain.content == b"hello world"
    assert plain.filename == "data.txt"

    encoded = base64.b64encode("内容".encode()).decode()
    binary = decode_data_url(f"data:text/markdown;base64,{encoded}")
    assert binary.content.decode() == "内容"
    assert binary.filename == "data.md"

    with pytest.raises(BusinessError) as invalid:
        decode_data_url("data:text/plain")
    assert invalid.value.msg_key == "fetch_webpage_unsupported_scheme"


def test_decode_data_url_enforces_size():
    with pytest.raises(BusinessError) as too_large:
        decode_data_url("data:text/plain,abcdef", max_bytes=3)
    assert too_large.value.msg_key == "file_too_large"

    encoded = base64.b64encode(b"abcdef").decode()
    with pytest.raises(BusinessError):
        decode_data_url(f"data:text/plain;base64,{encoded}", max_bytes=3)


def test_decode_text_never_replaces_unreadable_bytes():
    assert asset_url_import.decode_text(b"hello", "utf-8") == "hello"
    with pytest.raises(ValueError, match="document_extraction_decode_failed"):
        asset_url_import.decode_text(b"\xff\xff", "utf-8")


@pytest.mark.asyncio
async def test_fetch_external_rejects_non_success_status(monkeypatch):
    url = "https://example.test/cached"
    _fakes(monkeypatch, {url: _response(304, b"")}, [])
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as error:
        await fetch_external_url(url)
    assert error.value.msg_key == "file_download_failed"


@pytest.mark.asyncio
async def test_persist_scoped_document_uses_protected_storage(
    database, upload_root, monkeypatch
):
    scope_id = uuid4()
    team_id = None
    authorize_scope = AsyncMock(return_value=team_id)
    monkeypatch.setattr(asset_url_import, "authorize_asset_scope", authorize_scope)

    persisted = await persist_scoped_document(
        b"# heading\nbody",
        filename="../report.pdf",
        content_type="text/markdown",
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=scope_id,
        user=None,
        expected_team_id=team_id,
        provenance={"origin": "web"},
    )

    asset = await Asset.get(id=persisted.asset.id)
    assert asset.source == AssetSource.UPLOAD
    assert asset.team_id == team_id
    assert asset.display_filename == "report.pdf"
    assert asset.provenance == {"origin": "web"}
    assert asset.storage_key.startswith(
        f"{asset_url_import.PROTECTED_IMPORT_CATEGORY}/"
    )
    binding = await asset.scope_refs.all()
    assert len(binding) == 1
    assert binding[0].ref == persisted.ref
    assert binding[0].scope_id == scope_id

    storage = LocalUploadStorage(upload_root)
    assert await storage.read(asset.storage_key) == b"# heading\nbody"
    authorize_scope.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_external_maps_timeout_and_connection_errors(monkeypatch):
    class TimeoutClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, *_args):
            raise asset_url_import.httpx.TimeoutException("slow")

    monkeypatch.setattr(asset_url_import.httpx, "AsyncClient", TimeoutClient)
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as timeout:
        await fetch_external_url("https://example.test/slow")
    assert timeout.value.msg_key == "tool_execution_timeout"

    class OfflineClient(TimeoutClient):
        def stream(self, *_args):
            raise asset_url_import.httpx.ConnectError("offline")

    monkeypatch.setattr(asset_url_import.httpx, "AsyncClient", OfflineClient)
    with pytest.raises(BusinessError) as offline:
        await fetch_external_url("https://example.test/offline")
    assert offline.value.msg_key == "file_download_failed"


@pytest.mark.asyncio
async def test_load_internal_missing_or_derived_asset_is_not_found(
    database, monkeypatch
):
    monkeypatch.setattr(
        asset_url_import,
        "authorize_asset_scope",
        AsyncMock(return_value=None),
    )
    query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(asset_url_import.Asset, "filter", lambda **_: query)

    with pytest.raises(BusinessError) as missing:
        await load_url_document(
            "/api/v1/upload/files/agent-attachments/2026/10/missing.txt",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=None,
            expected_team_id=None,
        )
    assert missing.value.msg_key == "file_not_found"

    query.first.return_value = SimpleNamespace(
        id=uuid4(), source=AssetSource.DERIVED_TEXT
    )
    with pytest.raises(BusinessError) as derived:
        await load_url_document(
            "/api/v1/upload/files/agent-attachments/2026/10/derived.txt",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=None,
            expected_team_id=None,
        )
    assert derived.value.msg_key == "file_not_found"


@pytest.mark.asyncio
async def test_load_url_document_handles_data_and_unsupported_schemes(
    database, monkeypatch
):
    monkeypatch.setattr(
        asset_url_import,
        "authorize_asset_scope",
        AsyncMock(return_value=None),
    )

    data = await load_url_document(
        "data:text/plain,hello",
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=uuid4(),
        user=None,
        expected_team_id=None,
    )
    assert data.content == b"hello"

    with pytest.raises(BusinessError) as unsupported:
        await load_url_document(
            "file:///etc/passwd",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=None,
            expected_team_id=None,
        )
    assert unsupported.value.msg_key == "fetch_webpage_unsupported_scheme"

    with pytest.raises(BusinessError) as invalid:
        await load_url_document(
            "",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=None,
            expected_team_id=None,
        )
    assert invalid.value.msg_key == "validation_error"


@pytest.mark.asyncio
async def test_persist_rejects_empty_content_before_authorization(monkeypatch):
    authorize = AsyncMock()
    monkeypatch.setattr(asset_url_import, "authorize_asset_scope", authorize)

    with pytest.raises(BusinessError) as empty:
        await persist_scoped_document(
            b"",
            filename="a.txt",
            content_type="text/plain",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=None,
            expected_team_id=None,
        )
    assert empty.value.msg_key == "file_download_failed"
    authorize.assert_not_awaited()


def test_extension_helpers():
    assert asset_url_import.infer_filename_extension("text/html", None) == ".html"
    assert asset_url_import.infer_filename_extension("text/markdown", None) == ".md"
    assert asset_url_import.infer_filename_extension("application/pdf", None) == ".pdf"
    assert asset_url_import.infer_filename_extension(None, "notes.csv") == ".csv"
    assert asset_url_import.infer_filename_extension(None, None) == ".bin"
    assert asset_url_import.is_html_document("text/html", None) is True
    assert asset_url_import.is_html_document(None, "index.HTM") is True
    assert asset_url_import.is_html_document("text/plain", "notes.txt") is False


def test_decode_data_url_rejects_invalid_base64():
    with pytest.raises(BusinessError) as invalid:
        decode_data_url("data:text/plain;base64,!!!!")
    assert invalid.value.msg_key == "file_download_failed"


@pytest.mark.asyncio
async def test_fetch_external_rejects_invalid_max_bytes_before_client(monkeypatch):
    monkeypatch.setattr(
        asset_url_import.httpx,
        "AsyncClient",
        lambda **_: (_ for _ in ()).throw(AssertionError("client must not open")),
    )

    for value in (0, -1, "10"):
        with pytest.raises(BusinessError) as invalid:
            await fetch_external_url("https://example.test/a", max_bytes=value)
        assert invalid.value.msg_key == "validation_error"


@pytest.mark.asyncio
async def test_fetch_external_rejects_redirect_without_location(monkeypatch):
    url = "https://example.test/a"
    requests: list[str] = []
    _fakes(monkeypatch, {url: _response(302, b"", {})}, requests)
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as error:
        await fetch_external_url(url)
    assert error.value.msg_key == "file_download_failed"
    assert requests == [url]


@pytest.mark.asyncio
async def test_fetch_external_ignores_invalid_content_length(monkeypatch):
    url = "https://example.test/a"
    _fakes(
        monkeypatch,
        {
            url: _response(
                200,
                b"abc",
                {"content-type": "text/plain", "content-length": "unknown"},
            )
        },
        [],
    )
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    fetched = await fetch_external_url(url, max_bytes=10)
    assert fetched.content == b"abc"

    _fakes(
        monkeypatch,
        {
            url: _response(
                200,
                b"abc",
                {"content-type": "text/plain", "content-length": "3"},
            )
        },
        [],
    )
    fetched = await fetch_external_url(url, max_bytes=10)
    assert fetched.content == b"abc"


@pytest.mark.asyncio
async def test_fetch_external_rejects_streamed_oversize_without_header(monkeypatch):
    url = "https://example.test/a"
    _fakes(monkeypatch, {url: _response(200, b"abcdef")}, [])
    monkeypatch.setattr(
        asset_url_import, "ensure_external_http_url_allowed", AsyncMock()
    )

    with pytest.raises(BusinessError) as too_large:
        await fetch_external_url(url, max_bytes=3)
    assert too_large.value.msg_key == "file_too_large"


def test_decode_data_url_rejects_oversized_encoded_payloads():
    encoded = base64.b64encode(b"abcdef").decode()
    with pytest.raises(BusinessError) as base64_large:
        decode_data_url(f"data:text/plain;base64,{encoded}", max_bytes=1)
    assert base64_large.value.msg_key == "file_too_large"

    with pytest.raises(BusinessError) as percent_large:
        decode_data_url("data:text/plain,abcdef", max_bytes=1)
    assert percent_large.value.msg_key == "file_too_large"


def test_decode_data_url_rejects_empty_payload():
    with pytest.raises(BusinessError) as empty:
        decode_data_url("data:text/plain,")
    assert empty.value.msg_key == "file_download_failed"

    with pytest.raises(BusinessError) as undecodable:
        decode_data_url("data:text/plain,\ud800")
    assert undecodable.value.msg_key == "file_download_failed"


@pytest.mark.asyncio
async def test_load_url_document_delegates_http_to_secure_fetcher(
    database, monkeypatch
):
    monkeypatch.setattr(
        asset_url_import, "authorize_asset_scope", AsyncMock(return_value=None)
    )
    fetched = ExternalDocument(
        content=b"hello",
        content_type="text/plain",
        filename="a.txt",
        url="https://example.test/a.txt",
        final_url="https://example.test/a.txt",
    )
    fetch = AsyncMock(return_value=fetched)
    monkeypatch.setattr(asset_url_import, "fetch_external_url", fetch)

    source = await load_url_document(
        "https://example.test/a.txt",
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=uuid4(),
        user=None,
        expected_team_id=None,
        max_bytes=7,
    )

    assert source is fetched
    fetch.assert_awaited_once_with("https://example.test/a.txt", max_bytes=7)


def test_charset_and_extension_fallbacks():
    from app.services.asset_url_import import _decode_charset

    assert _decode_charset("text/html; foo=bar; charset='utf-8'") == "utf-8"
    assert _decode_charset("text/html; foo=bar") is None
    assert _decode_charset("text/html") is None
    assert asset_url_import.decode_text(b"hi", "") == "hi"
    assert (
        asset_url_import.infer_filename_extension(
            "application/x-qwerty-unknown", "notes.abc"
        )
        == ".abc"
    )


def _response(status_code, body, headers=None):
    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.headers = headers or {}
            self._body = body

        async def aiter_bytes(self):
            yield self._body

    return FakeResponse()
