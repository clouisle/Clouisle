import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '["https://one.example", "https://two.example"]',
            ["https://one.example", "https://two.example"],
        ),
        (
            "https://one.example, https://two.example",
            ["https://one.example", "https://two.example"],
        ),
        (["https://one.example"], ["https://one.example"]),
    ],
)
def test_settings_accepts_supported_cors_inputs(raw, expected):
    settings = Settings(_env_file=None, BACKEND_CORS_ORIGINS=raw)

    assert settings.BACKEND_CORS_ORIGINS == expected


def test_settings_rejects_unsupported_cors_input():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, BACKEND_CORS_ORIGINS=123)


def test_settings_preserves_explicit_database_url():
    settings = Settings(_env_file=None, DATABASE_URL="postgres://configured")

    assert settings.DATABASE_URL == "postgres://configured"


def test_settings_prefers_nonempty_internal_token_file(tmp_path):
    token_file = tmp_path / "internal-token"
    token_file.write_text(" from-file \n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        INTERNAL_API_TOKEN="fallback",
        INTERNAL_API_TOKEN_FILE=str(token_file),
    )

    assert settings.get_internal_api_token() == "from-file"
