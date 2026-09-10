"""
MySQL 数据库工具

功能: 连接 MySQL / MariaDB 数据库，执行表结构探查 (schema) 与只读 SQL 查询 (query)。

实际执行入口为 db_executor.execute_database_tool（自定义 `database` 工具类型），凭证来自
工具的业务编排配置 (tools_config.database_config)，不暴露给 LLM 工具参数。
"""

from typing import Any

from .db_common import sanitize_value, validate_readonly_sql


def _parse_mysql_config(db_config: dict[str, Any] | None) -> dict[str, Any]:
    """将工具配置归一化为 asyncmy 连接参数（user/database 键名）。"""
    import urllib.parse

    config = dict(db_config or {})

    host = config.get("host") or "127.0.0.1"
    port = int(config.get("port") or 3306)
    user = config.get("username") or config.get("user") or ""
    password = config.get("password") or ""
    database = config.get("database") or ""

    if url := config.get("url"):
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname:
            host = parsed.hostname
        if parsed.port:
            port = parsed.port
        if parsed.username:
            user = urllib.parse.unquote(parsed.username)
        if parsed.password:
            password = urllib.parse.unquote(parsed.password)
        if parsed.path.lstrip("/"):
            database = parsed.path.lstrip("/")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


async def _mysql_schema(
    db_config: dict[str, Any], tables: list[str] | None, include_samples: bool
) -> dict[str, Any]:
    import asyncmy

    conn = await asyncmy.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        connect_timeout=10.0,
    )
    try:
        async with conn.cursor(cursor=asyncmy.cursors.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """,
                (db_config["database"],),
            )
            table_rows = await cursor.fetchall()
            all_tables = [r["table_name"] for r in table_rows]
            target_tables = (
                [t for t in tables if t in all_tables] if tables else all_tables
            )

            schema_info: dict[str, Any] = {}
            for table in target_tables:
                await cursor.execute(
                    """
                    SELECT
                        column_name,
                        column_type,
                        is_nullable,
                        column_key,
                        column_default,
                        column_comment
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position;
                    """,
                    (db_config["database"], table),
                )
                col_rows = await cursor.fetchall()
                columns = [
                    {
                        "name": r["column_name"],
                        "type": r["column_type"],
                        "nullable": r["is_nullable"] == "YES",
                        "primary_key": r["column_key"] == "PRI",
                        "default": r["column_default"],
                        "comment": r["column_comment"],
                    }
                    for r in col_rows
                ]

                samples = []
                if include_samples:
                    await cursor.execute(f"SELECT * FROM `{table}` LIMIT 3")
                    s_rows = await cursor.fetchall()
                    if s_rows:
                        samples = [
                            {k: sanitize_value(v) for k, v in sr.items()}
                            for sr in s_rows
                        ]

                schema_info[table] = {
                    "columns": columns,
                    "samples": samples if include_samples else None,
                }

            return {
                "database": db_config["database"],
                "tables": all_tables,
                "selected_schemas": schema_info,
                "success": True,
            }
    finally:
        conn.close()


async def _mysql_query(
    db_config: dict[str, Any], sql: str, limit: int
) -> dict[str, Any]:
    import asyncmy

    validate_readonly_sql(sql)

    conn = await asyncmy.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        connect_timeout=10.0,
    )
    try:
        async with conn.cursor(cursor=asyncmy.cursors.DictCursor) as cursor:
            await cursor.execute("SET SESSION TRANSACTION READ ONLY;")

            wrapped_sql = sql.strip()
            if "limit" not in wrapped_sql.lower():
                wrapped_sql = f"{wrapped_sql} LIMIT {limit + 1}"

            await cursor.execute(wrapped_sql)
            records = await cursor.fetchall()
            if not records:
                cols = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                return {
                    "columns": cols,
                    "rows": [],
                    "total_rows": 0,
                    "truncated": False,
                    "success": True,
                }

            cols = list(records[0].keys())
            truncated = len(records) > limit
            result_rows = [
                [sanitize_value(val) for val in record.values()]
                for record in records[:limit]
            ]
            return {
                "columns": cols,
                "rows": result_rows,
                "total_rows": len(result_rows),
                "truncated": truncated,
                "success": True,
            }
    finally:
        conn.close()
