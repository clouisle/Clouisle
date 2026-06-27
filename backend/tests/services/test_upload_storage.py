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


@pytest.mark.anyio
async def test_get_upload_storage_backend_defaults_to_local(tmp_path: Path):
    with patch.object(
        upload_storage.SiteSetting,
        "get_all_by_category",
        return_value={},
    ):
        storage = await get_upload_storage_backend(tmp_path)

    assert isinstance(storage, LocalUploadStorage)


@pytest.mark.anyio
async def test_get_upload_storage_backend_rejects_unknown_backend(tmp_path: Path):
    with (
        patch.object(
            upload_storage.SiteSetting,
            "get_all_by_category",
            return_value={"upload_storage_backend": "ftp"},
        ),
        pytest.raises(RuntimeError, match="upload_storage_backend"),
    ):
        await get_upload_storage_backend(tmp_path)


@pytest.mark.anyio
async def test_object_storage_requires_settings(tmp_path: Path):
    with (
        patch.object(
            upload_storage.SiteSetting,
            "get_all_by_category",
            return_value={
                "upload_storage_backend": "object",
                "object_storage_bucket": "bucket",
                "object_storage_access_key": "access",
                "object_storage_secret_key": "secret",
            },
        ),
        pytest.raises(RuntimeError, match="object_storage_endpoint"),
    ):
        await get_upload_storage_backend(tmp_path)


@pytest.mark.anyio
async def test_object_storage_save_read_delete(monkeypatch, tmp_path: Path):
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

    with patch.object(
        upload_storage.SiteSetting,
        "get_all_by_category",
        return_value={
            "upload_storage_backend": "object",
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_region": "us-east-1",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
            "object_storage_secure": False,
            "object_storage_force_path_style": True,
        },
    ):
        storage = await get_upload_storage_backend(tmp_path)

    assert isinstance(storage, ObjectUploadStorage)
    path = await storage.save("general/2026/06/file.txt", b"ok", "text/plain")
    exists = await storage.exists("general/2026/06/file.txt")
    response = await storage.response("general/2026/06/file.txt")
    await storage.delete("general/2026/06/file.txt")

    assert path == "s3://uploads/general/2026/06/file.txt"
    assert exists is True
    assert response.media_type == "text/plain"
    assert (
        "put_object",
        {
            "Bucket": "uploads",
            "Key": "general/2026/06/file.txt",
            "Body": b"ok",
            "ContentType": "text/plain",
        },
    ) in calls
    assert (
        "delete_object",
        {
            "Bucket": "uploads",
            "Key": "general/2026/06/file.txt",
        },
    ) in calls


@pytest.mark.anyio
async def test_object_storage_exists_returns_false_for_missing(monkeypatch):
    class FakeClient:
        async def head_object(self, **kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
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

    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
            "object_storage_secure": True,
            "object_storage_force_path_style": True,
        }
    )

    assert await storage.exists("missing.txt") is False
