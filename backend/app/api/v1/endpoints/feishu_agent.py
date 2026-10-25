"""Public Feishu event callback: challenge, signature, and message intake.

This endpoint is the only unauthenticated route in the product, so it is
deliberately paranoid and small:

1. the request body is bounded and never buffered past that bound,
2. the callback signature (``SHA256(timestamp + nonce + key + body)``) is
   verified in constant time *before* any database row is read,
3. an encrypted callback is decrypted with the configured Encrypt Key and its
   token / app id are checked against the stored integration,
4. only then does an ``im.message.receive_v1`` event reach the durable Agent
   runtime, which owns identity mapping, deduplication, and delivery.

Feishu requires a fast ``200`` with ``{"challenge": ...}`` for the URL
verification request, so the challenge branch answers before any runtime or
queue machinery is touched.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from lark_oapi.core.utils.decryptor import AESCipher

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.integrations.credentials import IntegrationSecretError, decrypt_secret
from app.integrations.registry import IntegrationCapability, integration_registry
from app.models.integration import Integration
from app.schemas.response import success
from app.services.integration_config import get_builtin_integration
from app.services.feishu_agent_events import get_connection_mode, receive_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Feishu event callbacks carry a single message, never a bulk payload.
MAX_BODY_BYTES = 64 * 1024
# Callback timestamps are tolerated only while they are still fresh, which
# stops a captured request from being replayed later.
MAX_TIMESTAMP_SKEW_SECONDS = 300


def _rejected(message: str, msg_key: str = "access_denied") -> JSONResponse:
    """Fail closed without echoing any request detail back to the caller."""
    logger.warning("Rejected Feishu callback: %s", message)
    return JSONResponse(status_code=403, content=success(data=None, msg_key=msg_key))


def _content_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _read_body(request: Request) -> bytes:
    """Read at most ``MAX_BODY_BYTES``; anything larger is refused."""
    declared = _content_length(request)
    if declared is not None and declared > MAX_BODY_BYTES:
        raise ValueError("callback body too large")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("callback body too large")
    return body


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("callback body is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("callback body is not an object")
    return payload


def _fresh_timestamp(value: str) -> bool:
    """Feishu signs every request; an old timestamp cannot be replayed."""
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return False
    return abs(time.time() - timestamp) <= MAX_TIMESTAMP_SKEW_SECONDS


def _verify_signature(
    *, signature: str, timestamp: str, nonce: str, encrypt_key: str, body: bytes
) -> bool:
    """Constant-time check of SHA256(timestamp + nonce + key + body)."""
    if not signature or not timestamp or not nonce or not encrypt_key:
        return False
    expected = hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode() + body
    ).hexdigest()
    return hmac.compare_digest(signature.lower(), expected)


def _decrypt(encrypted: str, encrypt_key: str) -> dict[str, Any]:
    """Decrypt Lark's IV-prefixed AES-CBC ciphertext into a JSON object.

    The SDK hashes the UTF-8 Encrypt Key with SHA-256. Its event dispatcher
    parses the decrypted plaintext directly as JSON, without an inner frame.
    The callback validates the JSON token and event header app id afterwards.
    """
    try:
        ciphertext = base64.b64decode(encrypted, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("callback payload is not valid base64") from exc
    if len(ciphertext) < 32 or len(ciphertext) % 16 != 0:
        raise ValueError("callback payload length is invalid")
    try:
        plaintext = AESCipher(encrypt_key).decrypt(ciphertext)
    except ValueError as exc:
        raise ValueError("callback payload decryption failed") from exc
    payload = _parse_json(plaintext)
    if "encrypt" in payload:
        raise ValueError("callback payload is doubly encrypted")
    return payload


async def _agent_chat_secrets(integration: Integration) -> tuple[str, str]:
    """Decrypt the two callback secrets, or fail closed."""
    encrypt_key = decrypt_secret(integration.credentials.get("event_encrypt_key") or "")
    verification_token = decrypt_secret(
        integration.credentials.get("event_verification_token") or ""
    )
    return encrypt_key, verification_token


async def _agent_chat_integration() -> Integration | None:
    """The builtin Feishu integration, or ``None`` when it cannot serve events.

    A missing, disabled, or capability-less integration is a rejection rather
    than an error: an unconfigured deployment simply has no callback to serve.
    """
    try:
        definition = integration_registry.get("feishu")
    except ValueError:
        return None
    if IntegrationCapability.AGENT_CHAT not in definition.capabilities:
        return None
    try:
        integration = await get_builtin_integration("feishu")
    except ValueError:
        logger.warning("Feishu callback received without a builtin integration")
        return None
    if (
        not integration.is_enabled
        or IntegrationCapability.AGENT_CHAT not in integration.enabled_capabilities
        or get_connection_mode(integration) != "callback"
    ):
        return None
    return integration


def _header(request: Request, name: str) -> str:
    return (request.headers.get(name) or "").strip()


@router.post("/callback")
async def feishu_event_callback(request: Request):
    """Feishu URL verification, event challenge, and message intake."""
    # The channel gate runs first: a disabled channel must not even read the
    # request, and the configuration it loads is only the verification key.
    integration = await _agent_chat_integration()
    if integration is None:
        return _rejected("agent chat is not configured or not enabled")
    try:
        encrypt_key, verification_token = await _agent_chat_secrets(integration)
    except IntegrationSecretError:
        logger.exception("Feishu callback secrets could not be decrypted")
        return _rejected("callback secrets are undecryptable", "validation_error")
    if not encrypt_key or not verification_token:
        return _rejected("callback secrets are not configured", "validation_error")

    try:
        body = await _read_body(request)
        payload = _parse_json(body)
    except ValueError as exc:
        return _rejected(str(exc), "validation_error")

    timestamp = _header(request, "X-Lark-Request-Timestamp")
    nonce = _header(request, "X-Lark-Request-Nonce")
    signature = _header(request, "X-Lark-Signature")
    if not _fresh_timestamp(timestamp):
        return _rejected("callback timestamp is stale or missing")
    if not _verify_signature(
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
        encrypt_key=encrypt_key,
        body=body,
    ):
        return _rejected("callback signature mismatch")

    configured_app_id = str(integration.config.get("app_id") or "")
    if not configured_app_id:
        return _rejected("callback app id is not configured", "validation_error")
    if payload.get("encrypt"):
        try:
            payload = _decrypt(str(payload["encrypt"]), encrypt_key)
        except ValueError as exc:
            return _rejected(str(exc), "validation_error")

    if "challenge" in payload:
        # URL verification. The signature above already binds this request to
        # the configured Encrypt Key, so echoing the challenge is safe; the
        # token is still checked because Feishu sends it.
        if not hmac.compare_digest(str(payload.get("token") or ""), verification_token):
            return _rejected("challenge token mismatch")
        return JSONResponse(content={"challenge": str(payload["challenge"])})

    header = payload.get("header")
    header = header if isinstance(header, dict) else {}
    app_id = str(header.get("app_id") or "")
    if not app_id or not hmac.compare_digest(
        app_id.encode(), configured_app_id.encode()
    ):
        return _rejected("event app id mismatch")
    if not hmac.compare_digest(str(header.get("token") or ""), verification_token):
        return _rejected("event token mismatch")

    if header.get("event_type") != "im.message.receive_v1":
        # Acknowledged but ignored: nothing else is subscribed on this route.
        return JSONResponse(content=success())

    event = payload.get("event")
    if not isinstance(event, dict):
        return JSONResponse(content=success())
    try:
        await receive_message(event, app_id=configured_app_id)
    except Exception:
        logger.exception("Feishu runtime rejected the inbound event")
        return JSONResponse(content=success())
    return JSONResponse(content=success())
