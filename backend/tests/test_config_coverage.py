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


def test_settings_rejects_zero_sandbox_worker_recovery_seconds():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SANDBOX_WORKER_RECOVERY_SECONDS=0)


def test_settings_rejects_zero_sandbox_package_install_timeout():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SANDBOX_PACKAGE_INSTALL_TIMEOUT_SECONDS=0)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SANDBOX_TASK_MEMORY_MB", 0),
        ("SANDBOX_TASK_MAX_FILE_SIZE_MB", 0),
        ("SANDBOX_TASK_MAX_OPEN_FILES", 31),
        ("SANDBOX_TASK_MAX_CPU_SECONDS", 0),
    ],
)
def test_settings_reject_invalid_sandbox_task_limits(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


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


def test_default_cors_origins_cover_both_loopback_spellings():
    """The dev server answers on both spellings; the default must allow both.

    Opening the app on the spelling missing from CORS makes every browser API
    call fail with "Disallowed CORS origin", which hides real UI behaviour
    behind a blank page.
    """
    settings = Settings(_env_file=None)

    hosts = {
        origin.rsplit(":", 1)[0].removeprefix("http://")
        for origin in settings.BACKEND_CORS_ORIGINS
    }
    assert "127.0.0.1" in hosts
    assert "localhost" in hosts
    assert len(settings.BACKEND_CORS_ORIGINS) == len(set(settings.BACKEND_CORS_ORIGINS))

def test_skill_sync_timeout_matches_sandbox_limits_floor():
    """A sub-second timeout passes settings but fails job construction."""
    from app.services.sandbox.models import SandboxLimits

    assert Settings.model_fields["SKILL_SYNC_TIMEOUT_SECONDS"].metadata
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SKILL_SYNC_TIMEOUT_SECONDS=0.5)
    assert SandboxLimits(timeout_seconds=1.0).timeout_seconds == 1.0
