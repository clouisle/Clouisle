from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from app.services import upload_storage
from app.schemas.response import BusinessError, ResponseCode
from app.services.upload_storage import (
    LocalUploadStorage,
    ObjectUploadStorage,
    ObjectStorageConfig,
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
    await storage.delete("general/2026/06/file.txt")

    assert await storage.exists("general/2026/06/file.txt") is False


@pytest.mark.anyio
async def test_local_upload_storage_read_response_and_traversal(tmp_path: Path):
    storage = LocalUploadStorage(tmp_path)
    await storage.save("file.txt", b"contents")

    assert await storage.read("file.txt") == b"contents"
    response = await storage.response(
        "file.txt", content_type="text/plain", filename="download.txt"
    )
    assert response.media_type == "text/plain"
    assert response.filename == "download.txt"

    with pytest.raises(BusinessError) as exc_info:
        await storage.save("../outside.txt", b"blocked")
    assert exc_info.value.code == ResponseCode.FORBIDDEN
    assert exc_info.value.status_code == 403


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
        def __init__(self):
            self.chunks = [b"ok", b""]

        async def read(self, size=-1):
            return self.chunks.pop(0)

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


@pytest.mark.parametrize("error_code", ["404", "NoSuchKey", "NotFound"])
@pytest.mark.anyio
async def test_object_storage_exists_recognizes_missing_error_codes(
    monkeypatch, error_code: str
):
    class FakeClient:
        async def head_object(self, **kwargs):
            raise ClientError({"Error": {"Code": error_code}}, "HeadObject")

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        upload_storage,
        "get_session",
        lambda: type(
            "Session", (), {"create_client": lambda *args, **kwargs: FakeContext()}
        )(),
    )
    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "https://minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
        }
    )

    assert await storage.exists("missing.txt") is False


@pytest.mark.anyio
async def test_object_storage_client_options_read_and_save_without_content_type(
    monkeypatch,
):
    calls: list[tuple[str, dict]] = []

    class Body:
        async def read(self, size=-1):
            return b"contents"

    class FakeClient:
        async def put_object(self, **kwargs):
            calls.append(("put_object", kwargs))

        async def get_object(self, **kwargs):
            return {"Body": Body()}

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        def create_client(self, *args, **kwargs):
            calls.append(("create_client", {"args": args, **kwargs}))
            return FakeContext()

    monkeypatch.setattr(upload_storage, "get_session", lambda: FakeSession())
    storage = ObjectUploadStorage(
        ObjectStorageConfig(
            endpoint="https://minio:9000",
            bucket="uploads",
            region=None,
            access_key="access",
            secret_key="secret",
            secure=False,
            force_path_style=False,
        )
    )

    await storage.save("file.txt", b"contents")
    assert await storage.read("file.txt") == b"contents"

    create_call = next(value for name, value in calls if name == "create_client")
    assert create_call["args"] == ("s3",)
    assert create_call["endpoint_url"] == "https://minio:9000"
    assert create_call["region_name"] is None
    assert create_call["config"].s3["addressing_style"] == "auto"
    assert (
        "put_object",
        {"Bucket": "uploads", "Key": "file.txt", "Body": b"contents"},
    ) in calls


@pytest.mark.anyio
async def test_object_storage_validation_wraps_client_error(monkeypatch):
    error = ClientError({"Error": {"Code": "Forbidden"}}, "HeadBucket")

    class FakeClient:
        async def head_bucket(self, **kwargs):
            raise error

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        upload_storage,
        "get_session",
        lambda: type(
            "Session", (), {"create_client": lambda *args, **kwargs: FakeContext()}
        )(),
    )
    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
        }
    )

    with pytest.raises(RuntimeError, match="bucket validation failed") as exc_info:
        await storage.validate()
    assert exc_info.value.__cause__ is error


@pytest.mark.anyio
async def test_object_storage_response_streams_and_closes_context(monkeypatch):
    exits = 0

    class Body:
        def __init__(self):
            self.chunks = [b"one", b"two", b""]

        async def read(self, size=-1):
            return self.chunks.pop(0)

    class FakeClient:
        async def get_object(self, **kwargs):
            return {"Body": Body()}

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            nonlocal exits
            exits += 1

    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
        }
    )
    monkeypatch.setattr(storage, "_client", lambda: FakeContext())

    response = await storage.response("file.bin", filename="download.bin")
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == [b"one", b"two"]
    assert response.media_type == "application/octet-stream"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="download.bin"'
    )
    assert exits == 1


@pytest.mark.anyio
async def test_object_storage_response_closes_context_when_get_fails(monkeypatch):
    exits = 0

    class FakeClient:
        async def get_object(self, **kwargs):
            raise OSError("unavailable")

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            nonlocal exits
            exits += 1

    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
        }
    )
    monkeypatch.setattr(storage, "_client", lambda: FakeContext())

    with pytest.raises(OSError, match="unavailable"):
        await storage.response("file.bin")
    assert exits == 1


@pytest.mark.anyio
async def test_object_storage_exists_reraises_non_missing_error(monkeypatch):
    error = ClientError({"Error": {"Code": "Forbidden"}}, "HeadObject")

    class FakeClient:
        async def head_object(self, **kwargs):
            raise error

    class FakeContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    storage = ObjectUploadStorage.from_settings(
        {
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
        }
    )
    monkeypatch.setattr(storage, "_client", lambda: FakeContext())

    with pytest.raises(ClientError) as exc_info:
        await storage.exists("file.txt")
    assert exc_info.value is error
