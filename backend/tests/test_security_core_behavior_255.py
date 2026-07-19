from datetime import datetime, timedelta, timezone

import jwt

from app.core import security
from app.core.config import settings


def test_password_hash_round_trip_and_bcrypt_byte_limit() -> None:
    password = "密" * 24
    hashed = security.get_password_hash(password + "first suffix")

    assert security.verify_password(password + "first suffix", hashed)
    assert security.verify_password(password + "different suffix", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_access_token_uses_requested_and_default_expiration(monkeypatch) -> None:
    issued_at = datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc)
    monkeypatch.setattr(security, "now_utc", lambda: issued_at)

    requested = jwt.decode(
        security.create_access_token(123, timedelta(minutes=5)),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    default = jwt.decode(
        security.create_access_token("user-id"),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert requested == {
        "exp": int((issued_at + timedelta(minutes=5)).timestamp()),
        "sub": "123",
    }
    assert default == {
        "exp": int(
            (
                issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            ).timestamp()
        ),
        "sub": "user-id",
    }
