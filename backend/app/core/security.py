from datetime import timedelta
from typing import Any, Union

import bcrypt
import jwt

from app.core.config import settings
from app.core.timezone import now_utc

# bcrypt has a maximum password length of 72 bytes
BCRYPT_MAX_PASSWORD_LENGTH = 72


def _prepare_password(password: str) -> bytes:
    """Encode and truncate password to bcrypt's maximum length of 72 bytes."""
    return password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_LENGTH]


def create_access_token(subject: Union[str, Any], expires_delta: timedelta) -> str:
    """Encode an access token that expires after ``expires_delta``.

    The lifetime is required: callers own their session semantics (the site
    ``session_timeout_days`` setting for logins and SSO, short fixed windows for
    TOTP hand-off tokens), so there is no config default to fall back on.
    """
    to_encode = {"exp": now_utc() + expires_delta, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        _prepare_password(plain_password), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt()).decode("utf-8")
