"""
Database builtin execution.

The engine configuration and credentials arrive as a plain mapping resolved
from the selected ``ToolConnection``; nothing here reads a Tool row. Supported
engines keep the previous read-only guarantees: PostgreSQL/MySQL run in
read-only transactions after ``validate_readonly_sql``, Redis only exposes an
allowlisted command set, and MongoDB rejects ``$out`` / ``$merge`` aggregation
stages.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from .db_common import sanitize_value, validate_readonly_sql
from .postgresql import _parse_pg_config, _pg_schema, _pg_query
from .mysql_db import _parse_mysql_config, _mysql_schema, _mysql_query
from .redis_db import _get_redis_client, READONLY_COMMANDS, DANGEROUS_COMMANDS
from .mongo_db import (
    _get_mongo_client_and_db,
    _infer_schema_from_docs,
    DISALLOWED_AGGREGATION_STAGES,
)

logger = logging.getLogger(__name__)


def _normalize_config(db_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy a connection mapping into driver-friendly Python values.

    Connection fields are strings (encrypted JSON stores strings), while the
    drivers expect integers/booleans. Unknown keys are ignored here; only the
    engine parsers consume what they recognize.
    """
    config = dict(db_config or {})
    for key in ("port", "db", "timeout", "max_limit"):
        value = config.get(key)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                config.pop(key, None)
                continue
            try:
                config[key] = int(value)
            except ValueError:
                raise ValueError(f"database_{key}_invalid") from None
    ssl = config.get("ssl")
    if isinstance(ssl, str):
        normalized = ssl.strip().lower()
        if normalized in {"", "false", "0", "no", "off", "disable", "disabled"}:
            config.pop("ssl", None)
        elif normalized in {"true", "1", "yes", "on"}:
            config["ssl"] = True
        # Anything else ("require", "verify-full", a CA path, ...) is passed
        # to the driver verbatim.
    return config


