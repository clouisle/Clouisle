"""Bounded, tenant-authenticated Feishu content downloads and document exports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from email.message import Message
import json as json_module
import mimetypes
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.integrations.feishu import (
    API_BASE,
    TIMEOUT,
    FeishuAPIError,
    FeishuClient,
    _error_message,
    _required_scopes,
    _short,
)
from app.models.site_setting import (
    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
    SiteSetting,
)

EXPORT_TIMEOUT_SECONDS = 120.0
EXPORT_POLL_SECONDS = 0.7
_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_EXPORT_FORMATS = {
    "doc": {"docx", "pdf"},
    "docx": {"docx", "pdf"},
    "sheet": {"xlsx", "csv"},
    "bitable": {"xlsx", "csv"},
}
_MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class UnsupportedContentError(ValueError):
    """The source format has no supported knowledge-base content parser."""


@dataclass
class FeishuContent:
    filename: str
    content: bytes
    warnings: list[str] = field(default_factory=list)


async def content_limit_bytes() -> int:
    """Apply the same configurable size bounds as knowledge-base uploads."""
    value = await SiteSetting.get_value(
        "kb_document_max_upload_size_mb", KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB
    )
    if not isinstance(value, int) or isinstance(value, bool):
        value = KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB
    return (
        min(
            max(value, KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
            KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
        )
        * 1024
        * 1024
    )


def _api_path(path: str) -> str:
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or parsed.scheme
        or parsed.netloc
    ):
        raise FeishuAPIError("Feishu content requests require a relative API path")
    return path


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_BASE, timeout=TIMEOUT, follow_redirects=False, trust_env=False
    )


async def _pace(client: FeishuClient, path: str) -> None:
    interval = 0.61 if path.startswith(("/wiki/", "/drive/v1/export_tasks")) else 0.21
    delay = client._knowledge_request_at + interval - time.monotonic()
    if delay > 0:
        await asyncio.sleep(delay)
    client._knowledge_request_at = time.monotonic()


async def request_json(
    client: FeishuClient,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the full checked Feishu envelope, retaining its API error codes."""
    path = _api_path(path)
    async with _http_client() as http:
        token = await client._token(http)
        await _pace(client, path)
        return await client._request(
            http,
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            json=json,
        )


def _safe_filename(value: str | None, mime: str, fallback: str = "feishu-file") -> str:
    name = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127)
    name = name.strip(" .")[:200] or fallback
    suffix = name.rsplit(".", 1)[-1] if "." in name else ""
    if not re.fullmatch(r"[A-Za-z0-9]{1,10}", suffix):
        extension = _MIME_EXTENSIONS.get(mime) or mimetypes.guess_extension(
            mime, strict=False
        )
        if extension and re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", extension):
            name += extension
    return name


def _response_filename(response: httpx.Response) -> str | None:
    disposition = response.headers.get("content-disposition")
    if not disposition:
        return None
    message = Message()
    message["content-disposition"] = disposition
    filename = message.get_filename()
    return filename if isinstance(filename, str) and filename.strip() else None


def _binary_error(response: httpx.Response, content: bytes) -> None:
    """Keep download failures compatible with the normal Feishu error contract."""
    body = None
    # Named successful JSON attachments may themselves contain code/msg fields.
    # Bound error parsing separately from the much larger download limit.
    if len(content) <= 64 * 1024 and (
        response.status_code != 200 or not response.headers.get("content-disposition")
    ):
        try:
            body = json_module.loads(content)
        except (ValueError, UnicodeDecodeError):
            pass
    code = body.get("code") if isinstance(body, dict) else None
    if response.status_code != 200:
        buffered = httpx.Response(
            response.status_code,
            headers=response.headers,
            content=content,
            request=response.request,
        )
        message, detail = _error_message(buffered)
        raise FeishuAPIError(
            message,
            detail=detail,
            code=code if isinstance(code, int) else None,
            status_code=response.status_code,
            required_scopes=_required_scopes(body, response.request.url.path),
        )
    if isinstance(body, dict) and isinstance(code, int) and code != 0 and "msg" in body:
        raise FeishuAPIError(
            f"Feishu API error {code}: {_short(body['msg'])}",
            detail=str(body)[:1024],
            code=code,
            status_code=response.status_code,
            required_scopes=_required_scopes(body, response.request.url.path),
        )


