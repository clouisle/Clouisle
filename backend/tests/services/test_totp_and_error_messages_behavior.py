import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.services.error_messages import (
    is_safe_user_visible_error,
    resolve_user_visible_error,
)
from app.services.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    get_remaining_backup_codes,
    verify_backup_code,
)


def test_totp_secret_encryption_round_trips():
    encrypted = encrypt_secret("JBSWY3DPEHPK3PXP")

    assert encrypted != "JBSWY3DPEHPK3PXP"
    assert decrypt_secret(encrypted) == "JBSWY3DPEHPK3PXP"


def test_backup_codes_are_formatted_and_verify_marks_only_matched_code_used():
    codes = generate_backup_codes(3)
    assert len(codes) == 3
    assert all(
        len(code) == 9 and code[4] == "-" and code.replace("-", "").isdigit()
        for code in codes
    )

    user = SimpleNamespace(
        totp_backup_codes_hash=json.dumps(
            [
                {"hash": "old", "used": True},
                {"hash": "matching", "used": False},
                {"hash": "remaining", "used": False},
            ]
        )
    )
    with patch(
        "app.services.totp.verify_password",
        side_effect=lambda code, password_hash: (
            code == "12345678" and password_hash == "matching"
        ),
    ):
        valid, remaining = verify_backup_code(user, "1234-5678")

    assert (valid, remaining) == (True, 1)
    assert json.loads(user.totp_backup_codes_hash)[1]["used"] is True


def test_invalid_backup_code_preserves_remaining_codes():
    user = SimpleNamespace(
        totp_backup_codes_hash=json.dumps([{"hash": "unused", "used": False}])
    )
    with patch("app.services.totp.verify_password", return_value=False):
        assert verify_backup_code(user, "1234-5678") == (False, 1)

    assert json.loads(user.totp_backup_codes_hash) == [
        {"hash": "unused", "used": False}
    ]


def test_remaining_backup_codes_counts_unused_entries():
    user = SimpleNamespace(
        totp_backup_codes_hash=json.dumps(
            [{"hash": "used", "used": True}, {"hash": "unused", "used": False}]
        )
    )

    assert asyncio.run(get_remaining_backup_codes(user)) == 1


def test_user_visible_error_resolution_translates_keys_and_hides_unsafe_messages():
    with (
        patch(
            "app.services.error_messages.has_translation",
            side_effect=lambda key: key == "known.error",
        ),
        patch(
            "app.services.error_messages.t", side_effect=lambda key: f"translated:{key}"
        ),
    ):
        assert resolve_user_visible_error(" known.error ") == "translated:known.error"
        assert (
            resolve_user_visible_error(
                'Traceback (most recent call last):\nFile "/tmp/x"'
            )
            == "translated:tool_execution_failed"
        )

    assert is_safe_user_visible_error("Connection unavailable") is True
    assert is_safe_user_visible_error("/private/token leaked") is False
