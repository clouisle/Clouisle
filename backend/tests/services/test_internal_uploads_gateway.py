"""Tests for the worker -> api internal upload gateway.

Covers: token auth (fail-closed), the /internal/uploads/* endpoints, the
document_processor remote-mode branches (explicit HTTP calls), and the
UploadStorageBackend.list() capability added for media asset deletion.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

import app.services  # noqa: F401  # Initialize service exports before the endpoints.

from app.api.v1.endpoints.internal_uploads import router as internal_router
from app.core.config import settings
from app.services import upload_storage
from app.services.document_processor import DocumentProcessor, UploadGatewayError


@pytest.fixture
def gateway_app():
    app = FastAPI()
    app.include_router(internal_router, prefix="/internal")
    return app


@pytest.fixture
def gateway_client(gateway_app):
    return TestClient(gateway_app)


def _mock_storage(monkeypatch):
    storage = Mock()
    storage.response = AsyncMock(return_value=Response(content=b"bytes"))
    storage.save = AsyncMock(return_value="/tmp/uploads/key.bin")
    storage.exists = AsyncMock(return_value=True)
    storage.delete = AsyncMock()
    monkeypatch.setattr(
        "app.api.v1.endpoints.internal_uploads.get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )
    return storage


# ── Auth ──────────────────────────────────────────────────────────


def test_gateway_fails_closed_when_token_unset(gateway_client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
    resp = gateway_client.get("/internal/uploads/read", params={"key": "documents/x"})
    assert resp.status_code == 404


def test_gateway_rejects_missing_and_wrong_token(gateway_client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    resp = gateway_client.get("/internal/uploads/read", params={"key": "documents/x"})
    assert resp.status_code == 401

    resp = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/x"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401

    resp = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/x"},
        headers={"Authorization": "Token secret-token"},
    )
    assert resp.status_code == 401


def test_gateway_reads_token_from_rotating_secret_file(
    gateway_client, monkeypatch, tmp_path
):
    token_file = tmp_path / "internal-api-token"
    token_file.write_text("first-token", encoding="utf-8")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", str(token_file))
    _mock_storage(monkeypatch)

    first = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/kb/doc.pdf"},
        headers={"Authorization": "Bearer first-token"},
    )
    assert first.status_code == 200

    token_file.write_text("rotated-token", encoding="utf-8")
    rotated = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/kb/doc.pdf"},
        headers={"Authorization": "Bearer rotated-token"},
    )
    assert rotated.status_code == 200


def test_token_file_falls_back_to_environment_token(monkeypatch, tmp_path):
    token_file = tmp_path / "internal-api-token"
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "environment-token")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", str(token_file))

    assert settings.get_internal_api_token() == "environment-token"

    token_file.write_text("\n", encoding="utf-8")
    assert settings.get_internal_api_token() == "environment-token"


# ── Endpoints ─────────────────────────────────────────────────────


def test_read_streams_storage_response(gateway_client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    storage = _mock_storage(monkeypatch)

    resp = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/kb/doc.pdf"},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert resp.status_code == 200
    assert resp.content == b"bytes"
    storage.exists.assert_awaited_once_with("documents/kb/doc.pdf")
    storage.response.assert_awaited_once_with("documents/kb/doc.pdf")


def test_read_404_when_missing(gateway_client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    storage = _mock_storage(monkeypatch)
    storage.exists.return_value = False

    resp = gateway_client.get(
        "/internal/uploads/read",
        params={"key": "documents/missing.pdf"},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert resp.status_code == 404


def test_save_and_delete_and_exists(gateway_client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    storage = _mock_storage(monkeypatch)
    headers = {"Authorization": "Bearer secret-token"}

    save = gateway_client.put(
        "/internal/uploads/save",
        params={"key": "documents/kb/doc.pdf"},
        content=b"pdf",
        headers=headers,
    )
    assert save.status_code == 200
    assert save.json() == {"storage_path": "/tmp/uploads/key.bin"}
    storage.save.assert_awaited_once_with("documents/kb/doc.pdf", b"pdf")

    exists = gateway_client.head(
        "/internal/uploads/exists",
        params={"key": "documents/kb/doc.pdf"},
        headers=headers,
    )
    assert exists.status_code == 200

    storage.exists.return_value = False
    missing = gateway_client.head(
        "/internal/uploads/exists",
        params={"key": "documents/missing.pdf"},
        headers=headers,
    )
    assert missing.status_code == 404

    delete = gateway_client.delete(
        "/internal/uploads/delete",
        params={"key": "documents/kb/doc.pdf"},
        headers=headers,
    )
    assert delete.status_code == 204
    storage.delete.assert_awaited_once_with("documents/kb/doc.pdf")


def test_media_save_and_delete_delegate_to_document_processor(
    gateway_client, monkeypatch
):
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    headers = {"Authorization": "Bearer secret-token"}
    save_asset = AsyncMock(
        return_value={
            "path": "documents/kb/media/doc/a.png",
            "url": "/api/v1/knowledge-bases/kb/documents/doc/media/a.png",
            "filename": "a.png",
            "content_type": "image/png",
            "size": 3,
        }
    )
    delete_assets = AsyncMock()
    monkeypatch.setattr(
        "app.api.v1.endpoints.internal_uploads.document_processor",
        Mock(_save_media_asset=save_asset, delete_media_assets=delete_assets),
    )

    save = gateway_client.put(
        "/internal/uploads/media/11111111-1111-1111-1111-111111111111/"
        "22222222-2222-2222-2222-222222222222",
        content=b"png",
        headers={**headers, "Content-Type": "image/png"},
    )
    assert save.status_code == 200
    assert save.json()["filename"] == "a.png"
    save_asset.assert_awaited_once()

    delete = gateway_client.delete(
        "/internal/uploads/media/11111111-1111-1111-1111-111111111111/"
        "22222222-2222-2222-2222-222222222222",
        headers=headers,
    )
    assert delete.status_code == 204
    delete_assets.assert_awaited_once()


@pytest.fixture
def remote_processor(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_STORAGE_MODE", "remote")
    monkeypatch.setattr(settings, "API_INTERNAL_BASE_URL", "http://api:8000")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "secret-token")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", "")
    return DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))


def _patch_http_client(monkeypatch, *, status_code=200, stream_error=None):
    import importlib

    module = importlib.import_module("app.services.document_processor")

    async def aiter_bytes():
        if stream_error is not None:
            raise stream_error
        yield b"by"
        yield b"tes"

    stream_response = SimpleNamespace(
        status_code=status_code,
        raise_for_status=Mock(),
        aiter_bytes=aiter_bytes,
    )

    class StreamContext:
        async def __aenter__(self):
            return stream_response

        async def __aexit__(self, *_args):
            return None

    fake_resp = SimpleNamespace(status_code=200, raise_for_status=Mock())
    fake_client = AsyncMock()
    fake_client.put = AsyncMock(return_value=fake_resp)
    fake_client.delete = AsyncMock(return_value=fake_resp)
    fake_client.request = AsyncMock(return_value=fake_resp)
    fake_client.stream = Mock(return_value=StreamContext())
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    import httpx

    fake_httpx = SimpleNamespace(
        AsyncClient=Mock(return_value=fake_client), HTTPError=httpx.HTTPError
    )
    monkeypatch.setattr(module, "httpx", fake_httpx)
    return fake_client


@pytest.mark.asyncio
async def test_remote_read_file_streams_internal_endpoint(
    remote_processor, monkeypatch
):
    fake_client = _patch_http_client(monkeypatch)

    content = await remote_processor.read_file("documents/kb/doc.pdf")

    assert content == b"bytes"
    fake_client.stream.assert_called_once_with(
        "GET", "/internal/uploads/read", params={"key": "documents/kb/doc.pdf"}
    )


@pytest.mark.asyncio
async def test_remote_read_file_preserves_missing_error(remote_processor, monkeypatch):
    _patch_http_client(monkeypatch, status_code=404)

    with pytest.raises(FileNotFoundError, match="documents/kb/doc.pdf"):
        await remote_processor.read_file("documents/kb/doc.pdf")


@pytest.mark.asyncio
async def test_remote_read_file_wraps_network_error(remote_processor, monkeypatch):
    import httpx

    _patch_http_client(monkeypatch, stream_error=httpx.ReadError("connection reset"))

    with pytest.raises(UploadGatewayError, match="api gateway"):
        await remote_processor.read_file("documents/kb/doc.pdf")


@pytest.mark.asyncio
async def test_remote_processor_reads_through_internal_gateway_app(
    gateway_app, monkeypatch, tmp_path
):
    import httpx

    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "gateway-token")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", "")
    monkeypatch.setattr(settings, "UPLOAD_STORAGE_MODE", "remote")
    storage = _mock_storage(monkeypatch)
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))
    transport = httpx.ASGITransport(app=gateway_app)
    monkeypatch.setattr(
        processor,
        "_internal_client",
        lambda: httpx.AsyncClient(
            transport=transport,
            base_url="http://gateway",
            headers={"Authorization": "Bearer gateway-token"},
        ),
    )

    assert await processor.read_file("documents/kb/doc.pdf") == b"bytes"
    storage.response.assert_awaited_once_with("documents/kb/doc.pdf")


@pytest.mark.asyncio
async def test_remote_delete_file_calls_internal_endpoint(
    remote_processor, monkeypatch
):
    fake_client = _patch_http_client(monkeypatch)

    assert await remote_processor.delete_file("documents/kb/doc.pdf") is True
    fake_client.request.assert_awaited_once_with(
        "DELETE",
        "/internal/uploads/delete",
        params={"key": "documents/kb/doc.pdf"},
    )


@pytest.mark.asyncio
async def test_remote_media_save_and_delete_use_gateway(remote_processor, monkeypatch):
    fake_client = _patch_http_client(monkeypatch)
    kb_id, doc_id = __import__("uuid").uuid4(), __import__("uuid").uuid4()

    asset = await remote_processor._save_media_asset(
        kb_id=kb_id,
        document_id=doc_id,
        content_type="image/png",
        content=b"png",
    )

    assert asset["filename"].endswith(".png")
    assert asset["url"] == (
        f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/media/{asset['filename']}"
    )
    fake_client.put.assert_awaited_once()

    await remote_processor.delete_media_assets(kb_id, doc_id)
    fake_client.delete.assert_awaited_once_with(
        f"/internal/uploads/media/{kb_id}/{doc_id}"
    )


# ── UploadStorageBackend.list ─────────────────────────────────────


@pytest.mark.asyncio
async def test_local_storage_list_returns_relative_keys(tmp_path):
    root = tmp_path / "uploads"
    (root / "documents" / "kb1" / "media" / "doc1").mkdir(parents=True)
    (root / "documents" / "kb1" / "media" / "doc1" / "a.png").write_bytes(b"a")
    (root / "documents" / "kb1" / "media" / "doc1" / "b.png").write_bytes(b"b")
    storage = upload_storage.LocalUploadStorage(root)

    keys = await storage.list("documents/kb1/media/doc1/")

    assert keys == [
        "documents/kb1/media/doc1/a.png",
        "documents/kb1/media/doc1/b.png",
    ]
    assert await storage.list("documents/kb1/media/missing/") == []
    assert await storage.list("../../escape") == []


@pytest.mark.asyncio
async def test_local_storage_list_empty_prefix_lists_all(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "a.txt").write_bytes(b"a")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_bytes(b"b")
    storage = upload_storage.LocalUploadStorage(root)

    assert await storage.list("") == ["a.txt", "sub/b.txt"]


@pytest.mark.asyncio
async def test_object_storage_list_paginates(monkeypatch):
    first_page = {
        "Contents": [{"Key": "documents/kb/a.png"}, {"Key": "documents/kb/b.png"}]
    }
    second_page = {"Contents": [{"Key": "documents/kb/c.png"}]}

    async def _pages():
        yield first_page
        yield second_page

    paginator = Mock()
    paginator.paginate = Mock(return_value=_pages())
    client = Mock()
    client.get_paginator = Mock(return_value=paginator)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = Mock()
    session.create_client = Mock(return_value=ctx)
    monkeypatch.setattr(upload_storage, "get_session", lambda: session)

    storage = upload_storage.ObjectUploadStorage(
        upload_storage.ObjectStorageConfig(
            endpoint="minio:9000",
            bucket="uploads",
            region=None,
            access_key="a",
            secret_key="s",
            secure=False,
            force_path_style=True,
        )
    )

    keys = await storage.list("documents/kb/")

    assert keys == ["documents/kb/a.png", "documents/kb/b.png", "documents/kb/c.png"]
    client.get_paginator.assert_called_once_with("list_objects_v2")