async def _download(
    client: FeishuClient,
    path: str,
    *,
    params: dict[str, str] | None = None,
    expected_size: int | None = None,
) -> tuple[bytes, str, str | None]:
    path = _api_path(path)
    limit = await content_limit_bytes()
    if expected_size is not None and expected_size > limit:
        raise FeishuAPIError("Feishu file exceeds the knowledge-base upload size limit")
    async with _http_client() as http:
        token = await client._token(http)
        await _pace(client, path)
        async with http.stream(
            "GET", path, headers={"Authorization": f"Bearer {token}"}, params=params
        ) as response:
            length = response.headers.get("content-length")
            if length is not None:
                try:
                    declared_size = int(length)
                except ValueError as exc:
                    raise FeishuAPIError(
                        "Feishu returned an invalid content length"
                    ) from exc
                if declared_size < 0:
                    raise FeishuAPIError("Feishu returned an invalid content length")
                if declared_size > limit:
                    raise FeishuAPIError(
                        "Feishu file exceeds the knowledge-base upload size limit"
                    )
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                if len(content) + len(chunk) > limit:
                    raise FeishuAPIError(
                        "Feishu file exceeds the knowledge-base upload size limit"
                    )
                content.extend(chunk)
            payload = bytes(content)
            _binary_error(response, payload)
            if expected_size is not None and len(payload) != expected_size:
                raise FeishuAPIError(
                    "Feishu export download size does not match its result"
                )
            if (
                length is not None
                and not response.headers.get("content-encoding")
                and len(payload) != declared_size
            ):
                raise FeishuAPIError("Feishu download is incomplete")
            if not payload:
                raise FeishuAPIError("Feishu returned an empty file")
            mime = (
                response.headers.get("content-type", "application/octet-stream")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            return payload, mime, _response_filename(response)


async def download_media(
    client: FeishuClient,
    token: str,
    *,
    extra: str | None = None,
) -> tuple[bytes, str]:
    """Download docx/sheet/Base media, never the arbitrary URL in a cell."""
    payload, mime, _ = await _download(
        client,
        f"/drive/v1/medias/{quote(token, safe='')}/download",
        params={"extra": extra} if extra else None,
    )
    return payload, mime


async def download_file(
    client: FeishuClient,
    token: str,
    filename: str | None = None,
) -> FeishuContent:
    """Download a Drive file using its metadata title or response filename."""
    # Wiki titles may omit the real file suffix. Only query metadata when needed;
    # callers that already know the original filename do not need extra scopes.
    if not filename or not re.search(r"\.[A-Za-z0-9]{1,10}$", filename):
        body = await request_json(
            client,
            "POST",
            "/drive/v1/metas/batch_query",
            json={"request_docs": [{"doc_token": token, "doc_type": "file"}]},
        )
        data = body.get("data")
        metas = data.get("metas") if isinstance(data, dict) else None
        if (
            not isinstance(metas, list)
            or not isinstance(data.get("failed_list", []), list)
            or data.get("failed_list")
        ):
            raise FeishuAPIError("Feishu did not return file metadata")
        matches = [
            item
            for item in metas
            if isinstance(item, dict)
            and item.get("doc_token") == token
            and str(item.get("doc_type", "")).lower() == "file"
        ]
        if (
            len(matches) != 1
            or not isinstance(matches[0].get("title"), str)
            or not matches[0]["title"].strip()
        ):
            raise FeishuAPIError("Feishu returned invalid file metadata")
        filename = matches[0]["title"]
    payload, mime, response_name = await _download(
        client, f"/drive/v1/files/{quote(token, safe='')}/download"
    )
    from app.services.document_processor import EXT_TYPE_MAP

    name = _safe_filename(response_name or filename, mime)
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in EXT_TYPE_MAP:
        raise UnsupportedContentError(
            f"Unsupported Feishu file extension: {suffix or '(none)'}"
        )
    return FeishuContent(name, payload)


async def export_document(
    client: FeishuClient,
    token: str,
    obj_type: str,
    extension: str,
) -> FeishuContent:
    """Export only supported formats; incomplete/failed exports must not replace content."""
    if extension not in _EXPORT_FORMATS.get(obj_type, set()):
        raise UnsupportedContentError(
            f"Feishu does not support exporting {obj_type} to {extension}"
        )
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            body = await request_json(
                client,
                "POST",
                "/drive/v1/export_tasks",
                json={"token": token, "type": obj_type, "file_extension": extension},
            )
            data = body.get("data")
            ticket = data.get("ticket") if isinstance(data, dict) else None
            if not isinstance(ticket, str) or not ticket:
                raise FeishuAPIError("Feishu did not return an export task ticket")
            while True:
                body = await request_json(
                    client,
                    "GET",
                    f"/drive/v1/export_tasks/{quote(ticket, safe='')}",
                    params={"token": token},
                )
                data = body.get("data")
                result = data.get("result") if isinstance(data, dict) else None
                if not isinstance(result, dict):
                    raise FeishuAPIError(
                        "Feishu returned an invalid export task result"
                    )
                status = result.get("job_status")
                if type(status) is not int:
                    raise FeishuAPIError("Feishu did not confirm export task status")
                if status in (1, 2):
                    await asyncio.sleep(EXPORT_POLL_SECONDS)
                    continue
                if status != 0:
                    raise FeishuAPIError(
                        f"Feishu export failed (status {status}): {_short(result.get('job_error_msg', ''))}",
                        detail=str(result)[:1024],
                    )
                file_token = result.get("file_token")
                size = result.get("file_size")
                name = result.get("file_name")
                if (
                    not isinstance(file_token, str)
                    or not file_token
                    or type(size) is not int
                    or size <= 0
                    or not isinstance(name, str)
                    or not name.strip()
                    or result.get("file_extension") != extension
                    or result.get("type") != obj_type
                ):
                    raise FeishuAPIError(
                        "Feishu returned incomplete export file metadata"
                    )
                payload, mime, _ = await _download(
                    client,
                    f"/drive/v1/export_tasks/file/{quote(file_token, safe='')}/download",
                    expected_size=size,
                )
                name = _safe_filename(name, "")
                if not name.lower().endswith(f".{extension}"):
                    name += f".{extension}"
                return FeishuContent(name, payload)
    except TimeoutError as exc:
        raise FeishuAPIError("Feishu document export exceeded its deadline") from exc
