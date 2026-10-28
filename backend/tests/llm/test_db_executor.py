"""Builtin database execution: connection config, SSRF and dispatch."""

from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.builtin.db_executor import execute_database_query
from app.llm.tools import tool_registry  # registration side effects
from app.llm.tools.builtin.database import (
    mongodb_query,
    mysql_query,
    postgresql_query,
    redis_query,
)


@pytest.fixture(autouse=True)
def _allow_database_hosts(monkeypatch):
    from app.llm.tools.builtin.database import register_database_tools

    register_database_tools()

    async def _allowlist():
        return []

    monkeypatch.setattr(
        "app.core.network_security.get_ssrf_allowed_targets", _allowlist
    )
    monkeypatch.setattr(
        "app.core.network_security.validate_database_config", lambda *a, **k: None
    )


@pytest.mark.parametrize(
    ("name", "engine"),
    [
        ("postgresql_query", "postgresql"),
        ("mysql_query", "mysql"),
        ("redis_query", "redis"),
        ("mongodb_query", "mongodb"),
    ],
)
def test_database_builtins_are_registered(name, engine):
    info = tool_registry.get_tool(name)
    assert info is not None
    assert info.handler is not None
    action = next(param for param in info.parameters if param.name == "action")
    assert action.required is True
    assert action.enum


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler", [postgresql_query, mysql_query, redis_query, mongodb_query]
)
async def test_handlers_inject_engine_from_tool_key(handler):
    captured = {}

    async def fake_execute(config, arguments):
        captured.update(config)
        return {"success": True, "action": arguments.get("action")}

    with patch("app.llm.tools.builtin.database.execute_database_query", fake_execute):
        result = await handler(
            credentials={"host": "db.internal", "password": "s3cret"},
            action="schema",
        )
    assert result["success"] is True
    assert captured["host"] == "db.internal"
    assert captured["password"] == "s3cret"
    assert captured["db_type"] in {"postgresql", "mysql", "redis", "mongodb"}


@pytest.mark.asyncio
async def test_execute_database_query_blocks_disallowed_host():
    with (
        patch(
            "app.core.network_security.get_ssrf_allowed_targets",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.core.network_security.validate_database_config",
            side_effect=_business_error("database_host_not_allowed"),
        ),
    ):
        result = await execute_database_query(
            {"db_type": "postgresql", "host": "127.0.0.1", "port": "5432"},
            {"action": "schema"},
        )
    assert result == {"error": "database_host_not_allowed", "success": False}


def _business_error(msg_key: str):
    from app.schemas.response import BusinessError

    def _raise(*args, **kwargs):
        raise BusinessError(code=400, msg_key=msg_key, status_code=400)

    return _raise


@pytest.mark.asyncio
async def test_execute_database_query_normalizes_string_numbers():
    config = {
        "db_type": "postgresql",
        "host": "db.internal",
        "port": "5432",
        "timeout": "9",
        "max_limit": "25",
        "ssl": "false",
    }
    with patch(
        "app.llm.tools.builtin.db_executor._pg_schema", new_callable=AsyncMock
    ) as mock_schema:
        mock_schema.return_value = {"success": True}
        await execute_database_query(config, {"action": "schema"})
    pg_config = mock_schema.call_args.args[0]
    assert pg_config["port"] == 5432
    assert "ssl" not in pg_config or pg_config["ssl"] is None


@pytest.mark.asyncio
async def test_execute_database_query_rejects_unknown_engine():
    result = await execute_database_query(
        {"db_type": "cassandra", "host": "db.internal"}, {"action": "schema"}
    )
    assert result == {
        "error": "unsupported_database_type: cassandra",
        "success": False,
    }


@pytest.mark.asyncio
async def test_execute_database_query_requires_host_or_url():
    result = await execute_database_query(
        {"db_type": "postgresql"}, {"action": "schema"}
    )
    # validate_database_config is patched in this module, so the executor's
    # own incomplete-config guard must still fail closed.
    assert result == {"error": "database_host_invalid", "success": False}


@pytest.mark.asyncio
async def test_invalid_numeric_connection_field_returns_structured_error():
    result = await execute_database_query(
        {"db_type": "postgresql", "host": "db.test", "max_limit": "many"}, {}
    )
    assert result == {"error": "database_max_limit_invalid", "success": False}


def test_legacy_float_timeout_string_is_accepted():
    from app.llm.tools.builtin.db_executor import _normalize_config

    assert _normalize_config({"timeout": "15.0"})["timeout"] == 15
