"""Fail-closed edges of the tool secret envelope.

Malformed keyring entries, ambiguous write keys and corrupt envelopes must
raise typed errors instead of producing a token nobody can decrypt, and a
legacy/old-key token must round-trip only through the explicit rotation path.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.tool_secrets import (
    ENVELOPE_PREFIX,
    ToolSecretError,
    ToolSecretKeyError,
    current_key_id,
    decrypt_tool_secret,
    encrypt_tool_secret,
    keyring_key_ids,
    reencrypt_tool_secret,
    reload_keyring,
)

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _reset_keyring():
    reload_keyring()
    yield
    reload_keyring()


def _configure(monkeypatch, *, primary: str, keys: str) -> None:
    monkeypatch.setattr(settings, "TOOL_SECRET_KEYS", keys)
    monkeypatch.setattr(settings, "TOOL_SECRET_PRIMARY_KEY_ID", primary)
    reload_keyring()


def test_keyring_ignores_blank_entries(monkeypatch):
    _configure(monkeypatch, primary="a", keys=f" , a:{KEY_A} , , ")

    assert keyring_key_ids() == ("a",)
    assert current_key_id() == "a"


def test_keyring_rejects_duplicate_ids(monkeypatch):
    _configure(monkeypatch, primary="", keys=f"a:{KEY_A},a:{KEY_B}")

    with pytest.raises(ToolSecretKeyError, match="duplicate TOOL_SECRET_KEYS id"):
        keyring_key_ids()


def test_keyring_rejects_a_non_fernet_value(monkeypatch):
    _configure(monkeypatch, primary="", keys="a:not-a-fernet-key")

    with pytest.raises(ToolSecretKeyError, match="is not a valid Fernet key"):
        keyring_key_ids()


def test_keyring_with_only_separators_is_rejected(monkeypatch):
    _configure(monkeypatch, primary="", keys=" , , ")

    with pytest.raises(
        ToolSecretKeyError, match="TOOL_SECRET_KEYS contains no usable keys"
    ):
        keyring_key_ids()


def test_multiple_keys_require_an_explicit_primary(monkeypatch):
    _configure(monkeypatch, primary="", keys=f"a:{KEY_A},b:{KEY_B}")

    with pytest.raises(
        ToolSecretKeyError,
        match="TOOL_SECRET_PRIMARY_KEY_ID is required when the keyring has multiple keys",
    ):
        current_key_id()


def test_encrypt_rejects_non_string_values(monkeypatch):
    _configure(monkeypatch, primary="a", keys=f"a:{KEY_A}")

    with pytest.raises(ToolSecretError, match="tool secret must be a string"):
        encrypt_tool_secret(b"bytes")  # type: ignore[arg-type]


def test_decrypt_rejects_empty_values(monkeypatch):
    _configure(monkeypatch, primary="a", keys=f"a:{KEY_A}")

    for value in ("", None):
        with pytest.raises(ToolSecretError, match="tool secret is empty"):
            decrypt_tool_secret(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        f"{ENVELOPE_PREFIX}missing-separator",
        f"{ENVELOPE_PREFIX}a:",
        f"{ENVELOPE_PREFIX}bad id!:token",
    ],
)
def test_malformed_envelopes_are_rejected(monkeypatch, value):
    _configure(monkeypatch, primary="a", keys=f"a:{KEY_A}")

    with pytest.raises(ToolSecretError, match="malformed tool secret envelope"):
        decrypt_tool_secret(value)


def test_wrong_key_ciphertext_reports_the_envelope_key_id(monkeypatch):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")
    foreign_token = Fernet(KEY_A.encode()).encrypt(b"payload").decode()

    with pytest.raises(
        ToolSecretError, match="tool secret cannot be decrypted with key id 'b'"
    ):
        decrypt_tool_secret(f"{ENVELOPE_PREFIX}b:{foreign_token}")


def test_reencryption_skips_empty_values(monkeypatch):
    _configure(monkeypatch, primary="a", keys=f"a:{KEY_A}")

    assert reencrypt_tool_secret("") == ("", False)
    assert reencrypt_tool_secret(None) == (None, False)  # type: ignore[arg-type]
