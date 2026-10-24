"""Credential encryption shared by every integration capability."""

import base64

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class IntegrationSecretError(ValueError):
    """Credentials cannot be read using the deployment's current SECRET_KEY."""


def _fernet() -> Fernet:
    # Preserve the existing Feishu encryption format for migrated credentials.
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32].ljust(32, b"0"))
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(secret: str) -> str:
    try:
        return _fernet().decrypt(secret.encode()).decode()
    except InvalidToken as exc:
        raise IntegrationSecretError(
            "Stored integration credential cannot be decrypted"
        ) from exc
