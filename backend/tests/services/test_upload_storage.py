from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from app.services import upload_storage
from app.services.upload_storage import (
    LocalUploadStorage,
    ObjectUploadStorage,
    get_upload_storage_backend,
)


@pytest.mark.anyio
async def test_local_upload_storage_save_read_delete(tmp_path: Path):
    storage = LocalUploadStorage(tmp_path)

    path = await storage.save("general/2026/06/file.txt", b"ok", "text/plain")

    assert path == str(tmp_path / "general" / "2026" / "06" / "file.txt")
    assert await storage.exists("general/2026/06/file.txt") is True
    response = await storage.response("general/2026/06/file.txt")
    assert str(response.path) == path

    await storage.delete("general/2026/06/file.txt")

    assert await storage.exists("general/2026/06/file.txt") is False


def test_get_upload_storage_backend_defaults_to_local(tmp_path: Path):
    with patch.object(upload_storage.settings, "UPLOAD_STORAGE_BACKEND", "local"):
        storage = get_upload_storage_backend(tmp_path)

    assert isinstance(storage, LocalUploadStorage)


def test_get_upload_storage_backend_rejects_unknown_backend(tmp_path: Path):
    with (
        patch.object(upload_storage.settings, "UPLOAD_STORAGE_BACKEND", "ftp"),
        pytest.raises(RuntimeError, match="UPLOAD_STORAGE_BACKEND"),
    ):
        get_upload_storage_backend(tmp_path)


def test_object_storage_validate_requires_config():
    with (
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ENDPOINT", None),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_BUCKET", "bucket"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ACCESS_KEY", "access"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_SECRET_KEY", "secret"),
    ):
        storage = ObjectUploadStorage()

    with pytest.raises(RuntimeError, match="OBJECT_STORAGE_ENDPOINT"):
        storage._validate_config_values()


@pytest.mark.anyio
async def test_object_storage_save_read_delete(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class FakeBody:
        async def read(self):
            return b"ok"

    class FakeClient:
        async def put_object(self, **kwargs):
            calls.append(("put_object", kwargs))

        async def head_object(self, **kwargs):
            calls.append(("head_object", kwargs))

        async def get_object(self, **kwargs):
            calls.append(("get_object", kwargs))
            return {"Body": FakeBody(), "ContentType": "text/plain"}

        async def delete_object(self, **kwargs):
            calls.append(("delete_object", kwargs))

    class FakeClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        def create_client(self, *args, **kwargs):
            calls.append(("create_client", kwargs))
            return FakeClientContext()

    monkeypatch.setattr(upload_storage, "get_session", lambda: FakeSession())

    with (
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ENDPOINT", "minio:9000"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_BUCKET", "uploads"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_REGION", "us-east-1"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ACCESS_KEY", "access"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_SECRET_KEY", "secret"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_SECURE", False),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_FORCE_PATH_STYLE", True),
    ):
        storage = ObjectUploadStorage()

    path = await storage.save("general/2026/06/file.txt", b"ok", "text/plain")
    exists = await storage.exists("general/2026/06/file.txt")
    response = await storage.response("general/2026/06/file.txt")
    await storage.delete("general/2026/06/file.txt")

    assert path == "s3://uploads/general/2026/06/file.txt"
    assert exists is True
    assert response.media_type == "text/plain"
    assert ("put_object", {
        "Bucket": "uploads",
        "Key": "general/2026/06/file.txt",
        "Body": b"ok",
        "ContentType": "text/plain",
    }) in calls
    assert ("delete_object", {
        "Bucket": "uploads",
        "Key": "general/2026/06/file.txt",
    }) in calls


@pytest.mark.anyio
async def test_object_storage_exists_returns_false_for_missing(monkeypatch):
    class FakeClient:
        async def head_object(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )

    class FakeClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        def create_client(self, *args, **kwargs):
            return FakeClientContext()

    monkeypatch.setattr(upload_storage, "get_session", lambda: FakeSession())

    with (
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ENDPOINT", "minio:9000"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_BUCKET", "uploads"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_ACCESS_KEY", "access"),
        patch.object(upload_storage.settings, "OBJECT_STORAGE_SECRET_KEY", "secret"),
    ):
        storage = ObjectUploadStorage()

    assert await storage.exists("missing.txt") is False
