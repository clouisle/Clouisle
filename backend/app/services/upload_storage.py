from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiofiles
from aiobotocore.session import get_session
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.responses import FileResponse, Response as FastAPIResponse, StreamingResponse

from app.core.config import settings
from app.schemas.response import BusinessError, ResponseCode


class UploadStorageBackend(ABC):
    @abstractmethod
    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        """Persist content at key and return an internal storage path."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return whether key exists."""

    @abstractmethod
    async def response(self, key: str) -> FastAPIResponse:
        """Return a FastAPI response for key content."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key if it exists."""

    async def validate(self) -> None:
        return None


class LocalUploadStorage(UploadStorageBackend):
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        candidate = self.root.joinpath(*key.split("/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="access_denied",
                status_code=403,
            )
        return candidate

    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        os.makedirs(path.parent, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return str(path)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def response(self, key: str) -> FastAPIResponse:
        return FileResponse(self._path(key))

    async def delete(self, key: str) -> None:
        self._path(key).unlink()


class ObjectUploadStorage(UploadStorageBackend):
    def __init__(self) -> None:
        self.endpoint = settings.OBJECT_STORAGE_ENDPOINT
        self.bucket = settings.OBJECT_STORAGE_BUCKET
        self.region = settings.OBJECT_STORAGE_REGION
        self.access_key = settings.OBJECT_STORAGE_ACCESS_KEY
        self.secret_key = settings.OBJECT_STORAGE_SECRET_KEY
        self.secure = settings.OBJECT_STORAGE_SECURE
        self.force_path_style = settings.OBJECT_STORAGE_FORCE_PATH_STYLE

    def _validate_config_values(self) -> None:
        missing = [
            name
            for name, value in {
                "OBJECT_STORAGE_ENDPOINT": self.endpoint,
                "OBJECT_STORAGE_BUCKET": self.bucket,
                "OBJECT_STORAGE_ACCESS_KEY": self.access_key,
                "OBJECT_STORAGE_SECRET_KEY": self.secret_key,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Object storage config is missing required value(s): "
                + ", ".join(missing)
            )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        self._validate_config_values()
        session = get_session()
        scheme = "https" if self.secure else "http"
        endpoint_url = str(self.endpoint)
        if not endpoint_url.startswith(("http://", "https://")):
            endpoint_url = f"{scheme}://{endpoint_url}"
        config = Config(s3={"addressing_style": "path" if self.force_path_style else "auto"})
        async with session.create_client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=config,
        ) as client:
            yield client

    async def validate(self) -> None:
        self._validate_config_values()
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                raise RuntimeError(
                    f"Object storage bucket validation failed: {exc}"
                ) from exc

    async def save(self, key: str, content: bytes, content_type: str | None = None) -> str:
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        async with self._client() as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                **extra_args,
            )
        return f"s3://{self.bucket}/{key}"

    async def exists(self, key: str) -> bool:
        async with self._client() as client:
            try:
                await client.head_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                error_code = exc.response.get("Error", {}).get("Code")
                if status == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise
        return True

    async def response(self, key: str) -> FastAPIResponse:
        async with self._client() as client:
            result = await client.get_object(Bucket=self.bucket, Key=key)
            body = await result["Body"].read()
            content_type = result.get("ContentType") or "application/octet-stream"
        return StreamingResponse(iter([body]), media_type=content_type)

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self.bucket, Key=key)


def get_upload_storage_backend(root: Path) -> UploadStorageBackend:
    backend = settings.UPLOAD_STORAGE_BACKEND.lower()
    if backend == "local":
        return LocalUploadStorage(root)
    if backend in {"object", "s3"}:
        return ObjectUploadStorage()
    raise RuntimeError(
        "UPLOAD_STORAGE_BACKEND must be one of: local, object, s3"
    )
