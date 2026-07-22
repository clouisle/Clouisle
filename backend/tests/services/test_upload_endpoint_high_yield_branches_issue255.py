import hashlib
import hmac
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile

import app.services  # noqa: F401  # initialize package before upload endpoint
from app.api.v1.endpoints import upload
from app.schemas.response import BusinessError, ResponseCode


def assert_business_error(exc_info, code, key):
    assert exc_info.value.code == code
    assert exc_info.value.msg_key == key


def test_resolve_upload_path_rejects_escape():
    with pytest.raises(BusinessError) as exc_info:
        upload._resolve_upload_path("..", "outside.txt")

    assert_business_error(exc_info, ResponseCode.FORBIDDEN, "access_denied")


def test_infer_extension_uses_mimetypes_guess():
    with patch.object(upload.mimetypes, "guess_extension", return_value=".custom"):
        assert upload.infer_extension(content_type="application/x-custom") == ".custom"


@pytest.mark.parametrize(
    ("timestamp", "signature"),
    [
        (None, None),
        ("not-an-int", "signature"),
        ("1", "signature"),
        ("current", "wrong-signature"),
    ],
)
def test_validate_sandbox_signature_rejects_invalid_credentials(timestamp, signature):
    content = b"artifact"
    filename = "result.txt"
    current_timestamp = "1700000000"
    resolved_timestamp = current_timestamp if timestamp == "current" else timestamp

    fake_datetime = SimpleNamespace(
        now=lambda: SimpleNamespace(timestamp=lambda: 1700000000)
    )
    with (
        patch.object(upload, "datetime", fake_datetime),
        pytest.raises(BusinessError) as exc_info,
    ):
        upload._validate_sandbox_artifact_signature(
            content=content,
            filename=filename,
            timestamp=resolved_timestamp,
            signature=signature,
        )

    assert_business_error(exc_info, ResponseCode.UNAUTHORIZED, "not_authenticated")


def test_validate_sandbox_signature_accepts_matching_digest():
    content = b"artifact"
    filename = "result.txt"
    timestamp = "1700000000"
    digest = hashlib.sha256(content).hexdigest()
    signature = hmac.new(
        upload.settings.SECRET_KEY.encode(),
        f"{timestamp}:{filename}:{digest}".encode(),
        hashlib.sha256,
    ).hexdigest()

    fake_datetime = SimpleNamespace(
        now=lambda: SimpleNamespace(timestamp=lambda: 1700000000)
    )
    with patch.object(upload, "datetime", fake_datetime):
        upload._validate_sandbox_artifact_signature(
            content=content,
            filename=filename,
            timestamp=timestamp,
            signature=signature,
        )


def test_validate_allowed_content_type_falls_back_to_filename():
    with (
        patch.object(upload.file_parser_service, "is_supported", return_value=True),
        patch.object(
            upload.file_parser_service, "get_mime_type", return_value="text/plain"
        ),
    ):
        assert (
            upload._validate_allowed_content_type(
                content_type="application/octet-stream",
                filename="notes.txt",
                allowed_types={"text/plain"},
            )
            == "text/plain"
        )


@pytest.mark.asyncio
async def test_upload_image_rejects_invalid_content_type_before_reading():
    file = SimpleNamespace(content_type="text/plain", read=AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await upload.upload_image(SimpleNamespace(), file, "general", SimpleNamespace())

    assert_business_error(exc_info, ResponseCode.VALIDATION_ERROR, "invalid_file_type")
    file.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_sandbox_artifact_requires_filename():
    file = UploadFile(file=BytesIO(b"artifact"), filename="")

    with pytest.raises(BusinessError) as exc_info:
        await upload.upload_sandbox_artifact(SimpleNamespace(), file, None, None, None)

    assert_business_error(exc_info, ResponseCode.VALIDATION_ERROR, "file_required")


@pytest.mark.asyncio
async def test_parse_file_rejects_oversized_supported_file():
    file = UploadFile(file=BytesIO(b"large"), filename="notes.txt")

    with (
        patch.object(upload.file_parser_service, "is_supported", return_value=True),
        patch.object(upload, "MAX_PARSE_FILE_SIZE", 1),
        pytest.raises(BusinessError) as exc_info,
    ):
        await upload.parse_file(file, 1000, "end", SimpleNamespace())

    assert_business_error(exc_info, ResponseCode.VALIDATION_ERROR, "file_too_large")
