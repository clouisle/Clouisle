import pytest

from app.api.v1.endpoints.site_settings import (
    _normalize_hex_color,
    _normalize_kb_document_max_upload_size_mb,
)
from app.models import (
    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
)


def test_normalize_hex_color_rejects_non_hex_digits():
    assert _normalize_hex_color("#xyz") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB - 1, KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB + 1, KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB, KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
    ],
)
def test_normalize_kb_document_upload_size_bounds(value, expected):
    assert _normalize_kb_document_max_upload_size_mb(value) == expected
