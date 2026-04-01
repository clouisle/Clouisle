"""
TOTP (Time-based One-Time Password) Service
Handles TOTP secret generation, encryption, QR code generation, and backup codes
"""

import base64
import io
import json
import secrets
from typing import List, Tuple

import pyotp
import qrcode
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.user import User


def _get_fernet() -> Fernet:
    """Get Fernet cipher using SECRET_KEY"""
    # Derive a 32-byte key from SECRET_KEY
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32].ljust(32, b"0"))
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    """Encrypt TOTP secret for storage"""
    fernet = _get_fernet()
    return fernet.encrypt(secret.encode()).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypt TOTP secret from storage"""
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_secret.encode()).decode()


def generate_totp_secret() -> str:
    """Generate a new TOTP secret (base32 encoded)"""
    return pyotp.random_base32()


def generate_qr_code(secret: str, username: str, issuer: str = "Clouisle") -> str:
    """
    Generate QR code as base64 data URL

    Args:
        secret: TOTP secret
        username: User's username or email
        issuer: Service name (default: Clouisle)

    Returns:
        Base64 data URL (data:image/png;base64,...)
    """
    # Generate provisioning URI
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name=issuer)

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)

    # Convert to image
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode()

    return f"data:image/png;base64,{img_base64}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """
    Verify TOTP code

    Args:
        secret: TOTP secret
        code: 6-digit code to verify
        window: Time window tolerance (default: 1 = ±30 seconds)

    Returns:
        True if code is valid
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=window)


def generate_backup_codes(count: int = 10) -> List[str]:
    """
    Generate backup codes in format XXXX-XXXX

    Args:
        count: Number of codes to generate (default: 10)

    Returns:
        List of backup codes
    """
    codes = []
    for _ in range(count):
        # Generate 8 random digits
        code = "".join(str(secrets.randbelow(10)) for _ in range(8))
        # Format as XXXX-XXXX
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def hash_backup_codes(codes: List[str]) -> str:
    """
    Hash backup codes for storage

    Args:
        codes: List of backup codes

    Returns:
        JSON string of hashed codes with metadata
    """
    hashed_codes = []
    for code in codes:
        # Remove dash for hashing
        clean_code = code.replace("-", "")
        hashed = get_password_hash(clean_code)
        hashed_codes.append({"hash": hashed, "used": False})

    return json.dumps(hashed_codes)


def verify_backup_code(user: User, code: str) -> Tuple[bool, int]:
    """
    Verify backup code and mark as used

    Args:
        user: User model instance
        code: Backup code to verify

    Returns:
        Tuple[bool, int]: (is_valid, remaining_codes)
    """
    if not user.totp_backup_codes_hash:
        return False, 0

    # Parse stored codes
    codes_data = json.loads(user.totp_backup_codes_hash)

    # Remove dash for verification
    clean_code = code.replace("-", "")

    # Check each code
    for i, code_data in enumerate(codes_data):
        if code_data["used"]:
            continue

        if verify_password(clean_code, code_data["hash"]):
            # Mark as used
            codes_data[i]["used"] = True
            user.totp_backup_codes_hash = json.dumps(codes_data)  # type: ignore[assignment]

            # Count remaining codes
            remaining = sum(1 for c in codes_data if not c["used"])
            return True, remaining

    return False, sum(1 for c in codes_data if not c["used"])


async def get_remaining_backup_codes(user: User) -> int:
    """Get count of remaining (unused) backup codes"""
    if not user.totp_backup_codes_hash:
        return 0

    codes_data = json.loads(user.totp_backup_codes_hash)
    return sum(1 for c in codes_data if not c["used"])

