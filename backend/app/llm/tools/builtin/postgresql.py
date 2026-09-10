"""
PostgreSQL 数据库工具

功能: 连接 PostgreSQL 数据库，执行表结构探查 (schema) 与只读 SQL 查询 (query)。

实际执行入口为 db_executor.execute_database_tool（自定义 `database` 工具类型），凭证来自
工具的业务编排配置 (tools_config.database_config)，不暴露给 LLM 工具参数。
"""

from typing import Any

from .db_common import sanitize_value, validate_readonly_sql


def _parse_pg_config(db_config: dict[str, Any] | None) -> dict[str, Any]:
    """将工具配置归一化为 asyncpg 连接参数（user/database 键名）。"""
    import urllib.parse

    config = dict(db_config or {})

    host = config.get("host") or "127.0.0.1"
    port = int(config.get("port") or 5432)
    user = config.get("username") or config.get("user") or ""
    password = config.get("password") or ""
    database = config.get("database") or ""
    ssl = config.get("ssl") or None

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
        "ssl": ssl,
    }


async def _pg_schema(
    db_config: dict[str, Any], tables: list[str] | None, include_samples: bool
) -> dict[str, Any]:
    import asyncpg

    conn = await asyncpg.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        ssl=db_config.get("ssl"),
        timeout=10.0,
    )
    try:
        table_rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """
        )
        all_tables = [r["table_name"] for r in table_rows]
        target_tables = [t for t in tables if t in all_tables] if tables else all_tables

        schema_info: dict[str, Any] = {}
        for table in target_tables:
            col_rows = await conn.fetch(
                """
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    pgd.description AS column_comment
                FROM information_schema.columns c
                LEFT JOIN pg_catalog.pg_statio_all_tables st
                    ON c.table_schema = st.schemaname AND c.table_name = st.relname
                LEFT JOIN pg_catalog.pg_description pgd
                    ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
                WHERE c.table_schema = 'public' AND c.table_name = $1
                ORDER BY c.ordinal_position;
                """,
                table,
            )

            pk_rows = await conn.fetch(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = $1;
                """,
                table,
            )
            pk_cols = {r["column_name"] for r in pk_rows}

            columns = [
                {
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "primary_key": r["column_name"] in pk_cols,
                    "default": r["column_default"],
                    "comment": r["column_comment"],
                }
                for r in col_rows
            ]

            samples = []
            if include_samples:
                s_rows = await conn.fetch(f'SELECT * FROM "{table}" LIMIT 3')
                if s_rows:
                    col_names = list(s_rows[0].keys())
                    samples = [
                        dict(zip(col_names, [sanitize_value(v) for v in sr.values()]))
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
        await conn.close()


async def _pg_query(db_config: dict[str, Any], sql: str, limit: int) -> dict[str, Any]:
    import asyncpg

    validate_readonly_sql(sql)

    conn = await asyncpg.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        ssl=db_config.get("ssl"),
        timeout=10.0,
    )
    try:
        async with conn.transaction(readonly=True):
            wrapped_sql = sql.strip()
            if "limit" not in wrapped_sql.lower():
                wrapped_sql = f"{wrapped_sql} LIMIT {limit + 1}"

            records = await conn.fetch(wrapped_sql)
            if not records:
                return {
                    "columns": [],
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
        await conn.close()