async def execute_database_query(
    db_config: Mapping[str, Any] | None,
    arguments: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Execute one read-only database action using a resolved configuration.

    ``db_config`` must include ``db_type`` (injected by the builtin handler).
    """
    config = _normalize_config(db_config)
    args = dict(arguments or {})
    db_type = str(config.get("db_type") or "").strip().lower()
    query_timeout = float(config.get("timeout") or 15.0)
    max_limit = int(config.get("max_limit") or 100)

    # Never let a driver default (127.0.0.1) stand in for a missing identity.
    if not config.get("host") and not (config.get("url") or config.get("uri")):
        return {"error": "database_host_invalid", "success": False}

    # Re-validate the destination on every execution. The connection was
    # written by a tool editor, but DNS can change after the write; the central
    # SSRF policy stays authoritative for every outbound database connection.
    from app.core.network_security import (
        get_ssrf_allowed_targets,
        validate_database_config,
    )
    from app.schemas.response import BusinessError

    try:
        allowlist = await get_ssrf_allowed_targets()
        await asyncio.to_thread(validate_database_config, config, allowlist=allowlist)
    except BusinessError as exc:
        return {"error": exc.msg_key or "database_host_not_allowed", "success": False}

    act = str(args.get("action") or "schema").strip().lower()

    if db_type in ("postgresql", "postgres", "pgsql"):
        pg_config = _parse_pg_config(config)
        if act == "schema":
            tables = args.get("tables")
            include_samples = bool(args.get("include_samples", False))
            return await asyncio.wait_for(
                _pg_schema(pg_config, tables, include_samples), timeout=query_timeout
            )
        if act == "query":
            sql = args.get("sql") or ""
            if not str(sql).strip():
                return {"error": "sql_query_required", "success": False}
            validate_readonly_sql(sql, dialect="postgres")
            limit = min(int(args.get("limit") or 50), max_limit)
            return await asyncio.wait_for(
                _pg_query(pg_config, sql, limit), timeout=query_timeout
            )
        return {"error": f"unsupported_action: {act}", "success": False}

    if db_type in ("mysql", "mariadb"):
        mysql_config = _parse_mysql_config(config)
        if act == "schema":
            tables = args.get("tables")
            include_samples = bool(args.get("include_samples", False))
            return await asyncio.wait_for(
                _mysql_schema(mysql_config, tables, include_samples),
                timeout=query_timeout,
            )
        if act == "query":
            sql = args.get("sql") or ""
            if not str(sql).strip():
                return {"error": "sql_query_required", "success": False}
            validate_readonly_sql(sql, dialect="mysql")
            limit = min(int(args.get("limit") or 50), max_limit)
            return await asyncio.wait_for(
                _mysql_query(mysql_config, sql, limit), timeout=query_timeout
            )
        return {"error": f"unsupported_action: {act}", "success": False}

    if db_type == "redis":
        client = _get_redis_client(config)
        try:
            if act == "scan":
                pattern = args.get("pattern") or "*"
                count = min(int(args.get("count") or 20), 100)
                max_iterations = 100

                async def _do_scan():
                    cursor = 0
                    matched_keys = []
                    iterations = 0
                    while iterations < max_iterations:
                        iterations += 1
                        cursor, keys = await client.scan(
                            cursor=cursor, match=pattern, count=count
                        )
                        matched_keys.extend(keys)
                        if cursor == 0 or len(matched_keys) >= count:
                            break
                    matched_keys = matched_keys[:count]
                    items = []
                    for k in matched_keys:
                        k_type = await client.type(k)
                        k_ttl = await client.ttl(k)
                        items.append({"key": k, "type": k_type, "ttl_seconds": k_ttl})
                    return {
                        "pattern": pattern,
                        "total_found": len(items),
                        "keys": items,
                        "success": True,
                    }

                return await asyncio.wait_for(_do_scan(), timeout=query_timeout)

            if act == "get":
                key = args.get("key")
                if not key:
                    return {"error": "key_required", "success": False}
                exists = await client.exists(key)
                if not exists:
                    return {"key": key, "exists": False, "success": True}
                k_type = await client.type(key)
                k_ttl = await client.ttl(key)
                val = None
                if k_type == "string":
                    val = await client.get(key)
                elif k_type == "hash":
                    val = await client.hgetall(key)
                elif k_type == "list":
                    val = await client.lrange(key, 0, 49)
                elif k_type == "set":
                    val = list(await client.smembers(key))[:50]
                elif k_type == "zset":
                    val = await client.zrange(key, 0, 49, withscores=True)
                return {
                    "key": key,
                    "exists": True,
                    "type": k_type,
                    "ttl_seconds": k_ttl,
                    "value": sanitize_value(val),
                    "success": True,
                }

            if act == "command":
                cmd = str(args.get("command") or "").strip().upper()
                key = args.get("key")
                if not cmd or not key:
                    return {"error": "command_and_key_required", "success": False}
                if cmd in DANGEROUS_COMMANDS:
                    return {
                        "error": f"dangerous_command_blocked: {cmd}",
                        "success": False,
                    }
                if cmd not in READONLY_COMMANDS:
                    return {"error": f"command_not_permitted: {cmd}", "success": False}
                cmd_args = [key] + (args.get("args") or [])
                res = await client.execute_command(cmd, *cmd_args)
                return {
                    "command": cmd,
                    "key": key,
                    "result": sanitize_value(res),
                    "success": True,
                }

            return {"error": f"unsupported_action: {act}", "success": False}
        finally:
            await client.aclose()

    if db_type == "mongodb":
        client, db = _get_mongo_client_and_db(config)
        try:
            if act == "schema":
                coll_name = args.get("collection")
                if not coll_name:
                    coll_names = await asyncio.wait_for(
                        db.list_collection_names(), timeout=query_timeout
                    )
                    summary = []
                    for name in sorted(coll_names):
                        cnt = await db[name].estimated_document_count()
                        summary.append({"collection": name, "estimated_count": cnt})
                    return {
                        "database": db.name,
                        "collections": summary,
                        "success": True,
                    }
                target_coll = db[coll_name]
                sample_size = min(int(args.get("sample_size") or 3), 5)
                cursor = target_coll.find().limit(sample_size)
                samples = await asyncio.wait_for(
                    cursor.to_list(length=sample_size), timeout=query_timeout
                )
                schema = _infer_schema_from_docs(samples)
                return {
                    "database": db.name,
                    "collection": coll_name,
                    "fields_schema": schema,
                    "samples": sanitize_value(samples),
                    "success": True,
                }

            if act == "find":
                coll_name = args.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                limit = min(int(args.get("limit") or 20), max_limit)
                cursor = (
                    db[coll_name]
                    .find(
                        args.get("filter") or {},
                        projection=args.get("projection"),
                    )
                    .limit(limit)
                )
                docs = await asyncio.wait_for(
                    cursor.to_list(length=limit), timeout=query_timeout
                )
                return {
                    "collection": coll_name,
                    "count": len(docs),
                    "results": sanitize_value(docs),
                    "success": True,
                }

            if act == "count":
                coll_name = args.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                cnt = await asyncio.wait_for(
                    db[coll_name].count_documents(args.get("filter") or {}),
                    timeout=query_timeout,
                )
                return {"collection": coll_name, "count": cnt, "success": True}

            if act == "aggregate":
                coll_name = args.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                pipe = list(args.get("pipeline") or [])
                for stage in pipe:
                    for k in stage.keys():
                        if k in DISALLOWED_AGGREGATION_STAGES:
                            return {
                                "error": f"aggregation_stage_not_permitted: {k}",
                                "success": False,
                            }
                limit = min(int(args.get("limit") or 20), max_limit)
                if not any("$limit" in stage for stage in pipe):
                    pipe.append({"$limit": limit})
                cursor = db[coll_name].aggregate(pipe)
                docs = await asyncio.wait_for(
                    cursor.to_list(length=limit), timeout=query_timeout
                )
                return {
                    "collection": coll_name,
                    "count": len(docs),
                    "results": sanitize_value(docs),
                    "success": True,
                }

            return {"error": f"unsupported_action: {act}", "success": False}
        finally:
            client.close()

    return {"error": f"unsupported_database_type: {db_type}", "success": False}


__all__ = ["execute_database_query"]
