"""One resolved DATABASE_URL feeds every Tortoise initialisation site.

Settings resolves the connection string once (explicit DATABASE_URL first,
otherwise assembled from the POSTGRES_* parts), so the API lifespan, Celery
worker init, migrations, and secret rotation must pass that value through
instead of re-deriving it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.core import celery as celery_module
from app.core import tool_secret_migration, tool_secret_rotation
from app.core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"


def test_only_settings_reads_postgres_parts():
    """Assembly stays in Settings; consumers never rebuild the URL."""
    offenders = sorted(
        str(path.relative_to(BACKEND_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if "POSTGRES_" in path.read_text(encoding="utf-8")
    )

    assert offenders == ["app/core/config.py"]


def _fail_lock_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop worker init before document recovery touches the database."""
    import app.core.redis as redis_module

    monkeypatch.setattr(
        redis_module,
        "get_redis",
        AsyncMock(return_value=SimpleNamespace(set=AsyncMock(return_value=False))),
    )


def test_celery_worker_init_uses_resolved_database_url(
    monkeypatch: pytest.MonkeyPatch,
):
    init = AsyncMock()
    monkeypatch.setattr(Tortoise, "init", init)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite://worker-init.sqlite3")
    _fail_lock_redis(monkeypatch)

    loop = asyncio.new_event_loop()
    monkeypatch.setattr(asyncio, "new_event_loop", lambda: loop)
    try:
        celery_module.init_tortoise()
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    assert init.await_args.kwargs["db_url"] == "sqlite://worker-init.sqlite3"


def test_migration_cli_uses_resolved_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    init = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(Tortoise, "init", init)
    monkeypatch.setattr(Tortoise, "close_connections", close)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite://migration.sqlite3")
    monkeypatch.setattr(
        tool_secret_migration,
        "migrate_global_tool_config",
        AsyncMock(return_value=str(uuid4())),
    )

    exit_code = tool_secret_migration.main(
        ["--tool-name", "get_current_time", "--target-team", str(uuid4())]
    )

    capsys.readouterr()
    assert exit_code == 0
    assert init.await_args.kwargs["db_url"] == "sqlite://migration.sqlite3"
    close.assert_awaited_once()


def test_rotation_cli_uses_resolved_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    init = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(Tortoise, "init", init)
    monkeypatch.setattr(Tortoise, "close_connections", close)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite://rotation.sqlite3")
    monkeypatch.setattr(
        tool_secret_rotation,
        "rotate_tool_secrets",
        AsyncMock(return_value={"failed": 0}),
    )

    exit_code = tool_secret_rotation.main([])

    capsys.readouterr()
    assert exit_code == 0
    assert init.await_args.kwargs["db_url"] == "sqlite://rotation.sqlite3"
    close.assert_awaited_once()
