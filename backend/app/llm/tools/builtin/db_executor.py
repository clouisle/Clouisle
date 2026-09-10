"""
数据库自定义工具执行器与连通性测试模块
"""

import asyncio
import logging
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


async def test_database_connection(db_config: dict[str, Any]) -> dict[str, Any]:
    """测试数据库连通性"""
    db_type = str(db_config.get("db_type") or "").strip().lower()
    timeout = float(db_config.get("timeout") or 5.0)

    try:
        if db_type in ("postgresql", "postgres", "pgsql"):
            import asyncpg

            pg_config = _parse_pg_config(db_config)
            conn = await asyncio.wait_for(
                asyncpg.connect(
                    host=pg_config["host"],
                    port=pg_config["port"],
                    user=pg_config["user"],
                    password=pg_config["password"],
                    database=pg_config["database"],
                    ssl=pg_config["ssl"],
                    timeout=timeout,
                ),
                timeout=timeout,
            )
            try:
                row = await conn.fetchrow("SELECT 1 AS ok")
                return {
                    "success": True,
                    "message": "PostgreSQL connection successful",
                    "ping": row["ok"],
                }
            finally:
                await conn.close()

        elif db_type in ("mysql", "mariadb"):
            import asyncmy

            mysql_config = _parse_mysql_config(db_config)
            conn = await asyncio.wait_for(
                asyncmy.connect(
                    host=mysql_config["host"],
                    port=mysql_config["port"],
                    user=mysql_config["user"],
                    password=mysql_config["password"],
                    database=mysql_config["database"],
                    connect_timeout=timeout,
                ),
                timeout=timeout,
            )
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1 AS ok")
                    row = await cursor.fetchone()
                    return {
                        "success": True,
                        "message": "MySQL connection successful",
                        "ping": row[0],
                    }
            finally:
                conn.close()

        elif db_type == "redis":
            client = _get_redis_client(db_config)
            try:
                ping_res = await asyncio.wait_for(client.ping(), timeout=timeout)
                return {
                    "success": True,
                    "message": "Redis connection successful",
                    "ping": ping_res,
                }
            finally:
                await client.aclose()

        elif db_type == "mongodb":
            client, db = _get_mongo_client_and_db(db_config)
            try:
                res = await asyncio.wait_for(db.command("ping"), timeout=timeout)
                return {
                    "success": True,
                    "message": "MongoDB connection successful",
                    "ping": res,
                }
            finally:
                client.close()

        else:
            return {"success": False, "error": f"unsupported_db_type: {db_type}"}

    except Exception as e:
        logger.warning("Database connection test failed (%s): %s", db_type, e)
        return {"success": False, "error": str(e)}


async def execute_database_tool(
    tool: Any,
    arguments: dict[str, Any],
    timeout: float = 15.0,
) -> dict[str, Any]:
    """执行自定义数据库工具"""
    db_config = tool.database_config or {}
    db_type = str(db_config.get("db_type") or "").strip().lower()
    query_timeout = float(db_config.get("timeout") or timeout)
    max_limit = int(db_config.get("max_limit") or 100)

    act = str(arguments.get("action") or "schema").strip().lower()

    if db_type in ("postgresql", "postgres", "pgsql"):
        pg_config = _parse_pg_config(db_config)
        if act == "schema":
            tables = arguments.get("tables")
            include_samples = bool(arguments.get("include_samples", False))
            return await asyncio.wait_for(
                _pg_schema(pg_config, tables, include_samples), timeout=query_timeout
            )
        elif act == "query":
            sql = arguments.get("sql") or ""
            if not sql.strip():
                return {"error": "sql_query_required", "success": False}
            validate_readonly_sql(sql)
            limit = min(int(arguments.get("limit") or 50), max_limit)
            return await asyncio.wait_for(
                _pg_query(pg_config, sql, limit), timeout=query_timeout
            )
        else:
            return {"error": f"unsupported_action: {act}", "success": False}

    elif db_type in ("mysql", "mariadb"):
        mysql_config = _parse_mysql_config(db_config)
        if act == "schema":
            tables = arguments.get("tables")
            include_samples = bool(arguments.get("include_samples", False))
            return await asyncio.wait_for(
                _mysql_schema(mysql_config, tables, include_samples),
                timeout=query_timeout,
            )
        elif act == "query":
            sql = arguments.get("sql") or ""
            if not sql.strip():
                return {"error": "sql_query_required", "success": False}
            validate_readonly_sql(sql)
            limit = min(int(arguments.get("limit") or 50), max_limit)
            return await asyncio.wait_for(
                _mysql_query(mysql_config, sql, limit), timeout=query_timeout
            )
        else:
            return {"error": f"unsupported_action: {act}", "success": False}

    elif db_type == "redis":
        client = _get_redis_client(db_config)
        try:
            if act == "scan":
                pattern = arguments.get("pattern") or "*"
                count = min(int(arguments.get("count") or 20), 100)
                cursor = 0
                matched_keys = []
                while True:
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

            elif act == "get":
                key = arguments.get("key")
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

            elif act == "command":
                cmd = (arguments.get("command") or "").strip().upper()
                key = arguments.get("key")
                if not cmd or not key:
                    return {"error": "command_and_key_required", "success": False}
                if cmd in DANGEROUS_COMMANDS:
                    return {
                        "error": f"dangerous_command_blocked: {cmd}",
                        "success": False,
                    }
                if cmd not in READONLY_COMMANDS:
                    return {"error": f"command_not_permitted: {cmd}", "success": False}
                cmd_args = [key] + (arguments.get("args") or [])
                res = await client.execute_command(cmd, *cmd_args)
                return {
                    "command": cmd,
                    "key": key,
                    "result": sanitize_value(res),
                    "success": True,
                }

            else:
                return {"error": f"unsupported_action: {act}", "success": False}
        finally:
            await client.aclose()

    elif db_type == "mongodb":
        client, db = _get_mongo_client_and_db(db_config)
        try:
            if act == "schema":
                coll_name = arguments.get("collection")
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
                sample_size = min(int(arguments.get("sample_size") or 3), 5)
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

            elif act == "find":
                coll_name = arguments.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                limit = min(int(arguments.get("limit") or 20), max_limit)
                cursor = (
                    db[coll_name]
                    .find(
                        arguments.get("filter") or {},
                        projection=arguments.get("projection"),
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

            elif act == "count":
                coll_name = arguments.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                cnt = await asyncio.wait_for(
                    db[coll_name].count_documents(arguments.get("filter") or {}),
                    timeout=query_timeout,
                )
                return {"collection": coll_name, "count": cnt, "success": True}

            elif act == "aggregate":
                coll_name = arguments.get("collection")
                if not coll_name:
                    return {"error": "collection_required", "success": False}
                pipe = list(arguments.get("pipeline") or [])
                for stage in pipe:
                    for k in stage.keys():
                        if k in DISALLOWED_AGGREGATION_STAGES:
                            return {
                                "error": f"aggregation_stage_not_permitted: {k}",
                                "success": False,
                            }
                limit = min(int(arguments.get("limit") or 20), max_limit)
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

            else:
                return {"error": f"unsupported_action: {act}", "success": False}
        finally:
            client.close()

    else:
        return {"error": f"unsupported_database_type: {db_type}", "success": False}
