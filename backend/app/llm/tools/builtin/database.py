"""Builtin database query tools.

Four engines are exposed as ordinary builtin tools. Each definition is
materialized per team exactly like ``get_current_time`` or ``web_search``; the
database *identity* (host, database, username, password, URL, limits) lives in
a personal or team ``ToolConnection``. A team can therefore attach several
databases of the same engine by selecting a different connection, and rotating
credentials never touches an Agent or workflow definition.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..registry import ToolInfo, ToolParameter, tool_registry
from .db_executor import execute_database_query

_ACTION_DESCRIPTION = "Operation to perform"

_DATABASE_TOOLS: list[ToolInfo] = []


def _database_tool(**metadata):
    def decorate(handler):
        _DATABASE_TOOLS.append(ToolInfo(handler=handler, **metadata))
        return handler

    return decorate


def register_database_tools() -> None:
    for info in _DATABASE_TOOLS:
        tool_registry.register_tool(info)


def _sql_query_parameters() -> list[ToolParameter]:
    return [
        ToolParameter(
            name="action",
            type="string",
            description=_ACTION_DESCRIPTION,
            required=True,
            enum=["schema", "query"],
            default="schema",
        ),
        ToolParameter(
            name="tables",
            type="array",
            description="Table names to describe; omit for every table",
            items={"type": "string"},
        ),
        ToolParameter(
            name="include_samples",
            type="boolean",
            description="Include up to three sample rows per table",
            default=False,
        ),
        ToolParameter(
            name="sql",
            type="string",
            description="Read-only SELECT statement for action=query",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum rows to return (capped by the connection)",
        ),
    ]


async def _run(
    engine: str,
    credentials: Mapping[str, str] | None,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    config = dict(credentials or {})
    # The engine is fixed by the builtin key, never by client arguments: a
    # connection migrated from a PostgreSQL tool can never run MySQL code.
    config["db_type"] = engine
    return await execute_database_query(config, arguments)


@_database_tool(
    name="postgresql_query",
    description=(
        "Inspect a PostgreSQL database read-only: describe tables and run "
        "single SELECT statements. The database is chosen by the connection."
    ),
    parameters=_sql_query_parameters(),
)
async def postgresql_query(
    credentials: Mapping[str, str] | None = None,
    **arguments: Any,
) -> dict[str, Any]:
    return await _run("postgresql", credentials, arguments)


@_database_tool(
    name="mysql_query",
    description=(
        "Inspect a MySQL or MariaDB database read-only: describe tables and run "
        "single SELECT statements. The database is chosen by the connection."
    ),
    parameters=_sql_query_parameters(),
)
async def mysql_query(
    credentials: Mapping[str, str] | None = None,
    **arguments: Any,
) -> dict[str, Any]:
    return await _run("mysql", credentials, arguments)


@_database_tool(
    name="redis_query",
    description=(
        "Inspect a Redis database read-only: scan key names, read one key, or "
        "run an allowlisted read command. The database is chosen by the connection."
    ),
    parameters=[
        ToolParameter(
            name="action",
            type="string",
            description=_ACTION_DESCRIPTION,
            required=True,
            enum=["scan", "get", "command"],
            default="scan",
        ),
        ToolParameter(
            name="pattern",
            type="string",
            description="SCAN match pattern",
            default="*",
        ),
        ToolParameter(
            name="count",
            type="integer",
            description="Maximum keys to inspect",
        ),
        ToolParameter(
            name="key",
            type="string",
            description="Key for action=get or action=command",
        ),
        ToolParameter(
            name="command",
            type="string",
            description="Read-only command name for action=command",
        ),
        ToolParameter(
            name="args",
            type="array",
            description="Additional command arguments",
            items={"type": "string"},
        ),
    ],
)
async def redis_query(
    credentials: Mapping[str, str] | None = None,
    **arguments: Any,
) -> dict[str, Any]:
    return await _run("redis", credentials, arguments)


@_database_tool(
    name="mongodb_query",
    description=(
        "Inspect a MongoDB database read-only: list collections, infer document "
        "fields, find/count documents, or run a safe aggregation pipeline. The "
        "database is chosen by the connection."
    ),
    parameters=[
        ToolParameter(
            name="action",
            type="string",
            description=_ACTION_DESCRIPTION,
            required=True,
            enum=["schema", "find", "count", "aggregate"],
            default="schema",
        ),
        ToolParameter(
            name="collection",
            type="string",
            description="Collection name; omit for action=schema to list collections",
        ),
        ToolParameter(
            name="sample_size",
            type="integer",
            description="Documents used to infer fields for action=schema",
        ),
        ToolParameter(
            name="filter",
            type="object",
            description="MongoDB filter document",
        ),
        ToolParameter(
            name="projection",
            type="object",
            description="Field projection document",
        ),
        ToolParameter(
            name="pipeline",
            type="array",
            description="Aggregation pipeline ($out and $merge are rejected)",
            items={"type": "object"},
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum documents to return",
        ),
    ],
)
async def mongodb_query(
    credentials: Mapping[str, str] | None = None,
    **arguments: Any,
) -> dict[str, Any]:
    return await _run("mongodb", credentials, arguments)


__all__ = [
    "register_database_tools",
    "mongodb_query",
    "mysql_query",
    "postgresql_query",
    "redis_query",
]
