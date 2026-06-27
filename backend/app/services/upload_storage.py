from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles
from aiobotocore.session import get_session
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.responses import (
    FileResponse,
    Response as FastAPIResponse,
    StreamingResponse,
)

from app.models import DEFAULT_SETTINGS, SiteSetting
from app.schemas.response import BusinessError, ResponseCode


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint: str
    bucket: str
    region: str | None
    access_key: str
    secret_key: str
    secure: bool
    force_path_style: bool


class UploadStorageBackend(ABC):
    @abstractmethod
    async def save(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> str:
        """Persist content at key and return an internal storage path."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return whether key exists."""

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """Read key content."""

    @abstractmethod
    async def response(
        self,
        key: str,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> FastAPIResponse:
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

    async def save(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> str:
        path = self._path(key)
        os.makedirs(path.parent, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)
        return str(path)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def read(self, key: str) -> bytes:
        async with aiofiles.open(self._path(key), "rb") as f:
            return await f.read()

    async def response(
        self,
        key: str,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> FastAPIResponse:
        return FileResponse(self._path(key), media_type=content_type, filename=filename)

    async def delete(self, key: str) -> None:
        self._path(key).unlink()


class ObjectUploadStorage(UploadStorageBackend):
    def __init__(self, config: ObjectStorageConfig) -> None:
        self.config = config

    @staticmethod
    def from_settings(settings: dict[str, Any]) -> ObjectUploadStorage:
        missing = [
            key
            for key in (
                "object_storage_endpoint",
                "object_storage_bucket",
                "object_storage_access_key",
                "object_storage_secret_key",
            )
            if not settings.get(key)
        ]
        if missing:
            raise RuntimeError(
                "Object storage settings are missing required value(s): "
                + ", ".join(missing)
            )
        return ObjectUploadStorage(
            ObjectStorageConfig(
                endpoint=str(settings["object_storage_endpoint"]),
                bucket=str(settings["object_storage_bucket"]),
                region=str(settings.get("object_storage_region") or "") or None,
                access_key=str(settings["object_storage_access_key"]),
                secret_key=str(settings["object_storage_secret_key"]),
                secure=bool(settings.get("object_storage_secure", True)),
                force_path_style=bool(
                    settings.get("object_storage_force_path_style", True)
                ),
            )
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        session = get_session()
        scheme = "https" if self.config.secure else "http"
        endpoint_url = self.config.endpoint
        if not endpoint_url.startswith(("http://", "https://")):
            endpoint_url = f"{scheme}://{endpoint_url}"
        config = Config(
            s3={"addressing_style": "path" if self.config.force_path_style else "auto"}
        )
        async with session.create_client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self.config.region,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            config=config,
        ) as client:
            yield client

    async def validate(self) -> None:
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self.config.bucket)
            except ClientError as exc:
                raise RuntimeError(
                    f"Object storage bucket validation failed: {exc}"
                ) from exc

    async def save(
        self, key: str, content: bytes, content_type: str | None = None
    ) -> str:
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        async with self._client() as client:
            await client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=content,
                **extra_args,
            )
        return f"s3://{self.config.bucket}/{key}"

    async def exists(self, key: str) -> bool:
        async with self._client() as client:
            try:
                await client.head_object(Bucket=self.config.bucket, Key=key)
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                error_code = exc.response.get("Error", {}).get("Code")
                if status == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
                    return False
                raise
        return True

    async def read(self, key: str) -> bytes:
        async with self._client() as client:
            result = await client.get_object(Bucket=self.config.bucket, Key=key)
            return await result["Body"].read()

    async def response(
        self,
        key: str,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> FastAPIResponse:
        async with self._client() as client:
            result = await client.get_object(Bucket=self.config.bucket, Key=key)
            body = await result["Body"].read()
            media_type = content_type or result.get("ContentType") or "application/octet-stream"
        headers = {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return StreamingResponse(iter([body]), media_type=media_type, headers=headers)

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self.config.bucket, Key=key)


def _storage_defaults() -> dict[str, Any]:
    return {
        key: config["value"]
        for key, config in DEFAULT_SETTINGS.items()
        if config["category"] == "storage"
    }


async def get_upload_storage_backend(root: Path) -> UploadStorageBackend:
    storage_settings = _storage_defaults()
    storage_settings.update(await SiteSetting.get_all_by_category(category="storage"))
    backend = str(storage_settings.get("upload_storage_backend", "local")).lower()
    if backend == "local":
        return LocalUploadStorage(root)
    if backend in {"object", "s3"}:
        return ObjectUploadStorage.from_settings(storage_settings)
    raise RuntimeError("upload_storage_backend must be one of: local, object, s3")
