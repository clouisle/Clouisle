from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import settings


def test_password_hash_round_trip_and_bcrypt_byte_limit() -> None:
    password = "密" * 24
    hashed = security.get_password_hash(password + "first suffix")

    assert security.verify_password(password + "first suffix", hashed)
    assert security.verify_password(password + "different suffix", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_access_token_requires_explicit_expiration(monkeypatch) -> None:
    issued_at = datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc)
    monkeypatch.setattr(security, "now_utc", lambda: issued_at)

    token = security.create_access_token("user-id", expires_delta=timedelta(minutes=5))

    assert jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]) == {
        "exp": int((issued_at + timedelta(minutes=5)).timestamp()),
        "sub": "user-id",
    }

    with pytest.raises(TypeError):
        security.create_access_token("user-id")  # type: ignore[call-arg]
