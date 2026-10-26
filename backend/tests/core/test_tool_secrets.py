"""Envelope tool-secret encryption, legacy fallback and rotation command."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from tortoise.context import TortoiseContext

from app.core.config import settings
from app.core.tool_secret_rotation import rotate_tool_secrets
from app.core.tool_secrets import (
    ENVELOPE_PREFIX,
    ToolSecretKeyError,
    current_key_id,
    decrypt_tool_secret,
    encrypt_tool_secret,
    keyring_key_ids,
    reencrypt_tool_secret,
    reload_keyring,
)
from app.integrations.credentials import encrypt_secret as legacy_encrypt
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
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


def test_envelope_roundtrip_and_key_ids(monkeypatch):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")
    assert keyring_key_ids() == ("a", "b")
    assert current_key_id() == "b"

    ciphertext = encrypt_tool_secret("s3cr3t")
    assert ciphertext.startswith(f"{ENVELOPE_PREFIX}b:")
    assert "s3cr3t" not in ciphertext
    assert decrypt_tool_secret(ciphertext) == "s3cr3t"


def test_legacy_token_decrypts_and_rewraps(monkeypatch):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")
    legacy = legacy_encrypt("legacy-value")

    assert decrypt_tool_secret(legacy) == "legacy-value"
    rewritten, changed = reencrypt_tool_secret(legacy)
    assert changed is True
    assert rewritten.startswith(f"{ENVELOPE_PREFIX}b:")
    assert decrypt_tool_secret(rewritten) == "legacy-value"
    assert reencrypt_tool_secret(rewritten) == (rewritten, False)


def test_unknown_key_id_and_bad_keyring_fail_closed(monkeypatch):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")
    foreign = f"{ENVELOPE_PREFIX}c:{Fernet(KEY_A.encode()).encrypt(b'x').decode()}"
    with pytest.raises(ToolSecretKeyError):
        decrypt_tool_secret(foreign)

    _configure(monkeypatch, primary="missing", keys=f"a:{KEY_A}")
    with pytest.raises(ToolSecretKeyError):
        encrypt_tool_secret("x")

    monkeypatch.setattr(settings, "TOOL_SECRET_KEYS", "bad-entry")
    reload_keyring()
    with pytest.raises(ToolSecretKeyError):
        keyring_key_ids()


def test_derived_fallback_key_is_explicit_and_usable(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_SECRET_KEYS", "")
    monkeypatch.setattr(settings, "TOOL_SECRET_PRIMARY_KEY_ID", "")
    reload_keyring()
    assert current_key_id() == "secret_key"
    ciphertext = encrypt_tool_secret("fallback")
    assert ciphertext.startswith(f"{ENVELOPE_PREFIX}secret_key:")
    assert decrypt_tool_secret(ciphertext) == "fallback"


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-secrets.sqlite3'}"

    def run(scenario):
        async def _wrapped():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                await context.generate_schemas()
                return await scenario()

        return runner.run(_wrapped())

    try:
        yield run
    finally:
        runner.close()


def _site_connection(ciphertext: str) -> ToolConnection:
    return ToolConnection(
        id=uuid4(),
        team_id=None,
        tool_id=None,
        builtin_tool_key="rotate-test",
        scope=ToolConnectionScope.SITE,
        owner_user_id=None,
        name="Rotate test",
        encrypted_config=ciphertext,
        secret_fields=["api_key"],
        secret_version=1,
        status=ToolConnectionStatus.ACTIVE,
        is_default=False,
        default_slot=None,
    )


def test_rotation_rewraps_legacy_and_old_envelopes(run_orm, monkeypatch):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")

    old_envelope = (
        f"{ENVELOPE_PREFIX}a:{Fernet(KEY_A.encode()).encrypt(b'old-envelope').decode()}"
    )
    legacy = legacy_encrypt("legacy-plain")

    async def scenario():
        first = _site_connection(legacy)
        second = _site_connection(old_envelope)
        await first.save()
        await second.save()

        dry = await rotate_tool_secrets(dry_run=True)
        assert dry["dry_run"] is True
        assert dry["rotated"] == 2
        assert dry["failed"] == 0
        stored = await ToolConnection.get(id=first.id)
        assert stored.encrypted_config == legacy

        summary = await rotate_tool_secrets(batch_size=1)
        assert summary["key_id"] == "b"
        assert summary["rotated"] == 2
        assert summary["failed"] == 0
        connection_stats = next(
            item for item in summary["targets"] if item["model"] == "ToolConnection"
        )
        assert connection_stats["source_key_ids"] == {"a": 1, "legacy": 1}

        for row, plaintext in ((first, "legacy-plain"), (second, "old-envelope")):
            stored = await ToolConnection.get(id=row.id)
            assert stored.encrypted_config.startswith(f"{ENVELOPE_PREFIX}b:")
            assert decrypt_tool_secret(stored.encrypted_config) == plaintext

        again = await rotate_tool_secrets(batch_size=1)
        assert again["rotated"] == 0
        assert again["unchanged"] == 2
        assert again["failed"] == 0

    run_orm(scenario)


def test_rotation_reports_undecryptable_rows_without_secret_output(
    run_orm, monkeypatch
):
    _configure(monkeypatch, primary="b", keys=f"a:{KEY_A},b:{KEY_B}")

    async def scenario():
        broken = _site_connection("not-a-token")
        await broken.save()
        summary = await rotate_tool_secrets()
        assert summary["failed"] == 1
        failure_rows = next(
            item for item in summary["targets"] if item["model"] == "ToolConnection"
        )["failures"]
        assert failure_rows == [str(broken.id)]
        stored = await ToolConnection.get(id=broken.id)
        assert stored.encrypted_config == "not-a-token"

    run_orm(scenario)
