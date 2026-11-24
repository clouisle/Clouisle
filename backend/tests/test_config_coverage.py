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
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgres://configured",
        POSTGRES_USER="ignored",
        POSTGRES_PASSWORD="ignored",
        POSTGRES_SERVER="ignored",
        POSTGRES_PORT=6543,
        POSTGRES_DB="ignored",
    )

    assert settings.DATABASE_URL == "postgres://configured"


def test_settings_assembles_database_url_from_postgres_parts(monkeypatch):
    """POSTGRES_* stays a supported interface; Settings owns the assembly."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(
        _env_file=None,
        POSTGRES_USER="app",
        POSTGRES_PASSWORD="secret",
        POSTGRES_SERVER="db.internal",
        POSTGRES_PORT=6543,
        POSTGRES_DB="appdb",
    )

    assert settings.DATABASE_URL == "postgres://app:secret@db.internal:6543/appdb"


def test_settings_treats_blank_database_url_as_absent(monkeypatch):
    """An empty DATABASE_URL means "not configured", so POSTGRES_* wins."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(
        _env_file=None,
        DATABASE_URL="",
        POSTGRES_USER="app",
        POSTGRES_PASSWORD="secret",
        POSTGRES_SERVER="db.internal",
        POSTGRES_PORT=6543,
        POSTGRES_DB="appdb",
    )

    assert settings.DATABASE_URL == "postgres://app:secret@db.internal:6543/appdb"


def test_settings_prefers_nonempty_internal_token_file(tmp_path):
    token_file = tmp_path / "internal-token"
    token_file.write_text(" from-file \n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        INTERNAL_API_TOKEN="fallback",
        INTERNAL_API_TOKEN_FILE=str(token_file),
    )

    assert settings.get_internal_api_token() == "from-file"


def test_skill_sync_timeout_matches_sandbox_limits_floor():
    """A sub-second timeout passes settings but fails job construction."""
    from app.services.sandbox.models import SandboxLimits

    assert Settings.model_fields["SKILL_SYNC_TIMEOUT_SECONDS"].metadata
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SKILL_SYNC_TIMEOUT_SECONDS=0.5)
    assert SandboxLimits(timeout_seconds=1.0).timeout_seconds == 1.0
