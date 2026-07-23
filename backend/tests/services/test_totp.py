"""Behavioral tests for TOTP service and account lifecycle endpoints."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints import totp as totp_endpoints
from app.schemas.response import BusinessError, ResponseCode
from app.services import totp


def make_user(**overrides):
    values = {
        "id": "user-id",
        "username": "alice",
        "email": "alice@example.com",
        "hashed_password": "password-hash",
        "totp_enabled": False,
        "totp_secret": None,
        "totp_enabled_at": None,
        "totp_backup_codes_hash": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def assert_business_error(exc_info, code):
    assert exc_info.value.code == code


def test_secret_encryption_round_trip(monkeypatch):
    monkeypatch.setattr(totp.settings, "SECRET_KEY", "short-secret")

    encrypted = totp.encrypt_secret("BASE32SECRET")

    assert encrypted != "BASE32SECRET"
    assert totp.decrypt_secret(encrypted) == "BASE32SECRET"


def test_generate_secret_delegates_to_pyotp(monkeypatch):
    random_base32 = MagicMock(return_value="NEWSECRET")
    monkeypatch.setattr(totp.pyotp, "random_base32", random_base32)

    assert totp.generate_totp_secret() == "NEWSECRET"
    random_base32.assert_called_once_with()


def test_generate_qr_code_builds_provisioning_image(monkeypatch):
    fake_totp = MagicMock()
    fake_totp.provisioning_uri.return_value = "otpauth://totp/account"
    monkeypatch.setattr(totp.pyotp, "TOTP", MagicMock(return_value=fake_totp))
    qr = MagicMock()
    image = MagicMock()
    qr.make_image.return_value = image
    monkeypatch.setattr(totp.qrcode, "QRCode", MagicMock(return_value=qr))

    result = totp.generate_qr_code("SECRET", "alice@example.com", "Issuer")

    fake_totp.provisioning_uri.assert_called_once_with(
        name="alice@example.com", issuer_name="Issuer"
    )
    qr.add_data.assert_called_once_with("otpauth://totp/account")
    qr.make.assert_called_once_with(fit=True)
    image.save.assert_called_once()
    assert result.startswith("data:image/png;base64,")


@pytest.mark.parametrize("window", [0, 1, 2])
def test_verify_totp_code_passes_window_boundary(monkeypatch, window):
    verifier = MagicMock(return_value=True)
    monkeypatch.setattr(
        totp.pyotp, "TOTP", MagicMock(return_value=SimpleNamespace(verify=verifier))
    )

    assert totp.verify_totp_code("SECRET", "123456", window=window) is True
    verifier.assert_called_once_with("123456", valid_window=window)


def test_generate_backup_codes_formats_requested_count(monkeypatch):
    digits = iter(range(10))
    monkeypatch.setattr(totp.secrets, "randbelow", lambda _: next(digits) % 10)

    assert totp.generate_backup_codes(1) == ["0123-4567"]
    assert totp.generate_backup_codes(0) == []


def test_hash_backup_codes_normalizes_codes(monkeypatch):
    password_hash = MagicMock(side_effect=lambda value: f"hash:{value}")
    monkeypatch.setattr(totp, "get_password_hash", password_hash)

    stored = json.loads(totp.hash_backup_codes(["1234-5678", "87654321"]))

    assert stored == [
        {"hash": "hash:12345678", "used": False},
        {"hash": "hash:87654321", "used": False},
    ]


def test_verify_backup_code_marks_match_used_and_counts_remaining(monkeypatch):
    user = make_user(
        totp_backup_codes_hash=json.dumps(
            [
                {"hash": "used", "used": True},
                {"hash": "match", "used": False},
                {"hash": "left", "used": False},
            ]
        )
    )
    verify = MagicMock(side_effect=lambda value, hashed: hashed == "match")
    monkeypatch.setattr(totp, "verify_password", verify)

    valid, remaining = totp.verify_backup_code(user, "1234-5678")

    assert (valid, remaining) == (True, 1)
    assert json.loads(user.totp_backup_codes_hash)[1]["used"] is True
    verify.assert_called_once_with("12345678", "match")


def test_verify_backup_code_failure_preserves_available_count(monkeypatch):
    stored = json.dumps(
        [{"hash": "one", "used": False}, {"hash": "used", "used": True}]
    )
    user = make_user(totp_backup_codes_hash=stored)
    monkeypatch.setattr(totp, "verify_password", MagicMock(return_value=False))

    assert totp.verify_backup_code(user, "bad-code") == (False, 1)
    assert user.totp_backup_codes_hash == stored


def test_verify_backup_code_without_codes_is_rejected():
    assert totp.verify_backup_code(make_user(), "1234-5678") == (False, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored, expected",
    [
        (None, 0),
        (json.dumps([{"used": False}, {"used": True}, {"used": False}]), 2),
    ],
)
async def test_get_remaining_backup_codes_boundaries(stored, expected):
    assert (
        await totp.get_remaining_backup_codes(make_user(totp_backup_codes_hash=stored))
        == expected
    )


@pytest.mark.asyncio
async def test_setup_stores_generated_credentials(monkeypatch):
    user = make_user()
    monkeypatch.setattr(
        totp_endpoints.totp_service, "generate_totp_secret", lambda: "SECRET"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "generate_qr_code", lambda **_: "QR"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "generate_backup_codes", lambda count: ["CODE"]
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "hash_backup_codes", lambda _: "HASHES"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "encrypt_secret", lambda _: "ENCRYPTED"
    )

    response = await totp_endpoints.setup_totp(MagicMock(), user)

    assert response["data"].model_dump() == {
        "secret": "SECRET",
        "qr_code": "QR",
        "backup_codes": ["CODE"],
    }
    assert (user.totp_secret, user.totp_backup_codes_hash) == ("ENCRYPTED", "HASHES")
    user.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_setup_rejects_already_enabled_user():
    with pytest.raises(BusinessError) as exc_info:
        await totp_endpoints.setup_totp(MagicMock(), make_user(totp_enabled=True))

    assert_business_error(exc_info, ResponseCode.TOTP_ALREADY_ENABLED)


@pytest.mark.asyncio
async def test_enable_verifies_secret_and_records_time(monkeypatch):
    enabled_at = datetime(2026, 1, 2, tzinfo=UTC)
    user = make_user(totp_secret="ENCRYPTED")
    monkeypatch.setattr(
        totp_endpoints.totp_service, "decrypt_secret", lambda _: "SECRET"
    )
    verify = MagicMock(return_value=True)
    monkeypatch.setattr(totp_endpoints.totp_service, "verify_totp_code", verify)
    monkeypatch.setattr(totp_endpoints, "now_utc", lambda: enabled_at)
    audit = AsyncMock()
    monkeypatch.setattr(totp_endpoints.AuditLogService, "log", audit)

    await totp_endpoints.enable_totp(
        MagicMock(), totp_endpoints.TOTPEnableRequest(code="123456"), user
    )

    assert user.totp_enabled is True
    assert user.totp_enabled_at == enabled_at
    verify.assert_called_once_with("SECRET", "123456")
    user.save.assert_awaited_once_with()
    audit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user, verifier, code",
    [
        (make_user(totp_enabled=True), True, ResponseCode.TOTP_ALREADY_ENABLED),
        (make_user(), True, ResponseCode.TOTP_SETUP_EXPIRED),
        (make_user(totp_secret="ENCRYPTED"), False, ResponseCode.TOTP_INVALID),
    ],
)
async def test_enable_failures_do_not_save(monkeypatch, user, verifier, code):
    monkeypatch.setattr(
        totp_endpoints.totp_service, "decrypt_secret", lambda _: "SECRET"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "verify_totp_code", lambda *_: verifier
    )

    with pytest.raises(BusinessError) as exc_info:
        await totp_endpoints.enable_totp(
            MagicMock(), totp_endpoints.TOTPEnableRequest(code="000000"), user
        )

    assert_business_error(exc_info, code)
    user.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("use_backup", [False, True])
async def test_disable_accepts_totp_or_backup_code(monkeypatch, use_backup):
    user = make_user(
        totp_enabled=True,
        totp_secret="ENCRYPTED",
        totp_enabled_at=datetime.now(UTC),
        totp_backup_codes_hash="HASHES",
    )
    monkeypatch.setattr(totp_endpoints, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        totp_endpoints.totp_service, "decrypt_secret", lambda _: "SECRET"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "verify_totp_code", lambda *_: True
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "verify_backup_code", lambda *_: (True, 9)
    )
    monkeypatch.setattr(totp_endpoints.AuditLogService, "log", AsyncMock())

    await totp_endpoints.disable_totp(
        MagicMock(),
        totp_endpoints.TOTPDisableRequest(
            password="password", code="123456", is_backup_code=use_backup
        ),
        user,
    )

    assert user.totp_enabled is False
    assert user.totp_secret is None
    assert user.totp_enabled_at is None
    assert user.totp_backup_codes_hash is None
    user.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user, password_valid, code_valid, expected",
    [
        (make_user(), True, True, ResponseCode.TOTP_NOT_ENABLED),
        (
            make_user(totp_enabled=True, totp_secret="ENCRYPTED"),
            False,
            True,
            ResponseCode.INVALID_CREDENTIALS,
        ),
        (make_user(totp_enabled=True), True, True, ResponseCode.TOTP_NOT_ENABLED),
        (
            make_user(totp_enabled=True, totp_secret="ENCRYPTED"),
            True,
            False,
            ResponseCode.TOTP_INVALID,
        ),
    ],
)
async def test_disable_failures_do_not_clear_credentials(
    monkeypatch, user, password_valid, code_valid, expected
):
    original_secret = user.totp_secret
    monkeypatch.setattr(totp_endpoints, "verify_password", lambda *_: password_valid)
    monkeypatch.setattr(
        totp_endpoints.totp_service, "decrypt_secret", lambda _: "SECRET"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "verify_totp_code", lambda *_: code_valid
    )

    with pytest.raises(BusinessError) as exc_info:
        await totp_endpoints.disable_totp(
            MagicMock(),
            totp_endpoints.TOTPDisableRequest(password="password", code="000000"),
            user,
        )

    assert_business_error(exc_info, expected)
    assert user.totp_secret == original_secret
    user.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_regenerate_backup_codes_replaces_stored_hashes(monkeypatch):
    user = make_user(totp_enabled=True, totp_secret="ENCRYPTED")
    monkeypatch.setattr(
        totp_endpoints.totp_service, "decrypt_secret", lambda _: "SECRET"
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "verify_totp_code", lambda *_: True
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "generate_backup_codes", lambda count: ["NEW-CODE"]
    )
    monkeypatch.setattr(
        totp_endpoints.totp_service, "hash_backup_codes", lambda _: "NEW-HASHES"
    )
    monkeypatch.setattr(totp_endpoints.AuditLogService, "log", AsyncMock())

    response = await totp_endpoints.regenerate_backup_codes(
        MagicMock(), totp_endpoints.TOTPRegenerateRequest(code="123456"), user
    )

    assert response["data"] == {"codes": ["NEW-CODE"]}
    assert user.totp_backup_codes_hash == "NEW-HASHES"
    user.save.assert_awaited_once_with()
