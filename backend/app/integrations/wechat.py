"""ClawBot iLink transport. No OpenClaw runtime or user-message execution."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import logging
import secrets
from pathlib import PurePosixPath
from urllib.parse import urlencode, urljoin, urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.network_security import validate_external_http_url

API_BASE = "https://ilinkai.weixin.qq.com"
CDN_BASE = "https://novac2c.cdn.weixin.qq.com/c2c"
LOG_HOST = "ilinkai.weixin.qq.com"
CDN_LOG_HOST = "novac2c.cdn.weixin.qq.com"
WECHAT_LOG_HOSTS = frozenset({LOG_HOST, CDN_LOG_HOST})
VERSION = "2.4.10"
BASE_INFO = {"channel_version": VERSION, "bot_agent": "Clouisle/0.1.0"}


def _is_wechat_transport_log(rendered: str) -> bool:
    """Match only http(s) URLs whose parsed host is the WeChat CDN/API domain.

    A plain substring test would also match `weixin.qq.com.evil.example`, so the
    URL is parsed and the host compared exactly.
    """
    for token in rendered.split():
        parsed = urlsplit(token.strip("\"'"))
        if (
            parsed.scheme in ("http", "https")
            and (parsed.hostname or "").lower() in WECHAT_LOG_HOSTS
        ):
            return True
    return False


class _RedactWeChatTransport(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # httpx logs the full QR/cursor/media query URL at INFO by default.
        rendered = record.getMessage()
        if "HTTP Request:" in rendered and _is_wechat_transport_log(rendered):
            record.msg = "WeChat transport request (URL redacted)"
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactWeChatTransport())


class WeChatAPIError(RuntimeError):
    def __init__(self, code: int | str = "connection"):
        self.code = code
        super().__init__("WeChat request failed")


def official_url(value: str, *, media: bool = False) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    suffix = ".cdn.weixin.qq.com" if media else ".weixin.qq.com"
    if (
        parsed.scheme != "https"
        or not host.endswith(suffix)
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
        or (not media and (parsed.query or parsed.path not in ("", "/")))
    ):
        raise WeChatAPIError("invalid_host")
    return value.rstrip("/") if not media else value


class WeChatClient:
    def __init__(self, base_url: str = API_BASE, token: str = ""):
        self.base_url = official_url(base_url)
        self.token = token
        self.http = httpx.AsyncClient(follow_redirects=False, timeout=40.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http.aclose()

    async def _request(
        self, endpoint: str, body: dict | None = None, *, authenticated: bool = True
    ) -> dict:
        headers = {
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": str((2 << 16) | (4 << 8) | 10),
        }
        if body is not None:
            headers.update(
                {
                    "AuthorizationType": "ilink_bot_token",
                    "X-WECHAT-UIN": base64.b64encode(
                        str(secrets.randbits(32)).encode()
                    ).decode(),
                }
            )
            if authenticated:
                headers["Authorization"] = f"Bearer {self.token}"
                body = {**body, "base_info": BASE_INFO}
        try:
            url = f"{self.base_url}/{endpoint}"
            await asyncio.to_thread(validate_external_http_url, url)
            async with self.http.stream(
                "POST" if body is not None else "GET", url, json=body, headers=headers
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > 4 * 1024 * 1024:
                        raise WeChatAPIError("response_size")
                    raw.extend(chunk)
            import json

            data = json.loads(raw)
            if not isinstance(data, dict):
                raise WeChatAPIError("response")
            code = data.get("ret") or data.get("errcode")
            if code:
                raise WeChatAPIError(code)
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise WeChatAPIError() from exc

    async def get_qrcode(self) -> dict:
        return await self._request(
            "ilink/bot/get_bot_qrcode?bot_type=3",
            {"local_token_list": []},
            authenticated=False,
        )

    async def get_qrcode_status(
        self, qrcode: str, verify_code: str | None = None
    ) -> dict:
        params = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code
        try:
            async with asyncio.timeout(20):
                return await self._request(
                    "ilink/bot/get_qrcode_status?" + urlencode(params)
                )
        except TimeoutError:
            return {"status": "wait"}

    async def get_updates(
        self, cursor: str, *, wait_seconds: float | None = None
    ) -> dict:
        """Fetch one update batch.

        ``wait_seconds`` bounds a single call so a scheduled task can return
        promptly instead of holding a worker slot for the full long-poll
        timeout. The upstream treats an empty batch as "nothing yet".
        """
        if wait_seconds is None:
            return await self._get_updates(cursor)
        try:
            async with asyncio.timeout(wait_seconds):
                return await self._get_updates(cursor)
        except TimeoutError:
            return {"msgs": [], "get_updates_buf": cursor}

    async def _get_updates(self, cursor: str) -> dict:
        try:
            return await self._request(
                "ilink/bot/getupdates", {"get_updates_buf": cursor}
            )
        except WeChatAPIError as exc:
            if isinstance(exc.__cause__, httpx.ReadTimeout):
                return {"msgs": [], "get_updates_buf": cursor}
            raise

    async def send_text(
        self, to: str, text: str, context_token: str, *, client_id: str | None = None
    ) -> None:
        if not context_token:
            raise WeChatAPIError("missing_context")
        await self._request(
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to,
                    "client_id": client_id or str(uuid4()),
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                }
            },
        )

    async def get_upload_url(
        self,
        *,
        filekey: str,
        media_type: int,
        to_user_id: str,
        raw_size: int,
        raw_file_md5: str,
        file_size: int,
        aeskey: str,
    ) -> tuple[str, str]:
        """Reserve a CDN upload slot; return (upload_url, reserved_param)."""
        response = await self._request(
            "ilink/bot/getuploadurl",
            {
                "filekey": filekey,
                "media_type": media_type,
                "to_user_id": to_user_id,
                "rawsize": raw_size,
                "rawfilemd5": raw_file_md5,
                "filesize": file_size,
                "no_need_thumb": True,
                "aeskey": aeskey,
            },
        )
        upload_url = str(response.get("upload_full_url") or "").strip()
        param = str(response.get("upload_param") or "").strip()
        if not upload_url:
            if not param:
                raise WeChatAPIError("upload_url")
            upload_url = f"{CDN_BASE}/upload?{urlencode({'encrypted_query_param': param, 'filekey': filekey})}"
        return upload_url, param

    async def upload_media(self, url: str, content: bytes) -> str:
        """POST ciphertext to the reserved CDN slot; return the download param."""
        try:
            official_url(url, media=True)
            await asyncio.to_thread(validate_external_http_url, url)
            async with self.http.stream(
                "POST",
                url,
                content=content,
                headers={"Content-Type": "application/octet-stream"},
            ) as response:
                response.raise_for_status()
                param = response.headers.get("x-encrypted-param", "")
                if not param:
                    raise WeChatAPIError("upload_param")
                return param
        except WeChatAPIError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise WeChatAPIError("media_upload") from exc

    async def send_media(
        self,
        to: str,
        context_token: str,
        *,
        item: dict,
        client_id: str | None = None,
    ) -> None:
        """Send one prepared CDN media item (image, video or file) to a user."""
        if not context_token:
            raise WeChatAPIError("missing_context")
        await self._request(
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to,
                    "client_id": client_id or str(uuid4()),
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": [item],
                }
            },
        )

    async def download_media(
        self, item: dict, max_bytes: int
    ) -> tuple[bytes, str, str]:
        kind = item.get("type")
        key = {2: "image_item", 3: "voice_item", 4: "file_item", 5: "video_item"}.get(
            kind
        )
        part = item.get(key, {}) if key else {}
        media = part.get("media") or {}
        if not media or (kind != 2 and not media.get("aes_key")):
            raise WeChatAPIError("missing_media")
        name = {2: "image.jpg", 3: "voice.silk", 5: "video.mp4"}.get(
            kind, part.get("file_name") or "file.bin"
        )
        name = PurePosixPath(str(name).replace("\\", "/")).name[:200]
        if name in ("", ".", ".."):
            raise WeChatAPIError("filename")
        url = (
            media.get("full_url")
            or f"{CDN_BASE}/download?{urlencode({'encrypted_query_param': media.get('encrypt_query_param', '')})}"
        )
        encrypted_limit = max_bytes + 16
        try:
            for _ in range(4):
                official_url(url, media=True)
                await asyncio.to_thread(validate_external_http_url, url)
                async with self.http.stream("GET", url, headers={}) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    if int(response.headers.get("content-length", 0)) > encrypted_limit:
                        raise WeChatAPIError("file_too_large")
                    content = bytearray()
                    async for block in response.aiter_bytes():
                        if len(content) + len(block) > encrypted_limit:
                            raise WeChatAPIError("file_too_large")
                        content.extend(block)
                    break
            else:
                raise WeChatAPIError("redirects")
            raw = bytes(content)
            encoded_key = media.get("aes_key")
            if kind == 2 and part.get("aeskey"):
                aes_key = bytes.fromhex(part["aeskey"])
            elif encoded_key:
                aes_key = base64.b64decode(encoded_key, validate=True)
                if len(aes_key) == 32:
                    aes_key = bytes.fromhex(aes_key.decode("ascii"))
            else:
                aes_key = None
            if aes_key:
                if len(aes_key) != 16:
                    raise WeChatAPIError("media_key")
                # The iLink CDN mandates AES-128-ECB + PKCS7 for media; the key
                # is single-use per upload, so ECB's determinism is not exposed
                # beyond what the provider protocol already fixes.
                decryptor = Cipher(  # lgtm[py/weak-cryptographic-algorithm]
                    algorithms.AES(aes_key), modes.ECB()
                ).decryptor()
                padded = decryptor.update(raw) + decryptor.finalize()
                unpadder = padding.PKCS7(128).unpadder()
                raw = unpadder.update(padded) + unpadder.finalize()
            if len(raw) > max_bytes or not raw:
                raise WeChatAPIError("file_too_large" if raw else "empty_media")
            return (
                raw,
                name,
                mimetypes.guess_type(name)[0] or "application/octet-stream",
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise WeChatAPIError("media_download") from exc
