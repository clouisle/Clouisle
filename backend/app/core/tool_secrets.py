"""Envelope encryption for tool-domain secrets with key rotation support.

Scope: tool connections, tool execution parameters, OAuth client secrets/PKCE
verifiers and interaction responses. Integration credentials keep their
existing single-key helper (out of scope).

Ciphertext layout::

    enc:tool:v1:<key_id>:<fernet-token>

Legacy unprefixed Fernet tokens (produced from ``SECRET_KEY`` before this
module existed) remain decryptable and are rewrapped by the rotation command.
Key material comes from ``TOOL_SECRET_KEYS`` (``key_id:fernet_key`` entries)
with ``TOOL_SECRET_PRIMARY_KEY_ID`` selecting the write key. Without a
configured keyring, a derived key id ``secret_key`` preserves upgradeability;
production deployments must inject an explicit keyring.
"""

from __future__ import annotations

import base64
import logging
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.integrations.credentials import (
    IntegrationSecretError,
    decrypt_secret as _decrypt_legacy_secret,
)

logger = logging.getLogger(__name__)

ENVELOPE_PREFIX = "enc:tool:v1:"
FALLBACK_KEY_ID = "secret_key"
_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_warned_fallback = False


class ToolSecretError(ValueError):
    """Tool secret cannot be encrypted or decrypted safely."""


class ToolSecretKeyError(ToolSecretError):
    """Keyring configuration is missing, malformed or lacks the key id."""


def _derived_legacy_key() -> str:
    # Same derivation as the pre-envelope helper, so existing SECRET_KEY
    # tokens stay decryptable through the legacy fallback.
    return base64.urlsafe_b64encode(
        settings.SECRET_KEY.encode()[:32].ljust(32, b"0")
    ).decode()


def _fallback_keyring() -> dict[str, str]:
    global _warned_fallback
    if not _warned_fallback:
        _warned_fallback = True
        logger.warning(
            "TOOL_SECRET_KEYS is not configured; using the SECRET_KEY-derived "
            "fallback key. Configure an injected keyring before rotating."
        )
    return {FALLBACK_KEY_ID: _derived_legacy_key()}


def _parse_keyring() -> dict[str, str]:
    raw = (settings.TOOL_SECRET_KEYS or "").strip()
    if not raw:
        return _fallback_keyring()

    keyring: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key_id, separator, key = entry.partition(":")
        key_id = key_id.strip()
        key = key.strip()
        if not separator or not _KEY_ID_PATTERN.fullmatch(key_id):
            raise ToolSecretKeyError("invalid TOOL_SECRET_KEYS entry")
        if key_id in keyring:
            raise ToolSecretKeyError(f"duplicate TOOL_SECRET_KEYS id {key_id!r}")
        try:
            Fernet(key.encode())
        except (ValueError, TypeError):
            raise ToolSecretKeyError(
                f"TOOL_SECRET_KEYS entry {key_id!r} is not a valid Fernet key"
            ) from None
        keyring[key_id] = key
    if not keyring:
        raise ToolSecretKeyError("TOOL_SECRET_KEYS contains no usable keys")
    return keyring


@lru_cache(maxsize=1)
def _cached_keyring() -> dict[str, str]:
    return _parse_keyring()


def reload_keyring() -> None:
    """Test/rotation hook: re-read settings on next use."""
    _cached_keyring.cache_clear()


def keyring_key_ids() -> tuple[str, ...]:
    return tuple(sorted(_cached_keyring()))


def current_key_id() -> str:
    keyring = _cached_keyring()
    primary = (settings.TOOL_SECRET_PRIMARY_KEY_ID or "").strip()
    if primary:
        if primary not in keyring:
            raise ToolSecretKeyError(
                f"TOOL_SECRET_PRIMARY_KEY_ID {primary!r} is not in TOOL_SECRET_KEYS"
            )
        return primary
    if FALLBACK_KEY_ID in keyring:
        return FALLBACK_KEY_ID
    raise ToolSecretKeyError(
        "TOOL_SECRET_PRIMARY_KEY_ID is required when the keyring has multiple keys"
    )


def _fernet(key_id: str) -> Fernet:
    key = _cached_keyring().get(key_id)
    if key is None:
        raise ToolSecretKeyError(f"tool secret key id {key_id!r} is not configured")
    return Fernet(key.encode())


def is_envelope(value: str) -> bool:
    return bool(value) and value.startswith(ENVELOPE_PREFIX)


def encrypt_tool_secret(secret: str) -> str:
    if not isinstance(secret, str):
        raise ToolSecretError("tool secret must be a string")
    key_id = current_key_id()
    token = _fernet(key_id).encrypt(secret.encode()).decode()
    return f"{ENVELOPE_PREFIX}{key_id}:{token}"


def decrypt_tool_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ToolSecretError("tool secret is empty")
    if value.startswith(ENVELOPE_PREFIX):
        payload = value[len(ENVELOPE_PREFIX) :]
        key_id, separator, token = payload.partition(":")
        if not separator or not token or not _KEY_ID_PATTERN.fullmatch(key_id):
            raise ToolSecretError("malformed tool secret envelope")
        try:
            return _fernet(key_id).decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ToolSecretError(
                f"tool secret cannot be decrypted with key id {key_id!r}"
            ) from exc
    # Legacy pre-envelope token (SECRET_KEY-derived Fernet). Rewritten on the
    # next write or by the rotation command.
    try:
        return _decrypt_legacy_secret(value)
    except IntegrationSecretError as exc:
        raise ToolSecretError("stored tool secret cannot be decrypted") from exc


def reencrypt_tool_secret(value: str) -> tuple[str, bool]:
    """Return (value_on_primary_key, changed) for rotation commands."""
    if not value:
        return value, False
    if is_envelope(value):
        key_id = value[len(ENVELOPE_PREFIX) :].partition(":")[0]
        if key_id and key_id == current_key_id():
            # Already on the primary key; Fernet re-encryption would produce a
            # different token for the same plaintext, so do not rewrite.
            return value, False
    plaintext = decrypt_tool_secret(value)
    return encrypt_tool_secret(plaintext), True


__all__ = [
    "ENVELOPE_PREFIX",
    "FALLBACK_KEY_ID",
    "ToolSecretError",
    "ToolSecretKeyError",
    "current_key_id",
    "decrypt_tool_secret",
    "encrypt_tool_secret",
    "is_envelope",
    "keyring_key_ids",
    "reencrypt_tool_secret",
    "reload_keyring",
]
