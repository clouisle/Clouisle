"""Secure URL-to-Asset import for builtin web and document tools.

One implementation owns:

* execution-scope authorization **before** any network or storage IO,
* internal protected file URLs resolved through persisted Assets instead of
  public HTTP requests,
* external HTTP(S) downloads with the canonical SSRF checks on every redirect
  hop and a hard byte ceiling,
* persistence under the protected ``agent-attachments`` category only.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, unquote_to_bytes, urljoin, urlparse
from uuid import UUID

import httpx

from app.api.v1.endpoints.upload import save_generated_upload
from app.core.config import settings
from app.core.network_security import ensure_external_http_url_allowed
from app.models.asset import Asset, AssetScopeType, AssetSource, AssetStatus
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.services.asset import asset_service
from app.services.asset_access import (
    authorize_asset_for_scope,
    authorize_asset_scope,
    resolve_authorized_asset_ref,
)

INTERNAL_FILE_PREFIX = "/api/v1/upload/files/"
# Only protected categories are valid destinations: their storage keys are
# served through Asset scope authorization, never as public files.
PROTECTED_IMPORT_CATEGORY = "agent-attachments"
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 60.0

_UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f/\\]")
_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True, slots=True)
class InternalDocument:
    """An already-persisted protected document resolved from its file URL."""

    asset: Asset
    ref: str
    url: str
    internal: bool = True


@dataclass(frozen=True, slots=True)
class ExternalDocument:
    """Bytes downloaded from an external HTTP(S) or data URL."""

    content: bytes
    content_type: str
    filename: str
    url: str
    final_url: str
    charset: str | None = None
    internal: bool = False


@dataclass(frozen=True, slots=True)
class ScopedDocument:
    """A newly persisted protected Asset bound to an execution scope."""

    asset: Asset
    ref: str


def resolve_document_scope(
    *,
    conversation_id: UUID | str | None,
    workflow_run_id: UUID | str | None,
) -> tuple[AssetScopeType, UUID]:
    """Return the execution scope, failing before any IO when absent."""
    if workflow_run_id is not None:
        scope_type = AssetScopeType.WORKFLOW_RUN
        raw = workflow_run_id
    elif conversation_id is not None:
        scope_type = AssetScopeType.CONVERSATION
        raw = conversation_id
    else:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="validation_error",
        )
    try:
        return scope_type, UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="validation_error",
        ) from exc


def internal_storage_key(value: str) -> str | None:
    """Return the storage key for a relative or same-origin protected file URL.

    Other hosts that happen to share the path are ordinary external URLs; they
    must never be resolved against local persistence.
    """
    parsed = urlparse(value)
    if parsed.scheme not in {"", "http", "https"}:
        return None
    path = unquote(parsed.path)
    if not path.startswith(INTERNAL_FILE_PREFIX):
        return None
    if parsed.netloc:
        base = urlparse(str(settings.API_BASE_URL))
        if parsed.netloc.lower() != base.netloc.lower():
            return None
    key = path[len(INTERNAL_FILE_PREFIX) :].lstrip("/")
    return key or None


def safe_display_filename(value: str | None, *, default: str) -> str:
    """Derive a bounded display filename without path or control characters."""
    raw = value or ""
    looks_like_url = "://" in raw or raw.startswith(("/", "./", "../"))
    path = unquote(urlparse(raw).path) if looks_like_url else raw
    candidate = _UNSAFE_NAME.sub("_", path.rsplit("/", 1)[-1]).strip(" .")
    if not candidate:
        return default
    return candidate[-200:]


def infer_filename_extension(content_type: str | None, filename: str | None) -> str:
    """Infer a safe extension from the declared type before the URL name."""
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in _HTML_CONTENT_TYPES:
        return ".html"
    if normalized in {"text/markdown", "text/x-markdown"}:
        return ".md"
    if normalized:
        guessed = mimetypes.guess_extension(normalized, strict=False)
        if guessed:
            return guessed
    suffix = Path(filename or "").suffix.lower()
    return suffix or ".bin"


def is_html_document(content_type: str | None, filename: str | None = None) -> bool:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in _HTML_CONTENT_TYPES:
        return True
    return Path(filename or "").suffix.lower() in {".html", ".htm"}


def _decode_charset(content_type: str | None) -> str | None:
    for part in (content_type or "").split(";")[1:]:
        name, separator, value = part.partition("=")
        if separator and name.strip().lower() == "charset":
            return value.strip().strip('"').strip("'") or None
    return None


def decode_text(content: bytes, charset: str | None) -> str:
    """Decode fetched text strictly; never silently replace unreadable bytes."""
    candidates = [charset, "utf-8-sig", "utf-8", "gb18030"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    raise ValueError("document_extraction_decode_failed")


def _http_status_error(status_code: int) -> BusinessError:
    """Build an HTTP-error BusinessError whose message template receives the code.

    ``BusinessError.status_code`` is reserved for the HTTP response, so the
    ``{status_code}`` translation argument is supplied separately.
    """
    error = BusinessError(msg_key="fetch_webpage_http_error", status_code=status_code)
    error.kwargs["status_code"] = status_code
    return error


async def fetch_external_url(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
) -> ExternalDocument:
    """Download an external HTTP(S) URL with SSRF validation on every hop."""
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise BusinessError(msg_key="validation_error")
    current = url
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers=_DOWNLOAD_HEADERS,
        ) as client:
            for redirect_count in range(MAX_REDIRECTS + 1):
                await ensure_external_http_url_allowed(current)
                async with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise BusinessError(msg_key="file_download_failed")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise _http_status_error(response.status_code)
                    if not 200 <= response.status_code < 300:
                        raise BusinessError(msg_key="file_download_failed")
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        or "application/octet-stream"
                    )
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        try:
                            if int(declared) > max_bytes:
                                raise BusinessError(msg_key="file_too_large")
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise BusinessError(msg_key="file_too_large")
                        chunks.append(chunk)
                    break
    except BusinessError:
        raise
    except httpx.TimeoutException as exc:
        raise BusinessError(msg_key="tool_execution_timeout") from exc
    except httpx.HTTPError as exc:
        raise BusinessError(msg_key="file_download_failed") from exc

    content = b"".join(chunks)
    if not content:
        raise BusinessError(msg_key="file_download_failed")
    filename = safe_display_filename(current, default="download")
    return ExternalDocument(
        content=content,
        content_type=content_type,
        filename=filename,
        url=url,
        final_url=current,
        charset=_decode_charset(response.headers.get("content-type")),
    )


def decode_data_url(
    value: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ExternalDocument:
    """Decode a data: URL locally; no network or host resolution is involved."""
    header, separator, payload = value[5:].partition(",")
    if not separator:
        raise BusinessError(msg_key="fetch_webpage_unsupported_scheme")
    metadata = header.split(";") if header else []
    content_type = (
        metadata[0].strip() if metadata and "/" in metadata[0] else "text/plain"
    )
    is_base64 = any(part.lower() == "base64" for part in metadata[1:])
    if is_base64:
        # Reject before allocating decoded bytes.
        if len(payload) > (max_bytes * 4 // 3) + 4:
            raise BusinessError(msg_key="file_too_large")
        try:
            content = base64.b64decode(payload, validate=True)
        except Exception as exc:
            raise BusinessError(msg_key="file_download_failed") from exc
    else:
        # Percent decoding never expands beyond the encoded length, while raw
        # Unicode can expand up to 3x; precheck conservatively, then verify.
        if len(payload) > max_bytes * 3:
            raise BusinessError(msg_key="file_too_large")
        try:
            content = unquote_to_bytes(payload)
        except Exception as exc:
            raise BusinessError(msg_key="file_download_failed") from exc
    if not content:
        raise BusinessError(msg_key="file_download_failed")
    if len(content) > max_bytes:
        raise BusinessError(msg_key="file_too_large")
    extension = infer_filename_extension(content_type, None)
    return ExternalDocument(
        content=content,
        content_type=content_type,
        filename=f"data{extension}",
        url=value,
        final_url=value,
    )


async def load_url_document(
    url: str,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    expected_team_id: UUID | None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> InternalDocument | ExternalDocument:
    """Authorize the scope, then resolve internal Assets or fetch external bytes."""
    team_id = await authorize_asset_scope(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        expected_team_id=expected_team_id,
    )
    if not isinstance(url, str) or not url:
        raise BusinessError(msg_key="validation_error")

    storage_key = internal_storage_key(url)
    if storage_key is not None:
        asset = await Asset.filter(
            storage_key=storage_key,
            status=AssetStatus.AVAILABLE,
        ).first()
        if asset is None or asset.source == AssetSource.DERIVED_TEXT:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="file_not_found",
                status_code=404,
            )
        asset = await authorize_asset_for_scope(
            asset.id,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=team_id,
        )
        binding = await asset_service.get_or_create_ref(
            scope_type=scope_type,
            scope_id=scope_id,
            asset=asset,
        )
        # Reuse the canonical ref resolver so a document reachable only through
        # an inactive branch cannot be resurrected through its file URL.
        asset = await resolve_authorized_asset_ref(
            binding.ref,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=team_id,
        )
        return InternalDocument(asset=asset, ref=binding.ref, url=url)

    if url.startswith("data:"):
        return decode_data_url(url, max_bytes=max_bytes)
    if not url.startswith(("http://", "https://")):
        raise BusinessError(msg_key="fetch_webpage_unsupported_scheme")
    return await fetch_external_url(url, max_bytes=max_bytes)


async def persist_scoped_document(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    expected_team_id: UUID | None,
    provenance: dict | None = None,
) -> ScopedDocument:
    """Persist bytes as a protected Asset bound to the authorized scope."""
    if not content:
        raise BusinessError(msg_key="file_download_failed")
    team_id = await authorize_asset_scope(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        expected_team_id=expected_team_id,
    )
    display_filename = safe_display_filename(filename, default="document")
    upload_info = await save_generated_upload(
        content=content,
        category=PROTECTED_IMPORT_CATEGORY,
        content_type=content_type,
        filename=display_filename,
    )
    asset = await asset_service.register_bytes(
        storage_key=upload_info["storage_key"],
        original_filename=display_filename,
        content_type=content_type,
        content=content,
        source=AssetSource.UPLOAD,
        team_id=team_id,
        created_by_id=user.id if user is not None else None,
        provenance=provenance or {},
    )
    binding = await asset_service.get_or_create_ref(
        scope_type=scope_type,
        scope_id=scope_id,
        asset=asset,
    )
    return ScopedDocument(asset=asset, ref=binding.ref)
